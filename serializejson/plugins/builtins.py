try:
    from SmartFramework import bytearrayB64, bytesB64
    from SmartFramework.serialize.tools import encodedB64, classStrFromClass, compressedBytes
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson import bytearrayB64, bytesB64
    from serializejson.tools import encodedB64, classStrFromClass
    from serializejson import serialize_parameters

import blosc

blosc_compressions = set(blosc.cnames)


def tuple_from_bytearray(inst):
    compression = serialize_parameters.bytes_compression
    if compression and len(inst) >= serialize_parameters.bytes_size_compression_threshold:
        if compression in blosc_compressions:
            compressed = blosc.compress(
                inst,
                1,
                cname=compression,
                clevel=serialize_parameters.bytes_compression_level,
                shuffle=blosc.NOSHUFFLE,
            )
        else:
            raise Exception(f"{compression} compression unknow")
        if len(compressed) < len(inst):
            if serialize_parameters.bytearray_use_bytearrayB64:
                return (bytearrayB64, (encodedB64(compressed), compression), None)
            else:
                return (
                    "blosc.decompress",
                    (compressedBytes(compressed), True),
                    None,
                )  # a revoir y'a une bug va compression à l'infini
    if serialize_parameters.bytearray_use_bytearrayB64:
        return (bytearrayB64, (encodedB64(inst),), None)
    else:
        return (bytearray, (bytes(inst),), None)


def tuple_from_bytes(inst):
    compression = serialize_parameters.bytes_compression
    if compression and len(inst) >= serialize_parameters.bytes_size_compression_threshold:
        if compression in blosc_compressions:
            compressed = blosc.compress(
                inst,
                1,
                cname=compression,
                clevel=serialize_parameters.bytes_compression_level,
                shuffle=blosc.NOSHUFFLE,
            )
        else:
            raise Exception(f"{compression} compression unknow")
        if len(compressed) < len(inst):
            if serialize_parameters.bytes_use_bytesB64:
                return (bytesB64, (encodedB64(compressed), compression), None)
            else:
                return ("blosc.decompress", (compressedBytes(compressed),), None)
    if inst.isascii():
        try:
            string = inst.decode("ascii_printables")
            return (bytes, (string, "ascii"), None)
        except:
            pass
    # if serialize_parameters.bytes_use_bytesB64:
    #    return (bytesB64, (encodedB64(inst),), None)
    return ("base64.b64decode", (encodedB64(inst),), None)


def tuple_from_complex(inst):
    return ("complex", (inst.real, inst.imag), None)


def tuple_from_type(inst):
    return ("type", (classStrFromClass(inst),), None)


def tuple_from_function(inst):
    return ("function", (classStrFromClass(inst),), None)


def tuple_from_module(inst):
    state = dict()
    toRemove = ["__builtins__", "__file__", "__package__", "__name__", "__doc__"]
    for key, value in inst.__dict__.items():
        if key not in toRemove:
            state[key] = value
    return ("module", None, state)
