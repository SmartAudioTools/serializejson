try:
    import numpy
    from numpy import frombuffer, unpackbits, uint8, ndarray, int32, int64
    from numpy import dtype as numpy_dtype
except ModuleNotFoundError:
    pass
else:
    import blosc
    from pybase64 import b64decode_as_bytearray

    # base64 écrit directement dans la sortie, et compression blosc2 faite en C
    from rapidjson import (RawBytesToBase64, BloscToBase64, _cumsum_axis0,
                           _diff_axis0)
    import sys

    try:
        # from SmartFramework import numpyB64
        from SmartFramework.serialize.tools import (
            serializejson_,
            constructors,
            blosc_compressions,
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
            blosc_compressions,
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

    def numpyB64(str64, dtype=None, shape_len_compression=None, compression=None):
        if type(str64) is bytearray:
            # charge déjà décodée du base64 par le parseur C++,
            # sans chaîne intermédiaire
            decoded_bytearray = str64
        else:
            decoded_bytearray = b64decode_as_bytearray(str64, validate=True)
        if isinstance(shape_len_compression, str):
            compression = shape_len_compression
            shape_len = None
        else:
            shape_len = shape_len_compression
        use_diff = False
        if compression:
            if compression.endswith("_diff"):
                compression = compression[:-5]
                use_diff = True
            if compression in ("blosc", "blosc2"):
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
                              if array.ndim > 1 else 1)
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

    def _diff_sample(contiguous):
        # échantillon pour l'essai automatique : 1/8e du tableau, borné entre
        # 4 Ko (en dessous, la taille compressée n'est plus qu'un bruit
        # d'en-têtes et la décision ne veut rien dire — on prend alors le
        # tableau entier, que la compression gagnante réutilise) et 256 Ko.
        # STRATIFIÉ en quatre bandes réparties, de lignes ENTIÈRES (l'essai
        # d'axe 0 l'exige) : un prélèvement unique peut tomber sur une zone
        # atypique — le milieu de la voix de référence était du silence, et
        # la décision basculait du mauvais côté
        target = min(max(contiguous.nbytes // 8, 1 << 12), 1 << 18)
        axis_len = contiguous.shape[0]
        unit = contiguous.nbytes // axis_len if axis_len else 1
        per = max(1, target // (4 * unit))
        if 4 * per >= axis_len:
            sample = contiguous
        else:
            step = axis_len // 4
            offset = (step - per) // 2
            sample = numpy.concatenate(
                [contiguous[i * step + offset: i * step + offset + per]
                 for i in range(4)])
        return (sample, sample.size // sample.shape[0]) \
            if sample.ndim > 1 else (sample, 1)

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
                and data.nbytes >= serialize_parameters.bytes_size_compression_threshold
            ):

                # dérivée avant compression (opt-in par dtype) : réservée aux
                # ENTIERS, dont diff/cumsum se retournent exactement (arrondis
                # flottants non réversibles au bit près). Si la compression ne
                # vaut pas le coup, le repli non-compressé repart des données
                # d'ORIGINE (data), jamais de la dérivée.
                diff_dtypes = serialize_parameters.bytes_compression_diff_dtypes
                auto_diff = diff_dtypes is True
                use_diff = auto_diff or bool(
                    diff_dtypes and data.dtype in diff_dtypes)
                blosc2_compression = blosc2_compressions.get(compression, None)
                if blosc2_compression:
                    # compression faite en C (libblosc2), sans repasser par Python
                    if not use_blosc2_cpp:
                        raise Exception(
                            f"{compression} compression needs the python-blosc2 wheel"
                        )
                    nthreads = serialize_parameters.bytes_compression_threads
                    if use_blosc2_fork:
                        # fork déterministe : le multi-thread INTERNE de la lib
                        # produit déjà des octets stables -> trame unique
                        nthreads = 1
                    # dérivée : FILTRE blosc2 enregistré (delta d'octets après
                    # shuffle, PAR BLOC, dans le pipeline multithreadé des deux
                    # côtés, trame auto-descriptive — aucune étiquette)
                    contiguous = numpy.ascontiguousarray(data)
                    level = serialize_parameters.bytes_compression_level
                    shuffle = 2 if use_diff else 1  # 2 = filtre delta + shuffle
                    diff0 = False  # dérivée d'axe 0 (passe C + étiquette _diff)
                    if auto_diff:
                        # décision par ESSAI : un échantillon (lignes entières,
                        # ~256 Ko) est compressé avec chaque candidat, le
                        # gagnant s'applique au tableau entier. Candidats :
                        # shuffle seul, filtre delta (delta d'octets APRÈS
                        # shuffle, le long du dernier axe — les voisins en
                        # mémoire) et, pour les entiers, la dérivée
                        # arithmétique d'axe 0 — seule ou combinée au filtre.
                        # En 2D l'axe 0 est la direction perpendiculaire au
                        # filtre ; en 1D c'est la MÊME direction mais AVEC les
                        # retenues et avant shuffle : mesurée gagnante sur les
                        # entiers larges (int32 -13 %, timestamps int64 -16 %),
                        # perdante sur int16 où le filtre reste devant
                        sample, cols = _diff_sample(contiguous)
                        candidates = [(1, False, None), (2, False, None)]
                        if (contiguous.dtype.kind in "iu"
                                and sample.shape[0] > 1):
                            candidates += [(1, True, None), (2, True, None)]
                        if (contiguous.dtype.kind in "iu"
                                and contiguous.itemsize in (2, 4)):
                            # codec Rice enregistré (243) : prédicteurs fixes
                            # d'ordre 0-3 + Rice adapté par partition — fait
                            # sa propre prédiction, donc ni pré-passe ni
                            # filtre devant
                            candidates.append((0, False, "rice"))
                        best = None
                        for cand_shuffle, cand_diff0, cand_cname in candidates:
                            buf = (_diff_axis0(sample.data, sample.itemsize,
                                               cols)
                                   if cand_diff0 else sample)
                            try:
                                cand = BloscToBase64(
                                    buf, sample.itemsize, level, cand_shuffle,
                                    cand_cname or blosc2_compression, 1,
                                )
                            except ValueError:
                                if cand_cname is None:
                                    raise
                                continue  # codec absent (lib sans registre)
                            # à taille égale, le candidat le plus simple
                            # (listé en premier) l'emporte : déterministe
                            if best is None or cand.compressed_size < best[0]:
                                best = (cand.compressed_size, cand_shuffle,
                                        cand_diff0, cand_cname, cand)
                        _, shuffle, diff0, cname_gagnant, payload = best
                        # si l'échantillon était le tableau ENTIER, la
                        # compression gagnante est déjà faite : on la garde
                        # (trame unique, octets identiques quel que soit le
                        # nombre de threads) ; sinon on recompresse tout
                        if sample.nbytes != contiguous.nbytes:
                            payload = None
                    else:
                        cname_gagnant = None
                        payload = None
                    if payload is None:
                        if diff0:
                            to_compress = _diff_axis0(
                                contiguous.data,
                                contiguous.itemsize,
                                contiguous.size // contiguous.shape[0],
                            )
                        else:
                            to_compress = contiguous
                        payload = BloscToBase64(
                            to_compress,
                            data.itemsize,
                            level,
                            shuffle,
                            cname_gagnant or blosc2_compression,
                            nthreads if type(nthreads) is int else 1,
                        )
                    # le filtre est porté par la trame ; seule la dérivée
                    # d'axe 0 garde l'étiquette _diff (et sa somme cumulée
                    # d'axe 0 au chargement, chemin de lecture inchangé)
                    use_diff = diff0
                    compressed_size = payload.compressed_size
                    compression = "blosc2p" if payload.frames > 1 else "blosc2"
                else:
                    # voie python-blosc v1 (pas de filtres) : dérivée C en
                    # une passe + étiquette _diff historique — ENTIERS
                    # seulement (la dérivée arithmétique flottante ne se
                    # retourne pas au bit près, contrairement au filtre
                    # d'octets de la voie blosc2)
                    if use_diff and data.dtype.kind not in "iu":
                        use_diff = False
                    blosc_compression = blosc_compressions.get(compression, None)
                    if use_diff and auto_diff and blosc_compression:
                        # décision par essai sur échantillon (seule la dérivée
                        # d'axe 0 existe sur cette voie, pas de filtre)
                        contiguous = numpy.ascontiguousarray(data)
                        sample, cols = _diff_sample(contiguous)
                        level = serialize_parameters.bytes_compression_level
                        plain_size = len(blosc.compress(
                            sample, sample.itemsize,
                            cname=blosc_compression, clevel=level))
                        diff_size = len(blosc.compress(
                            _diff_axis0(sample.data, sample.itemsize, cols),
                            sample.itemsize,
                            cname=blosc_compression, clevel=level))
                        use_diff = diff_size < plain_size
                    if use_diff:
                        contiguous = numpy.ascontiguousarray(data)
                        data_to_compress = _diff_axis0(
                            contiguous.data,
                            data.itemsize,
                            data.size // data.shape[0]
                            if data.ndim > 1 else 1,
                        )
                    else:
                        data_to_compress = numpy.ascontiguousarray(data)
                    if blosc_compression:
                        compressed = blosc.compress(
                            data_to_compress,
                            data.itemsize,
                            cname=blosc_compression,
                            clevel=serialize_parameters.bytes_compression_level,
                        )
                        payload = RawBytesToBase64(compressed)
                        compressed_size = len(compressed)
                        compression = "blosc"
                    else:
                        raise Exception(f"{compression} compression unknow")
                if use_diff:
                    compression += "_diff"
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
