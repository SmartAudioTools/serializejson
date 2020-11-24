"""**serializejson** is a python library for serialization and deserialization of complex Python objects in 
`JSON <http://json.org>`_ build upon `python-rapidjson <https://github.com/python-rapidjson/python-rapidjson>`_ and `pybase64 <https://github.com/mayeut/pybase64>`_

- supports Python 3.7 (maybe lower) or greater.
- serializes arbitrary python objects into a dictionary by adding "__class__" ,and eventually "__init__" and "__state__" keys. 
- serializes and deserializes bytes and bytearray very quickly in base64 tanks to `pybase64 <https://github.com/mayeut/pybase64>`_.
- calls the same objects methods as pickle. Therefore almost all pickable objects are serializable with serializejson without any modification.
- serialized objects are human-readable. Your datas will never be unreadable if your code evolved, you will always be able to modify your datas with a text editor, unlike with pickle.
- serialized objects take generally less space than with pickle and just a little 30% more if big binaries data (numpy array, bytes, bytearray)
- only two times slower than pickle and much faster than jsonpickle.
- can safely load untrusted / unauthenticated sources if authorized_classes list parameter is set carefully with strictly necessary objects (unlike pickle).
- can update existing objects recursively instead of override them (serializejson can be used to save and restore in place a complete application state).
- filters attribute starting with "_" by default (unlike pickle).
- numpy arrays can be serialized in list with automatic conversion in both ways or in a conservative way. 
- supports circular references and serialize only once duplicated objects (WARNING: not yet if the object is a list or dictionary).
- try to call attribute setters and properties setters when loading if set_attributes  = True.
- accepts json with comment (// and /* */).
- can automatically recognize objects in json from keys names and recreate them, without the need of "__class__" key, if passed in recognized_classes. It allows loading foreign json serialized with others libraries who only save objects attributes. 
- dumps and loads support string path. 
- can iteratively encode (with append) and decode (with iterator) a list in json, saving memory space during the process of serialization et deserialization.
- WARNING: tuple, time.struct_time, collections.Counter, collections.OrderedDict, collections.defaultdict, namedtuples and dataclass are not yet correctly serialized 




"""


from SmartFramework.tools.dictionnaires import filtered

try:
    import importlib.metadata as importlib_metadata
except:
    import importlib_metadata
try:
    __version__ = importlib_metadata.version("serializejson")
except:
    pass
import os
import io
import sys
from collections import deque
import rapidjson

# from typing import TextIO,BinaryIO
from pybase64 import b64decode

try:
    import numpy
    from numpy import frombuffer, unpackbits, uint8, ndarray, int32, int64, copy
    from numpy import dtype as numpy_dtype

    use_numpy = True
except ModuleNotFoundError:
    ndarray = None
    use_numpy = False
import gc
from _collections_abc import list_iterator
from . import serialize_parameters
import blosc

blosc_compressions = set(blosc.cnames)

__all__ = ["dumps", "dump", "loads", "load", "append", "Encoder", "Decoder"]


# not_duplicates_types = set([type(None), bool, int, float, str])


# --- FONCTIONS FOR SERIALIZED OBJECTS IN BASE 64------------------------------
# defaultIntType =  numpy_dtype("int_")


nb_bits = sys.maxsize.bit_length() + 1


def bytearrayB64(b64, compression=None):
    if compression:
        if compression in blosc_compressions:
            return blosc.decompress(b64decode(b64, validate=True), as_bytearray=True)
        raise Exception(f"unknow {compression} compression")
    return bytearray(b64decode(b64, validate=True))


def bytesB64(b64, compression=None):
    if compression:
        if compression in blosc_compressions:
            return blosc.decompress(b64decode(b64, validate=True))
        raise Exception(f"unknow {compression} compression")
    return b64decode(b64, validate=True)


