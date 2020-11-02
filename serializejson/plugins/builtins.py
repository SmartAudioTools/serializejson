from base64 import b64decode
try:
    from SmartFramework import  bytearrayB64
    from SmartFramework.serialize.tools import encodedB64,classStrFromClass
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson import  bytearrayB64
    from serializejson.tools import encodedB64,classStrFromClass
    from serializejson import serialize_parameters


def tuple_from_bytearray(inst):
    if serialize_parameters.bytearray_use_bytearrayB64:
        return (bytearrayB64, (encodedB64(inst),), None)
    else:
        return (bytearray, (bytes(inst),), None)

def tuple_from_bytes(inst):
    if inst.isascii():
        try:
            # string = inst.decode("utf_8")
            # return (bytes,(string,"utf_8"),None)
            string = inst.decode("ascii_printables")
            return (bytes, (string, "ascii"), None)
        except:
            pass
    return (b64decode, (encodedB64(inst),), None)



def tuple_from_complex(inst):
    return ("complex", (inst.real, inst.imag), None)

def tuple_from_type(inst):
    return ("type", (classStrFromClass(inst),), None)

def tuple_from_module(inst):
    state = dict()
    toRemove = ["__builtins__", "__file__", "__package__", "__name__", "__doc__"]
    for key, value in inst.__dict__.items():
        if key not in toRemove:
            state[key] = value
    return ("module", None, state)

