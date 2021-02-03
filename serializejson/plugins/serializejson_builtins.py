try:
    from SmartFramework.serialize.tools import (
        class_str_from_class,
        serializejson_builtins,
        constructors,
        blosc_compressions,
    )
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson.tools import class_str_from_class, serializejson_builtins, constructors, blosc_compressions
    from serializejson import serialize_parameters

import blosc
import types
from pybase64 import b64decode, b64decode_as_bytearray, b64encode_as_string


def bytearrayB64(string, compression=None):
    if not compression or compression == "ascii":
        return bytearray(
            string, "ascii"
        )  # A REVOIR : 2 COPIES !!! a priori n'arrive jamsi d'encoder bytearray en "ascii"
    elif compression == "b64":
        return b64decode_as_bytearray(string, validate=True)
    elif compression == "b64_blosc":
        return blosc.decompress(b64decode(string, validate=True), as_bytearray=True)
    raise Exception(f"unknow {compression} compression")


constructors["bytearray"] = bytearrayB64


class bytesB64:
    def __new__(cls, string, compression=None):
        if not compression or compression == "ascii":
            return bytes(string, "ascii")  # A REVOIR : 2 COPIES !!!
        elif compression == "b64":
            return b64decode(string, validate=True)
        elif compression == "b64_blosc":
            return blosc.decompress(b64decode(string, validate=True))
        raise Exception(f"unknow {compression} compression")


constructors["bytes"] = bytesB64  # permet de se passer de l'encoding "ascii" et de limiter les copies ?


def serializejson_bytearray(inst):
    compression = serialize_parameters.bytes_compression
    if compression and len(inst) >= serialize_parameters.bytes_size_compression_threshold:
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
            return "bytearray", (b64encode_as_string(compressed), "b64_blosc"), None
    return "bytearray", (b64encode_as_string(inst), "b64"), None


serializejson_builtins[bytearray] = serializejson_bytearray


def serializejson_bytes(inst):
    compression = serialize_parameters.bytes_compression
    if compression and len(inst) >= serialize_parameters.bytes_size_compression_threshold:
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
            return ("bytes", None, None, None, None, (b64encode_as_string(compressed), "b64_blosc"))
    if inst.isascii():
        try:
            return ("bytes", None, None, None, None, (inst.decode("ascii_printables"),))
        except:
            pass
    return ("bytes", None, None, None, None, (b64encode_as_string(inst), "b64"))


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
