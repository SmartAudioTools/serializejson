try:
    from SmartFramework.serialize.tools import (
        class_str_from_class,
        serializejson_builtins,
        constructors,
        blosc2_compressions,
        blosc_decompress,
        blosc_chunks_decompress,
        use_blosc2_cpp,
    )
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson.tools import (
        class_str_from_class,
        serializejson_builtins,
        constructors,
        blosc2_compressions,
        blosc_decompress,
        blosc_chunks_decompress,
        use_blosc2_cpp,
    )
    from serializejson import serialize_parameters

import types
from base64 import b64decode

# base64 écrit directement dans la sortie, et compression blosc2 faite en C
# (BloscDiffere : compression déférée au writer C++ — son fil d'écriture
# compresse et choisit l'étiquette lui-même, mêmes octets que la voie hâtive)
from rapidjson import RawBytesToBase64, BloscToBase64, BloscDiffere


def sans_prefixe_longueur(string):
    # préfixe « <n>: » écrit devant le base64 par le sérialiseur (il permet
    # au parseur de sauter le scan de la chaîne) : ':' est hors de l'alphabet
    # base64, sa présence signe le préfixe ; anciens fichiers : intacts
    # (défini aussi dans tools.py : le greffon doit marcher avec les deux
    # empaquetages, SmartFramework ou serializejson)
    if string[:1].isdigit():
        deux_points = string.find(":", 1, 21)
        if deux_points != -1:
            return string[deux_points + 1 :]
    return string


def bytearrayB64(string, compression=None):
    if type(string) is bytearray:
        # charge déjà décodée du base64 par le parseur C++ (sans chaîne
        # intermédiaire) : il ne reste que l'éventuelle décompression
        if compression == "b64":
            return string
        if compression in ("b64_blosc", "b64_blosc2"):
            return blosc_decompress(string, as_bytearray=True)
        if compression == "b64_blosc2p":
            return blosc_chunks_decompress(string, as_bytearray=True)
        raise Exception(f"unknow {compression} compression")
    if not compression or compression == "ascii":
        return bytearray(
            string, "ascii"
        )  # A REVOIR : 2 COPIES !!! a priori n'arrive jamsi d'encoder bytearray en "ascii"
    elif compression == "b64":
        # voie FROIDE : en usage normal le parseur C++ décode le base64
        # lui-même et cette recette reçoit directement des bytearray
        return bytearray(b64decode(sans_prefixe_longueur(string), validate=True))
    elif compression in ("b64_blosc", "b64_blosc2"):
        return blosc_decompress(
            b64decode(sans_prefixe_longueur(string), validate=True),
            as_bytearray=True,
        )
    elif compression == "b64_blosc2p":
        return blosc_chunks_decompress(sans_prefixe_longueur(string), as_bytearray=True)
    raise Exception(f"unknow {compression} compression")


constructors["bytearray"] = bytearrayB64


class bytesB64:
    def __new__(cls, string, compression=None):
        if type(string) is bytes:
            # charge déjà décodée du base64 par le parseur C++ (sans chaîne
            # intermédiaire) : il ne reste que l'éventuelle décompression
            if compression == "b64":
                return string
            if compression in ("b64_blosc", "b64_blosc2"):
                return blosc_decompress(string)
            if compression == "b64_blosc2p":
                return blosc_chunks_decompress(string)
            raise Exception(f"unknow {compression} compression")
        if not compression or compression == "ascii":
            return bytes(string, "ascii")  # A REVOIR : 2 COPIES !!!
        elif compression == "b64":
            return b64decode(sans_prefixe_longueur(string), validate=True)
        elif compression in ("b64_blosc", "b64_blosc2"):
            return blosc_decompress(
                b64decode(sans_prefixe_longueur(string), validate=True)
            )
        elif compression == "b64_blosc2p":
            return blosc_chunks_decompress(sans_prefixe_longueur(string))
        raise Exception(f"unknow {compression} compression")


# permet de se passer de l'encoding "ascii" et de limiter les copies ?
constructors["bytes"] = bytesB64


