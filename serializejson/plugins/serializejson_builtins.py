try:
    from SmartFramework.serialize.tools import (
        class_str_from_class,
        serializejson_builtins,
        constructors,
        blosc_compressions,
        blosc2_compressions,
        blosc_decompress,
        blosc_chunks_decompress,
        use_blosc2_cpp,
        use_blosc2_fork,
    )
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson.tools import (
        class_str_from_class,
        serializejson_builtins,
        constructors,
        blosc_compressions,
        blosc2_compressions,
        blosc_decompress,
        blosc_chunks_decompress,
        use_blosc2_cpp,
        use_blosc2_fork,
    )
    from serializejson import serialize_parameters

import blosc
import types
from pybase64 import b64decode, b64decode_as_bytearray

# base64 écrit directement dans la sortie, et compression blosc2 faite en C
from rapidjson import RawBytesToBase64, BloscToBase64


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
        return b64decode_as_bytearray(string, validate=True)
    elif compression in ("b64_blosc", "b64_blosc2"):
        return blosc_decompress(b64decode(string, validate=True), as_bytearray=True)
    elif compression == "b64_blosc2p":
        return blosc_chunks_decompress(string, as_bytearray=True)
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
            return b64decode(string, validate=True)
        elif compression in ("b64_blosc", "b64_blosc2"):
            return blosc_decompress(b64decode(string, validate=True))
        elif compression == "b64_blosc2p":
            return blosc_chunks_decompress(string)
        raise Exception(f"unknow {compression} compression")


# permet de se passer de l'encoding "ascii" et de limiter les copies ?
constructors["bytes"] = bytesB64


def serializejson_bytearray(inst):
    compression = serialize_parameters.bytes_compression
    if (
        compression
        and len(inst) >= serialize_parameters.bytes_size_compression_threshold
    ):
        blosc2_compression = blosc2_compressions.get(compression, None)
        if blosc2_compression:
            # compression faite en C (libblosc2), sans repasser par Python
            if not use_blosc2_cpp:
                raise Exception(
                    f"{compression} compression needs the python-blosc2 wheel"
                )
            nthreads = serialize_parameters.bytes_compression_threads
            if use_blosc2_fork:
                # fork déterministe : le multi-thread INTERNE de la lib produit
                # déjà des octets stables -> trame unique standard
                nthreads = 1
            compressed = BloscToBase64(
                inst,
                1,
                serialize_parameters.bytes_compression_level,
                0,  # NOSHUFFLE
                blosc2_compression,
                nthreads if type(nthreads) is int else 1,
            )
            if compressed.compressed_size < len(inst):
                label = "b64_blosc2p" if compressed.frames > 1 else "b64_blosc2"
                return "bytearray", (compressed, label), None
        else:
            blosc_compression = blosc_compressions.get(compression, None)
            if blosc_compression:
                compressed = blosc.compress(
                    inst,
                    1,
                    cname=blosc_compression,
                    clevel=serialize_parameters.bytes_compression_level,
                    shuffle=blosc.NOSHUFFLE,
                )
            else:
                raise Exception(f"{compression} compression unknow")
            if len(compressed) < len(inst):
                return "bytearray", (RawBytesToBase64(compressed), "b64_blosc"), None
    return "bytearray", (RawBytesToBase64(inst), "b64"), None


serializejson_builtins[bytearray] = serializejson_bytearray


def serializejson_bytes(inst):
    compression = serialize_parameters.bytes_compression
    if (
        compression
        and len(inst) >= serialize_parameters.bytes_size_compression_threshold
    ):
        blosc2_compression = blosc2_compressions.get(compression, None)
        if blosc2_compression:
            # compression faite en C (libblosc2), sans repasser par Python
            if not use_blosc2_cpp:
                raise Exception(
                    f"{compression} compression needs the python-blosc2 wheel"
                )
            nthreads = serialize_parameters.bytes_compression_threads
            if use_blosc2_fork:
                # fork déterministe : le multi-thread INTERNE de la lib produit
                # déjà des octets stables -> trame unique standard
                nthreads = 1
            compressed = BloscToBase64(
                inst,
                1,
                serialize_parameters.bytes_compression_level,
                0,  # NOSHUFFLE
                blosc2_compression,
                nthreads if type(nthreads) is int else 1,
            )
            if compressed.compressed_size < len(inst):
                label = "b64_blosc2p" if compressed.frames > 1 else "b64_blosc2"
                return ("bytes", None, None, None, None, (compressed, label))
        else:
            blosc_compression = blosc_compressions.get(compression, None)
            if blosc_compression:
                compressed = blosc.compress(
                    inst,
                    1,
                    cname=blosc_compression,
                    clevel=serialize_parameters.bytes_compression_level,
                    shuffle=blosc.NOSHUFFLE,
                )
            else:
                raise Exception(f"{compression} compression unknow")
            if len(compressed) < len(inst):
                return (
                    "bytes",
                    None,
                    None,
                    None,
                    None,
                    (RawBytesToBase64(compressed), "b64_blosc"),
                )
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
