try:
    import numpy
    from numpy import frombuffer, unpackbits, uint8, ndarray, int32, int64
    from numpy import dtype as numpy_dtype
except ModuleNotFoundError:
    pass
else:
    from base64 import b64decode

    # base64 écrit directement dans la sortie, et compression blosc2 faite en C
    from rapidjson import (RawBytesToBase64, BloscToBase64, _cumsum_axis0,
                           _diff_axis0, blosc_decompress_chunks)
    import sys

    try:
        # from SmartFramework import numpyB64
        from SmartFramework.serialize.tools import (
            serializejson_,
            constructors,
            blosc2_compressions,
            blosc_decompress,
            blosc_chunks_decompress,
            use_blosc2_cpp,
            use_blosc2_fork,
            authorized_classes,
        )
        from SmartFramework.serialize import serialize_parameters
    except:
        from serializejson import serialize_parameters
        from serializejson.tools import (
            serializejson_,
            constructors,
            blosc2_compressions,
            blosc_decompress,
            blosc_chunks_decompress,
            use_blosc2_cpp,
            use_blosc2_fork,
            authorized_classes,
        )

    nb_bits = sys.maxsize.bit_length() + 1

    authorized_classes.update(
        {
            "numpy.bool_",
            "numpy.bool",  # nom canonique depuis numpy 2
            "numpy.int8",
            "numpy.int16",
            "numpy.int32",
            "numpy.int64",
            "numpy.uint8",
            "numpy.uint16",
            "numpy.uint32",
            "numpy.uint64",
            "numpy.float16",
            "numpy.float32",
            "numpy.float64",
            "numpy.dtype",
            "numpy.ndarray",
            "numpy.array",
            "numpy.frombuffer",
            "numpyB64",
            "numpy.core.multiarray._reconstruct",
            "numpy.core.multiarray.scalar",
            # renommés en numpy._core par numpy 2 (les anciens noms restent
            # nécessaires pour relire les fichiers écrits avec numpy 1)
            "numpy._core.multiarray._reconstruct",
            "numpy._core.multiarray.scalar",
        }
    )

    def sans_prefixe_longueur(string):
        # préfixe « <n>: » écrit devant le base64 par le sérialiseur (il
        # permet au parseur de sauter le scan de la chaîne) : ':' est hors
        # de l'alphabet base64, sa présence signe le préfixe ; anciens
        # fichiers : intacts (défini aussi dans tools.py : le greffon doit
        # marcher avec les deux empaquetages, SmartFramework ou serializejson)
        if string[:1].isdigit():
            deux_points = string.find(":", 1, 21)
            if deux_points != -1:
                return string[deux_points + 1 :]
        return string

    def numpyB64(str64, dtype=None, shape_len_compression=None, compression=None):
        if type(str64) is bytearray:
            # charge déjà décodée du base64 par le parseur C++,
            # sans chaîne intermédiaire
            decoded_bytearray = str64
        else:
            # voie FROIDE : en usage normal le parseur C++ a déjà décodé
            decoded_bytearray = bytearray(
                b64decode(sans_prefixe_longueur(str64), validate=True)
            )
        if isinstance(shape_len_compression, str):
            compression = shape_len_compression
            shape_len = None
        else:
            shape_len = shape_len_compression
        use_diff = False
        diff_block_rows = 0
        if compression:
            if "_diffb" in compression:
                # dérivée par BLOCS indépendants : l'étiquette porte la taille
                # de bloc en lignes, la somme cumulée se parallélise par bloc
                compression, _, bloc = compression.rpartition("_diffb")
                diff_block_rows = int(bloc)
                use_diff = True
            elif compression.endswith("_diff"):
                compression = compression[:-5]
                use_diff = True
            fusionne = (
                use_diff
                and use_blosc2_cpp
                and compression in ("blosc2", "blosc2p")
                and dtype not in ("bool", bool)
                and not isinstance(dtype, list)
            )
            if fusionne:
                # dérivée défaite PENDANT la décompression : somme cumulée
                # fusionnée dans le postfiltre par bloc (chaud en cache)
                # quand les blocs de la trame sont ceux de la dérivée,
                # post-passe C par blocs sinon — une seule passe RAM
                cols_diff = (
                    int(numpy.prod(shape_len[1:]))
                    if isinstance(shape_len, (list, tuple)) and len(shape_len) > 1
                    else 1
                )
                decoded_bytearray = blosc_decompress_chunks(
                    decoded_bytearray, 1, 0,
                    numpy_dtype(dtype).itemsize, cols_diff, diff_block_rows)
                use_diff = False  # déjà défait
            elif compression in ("blosc", "blosc2"):
                decoded_bytearray = blosc_decompress(
                    decoded_bytearray, as_bytearray=True
                )
            elif compression == "blosc2p":
                decoded_bytearray = blosc_chunks_decompress(
                    decoded_bytearray, as_bytearray=True
                )
            else:
                raise Exception(f"unknow {compression} compression")
        if dtype in ("bool", bool):
            # pas de copie -> read only
            numpy_uint8_containing_8bits = frombuffer(decoded_bytearray, uint8)
            # copie dans un numpy array de uint8 mutable
            numpy_uint8_containing_8bits = unpackbits(numpy_uint8_containing_8bits)
            if shape_len is None:
                shape_len = len(numpy_uint8_containing_8bits)
            # pas de recopie
            return ndarray(shape_len, dtype, numpy_uint8_containing_8bits)
        else:
            if isinstance(dtype, list):
                dtype = [(str(champName), champType) for champName, champType in dtype]
            if shape_len is None:
                array = frombuffer(decoded_bytearray, dtype)  # pas de recopie
            else:
                array = ndarray(shape_len, dtype, decoded_bytearray)  # pas de recopie
            if use_diff and array.size:
                # cumsum C du fork, en place : ~10x numpy.cumsum sur les
                # petits entiers (le tampon vient d'un bytearray, toujours
                # contigu et écrivable ; enroulement identique à numpy)
                _cumsum_axis0(array.data,
                              array.itemsize,
                              array.size // array.shape[0]
                              if array.ndim > 1 else 1,
                              diff_block_rows)
            if (
                nb_bits == 32
                and serialize_parameters.numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit
            ):  # pour pouvoir deserialiser les classifiers en python 32 bit ?
                if array.dtype in (int64, "int64"):
                    return array.astype(int32)
                elif isinstance(dtype, list):
                    newTypes = []
                    for champ in dtype:
                        champName, champType = champ
                        if champName:
                            champType = numpy_dtype(champType)
                            if champType in (int64, "int64"):
                                newTypes.append((champName, int32))
                            else:
                                newTypes.append((champName, champType))
                    newDtype = numpy_dtype(newTypes, align=True)
                    newN = ndarray(len(array), newDtype)
                    for champName, champType in newTypes:
                        if champName:
                            newN[champName][:] = array[champName]
                    return newN
            return array

    constructors["numpyB64"] = numpyB64

    def serializejson_ndarray(inst):

        # inst = numpy.ascontiguousarray(inst)
        dtype = inst.dtype
        # compression = serialize_parameters.bytes_compression
        if dtype.fields is None:
            dtype_str = str(dtype)
            max_size = serialize_parameters.numpy_array_readable_max_size
            if isinstance(max_size, dict):
                if dtype_str in max_size:
                    max_size = max_size[dtype_str]
                else:
                    max_size = 0
            if max_size is None or inst.size <= max_size:
                return (
                    "numpy.array",
                    (inst.tolist(), dtype_str),
                    None,
                )  #  A REVOIR : pass genial car va tester ultérieurement si tous les elements sont du même type....
        else:
            dtype_str = dtype.descr

            # return ("numpy.array", (RawJSON(numpy.array2string(inst,separator =',')), dtype_str), None)  plus lent.

        if serialize_parameters.numpy_array_use_numpyB64:
            if dtype == bool:
                data = numpy.packbits(inst.astype(numpy.uint8))
                if inst.ndim == 1:
                    len_or_shape = len(inst)
                else:
                    len_or_shape = list(inst.shape)
            else:
                data = inst
                if inst.ndim == 1:
                    len_or_shape = None
                else:
                    len_or_shape = list(inst.shape)
            compression = serialize_parameters.bytes_compression
            if (
                compression
                and data.nbytes >= serialize_parameters.numpy_size_compression_threshold
            ):

                # dérivée avant compression (opt-in par dtype) : réservée aux
                # ENTIERS, dont diff/cumsum se retournent exactement (arrondis
                # flottants non réversibles au bit près). Si la compression ne
                # vaut pas le coup, le repli non-compressé repart des données
                # d'ORIGINE (data), jamais de la dérivée.
                diff_dtypes = serialize_parameters.bytes_compression_diff_dtypes
                # « smart » est le DÉFAUT (choix de Baptiste, 05/08) ; True,
                # l'ancien essai automatique par sondes, est rabattu dessus —
                # le dispositif de sondes a été retiré
                smart = diff_dtypes == "smart" or diff_dtypes is True
                # « delta » : le filtre delta d'octets pour TOUS les dtypes,
                # sans en nommer aucun (aucun barreau du barème ne s'en sert,
                # il reste demandable à la main)
                use_diff = smart or diff_dtypes == "delta" or bool(
                    diff_dtypes and not isinstance(diff_dtypes, str)
                    and data.dtype in diff_dtypes)
                # écriture blosc2 seulement (l'écriture v1 python-blosc et sa
                # dérivée globale _diff ont été retirées le 05/08/2026, leur
                # LECTURE demeure) ; trame unique déterministe
                blosc2_compression = blosc2_compressions.get(compression, None)
                if blosc2_compression is None:
                    raise Exception(
                        f"{compression}: v1 python-blosc write support was"
                        " removed, use a blosc2_* compression (v1 files"
                        " remain readable)"
                    )
                if not use_blosc2_cpp:
                    raise Exception(
                        f"{compression} compression needs a loadable libblosc2"
                    )
                # dérivée : FILTRE blosc2 enregistré (delta d'octets après
                # shuffle, PAR BLOC, dans le pipeline multithreadé des deux
                # côtés, trame auto-descriptive — aucune étiquette)
                contiguous = numpy.ascontiguousarray(data)
                level = serialize_parameters.bytes_compression_level
                # 2 = filtre delta + shuffle ; 0 = « raw », aucun filtre, le
                # codec seul : la chaîne la moins chère À LA LECTURE
                shuffle = 0 if diff_dtypes == "raw" else 2 if use_diff else 1
                diff0 = False  # dérivée d'axe 0, par blocs (étiquette _diffb)
                if diff_dtypes == "zigzag":
                    # la chaîne smart PRIVÉE de sa dérivée : zigzag →
                    # bitshuffle, pour TOUS les dtypes. Elle occupe la bande
                    # de poids que ni le shuffle d'octets ni la chaîne smart
                    # complète n'atteignent, et se lit deux fois plus vite
                    # que le shuffle d'octets (bitshuffle vectorisé)
                    shuffle = 3
                elif smart and contiguous.dtype.kind in "iu":
                    # DÉFAUT « smart » (choix de Baptiste, 05/08) : la
                    # chaîne dérivée blocs → zigzag → bitshuffle → zstd
                    # appliquée DIRECTEMENT, sans sonde, aux entiers ;
                    # les autres dtypes (flottants compris : la dérivée
                    # arithmétique ne se retourne pas au bit près sur
                    # eux) passent par le filtre 242, bit-exact pour tous
                    shuffle = 3
                    diff0 = True
                blocksize = 0
                diff_cols = 0
                if diff0:
                    # dérivée par BLOCS de lignes entières : chaque bloc
                    # redémarre, la somme cumulée de lecture devient
                    # indépendante par bloc — et les blocs blosc2 sont
                    # CALÉS dessus (blocksize), pour que les deux sens
                    # fusionnent : la dérivée est calculée par le
                    # PRÉFILTRE au moment où la lib constitue chaque bloc
                    # (octets identiques, sans pré-passe ni tampon), la
                    # somme cumulée par l'arrière du filtre 244 à la
                    # lecture. Un tableau plus petit qu'un bloc est UN
                    # bloc (l'étiquette _diff globale n'est plus écrite)
                    cols = contiguous.size // contiguous.shape[0]
                    row_bytes = cols * contiguous.itemsize
                    # 512 Ko pour toutes les chaînes : L2-résident
                    # (lecture x1,35, écriture x1,1 mesurées sur la
                    # chaîne 244, poids conservé — sauf +0,9 point
                    # sur le 24/96, profil où rice gagnait)
                    block_rows = max(1, min((1 << 19) // row_bytes,
                                            contiguous.shape[0]))
                    diff_suffix = f"_diffb{block_rows}"
                    blocksize = block_rows * row_bytes
                    if use_blosc2_fork:
                        diff_cols = cols  # fusion par préfiltre
                        to_compress = contiguous
                    else:
                        to_compress = _diff_axis0(
                            contiguous.data, contiguous.itemsize,
                            cols, block_rows)
                else:
                    to_compress = contiguous
                payload = BloscToBase64(
                    to_compress,
                    data.itemsize,
                    level,
                    shuffle,
                    blosc2_compression,
                    1,
                    blocksize,
                    diff_cols,
                )
                compressed_size = payload.compressed_size
                compression = "blosc2"
                if diff0:
                    compression += diff_suffix
                if compressed_size < data.nbytes:
                    if len_or_shape is None:
                        return (
                            "numpyB64",
                            (payload, dtype_str, compression),
                            None,
                        )
                    else:
                        return (
                            "numpyB64",
                            (
                                payload,
                                dtype_str,
                                len_or_shape,
                                compression,
                            ),
                            None,
                        )
            if len_or_shape is None:
                return (
                    "numpyB64",
                    (RawBytesToBase64(numpy.ascontiguousarray(data)), dtype_str),
                    None,
                )
            else:
                return (
                    "numpyB64",
                    (
                        RawBytesToBase64(numpy.ascontiguousarray(data)),
                        dtype_str,
                        len_or_shape,
                    ),
                    None,
                )

        else:
            # if False :#inst.ndim == 1:
            #    return (numpy.frombuffer, (bytearray(inst), dtype_str), None)
            # else:
            return (
                "numpy.ndarray",
                (list(inst.shape), dtype_str, bytearray(inst)),
                None,
            )

    serializejson_[numpy.ndarray] = serializejson_ndarray

    def serializejson_dtype(inst):
        initArgs = (str(inst),)
        return (inst.__class__, initArgs, None)

    serializejson_[numpy.dtype] = serializejson_dtype

    def serializejson_bool_(inst):
        return (inst.__class__, (bool(inst),), None)

    serializejson_[numpy.bool_] = serializejson_bool_

    def serializejson_int(inst):
        return (inst.__class__, (int(inst),), None)

    serializejson_[numpy.int8] = serializejson_int
    serializejson_[numpy.int16] = serializejson_int
    serializejson_[numpy.int32] = serializejson_int
    serializejson_[numpy.int64] = serializejson_int
    serializejson_[numpy.uint8] = serializejson_int
    serializejson_[numpy.uint16] = serializejson_int
    serializejson_[numpy.uint32] = serializejson_int
    serializejson_[numpy.uint64] = serializejson_int

    def serializejson_float(inst):
        return (inst.__class__, (float(inst),), None)

    serializejson_[numpy.float16] = serializejson_float
    serializejson_[numpy.float32] = serializejson_float
    serializejson_[numpy.float64] = serializejson_float