def numpyB64(str64, dtype=None, shape_len_compression=None, compression=None):
    decodedBytes = b64decode(str64, validate=True)
    if isinstance(shape_len_compression, str):
        compression = shape_len_compression
        shape_len = None
    else:
        shape_len = shape_len_compression
    if compression:
        if compression in blosc_compressions:
            decodedBytes = blosc.decompress(decodedBytes, as_bytearray=True)
        else:
            raise Exception(f"unknow {compression} compression")
    # str64 -> bytes: decoding with copy
    if dtype in ("bool", bool):
        numpy_uint8_containing_8bits = frombuffer(decodedBytes, uint8)  # pas de copie -> read only
        numpy_uint8_containing_8bits = unpackbits(
            numpy_uint8_containing_8bits
        )  # copie dans un numpy array de uint8 mutable
        if shape_len is None:
            shape_len = len(numpy_uint8_containing_8bits)
        return ndarray(shape_len, dtype, numpy_uint8_containing_8bits)  # pas de recopie
    else:
        if isinstance(dtype, list):
            dtype = [(str(champName), champType) for champName, champType in dtype]
        if shape_len is None:
            array = frombuffer(decodedBytes, dtype)  # pas de recopie
        else:
            array = ndarray(shape_len, dtype, decodedBytes)  # pas de recopie
        if (
            nb_bits == 32 and serialize_parameters.numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit
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


# --- FONCTIONS BASED API ----------------------

from .tools import (
    instance,
    tupleFromInstance,
    classStrFromClass,
    encodedB64,
    classFromClassStr,
    from_name,
    _get_set_attributes_classes_strings,
    encoder_plugins_parameters_keys,
    encoder_plugins_parameters_default_values,
    _onlyOneDimSameTypeNumbers,
)


def dumps(obj, **argsDict):
    """
    Dump object into json string.

    Args:
        obj: object to dump.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    return Encoder(**argsDict)(obj)


def dump(obj, fp, **argsDict):
    """
    Dump an object into json file.

    Args:
        obj: object to dump.
        fp (str or file-like): path or file.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    if isinstance(fp, str):
        fp = open(fp, "wb")
    Encoder(**argsDict)(obj, fp)


def append(obj, fp=None, *, indent="\t", **argsDict):
    """
    Append an object into json file.

    Args:
        obj: object to dump.
        fp (str or file-like):
            path or file. The file must be empty or containing a json list.
        indent: indent passed to Encoder.
        **argsDict: other parameters passed to the Encoder (see documentation).
    """
    fp = _open_for_append(fp, indent)
    Encoder(**argsDict)(obj, fp)
    _close_for_append(fp, indent)


def loads(s, *, obj=None, iterator=False, **argsDict):  # on ne peut pas en meme temps updater objet
    """
    Load an object from a json string.

    Args:
        s:
            the json string.
        obj (optional):
            If provided, the object `obj` will be updated and no new object will be created.
        iterator:
            if `True` and the json corresponds to a list then the items will be read one by one which reduces RAM consumption.
        **argsDict:
            parameters passed to the Decoder (see documentation).

    Return:
        created object, updated object if `obj` is provided or elements iterator if `iterator` is `True`.
    """
    decoder = Decoder(**argsDict)
    if iterator:
        return decoder
    else:
        return decoder(fp_or_s=s, obj=obj)


def load(fp, *, obj=None, iterator=False, **argsDict):
    """
    Load an object from a json file.

    Args:
        fp (str or file-like):
            the json file.
        obj (optional):
            If provided, the object `obj` will be updated and no new object will be created.
        iterator:
            if `True` and the json corresponds to a list then the items will be read one by one which reduces RAM consumption.
        **argsDict:
            parameters passed to the Decoder (see documentation).

    Return:
        created object, updated object if passed obj or elements iterator if iterator is True.
    """

    if iterator:
        return Decoder(**argsDict)
    else:
        return Decoder(**argsDict).load(fp=fp, obj=obj)


# --- CLASSES BASED API -------------------------------------------------------


class Encoder(rapidjson.Encoder):
    """
    class for serialization of python objects into json.

    Args:
        fp (string or file-like):
            path or file-like object.
            When specified, the encoded result will be written there
            and you will not have to pass it to the `dump()` method later.

        attributes_filter:
            attributes_filter allow you to chose if you want to serialize
            privates attributes at the dump time, instead of hard coded in methodes.
            If an object instance has not __reduce__() or __gestate__() methodes
            given the state and if attributes_filter is set to "_" (by default),
            then all object attributes in __dict__ or __slots__ will
            be serialized except ones starting with "_" corresponding to
            privates attributs.
            If you want to serialize all attributes,
            private include, you sould set attributes_filter to None.
            If you want to still have the same behavior than pickle,
            you sould set attributes_filter to None and
            eventually hard coding a __reduce__() or __gestate__() methode filtering
            attributes starting with "_" with serializesjon.filtered() function.

        chunk_size:
            write the stream in chunks of this size at a time.

        ensure_ascii:
            whether non-ascii str are dumped with escaped unicode or utf-8.

        indent (None, int or '\\\\t'):
            indentation width to produce pretty printed JSON.

            - None: Json in one line (quicker than with indent).
            - int: new lines and `indent` spaces for indent.
            - '\\\\t': new lines and tabulations for indent (take less space than int > 1).

        single_line_init:
            whether `__init__` must be serialize in one line.

        single_line_list_numbers:
            whether list of numbers of same type must be serialize in one line.

        sort_keys:
            whether dictionary keys should be sorted alphabetically.

        bytes_compression(None or str):
            Compression for bytes, bytesarray and numpy arrays:

            - `None` : no compression
            - `str` : compression name ("blosclz", "lz4", "lz4hc", "zlib" or "zstd") with maximum compression level 9.
            - `tuple` : (compression name, compression level) with compression level from 0 (no compression) to 9 (maximum compression)

            By default the "zstd" compression is used with compression level 1.
            For the highest compression (but with slower dumping) use "zstd" with compression level 9

        bytes_size_compression_threshold (int):
            bytes size threshold beyond compression is tried to reduce size of
            bytes, bytesarray and numpy array if `bytes_compression` is not None.
            The default value is 512, generaly beside the compression is not
            worth it due to the header size and the additional cpu cost.

        numpy_array_readable_max_size (int,None or dict):
            Defines the maximum array size for serialization in readable numbers.
            By default numpy_array_readable_max_size is set to 0, all numpy arrays are encoded in base 64.

            - `int` : all numpy arrays smaller than this size are serialized in readable numbers.
            - `None` : there is no maximum size and all numpy arrays are serialized in readable numbers.
            - `dict` : for each dtype key, the value define the maximum size  of this dtype arrays for serialization in readable numbers. If value is `None` there is no maximum and numpy array of this dtype are all serialized in readable numbers. If you want only numpy arrays int32 to be readable, then you should pass `numpy_array_readable_max_size = {"int32":None}`

            .. note::

                serialization in readable decimals can take much less space in int32 if the values ar smaller or equal to 9999,
                but is much slower than in base 64 for big arrays. If you have lot or large numpy int32 arrays and
                performance matters, then you should stay with default value 0.

        numpy_array_to_list:
            whether numpy array should be serialized as list.

            .. warning::

                This should be used only for interoperability with other json libraries.
                If you want readable  values in your json, we recommend to use instead
                `numpy_array_readable_max_size` which is not destructive.

                With `numpy_array_to_list` set to `True`:

                - numpy arrays will be indistinctable from list in json.
                - `Decoder(numpy_array_from_list=True)` will recreate numpy array from lists of bool, int or float, if not an `__init__` args list, with the the risque of unwanted convertion of lists to numpy arrays.
                - dtype of the numpy array will be loosed loosed if not bool, int32 or float64 and converted to the bool, int32 or float64 when loading
                - Empty numpy array will be converted to [] without any way to guess the dtype and will stay an empty list when loading event with `numpy_array_from_list = True`

        numpy_types_to_python_types:
             whether numpy integers and floats outside of a array must be convert to python types.
             It save space and generally don't affect

        **plugins_parameters:
            extra keys arguments are stocked in "serialize_parameters"
            global module and accessible in plugins module in order to allow
            the choice between serialization options in plugins.

    """

    """
        bytearray_use_bytearrayB64: 
            save bytearray with references to serializejson.bytearrayB64
            instead of verbose use of base64.b64decode. It save space but make 
            the json file dependent of the serializejson module. 
        
        numpy_array_use_numpyB64: 
            save numpy arrays with references to serializejson.numpyB64
            instead of verbose use of base64.b64decode. It save space but make 
            the json file dependent of the serializejson module. 

    
    
        bytes_to_string:
            whether bytes must be dumped in string after utf-8 decode.
        skip_invalid_keys (bool): 
            whether invalid dict keys will be skipped.

        number_mode (int): 
            enable particular behaviors in handling numbers.

        datetime_mode (int):
            how should datetime, time and date instances be handled.

        uuid_mode (int):
            how should UUID instances be handled.

        write_mode: 
            WM_COMPACT: that produces the most compact JSON representation.
            WM_PRETTY: it will use RapidJSON's PrettyWriter.
            WM_SINGLE_LINE_ARRAY: arrays will be kept on a single line.
            
        bytes_mode: 
            BM_UTF8
            BM_NONE
    """

    def __new__(
        cls,
        fp=None,
        *,
        attributes_filter="_",
        chunk_size=65536,
        ensure_ascii=False,
        indent="\t",
        single_line_init=True,
        single_line_list_numbers=True,
        sort_keys=True,
        bytes_compression=("zstd", 1),  #
        bytes_size_compression_threshold=512,
        bytes_use_bytesB64=True,  # le laisser ?
        bytearray_use_bytearrayB64=True,  # le laisser ?
        numpy_array_use_numpyB64=True,  # le laisser ?
        numpy_array_readable_max_size=0,  #'int32':-1
        numpy_array_to_list=False,
        numpy_types_to_python_types=True,
        **plugins_parameters,
    ):

        # if not bytes_to_string:
        #   bytes_mode = rapidjson.BM_NONE
        # else:
        #    bytes_mode = rapidjson.BM_UTF8
        self = super().__new__(
            cls,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            bytes_mode=rapidjson.BM_NONE,
            number_mode=rapidjson.NM_NAN
            # **argsDict
        )
        self.attributes_filter = attributes_filter
        self.fp = fp
        # self.kargs = argsDict
        if indent is None:
            self.single_line_list_numbers = False
            self.single_line_init = False
        else:
            self.single_line_list_numbers = single_line_list_numbers
            self.single_line_init = single_line_init
        self.indent = indent  # rapid json enregistre self.indent_char et self.indent_count , mais ne permet pas de savoir si indent = None ...
        self._dump_one_line = indent is None
        self.dumped_classes = set()
        self.chunk_size = chunk_size
        bytes_compression_level = 9
        if bytes_compression is not None:
            if isinstance(bytes_compression, (list, tuple)):
                bytes_compression, bytes_compression_level = bytes_compression
                if bytes_compression not in blosc_compressions:
                    raise Exception(
                        f"{bytes_compression} compression unknown. Available values for bytes_compression are {', '.join(blosc_compressions)}"
                    )
        self.bytes_compression = bytes_compression
        self.bytes_compression_level = bytes_compression_level
        self.bytes_size_compression_threshold = bytes_size_compression_threshold
        self.bytes_use_bytesB64 = bytes_use_bytesB64
        self.bytearray_use_bytearrayB64 = bytearray_use_bytearrayB64
        self.numpy_array_to_list = numpy_array_to_list
        self.numpy_array_use_numpyB64 = numpy_array_use_numpyB64
        self.numpy_array_readable_max_size = numpy_array_readable_max_size
        self.numpy_types_to_python_types = numpy_types_to_python_types
        unexpected_keywords_arguments = set(plugins_parameters) - encoder_plugins_parameters_keys
        if unexpected_keywords_arguments:
            raise TypeError(
                "serializejson.Encoder got unexpected keywords arguments '"
                + ", ".join(unexpected_keywords_arguments)
                + "'"
            )
        self.plugins_parameters = encoder_plugins_parameters_default_values.copy()
        self.plugins_parameters.update(plugins_parameters)
        return self

    def dump(self, obj, fp=None):
        """
        Dump object into json file.

        Args:
            obj: object to dump.
            fp (optional str or file-like): path or file. If provided, the object will be
                dumped into this file instead of being dumped into the file passed at the Encoder constructor.
        """
        if fp is None:
            fp = self.fp
        if isinstance(fp, str):
            fp = open(fp, "wb")
        self.__call__(obj, stream=fp, chunk_size=self.chunk_size)

    def dumps(self, obj):
        """
        Dump object into json string.
        """
        return self.__call__(obj)

    def append(self, obj, fp=None):
        """
        Append object into json file.

        Args:
            obj: object to dump.
            fp (optional str or file-like): path or file. If provided, the object will be
                dumped into this file instead of being dumped into the file passed at the Encoder
                constructor. The file must be empty or contain a json list.
        """
        if fp is None:
            fp = self.fp
        fp = _open_for_append(fp, self.indent)
        rapidjson.Encoder.__call__(self, obj, stream=fp, chunk_size=self.chunk_size)
        _close_for_append(fp, self.indent)

    def get_dumped_classes(self):
        """
        Return the all dumped classes.
        In order to reuse them as `authorize_classes` argument when loading with a ``serializejson.Decoder``.
        """
        return self.dumped_classes

    # @profile
    def default(self, inst):  # Equivalent au calback "default" qu'on peut passer à dump ou dumps
        id_ = id(inst)
        if id_ in self._already_serialized:
            return {
                "__class__": "serializeJson.from_name",
                "__init__": self._get_path(inst),
            }
        self._already_serialized.add(id_)
        type_inst = type(inst)
        if type_inst in _numpy_types and self.numpy_types_to_python_types:
            if type_inst in _numpy_int_types:
                return int(inst)
            if type_inst in _numpy_float_types:
                return float(inst)
            if type_inst is numpy.bool_:
                return bool(inst)

        if type_inst is encodedB64:
            return bytes.decode(
                inst.encoded_bytes
            )  # inst.encoded_bytes.decode("ascii")   # 52% du temps dans default pour obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)
        if type_inst is tuple:
            # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tupleFromInstance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tupleFromInstance
            self.dumped_classes.add(tuple)
            if self._dump_one_line or not self.single_line_init:
                dic = {"__class__": "tuple", "__init__": list(inst)}
            else:
                dic = {
                    "__class__": "tuple",
                    "__init__": rapidjson.RawJSON(
                        rapidjson.dumps(
                            list(inst),
                            default=self._default_one_line,
                            ensure_ascii=self.ensure_ascii,
                            sort_keys=self.sort_keys,
                            bytes_mode=self.bytes_mode,
                            number_mode=self.number_mode
                            # **self.kargs
                        )
                    ),
                }
        elif use_numpy and type_inst is ndarray and self.numpy_array_to_list:
            if self._dump_one_line or not self.single_line_list_numbers:
                return (
                    inst.tolist()
                )  # A REVOIR : pas génial... va tester si nombres tous du meme type et ne pas pas utiliser rapidjson.NM_NATIVE?
            if inst.dtype in _numpy_float_dtypes:
                number_mode = self.number_mode
            else:
                number_mode = rapidjson.NM_NATIVE  # permet décceler pas mal
            if inst.ndim == 1:
                return rapidjson.RawJSON(rapidjson.dumps(inst.tolist(), ensure_ascii=False, number_mode=number_mode))
            return [
                rapidjson.RawJSON(rapidjson.dumps(elt.tolist(), ensure_ascii=False, number_mode=number_mode))
                for elt in inst
            ]  # inst.tolist()
        dic = self._dict_from_instance(
            inst
        )  # 8.6 % (correspond au temps pour conversion en b64 avec pybase64.b64encode) du temps sur obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)
        initArgs = dic.get("__init__", None)
        if (
            isinstance(initArgs, list) and not self._dump_one_line and self.single_line_init
        ):  # and dic["__class__"] in _oneline_init_classess :
            dic[
                "__init__"
            ] = rapidjson.RawJSON(  # 91.2 % du temps avec obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)
                rapidjson.dumps(
                    initArgs,
                    default=self._default_one_line,
                    ensure_ascii=self.ensure_ascii,
                    sort_keys=self.sort_keys,
                    bytes_mode=self.bytes_mode,
                    number_mode=self.number_mode
                    # **self.kargs
                )
            )
        if not self._dump_one_line and self.single_line_list_numbers:
            for key, value in dic.items():
                if (
                    key != "__class__"
                    and key != "__init__"
                    and type(value) in (list, tuple)
                    and _onlyOneDimSameTypeNumbers(value)
                ):

                    dic[key] = rapidjson.RawJSON(
                        rapidjson.dumps(
                            value,
                            ensure_ascii=self.ensure_ascii,
                            default=self._default_one_line,
                            bytes_mode=self.bytes_mode,
                            number_mode=self.number_mode
                            # **self.kargs
                        )
                    )
        self._already_serialized_id_dic_to_obj_dic[id(dic)] = (
            inst,
            dic,
        )  # important de metre dic avec sinon il va être detruit et son identifiant va être réutilisé.
        # if self.add_id:
        #    dic["_id"] = id_
        return dic
        # raise TypeError('%r is not JSON serializable' % inst)

    # @profile
    def _default_one_line(self, inst):
        type_inst = type(inst)
        if type_inst is encodedB64:
            return inst.encoded_bytes.decode("ascii")
        if type_inst in _numpy_types and self.numpy_types_to_python_types:
            if type_inst in _numpy_int_types:
                return int(inst)
            if type_inst in _numpy_float_types:
                return float(inst)
            if type_inst is numpy.bool_:
                return bool(inst)
        if (
            type_inst is tuple
        ):  # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tupleFromInstance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tupleFromInstance
            self.dumped_classes.add(tuple)
            return {"__class__": "tuple", "__init__": [list(inst)]}
        if type_inst is ndarray and self.numpy_array_to_list:
            return inst.tolist()
        return self._dict_from_instance(inst)

    def _dict_from_instance(self, inst):
        classe, initArgs, state = tupleFromInstance(
            inst
        )  # 97.5 %du temps sur obj = bytes(numpy.arange(2**18,dtype=numpy.float64).data)
        if type(classe) is not str:
            classe = classStrFromClass(classe)
        self.dumped_classes.add(classe)
        dictionnaire = {"__class__": classe}
        if initArgs is not None:
            if type(initArgs) is dict:
                dictionnaire["__init__"] = initArgs
            else:
                if classe in remove_add_braces:
                    dictionnaire["__init__"] = initArgs[0]
                elif len(initArgs) == 1:
                    type_first = type(initArgs[0])
                    if (
                        type_first not in (tuple, list)
                        and not (self.numpy_array_to_list and type_first is numpy.ndarray)
                        and ((type_first is not dict) or "__class__" in initArgs[0])
                    ):
                        dictionnaire["__init__"] = initArgs[0]
                    else:
                        dictionnaire["__init__"] = list(initArgs)  # initArgs is a tuple
                else:
                    dictionnaire["__init__"] = list(initArgs)  # initArgs is a tuple
        if state:
            if type(state) is dict:
                dictionnaire.update(state)
            else:
                dictionnaire["__state__"] = state
        return dictionnaire

    def __call__(self, obj, stream=None, chunk_size=65536):
        if type(obj) in (list, tuple) and self.single_line_list_numbers and _onlyOneDimSameTypeNumbers(obj):
            return rapidjson.dumps(
                obj,
                ensure_ascii=False,
                default=self._default_one_line,
                bytes_mode=self.bytes_mode,
                number_mode=self.number_mode
                # **self.kargs
            )
        blosc.set_nthreads(1)  # slower but for determinist behaviour in order to be able to versining jsons
        serialize_parameters.attributes_filter = self.attributes_filter
        serialize_parameters.bytes_compression = self.bytes_compression
        serialize_parameters.bytes_compression_level = self.bytes_compression_level
        serialize_parameters.bytes_size_compression_threshold = self.bytes_size_compression_threshold
        serialize_parameters.bytes_use_bytesB64 = self.bytes_use_bytesB64
        serialize_parameters.numpy_array_use_numpyB64 = self.numpy_array_use_numpyB64
        serialize_parameters.numpy_array_readable_max_size = self.numpy_array_readable_max_size
        serialize_parameters.bytearray_use_bytearrayB64 = self.bytearray_use_bytearrayB64
        serialize_parameters.__dict__.update(self.plugins_parameters)
        self.dumped_classes = set()
        self._already_serialized = set()
        self._already_serialized_id_dic_to_obj_dic = dict()
        self._root = obj
        encoded = rapidjson.Encoder.__call__(self, obj, stream=stream, chunk_size=chunk_size)
        del self._already_serialized
        del self._already_serialized_id_dic_to_obj_dic
        return encoded

    def _searchSerializedParent(self, obj, already_explored=set()):  # ,list_deep = 10):
        root = self._root
        if obj == root:
            return ["root"]
        id_obj = id(obj)
        if id_obj in already_explored:
            return []
        already_explored = already_explored.copy()
        already_explored.add(id_obj)
        pathElements = list()
        for parent_test in gc.get_referrers(obj):
            id_parent_test = id(parent_test)
            if id_parent_test not in already_explored:
                type_parent_test = type(parent_test)
                if type_parent_test is dict:
                    if id_parent_test in self._already_serialized_id_dic_to_obj_dic:
                        parent_inst, parent_dict = self._already_serialized_id_dic_to_obj_dic[id_parent_test]
                        for key in sorted(parent_test):
                            value = parent_test[key]
                            if value == obj:
                                pathElement = "." + key
                                for elt in self._searchSerializedParent(parent_inst, already_explored):
                                    pathElements.append(elt + pathElement)
                                break
                if type_parent_test is list and not type(parent_test[-1]) is list_iterator:
                    for key, value in enumerate(parent_test):
                        if value == obj:
                            for elt in self._searchSerializedParent(parent_test, already_explored):
                                pathElements.append(elt + "[%d]" % key)
                            break
        return pathElements

    def _get_path(self, obj):
        pathElements = self._searchSerializedParent(obj)
        return sorted(pathElements)[0]


class Decoder(rapidjson.Decoder):
    """
    Decoder for loading objects serialized in json files or strings.

    Args:
        fp (string or file-like):
            Path or file-like object containing the json.
            When specified, the decoder will read from this file
            and you will not have to pass it to the `load()` method later.

        authorized_classes (list):
            Define the classes that serializejson is authorized to recreate from
            the `__class__` keywords in json, in addition to the usuals classes.
            Usual classes are : complex ,bytes, bytearray, Decimal, type, set,
            frozenset, range, slice, deque,  datetime, timedelta, date, time
            numpy.array, numpy.dtype.
            authorized_classes must be a liste of classes or strings
            corresponding to the qualified names of classes (`module.class_name`).
            If the loading json contain an unauthorized  `__class__`,
            serializejson will raise a TypeError exception.

            .. warning::

                Do not load serializejson files from untrusted / unauthenticated
                sources without carefully set the `authorized_classes` parameter.
                Never authorize "eval", "exec", "apply" or other functions or
                classes which could allow execution of malicious code
                with for example :
                ``{"__class__":"eval","__init__":"do_bad_things()"}``


        recognized_classes (list):
            List of classes (string with qualified names or classes) that
            serializejson will try to recognize from keys names.

        updatables_classes (list):
            List of classes (string with qualified names or classes) that
            serializejson will try to update if already in the provided object `obj` when calling `load`.
            Objects will be recreated for other classes.

        set_attributes (bool or list):
            Controls whether `load` will try to call `set_xxx` or `setXxx` methods
            or `xxx` property setter for each attributes of the serialized objects
            when the object as no `__setstate__` method.
            if `set_attributes` is a list of classes or classes qualified names,
            `load` will try to call the setters only for these classes
            and for classes defined in plugins `set_attributes` lists
            (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )

            .. warning::
                **The attribute's setters are called in the json order !**

                - Always use `sort_keys = True` when dumping for determinist behavior.
                - Be carefull if you rename an attribute because setters calls order can still change.
                - If `set_attribute = True` (or is a list) then serializejson will differ from pickle that don't call attribute's setters.

                **It is best to add the __setate__() method to your object:**

                - If you want to call setter in a different order than alphabetic order.
                - If you want to be robust to an attribute name change.
                - If you want to be robust to this `set_attribute` parameter change.
                - If you want to avoid transitional states during setting of attribute one by one.
                - If you want the same behavior as pickle, for being able to still use pickle.

        accept_comments (bool):
            Controls whether serializejson accepts to parse json with comments.

        numpy_array_from_list (bool):
            Controls whether list of int or floats should be loaded into numpy arrays.

        default_value:
            The value returned if the path passed to `load` doesn't exist.
            It allows to have a default object at the first run of the script or
            when the json has been deleted.

        chunk_size (int):
            Chunk size used when reading the json file.



    """

    """
        Inherited from rapidjson.Decoder:

        number_mode (int): Enable particular behaviors in handling numbers
        datetime_mode (int): How should datetime, time and date instances be handled
        uuid_mode (int): How should UUID instances be handled
        parse_mode (int): Whether the parser should allow non-standard JSON extensions (nan, -inf, inf )
    """

    def __new__(
        cls,
        fp=None,
        *,
        authorized_classes=None,
        recognized_classes=None,
        updatables_classes=None,
        set_attributes=True,
        accept_comments=False,
        numpy_array_from_list=False,
        default_value=None,
        chunk_size=65536,
    ):

        if authorized_classes is None:
            authorized_classes = []
        if recognized_classes is None:
            recognized_classes = []
        if updatables_classes is None:
            updatables_classes = []
        if accept_comments:
            parse_mode = rapidjson.PM_COMMENTS
        else:
            parse_mode = rapidjson.PM_NONE
        self = super().__new__(cls, parse_mode=parse_mode)  # , **argsDict)
        self.fp = fp
        self.set_attributes = _get_set_attributes_classes_strings(set_attributes)
        self._authorized_classes_strs = _get_authorized_classes_strings(authorized_classes)
        self._class_from_attributes_names = _get_recognized_classes_dict(recognized_classes)
        # self.accept_comments = accept_comments
        # self.numpy_array_from_list=numpy_array_from_list
        self.default_value = default_value
        self.chunk_size = chunk_size
        self.fp_iter = None
        self._updating = False
        self.numpy_array_from_list = numpy_array_from_list
        if numpy_array_from_list:
            self.end_array = self._end_array_if_numpy_array_from_list
        self.set_updatables_classes(updatables_classes)
        return self

    def load(self, fp=None, obj=None):
        """
        Load object from json file.

        Args:
            fp (optional str or file-like):
                the object will be loaded from this file instead of being loaded from the
                file provided to the Decoder constructor.
            obj (optional):
                If provided, the object `obj` will be updated and no new object will be created.

        Return:
            created object or updated object if passed obj.
        """

        if fp is None:
            fp = self.fp
        if isinstance(fp, str):
            # print("load",fp)
            if not os.path.exists(fp):
                return self.default_value
            fp_or_s = _open_with_good_encoding(fp)
        elif fp is not None:
            fp_or_s = fp
        else:
            raise ValueError('Encoder.__call__() need a "s" string/bytes or "fp" path/file argument')
        return self.__call__(fp_or_s=fp_or_s, obj=obj)

    def loads(self, s, obj=None):
        """
        Load object from json string.

        Args:
            s:
                the json string.
            obj (optional):
                If provided, the object `obj` will be updated and no new object will be created.


                .. note::

                    **Updating an object** consists in restoring its state recursively.

                    * Neither `__new__()` or  `__init__()` will be called.
                    * All childrens of `updatables_classes` will be updated, otherwise will be recreated.
                    * If the object has a `__setstate__()` method, this method will be called with the state.
                    * Otherwise all the elements of the state dictionary will be restored as attributes. Passively if `set_attribute = False` (like pickle). Actively if `set_attribute=True` or `set_attribute=[your object's class]`, with call of setters (in alphabetic order if `sort_keys=True` or in random order if `sort_keys=False`).

                .. warning::

                    You must make sure to have all the needed information in the state and not in the `__init__` args that will be discarded when updating.
                    See documentation section: ref:`"If you want to make the object updatable"<updatable-note-label>`.



        Return:
            created object or updated object if passed obj.
        """
        return self.__call__(fp_or_s=s, obj=obj)

    def set_default_value(self, value):
        """
        Set the value returned if the path passed to load doesn't exist.
        It allows to have a default object at the first run of the script or
        when the json has been deleted.
        """
        self.default_value = value

    def set_authorized_classes(self, classes):
        """
        Define the classes that serializejson is authorized to recreate from
        the `__class__` keywords in json, in addition to the usuals classes.
        Usual classes are : complex ,bytes, bytearray, Decimal, type, set,
        frozenset, range, slice, deque,  datetime, timedelta, date, time
        numpy.array, numpy.dtype.
        authorized_classes must be a liste of classes or strings
        corresponding to the qualified names of classes (`module.class_name`).
        If the loading json contain an unauthorized  `__class__`,
        serializejson will raise a TypeError exception.

        .. warning::

            Do not load serializejson files from untrusted / unauthenticated
            sources without carefully set the `authorized_classes` parameter.
            Never authorize "eval", "exec", "apply" or other functions or
            classes which could allow execution of malicious code
            with for example :
            ``{"__class__":"eval","__init__":"do_bad_things()"}``
        """
        self._authorized_classes_strs = _get_authorized_classes_strings(classes)

    def set_recognized_classes(self, classes):
        """
        Set the classes (string with qualified name or classes) that
        serializejson will try to recognize from key names.
        """
        self._class_from_attributes_names = _get_recognized_classes_dict(classes)

    def set_updatables_classes(self, updatables):
        """
        Set the classes (string with qualified name or classes) that
        serializejson will try to update if already in the provided object `obj` when loading with `load` or `loads`.
        Otherwise the objects are recreated.
        """
        updatableClassStrs = set()
        for updatable in updatables:
            if isinstance(updatable, str):
                updatableClassStrs.add(updatable)
            else:
                updatableClassStrs.add(classStrFromClass(updatable))
        self.updatableClassStrs = updatableClassStrs

    def start_object(self):
        dict_ = dict()
        if (
            self.root is None and self.json_startswith_curly
        ):  # en vrai c'est pas forcement le root ,si par exeple le root est une liste ...
            self.root = dict_
        if self._updating:
            id_ = id(dict_)
            self.ancestors.append(id_)
        return dict_

    def end_object(self, inst):
        self._counter += 1
        # self._deserializeds.add()
        if self._updating:
            self.ancestors.pop()  # se retire lui meme
        class_str = inst.get("__class__", None)
        if class_str:
            if class_str == "serializeJson.from_name":
                # inst["devrait"] = "pas etre là" #permetait de verifier que le dictionnaire a bien été remplacé par un objet
                if self.root:
                    try:
                        inst_potential = from_name(
                            inst["__init__"], accept_dict_as_object=True, root=self.root
                        )  # essaye de remplacer tout de suite si possible
                        if (not type(inst_potential) is dict) or (
                            "__class__" not in inst_potential
                        ):  # verifi que ce n'est pas un objet qui n'a pas encore été recré
                            return inst_potential
                    except:
                        pass
                self.duplicates_to_replace.append(inst)
            elif self._updating:
                if class_str in self.updatableClassStrs:
                    ancestor = self.ancestors[-1]
                    self.node_has_descendants_to_recreate.add(ancestor)
                else:
                    return self._exploreDictToReCreateObjects(
                        inst
                    )  # idealement faudrait pouvoir eviter d'explorer, et aller directement rédydrater les descendant , le problème c'est que l'hydrattation n'est pas in place et les objet qui les contiennent de vont pas avoir leur champs mis à jour ... ex dans une liste
            else:
                return self._inst_from_dict(inst)
        # pour reconnaissant d'objet juste à partir des attributes
        elif self._class_from_attributes_names:
            class_from_attributes_names = self._class_from_attributes_names
            attributes_tuple = tuple(sorted(inst.keys()))
            if attributes_tuple in class_from_attributes_names:
                inst["__class__"] = class_from_attributes_names[attributes_tuple]
                recognized = True
            else:
                attributes_set = set(attributes_tuple)
                for attribute_names in class_from_attributes_names.keys():
                    if attributes_set.issuperset(attribute_names):
                        inst["__class__"] = class_from_attributes_names[attribute_names]
                        recognized = True
                        break
                else:
                    recognized = False
            if recognized:
                if self._updating:
                    if inst["__class__"] in self.updatableClassStrs:
                        ancestor = self.ancestors[-1]
                        self.node_has_descendants_to_recreate.add(ancestor)
                    else:
                        return self._exploreDictToReCreateObjects(
                            inst
                        )  # idealement faudrait pouvoir eviter d'explorer, et aller directement rédydrater les descendant , le problème c'est que l'hydrattation n'est pas in place et les objet qui les contiennent de vont pas avoir leur champs mis à jour ... ex dans une liste
                else:
                    return instance(
                        **inst
                    )  # pas de verification les objets recognized sont considérés comme authorized  #self._inst_from_dict(inst)
        return inst

    def __call__(self, fp_or_s, obj=None):
        """
        Args:
            fp(str,file-like): file-like or path of the file containing the JSON to be decoded
            s (str,bytes)    : either str or bytes (UTF-8) containing the JSON to be decoded
            obj              : object to update (optional)


        Returns:
            a python value

        examples:
            >>> decoder = Decoder()
            >>> decoder('"€ 0.50"')
            '€ 0.50'
            >>> decoder(b'"\xe2\x82\xac 0.50"')
            '€ 0.50'
            >>> decoder(io.StringIO('"€ 0.50"'))
            '€ 0.50'
            >>> decoder(io.BytesIO(b'"\xe2\x82\xac 0.50"'))
            '€ 0.50'
        """
        blosc.set_nthreads(blosc.ncores)
        serialize_parameters.set_attributes = self.set_attributes
        self.converted_numpy_array_from_lists = set()
        self._counter = 0
        self._updating = False
        # for duplicates -----------
        self.root = None
        if isinstance(fp_or_s, str):
            self.json_startswith_curly = fp_or_s.startswith("{")
        else:
            self.json_startswith_curly = fp_or_s.read(1) == "{"
            fp_or_s.seek(0)

        self.duplicates_to_replace = []
        if obj is None:
            self._updating = False
            loaded = rapidjson.Decoder.__call__(self, fp_or_s, chunk_size=self.chunk_size)
        else:  # update
            self._updating = True
            self.ancestors = deque()
            self.ancestors.append(None)
            self.node_has_descendants_to_recreate = set()
            loaded_dict = rapidjson.Decoder.__call__(self, fp_or_s, chunk_size=self.chunk_size)
            loaded = self._exploreToUpdate(obj, loaded_dict)
        # on restaure doublons qu'on a pu restaurer pendant deserialisation (dans une liste ou doublon referencant un parent)
        duplicates_to_replace = self.duplicates_to_replace
        while duplicates_to_replace:
            duplicate_to_replace = duplicates_to_replace.pop()
            for parent in gc.get_referrers(duplicate_to_replace):
                if type(parent) is dict:
                    for key, value in parent.items():
                        if value == duplicate_to_replace:
                            parent[key] = from_name(value["__init__"], accept_dict_as_object=True, root=loaded)
                            break
                elif type(parent) is list:
                    for key, value in enumerate(parent):
                        if value == duplicate_to_replace:
                            parent[key] = from_name(value["__init__"], accept_dict_as_object=True, root=loaded)
                            break
        # clean ---------------
        del self.duplicates_to_replace
        if self._updating:
            del self.ancestors
            del self.node_has_descendants_to_recreate
            self._updating = False
        if obj is not None:
            return obj
        return loaded

    def __iter__(self):
        self._updating = False
        fp = self.fp
        if isinstance(fp, str):
            if not os.path.exists(fp):
                return [self.default_value]
            self.fp_iter = _json_object_file_iterator(fp, mode="rb")
        else:
            raise Exception("not yet able to load_iter on %s" % str(type(fp)))
        return self

    def _inst_from_dict(self, inst):
        class_str = inst["__class__"]
        if class_str in self._authorized_classes_strs:
            if class_str in remove_add_braces:
                inst["__init__"] = (inst["__init__"],)
            if (
                self.numpy_array_from_list
                and "__init__" in inst
                and isinstance(inst["__init__"], numpy.ndarray)
                and id(inst["__init__"]) in self.converted_numpy_array_from_lists
            ):
                inst["__init__"] = inst["__init__"].tolist()
            return instance(**inst)
        raise TypeError("%s is not in authorized_classes" % inst["__class__"])

    def _exploreToUpdate(self, obj, loaded_node):

        # gère le cas où loaded_node est un dictionnaire ----------------------
        if isinstance(loaded_node, dict):
            obj_keys = None  # plutot que set vide un objet peut ne pas avoir d'attributes ni de slots initialisés
            if isinstance(obj, dict) and ("dict" in self.updatableClassStrs):
                is_dict = True
                obj_keys = set(obj)
                obj
            else:  # s'assure que c'est une instance
                is_dict = False
                class_str = loaded_node.get("__class__")
                if (
                    (class_str is not None)
                    and (class_str in self.updatableClassStrs)
                    and (class_str == classStrFromClass(obj.__class__))
                ):
                    if class_str == "set":
                        # on peut udpate le set MAIS PAS LES OJECTS QUI SONT DEDANS !!!! car on ne sait pas quel existant correspond à quel element json
                        obj.clear()
                        obj.update(self._exploreDictToReCreateObjects(loaded_node))
                        return obj
                    if hasattr(obj, "__setstate__"):
                        # j'ai du remplacer hasMethod(inst,"__setstate__") par hasattr(inst,"__setstate__") pour pouvoir deserialiser des sklearn.tree._tree.Tree en json "__setstate__" n'est pas reconnu comme étant une methdoe !? alors que bien là .
                        if "__state__" in loaded_node:
                            obj.__setstate__(loaded_node["__state__"])
                        else:
                            loaded_node.__delitem__("__class__")
                            if "__init__" in loaded_node:
                                loaded_node.__delitem__("__init__")
                            obj.__setstate__(loaded_node)
                        return obj
                    if hasattr(obj, "__dict__"):  # A REVOIR : ne marche pas avec les slots
                        obj_keys = set(obj.__dict__)
                    if hasattr(obj, "__slots__"):
                        if obj_keys is None:
                            obj_keys = set()
                        for base_class in obj.__class__.__mro__[
                            :-1
                        ]:  # on ne prend pas le dernier qui est toujours (?) object
                            for slot in getattr(base_class, "__slots__", ()):
                                # on utilise pas directement base_class.__slots__ car une classe de base n'a pas forcement redefinit __slots__
                                if hasattr(obj, slot):
                                    obj_keys.add(slot)
            if obj_keys is not None:
                if not is_dict:

                    set_attributes = serialize_parameters.set_attributes
                    set_attributes = set_attributes is True or (
                        (set_attributes is not False) and (class_str in set_attributes)
                    )

                # update dans le cas où l'objet pré-existant est un objet (avec __dict__ pas encore __slot__) ou un dictionnaire --
                loaded_node_has_descendants_to_recreate = id(loaded_node) in self.node_has_descendants_to_recreate

                # suprime les attributes de l'objet qui ne sont pas dans loaded..
                only_in_obj = obj_keys - set(loaded_node)
                for key in only_in_obj:
                    if not key.startswith("_"):
                        if is_dict:
                            del obj[key]
                        else:
                            obj.__delattr__(key)
                # update ou recrer les autres attributes
                for key, value in loaded_node.items():
                    if key not in ("__class__", "__init__"):
                        if key in obj_keys:
                            if is_dict:
                                old_value = obj[key]
                            else:
                                old_value = obj.__getattribute__(key)
                            value = self._exploreToUpdate(old_value, value)
                        elif loaded_node_has_descendants_to_recreate:
                            if isinstance(value, dict):
                                value = self._exploreDictToReCreateObjects(value)
                            elif isinstance(value, list):
                                value = self._exploreListToReCreateObjects(value)
                        if is_dict:
                            obj[key] = value
                        elif set_attributes:
                            attributeSetmethod = "set_" + key
                            if hasattr(obj, attributeSetmethod):
                                method = obj.__getattribute__(attributeSetmethod)
                                method(value)
                            else:
                                attributeSetmethod = "set" + key[0].upper() + key[1:]
                                if hasattr(obj, attributeSetmethod):
                                    method = obj.__getattribute__(attributeSetmethod)
                                    method(value)
                                else:
                                    obj.__setattr__(key, value)
                        else:
                            obj.__setattr__(key, value)
                return obj
            return self._exploreDictToReCreateObjects(loaded_node)

        # gère le cas où loaded_node est une liste ---------------------------
        if isinstance(loaded_node, list):
            if isinstance(obj, list) and ("list" in self.updatableClassStrs):
                # update dans le cas où l'objet pré-existant est une liste
                len_obj = len(obj)
                del obj[len(loaded_node) :]
                for i, value in enumerate(loaded_node):
                    if i < len_obj and isinstance(value, (list, dict)):
                        obj[i] = self._exploreToUpdate(obj[i], value)
                    else:
                        if isinstance(value, dict):
                            value = self._exploreDictToReCreateObjects(value)
                        elif isinstance(value, list):
                            value = self._exploreListToReCreateObjects(value)
                        obj.append(value)
                return obj
            else:  # sinon replace
                return self._exploreListToReCreateObjects(loaded_node)

        # gère les autres cas
        return loaded_node  # replace

    def _exploreDictToReCreateObjects(self, loaded_node):
        if id(loaded_node) in self.node_has_descendants_to_recreate:
            for key, value in loaded_node.items():
                if isinstance(value, dict):  # and "__class__" in value
                    loaded_node[key] = self._exploreDictToReCreateObjects(value)
                elif isinstance(value, list):
                    loaded_node[key] = self._exploreListToReCreateObjects(value)
        if "__class__" in loaded_node:
            return self._inst_from_dict(loaded_node)
        else:
            return loaded_node

    def _exploreListToReCreateObjects(self, loaded_node):
        for i, value in enumerate(loaded_node):
            if isinstance(value, dict):
                loaded_node[i] = self._exploreDictToReCreateObjects(value)
            elif isinstance(value, list):
                loaded_node[i] = self._exploreListToReCreateObjects(value)
        return loaded_node

    # ---------------------------------

    def _end_array_if_numpy_array_from_list(self, sequence):
        if _onlyOneDimSameTypeNumbers(sequence):
            array = numpy.array(sequence, dtype=type(sequence[0]))
            self.converted_numpy_array_from_lists.add(id(array))
            return array
        if len(sequence) and isinstance(sequence[0], ndarray):
            first_elt = sequence[0]
            first_elt_shape = first_elt.shape
            first_elt_dtype = first_elt.dtype
            if all(
                (isinstance(elt, ndarray) and elt.dtype is first_elt_dtype and elt.shape == first_elt_shape)
                for elt in sequence
            ):
                array = numpy.array(sequence, dtype=first_elt_dtype)
                self.converted_numpy_array_from_lists.add(id(array))
                return array
        return sequence

    def __next__(self):
        try:
            return rapidjson.Decoder.__call__(self, self.fp_iter, chunk_size=self.chunk_size)
        except rapidjson.JSONDecodeError as error:
            self.fp_iter.close()
            if error.args[0] == "Parse error at offset 0: The document is empty.":
                raise StopIteration
            else:
                raise


# ----------------------------------------------------------------------------------------------------------------------------
# --- INTERNES -----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------


default_authorized_classes_strs = set(
    [
        "complex",
        "bytes",
        "bytearray",
        "base64.b64decode",
        "SmartFramework.bytesB64",
        "SmartFramework.bytearrayB64",
        "SmartFramework.numpyB64",
        "serializejson.bytesB64",
        "serializejson.bytearrayB64",
        "serializejson.numpyB64",
        "numpy.array",
        "decimal.Decimal",
        "datetime.datetime",
        "datetime.timedelta",
        "datetime.date",
        "datetime.time",
        "type",
        "set",
        "frozenset",
        "range",
        "slice",
        "collections.deque",
        "numpy.dtype",
        "numpy.frombuffer",
        "blosc.decompress",
    ]
)
if use_numpy:
    _numpy_float_dtypes = set((numpy.dtype("float16"), numpy.dtype("float32"), numpy.dtype("float64")))

    _numpy_types = set(
        (
            numpy.bool_,
            numpy.int8,
            numpy.int16,
            numpy.int32,
            numpy.int64,
            numpy.uint8,
            numpy.uint16,
            numpy.uint32,
            numpy.uint64,
            numpy.float16,
            numpy.float32,
            numpy.float64,
        )
    )
    _numpy_float_types = set(
        (
            numpy.float16,
            numpy.float32,
            numpy.float64,
        )
    )
    _numpy_int_types = set(
        (
            numpy.int8,
            numpy.int16,
            numpy.int32,
            numpy.int64,
            numpy.uint8,
            numpy.uint16,
            numpy.uint32,
            numpy.uint64,
        )
    )

else:
    _numpy_types = set()

NoneType = type(None)
remove_add_braces = {"set", "frozenset", "collections.deque", "tuple"}


def _close_for_append(fp, indent):
    if indent is None:
        try:
            fp.write(b"]")
        except TypeError:
            fp.write("]")
    else:
        try:
            fp.write(b"\n]")
        except TypeError:
            fp.write("\n]")


def _open_for_append(fp, indent):
    length = 0
    if isinstance(fp, str):
        path = fp
        if os.path.exists(path):

            fp = open(path, "rb+")
            # detect encoding
            bytes_ = fp.read(3)
            len_bytes = len(bytes_)
            if len_bytes:
                if bytes_[0] == 0:
                    if bytes_[1] == 0:
                        fp = open(path, "r+", encoding="utf_32_be")
                    else:
                        fp = open(path, "r+", encoding="utf_16_be")
                elif len_bytes > 1 and bytes_[1] == 0:
                    if len_bytes > 2 and bytes_[2] == 0:
                        fp = open(path, "r+", encoding="utf_32_le")
                    else:
                        fp = open(path, "r+", encoding="utf_16_le")
            # remove last ]
            fp.seek(0, 2)
            length = fp.tell()
            if length == 1:
                fp.close()
                raise Exception("serializejson can append only to serialized lists")
            if length >= 2:
                fp.seek(-1, 2)  # va sur le dernier caractère
                lastcChar = fp.read(1)
                if lastcChar in (b"]", "]"):
                    fp.seek(-2, 2)
                    beforlastcChar = fp.read(1)
                    if beforlastcChar in (b"\n", "\n"):
                        fp.seek(-2, 2)
                    else:
                        fp.seek(-1, 2)  # va sur le dernier caractère
                    fp.truncate()
                else:
                    fp.close()
                    raise Exception("serializejson can append only to serialized lists")
            # fp = open(path, 'ab')
        else:
            fp = open(path, "wb")
    elif fp is None:
        raise Exception("Incorrect file (file, str ou unicode)")
    if length == 0:
        if indent is None:
            fp.write(b"[")
        else:
            fp.write(b"[\n")
    elif length > 2:
        if indent is None:
            try:
                fp.write(b",")
            except TypeError:
                fp.write(",")
        else:
            try:
                fp.write(b",\n")
            except TypeError:
                fp.write(",\n")
    return fp


def _open_with_good_encoding(path):
    # https://stackoverflow.com/questions/4990095/json-specification-and-usage-of-bom-charset-encoding/38036753
    fp = open(path, "rb")
    bytes_ = fp.read(3)
    fp.seek(0)
    len_bytes = len(bytes_)
    if len_bytes:
        if (
            bytes_ == b"\xef\xbb\xbf"
        ):  # normalement ne devrait pas arriver les json ne devraient jamais commencer par un BOM , mais parfoit si le fichier à été créer à la main dans un editeur de text, il peut y'en avoir un (exemple : personnel.json ).
            fp = open(path, "r", encoding="utf_8_sig")
        elif bytes_[0] == 0:
            if bytes_[1] == 0:
                fp = open(path, "r", encoding="utf_32_be")
            else:
                fp = open(path, "r", encoding="utf_16_be")
        elif len_bytes > 1 and bytes_[1] == 0:
            if len_bytes > 2 and bytes_[2] == 0:
                fp = open(path, "r", encoding="utf_32_le")
            else:
                fp = open(path, "r", encoding="utf_16_le")
    return fp


def _get_authorized_classes_strings(classes):
    if not isinstance(classes, set):
        if isinstance(classes, (list, tuple)):
            classes = set(classes)
        else:
            classes = set([classes])
    _authorized_classes_strs = default_authorized_classes_strs.copy()
    for elt in classes:
        if not isinstance(elt, str):
            elt = classStrFromClass(elt)
        _authorized_classes_strs.add(elt)
    return _authorized_classes_strs


def _get_recognized_classes_dict(classes):
    if classes is None:
        return dict()
    if not isinstance(classes, (list, tuple)):
        classes = [classes]
    else:
        classes = classes
    _class_from_attributes_names = dict()
    for class_ in classes:
        if isinstance(class_, str):
            classToRecStr = class_
            classToRecClass = classFromClassStr(class_)
        else:
            classToRecStr = classStrFromClass(class_)
            classToRecClass = class_
        instanceVide = classToRecClass()
        serializedattributes = tuple(
            sorted([attribute for attribute in instanceVide.__dict__.keys() if not attribute.startswith("_")])
        )
        _class_from_attributes_names[serializedattributes] = classToRecStr
    return _class_from_attributes_names


class _json_object_file_iterator(io.FileIO):
    def __init__(self, fp, mode, **kwargs):
        io.FileIO.__init__(self, fp, mode=mode, **kwargs)
        self.in_quotes = False
        self.in_curlys = 0
        self.in_squares = 0
        self.in_simple = False
        self.in_object = False
        self.backslash_escape = False
        self.shedule_break = False
        self.in_chunk_start = 0
        self.s = None
        # s = io.FileIO.read(self, 1)
        # if s not in (b"[", "["):
        #    raise Exception('the json data must start with "["')
        if "b" in mode:
            self.interesting = set(b'\\"{}[]')
            self.separators = set(b", \t\n\r")
            self.chars = list(b'\\"{}[]')
        else:
            self.interesting = set('\\"{}[]')
            self.separators = set(", \t\n\r")
            self.chars = list('\\"{}[]')

    def read(self, size=-1):
        if self.shedule_break:
            self.shedule_break = False
            # print("read(1): empty")
            return ""
        (
            backslash,
            doublecote,
            curly_open,
            curly_close,
            square_open,
            square_close,
        ) = self.chars
        interesting = self.interesting
        separators = self.separators
        in_quotes = self.in_quotes
        in_curlys = self.in_curlys
        in_squares = self.in_squares
        in_simple = self.in_simple
        in_object = self.in_object
        backslash_escape = self.backslash_escape  # true if we just saw a backslash
        in_chunk_start = self.in_chunk_start
        if in_chunk_start == 0:
            s = self.s = io.FileIO.read(self, size)
        else:
            s = self.s
        for i in range(in_chunk_start, len(s)):
            ch = s[i]
            if in_simple:
                if ch in separators or ch in ("]", 93):
                    if in_chunk_start < i:
                        self.shedule_break = True  # on prevoit d'arreter au read suivant sinon , va de tout facon arreter et on ne pourra pas remeter self.shedule_break à False
                    # self.seek(chunk_start + i + 1)
                    self.in_chunk_start = (i + 1) % len(s)
                    self.in_quotes = False
                    self.in_curlys = 0
                    self.in_squares = in_squares
                    self.in_simple = False
                    self.in_object = False
                    # print("read(2): ",s[in_chunk_start:i])
                    return s[in_chunk_start:i]
            elif ch in interesting:
                check = False
                if in_quotes:
                    if backslash_escape:
                        # we must have just seen a backslash; reset that flag and continue
                        backslash_escape = False
                    elif ch == backslash:  # \
                        backslash_escape = True  # we are in a quote and we see a backslash; escape next char
                    elif ch == doublecote:
                        in_quotes = False
                        check = True  # signale qu'on sort d'un truc et qu'il faudra checker
                elif ch == doublecote:  # "
                    in_quotes = True
                    in_object = True
                elif ch == curly_open:  # {
                    in_curlys += 1
                    in_object = True
                elif ch == curly_close:  # }
                    in_curlys -= 1
                    check = True
                elif ch == square_open:  # [
                    in_squares += 1
                    if in_squares > 1:
                        in_object = True
                    else:
                        in_chunk_start = (i + 1) % len(s)
                elif ch == square_close:  # ]
                    in_squares -= 1
                    check = True
                    if not in_squares:  # on a ateint la fin de la liste json
                        return ""
                if check and not in_quotes and not in_curlys and in_squares < 2:
                    if in_chunk_start < (i + 1):
                        self.shedule_break = True  # on prevoit d'arreter au read suivant sinon , va de tout facon arreter et on ne pourra pas remeter self.shedule_break à False
                    # self.seek(chunk_start + i + 1)
                    self.in_chunk_start = (i + 1) % len(s)
                    self.in_quotes = False
                    self.in_curlys = False
                    self.in_squares = in_squares
                    self.in_simple = False
                    self.in_object = False
                    # print("read(3): ",s[in_chunk_start: i + 1])
                    return s[in_chunk_start : i + 1]
            elif not in_object:
                if ch in separators:
                    in_chunk_start = i + 1
                else:
                    in_simple = True
        self.in_quotes = in_quotes
        self.in_curlys = in_curlys
        self.in_squares = in_squares
        self.in_simple = in_simple
        self.in_object = in_object
        self.backslash_escape = backslash_escape
        self.in_chunk_start = 0
        if in_chunk_start:
            # print("read(4): ",s[in_chunk_start:])
            return s[in_chunk_start:]
        return s
