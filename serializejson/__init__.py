"""serializejson is a python library for serialization (and deserialization) of complex Python objects in [JSON](http://json.org/) build upon [python-rapidjson](https://github.com/python-rapidjson/python-rapidjson) and [pybase64](https://github.com/mayeut/pybase64)

WARNING: serializejson can execute arbitrary Python code if the load parameter autorized_classes is "all" when loading json. 
Do not load serializejsons from untrusted / unauthenticated sources without carfuly set the autorized_classes parameter. 

- supports Python 3.7 (maybe lower) or greater.
- serialize arbitrary python objects in dictionnary adding "__class__" ,and eventually "__init__" and "__state__" keys. 
- bytes and bytearray are very quikly serialized and deserializaed in base64 tanks to [pybase64](https://github.com/mayeut/pybase64).
- call the sames objects methodes than pickle. Therefore allmost all pickable objects are serializable with serializejson without any modification.
- serialized objects are human-readable. (Your datas will never be unreadable if your code evolved, you will allway be able to modify your datas with a text editor, unlike with pickle)
- serialized objects take generaly less space than with pickle and juste a little 30% more if big binaries data (numpy array, bytes, bytearray)
- only two time slower than pickle and much more faster than jsonpickle.
- can safely load untrusted / unauthenticated sources if autorized_classes list parameter is set carfuly with stricly necessary objects (unlike pickle). 
- can update existing objects recursively instead of overide thems (serializejson can be used to save and restore in place a complet application state).
- filter attribut starting with "_" by default (unlike pickle).
- numpy arrays can be serialized in list with automatique conversion in both way or in a conservative way. 
- support circular references and serialize only once duplicated object (WARNING :not yet if the object is a list or dictionnary).
- try to call attributs setters and propreties setters when loading if set_attributs  = True.
- accept json with comment (// and /* */).
- can automaticly recognize objects in json from keys names and recreate them, without the need of "`__class__`" key, if passeds in recognized_classes. It allow to load foreign json serialized with others libraries who only save objects attributs. 
- dump and load support string path. 
- can iterativly encode (with append) and decode (with iterator) a list in json, saving memmory space during the process of serialization et deserialization.
- WARNING : tuple, time.struct_time, collections.Counter, collections.OrderedDict, collections.defaultdict, namedtuples and dataclass are not yet correctly serialized 
"""

import sys
from pybase64 import b64decode
from SmartFramework.serialize import serializeParameters
from SmartFramework.tools import objects
from .serializejson import dumps,dump,loads,load,append,Encoder,Decoder
try:
    from numpy import frombuffer, unpackbits, uint8, ndarray, int32, int64, copy
    from numpy import dtype as numpy_dtype
    use_numpy = True
except:
    ndarray = None
    use_numpy = False
import importlib.metadata
__version__ = importlib.metadata.version('serializejson')

# --- FONCTIONS FOR SERIALIZED OBJECTS IN BASE 64------------------------------
# defaultIntType =  numpy_dtype("int_")
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

objects.bytearrayB64 = bytearrayB64
objects.numpyB64 = numpyB64
objects.bytesB64 = bytesB64
