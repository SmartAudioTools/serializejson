# --- FONCTIONS FOR SERIALIZED OBJECTS IN BASE 64------------------------------
# defaultIntType =  numpy_dtype("int_")

import sys
from pybase64 import b64decode
try:
    from numpy import frombuffer, unpackbits, uint8, ndarray, int32, int64, copy
    from numpy import dtype as numpy_dtype
    use_numpy = True
except:
    ndarray = None
    use_numpy = False
from SmartFramework.serialize import serializeParameters

nb_bits = sys.maxsize.bit_length() + 1

def bytearrayB64(b64):
    return bytearray(b64decode(b64, validate=True))

def bytesB64(b64):
    return b64decode(b64, validate=True)


def numpyB64(str64, dtype=None, shapeOrLen=None):
    decodedBytes = b64decode(str64, validate=True)  # str64 -> bytes : decodage avec copie
    if dtype in ("bool", bool):
        numpy_uint8_containing_8bits = frombuffer(decodedBytes, uint8)  # pas de copie -> read only
        numpy_uint8_containing_8bits = unpackbits(
            numpy_uint8_containing_8bits
        )  # copie dans un numpy array de uint8 mutable
        if shapeOrLen is None:
            shapeOrLen = len(numpy_uint8_containing_8bits)
        return ndarray(shapeOrLen, dtype, numpy_uint8_containing_8bits)  # pas de recopie
    else:
        if isinstance(dtype, list):
            dtype = [(str(champName), champType) for champName, champType in dtype]
        if shapeOrLen is None:
            array = frombuffer(decodedBytes, dtype)  # pas de recopie
        else:
            array = ndarray(shapeOrLen, dtype, decodedBytes)  # pas de recopie
        if (
            nb_bits == 32 and serializeParameters.numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit
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

        try:
            array.flags.writeable = True  # work with numpy < ???
        except:
            array = copy(array)
        return array