def serializejson_bytearray(inst):
    compression = serialize_parameters.bytes_compression
    if (
        compression
        and len(inst) >= serialize_parameters.bytes_size_compression_threshold
    ):
        # écriture blosc2 seulement (l'écriture v1 python-blosc a été retirée
        # le 05/08/2026, sa LECTURE demeure) ; trame unique déterministe
        blosc2_compression = blosc2_compressions.get(compression, None)
        if blosc2_compression is None:
            raise Exception(
                f"{compression}: v1 python-blosc write support was removed,"
                " use a blosc2_* compression (v1 files remain readable)"
            )
        if not use_blosc2_cpp:
            raise Exception(
                f"{compression} compression needs a loadable libblosc2"
            )
        if serialize_parameters.single_line_init or serialize_parameters._dump_one_line:
            # la liste [charge, étiquette] sera compacte : le writer peut
            # l'écrire lui-même une fois la taille compressée connue — donc
            # différer la compression (au fil d'écriture pour un dump fichier)
            return (
                "bytearray",
                (
                    BloscDiffere(
                        inst,
                        serialize_parameters.bytes_compression_level,
                        blosc2_compression,
                    ),
                ),
                None,
            )
        compressed = BloscToBase64(
            inst,
            1,
            serialize_parameters.bytes_compression_level,
            0,  # NOSHUFFLE
            blosc2_compression,
        )
        if compressed.compressed_size < len(inst):
            return "bytearray", (compressed, "b64_blosc2"), None
    return "bytearray", (RawBytesToBase64(inst), "b64"), None


serializejson_builtins[bytearray] = serializejson_bytearray


def serializejson_bytes(inst):
    compression = serialize_parameters.bytes_compression
    if (
        compression
        and len(inst) >= serialize_parameters.bytes_size_compression_threshold
    ):
        # écriture blosc2 seulement (l'écriture v1 python-blosc a été retirée
        # le 05/08/2026, sa LECTURE demeure) ; trame unique déterministe
        blosc2_compression = blosc2_compressions.get(compression, None)
        if blosc2_compression is None:
            raise Exception(
                f"{compression}: v1 python-blosc write support was removed,"
                " use a blosc2_* compression (v1 files remain readable)"
            )
        if not use_blosc2_cpp:
            raise Exception(
                f"{compression} compression needs a loadable libblosc2"
            )
        if not inst.isascii() and (
            serialize_parameters.single_line_new
            or serialize_parameters._dump_one_line
        ):
            # compression déférée (voir bytearray) — mais PAS pour un bytes
            # ascii : si la compression ne gagne pas, sa forme de référence
            # est la CHAÎNE ascii_printables, que le writer ne peut pas
            # choisir après coup
            return (
                "bytes",
                None,
                None,
                None,
                None,
                (
                    BloscDiffere(
                        inst,
                        serialize_parameters.bytes_compression_level,
                        blosc2_compression,
                    ),
                ),
            )
        compressed = BloscToBase64(
            inst,
            1,
            serialize_parameters.bytes_compression_level,
            0,  # NOSHUFFLE
            blosc2_compression,
        )
        if compressed.compressed_size < len(inst):
            return ("bytes", None, None, None, None, (compressed, "b64_blosc2"))
    if inst.isascii():
        try:
            return ("bytes", None, None, None, None, (inst.decode("ascii_printables"),))
        except:
            pass
    return ("bytes", None, None, None, None, (RawBytesToBase64(inst), "b64"))


serializejson_builtins[bytes] = serializejson_bytes


def serializejson_type(inst):
    if inst is type:
        return ("type", None, None)
    else:
        return ("type", (class_str_from_class(inst),), None)


serializejson_builtins[type] = serializejson_type


def serializejson_function(inst):
    return ("function", (class_str_from_class(inst),), None)


serializejson_builtins[types.FunctionType] = serializejson_function


def serializejson_module(inst):
    state = dict()
    toRemove = ["__builtins__", "__file__", "__package__", "__name__", "__doc__"]
    for key, value in inst.__dict__.items():
        if key not in toRemove:
            state[key] = value
    return ("module", None, state)


serializejson_builtins[types.ModuleType] = serializejson_function
