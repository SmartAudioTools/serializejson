"""**serializejson** is a python library for serialization and deserialization of complex Python objects in 
`JSON <http://json.org>`_ build upon `python-rapidjson <https://github.com/python-rapidjson/python-rapidjson>`_ and `pybase64 <https://github.com/mayeut/pybase64>`_

	⚠ **serializejson can execute arbitrary Python code if the load parameter autorized_classes is "all" when loading json. 
	Do not load serializejsons from untrusted / unauthenticated sources without carfuly set the autorized_classes parameter.**

- supports Python 3.7 (maybe lower) or greater.
- serializes arbitrary python objects into a dictionary by adding "__class__" ,and eventually "__init__" and "__state__" keys. 
- serializes and deserializes bytes and bytearray very quickly in base64 tanks to `pybase64 <https://github.com/mayeut/pybase64>`_.
- calls the same objects methods as pickle. Therefore almost all pickable objects are serializable with serializejson without any modification.
- serialized objects are human-readable. Your datas will never be unreadable if your code evolved, you will always be able to modify your datas with a text editor, unlike with pickle.
- serialized objects take generally less space than with pickle and just a little 30% more if big binaries data (numpy array, bytes, bytearray)
- only two times slower than pickle and much faster than jsonpickle.
- can safely load untrusted / unauthenticated sources if autorized_classes list parameter is set carefully with strictly necessary objects (unlike pickle).
- can update existing objects recursively instead of override them (serializejson can be used to save and restore in place a complete application state).
- filters attribute starting with "_" by default (unlike pickle).
- numpy arrays can be serialized in list with automatique conversion in both ways or in a conservative way. 
- supports circular references and serialize only once duplicated objects (WARNING :not yet if the object is a list or dictionary).
- try to call attribute setters and properties setters when loading if set_attributs  = True.
- accepts json with comment (// and /* */).
- can automatically recognize objects in json from keys names and recreate them, without the need of "__class__" key, if passed in recognized_classes. It allows loading foreign json serialized with others libraries who only save objects attributes. 
- dumps and loads support string path. 
- can iteratively encode (with append) and decode (with iterator) a list in json, saving memory space during the process of serialization et deserialization.
- WARNING : tuple, time.struct_time, collections.Counter, collections.OrderedDict, collections.defaultdict, namedtuples and dataclass are not yet correctly serialized 




"""


from SmartFramework.tools.dictionnaires import filtered
try:
    import importlib.metadata as importlib_metadata
except : 
    import importlib_metadata
try:
	__version__ = importlib_metadata.version('serializejson')
except : 
	pass
import os
import io
import sys
from collections import deque
import rapidjson
#from typing import TextIO,BinaryIO
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
from SmartFramework.serialize import serializeParameters


__all__ = ['dumps', 'dump', 'loads', 'load', 'append', 'Encoder', 'Decoder']


#not_duplicates_types = set([type(None), bool, int, float, str])


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


# --- FONCTIONS BASED API ----------------------

from .tools import (
    instance,
    tupleFromInstance,
    classStrFromClass,
    encodedB64,
    classFromClassStr,
    from_name,
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
    Dump object into json file. 
    
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
    Append object into json file. 
    
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
    Load object from json string. 
    
    Args: 
        s: 
            the json string.
        obj (optional):
            the obj will be update instead of the creation of a new object.
        iterator: 
            if True and the json corespond to a list. Items are read one by one saving RAM.
        **argsDict: 
            parameters passed to the Decoder (see documentation).
        
    Return:
        created object, updated object if passed obj or elements iterator if iterator is True.
    """
    decoder = Decoder(**argsDict)
    if iterator:
        return decoder
    else:
        return decoder(fp_or_s=s, obj=obj)


def load(fp, *, obj=None, iterator=False, **argsDict):
    """
    Load object from json file. 
    
    Args: 
        fp (str or file-like): 
            the json file.
        obj (optional):
            the obj will be update instead of the creation of a new object.
        iterator: 
            if True and the json corespond to a list. Items are read one by one saving RAM.
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
            and  you will not have to pass it to the dump() methode later. 
        
        attributs_filter:
            objects attributs starting with attributs_filter will not be 
            serialized. ("_" by default).
        
        ensure_ascii: 
            whether non-ascii str are dumped with escaped unicode or utf-8.
        
        indent (None, int or '\\\\t'): 
            indentation width to produce pretty printed JSON.
            None: Json in one line (quicker than with indent).
            int: new lines and int spaces for indent.
            '\\\\t': new lines and tabulations for indent
            (take less space than int > 1).
       
        
        single_line_init:
            whether __init__ must be serialize in one line.
        
        single_line_list_numbers:
            whether list of numbers must be serialize in one line.
        
        sort_keys:    
            whether dictionary keys should be sorted alphabetically.
            
        chunk_size: 
            write the stream in chunks of this size at a time.
            
    
        bytearray_use_bytearrayB6 : 
            save bytearray with referencies to serializejson.bytearrayB64
            instead of verbose use of base64.b64decode. It save space but make 
            the json file dependent of the serializejson module. 
        
        numpy_array_use_numpyB64 : 
            save numpy arrays with referencies to serializejson.numpyB64
            instead of verbose use of base64.b64decode. It save space but make 
            the json file dependent of the serializejson module. 
            
        numpy_array_readable_max_size : 
            numpy array of smaler size will be serialized in readable decimals. 

        numpy_array_to_list : 
            whether numpy array should be serialized as list. 
          
            .. warning::

                Use it only for interoperability with other json libraries 
                Because numpy arrays will be indistinctable from list.
                Decoder(numpy_array_from_list=True) will be able to 
                recreate numpy array but but with the the risque of unwanted
                convertion of lists to numpy arrays. 
            
        numpy_types_to_python_types:
             wheter numpy ints ans floats must be convert to python types.
             It save space and generaly don't 

    """
    """
    
        bytes_to_string:
            whether bytes must be dumped in string after utf-8 decode.
        skip_invalid_keys (bool) : 
            whether invalid dict keys will be skipped.

        number_mode (int) : 
            enable particular behaviors in handling numbers.

        datetime_mode (int) :  
            how should datetime, time and date instances be handled.

        uuid_mode (int) :  
            how should UUID instances be handled.

        write_mode : 
            WM_COMPACT:that produces the most compact JSON representation.
            WM_PRETTY: it will use RapidJSON's PrettyWriter.
            WM_single_line_list_numbers: arrays will be kept on a single line.
            
        bytes_mode : 
            BM_UTF8
            BM_NONE
    """
    def __new__(
        cls,
        fp=None,
        *,
        attributs_filter="_",
        ensure_ascii=False,
        indent="\t",
        single_line_init=True,
        single_line_list_numbers=True,
        sort_keys=True,
        chunk_size=65536,
        bytearray_use_bytearrayB6=True,
        numpy_array_use_numpyB64=True,
        numpy_array_readable_max_size=0,
        numpy_array_to_list=False,
        numpy_types_to_python_types=True,
        #add_id:bool=False,
        #**argsDict
    ):
 

        #if not bytes_to_string:
        #   bytes_mode = rapidjson.BM_NONE
        #else:
        #    bytes_mode = rapidjson.BM_UTF8
        self = super().__new__(
            cls,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            bytes_mode=rapidjson.BM_NONE,
            #**argsDict
        )
        self.attributs_filter = attributs_filter
        self.fp = fp
        #self.kargs = argsDict
        if indent is None:
            self.single_line_list_numbers = False
            self.single_line_init = False
        else:
            self.single_line_list_numbers = single_line_list_numbers
            self.single_line_init = single_line_init
        self.indent = indent # rapid json enregistre self.indent_char et self.indent_count , mais ne permet pas de savoir si indent = None ...
        self.dumped_classes = set()
        self.chunk_size = chunk_size
        self.bytearray_use_bytearrayB6 = bytearray_use_bytearrayB6
        self.numpy_array_to_list = numpy_array_to_list
        self.numpy_array_use_numpyB64 = numpy_array_use_numpyB64
        self.numpy_array_readable_max_size = numpy_array_readable_max_size
        self.numpy_types_to_python_types = numpy_types_to_python_types
        return self

    def dump(self, obj, fp=None):
        """
        Dump object into json file. 
        
        Args: 
            obj: object to dump.
            fp (optional str or file-like): path or file, the object will be 
                dumped into this file instead into the file passed at Encoder constructor.
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
            fp (optional str or file-like): path or file, the object will be 
                dumped into this file instead into the file passed at Encoder 
                constructor.The file must be empty or containing a json list. 
         """
        if fp is None:
            fp = self.fp
        fp = _open_for_append(fp, self.indent)
        rapidjson.Encoder.__call__(self, obj, stream=fp, chunk_size=self.chunk_size)
        _close_for_append(fp, self.indent)

    def get_dumped_classes(self):
        """
        Return the all dumped classes. 
        In order to reuse them as autorize_classes when loading.
        """
        return self.dumped_classes

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
            return inst.decode("ascii")
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
                            ensure_ascii=False,
                            sort_keys=self.sort_keys,
                            bytes_mode=self.bytes_mode,
                            #**self.kargs
                        )
                    ),
                }
        elif use_numpy and type_inst is ndarray and self.numpy_array_to_list:
            if not self.single_line_list_numbers:
                return inst.tolist()
            if inst.ndim == 1:
                return rapidjson.RawJSON(rapidjson.dumps(inst.tolist()))
            return [rapidjson.RawJSON(rapidjson.dumps(elt.tolist())) for elt in inst]  # inst.tolist()
        dic = self._dict_from_instance(inst)
        initArgs = dic.get("__init__", None)
        if initArgs is not None and self.single_line_init:  # and  dic["__class__"] in  _oneline_init_classess :
            dic["__init__"] = rapidjson.RawJSON(
                rapidjson.dumps(
                    initArgs,
                    default=self._default_one_line,
                    ensure_ascii=self.ensure_ascii,
                    sort_keys=self.sort_keys,
                    bytes_mode=self.bytes_mode,
                    #**self.kargs
                )
            )
        if self.single_line_list_numbers:
            for key, value in dic.items():
                if (
                    key != "__class__"
                    and key != "__init__"
                    and type(value) in (list, tuple)
                    and _onlyOneDimNumbers(value)
                ):

                    dic[key] = rapidjson.RawJSON(
                        rapidjson.dumps(
                            value,
                            default=self._default_one_line,
                            bytes_mode=self.bytes_mode,
                            #**self.kargs
                        )
                    )
        self._already_serialized_id_dic_to_obj_dic[id(dic)] = (
            inst,
            dic,
        )  # important de metre dic avec sinon il va être detruit et son identifiant va être réutilisé ..
        #if self.add_id:
        #    dic["_id"] = id_
        return dic
        # raise TypeError('%r is not JSON serializable' % inst)

    def _default_one_line(self, inst):
        type_inst = type(inst)
        if type_inst is encodedB64:
            return inst.decode("ascii")
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
            # return rapidjson.RawJSON(rapidjson.dumps(inst.tolist(), bytes_mode=dump_bytes_mode))
            return inst.tolist()
        return self._dict_from_instance(inst)

    def _dict_from_instance(self, inst):
        classe, initArgs, state = tupleFromInstance(inst)
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
        if (
            type(obj) in (list, tuple)
            and self.single_line_list_numbers
            and _onlyOneDimNumbers(obj)
        ):
            return rapidjson.dumps(
                obj,
                default=self._default_one_line,
                bytes_mode=self.bytes_mode,
                #**self.kargs
            )
        serializeParameters.attributs_filter = self.attributs_filter
        serializeParameters.numpy_array_use_numpyB64 = self.numpy_array_use_numpyB64
        serializeParameters.numpy_array_readable_max_size = self.numpy_array_readable_max_size        
        serializeParameters.bytearray_use_bytearrayB6 = self.bytearray_use_bytearrayB6
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
    Decoder for load objects serialized in json files or strings.
    
    Args:
        fp (string or file-like) : 
            Path or file-like object containing the json. 
            When specified, the decoder will read from this file,
            and  you will not have to pass it to the load() methode later. 
            
        autorized_classes (None,list or "all"):
            List of classes (string with qualified name or classes) that
            serializejson is allowed to recreate from the __class__ 
            keyword in json. Otherwise the object will stay a dictonnary.   
            None : no class are recreated.
            []: only usual classes are recreated.
            [classe1,classe2]:usual classes and classe1,classe2 are recreated.
            "all": alls classes will be recreated with no verifications.\n
            .. warning::
                
                Do not load serializejsons from untrusted / unauthenticated 
                sources without carfuly set the autorized_classes parameter. 
                serializejson can execute arbitrary Python code if the load 
                parameter autorized_classes is "all" when loading json for 
                exemple with json containing 
                ``{"__class__":"eval","__init__":"do_anything()"}``\n
                use "all" only briefly when you are developping and you are 
                absolutly confident on your json files. 
                Never forget to remove it.                   
                

        recognized_classes (list):
            List of classes (string with qualified name or classes) that
            serializejons will try to recognize from keys names . 
            
        updatables_classes (list):
            List of classes (string with qualified name or classes) that
            serializejson will try to upadate if already in the passed obj.
            Otherwise the objects are recreated.
            
        set_attributs (bool):
            Whether load will try to call set_xxx or setXxx methodes 
            or xxx property setter for each attributs of serialized objects
            if the object as no __setstate__ methode.
            
        accept_comments (bool):
            Whether serializejson accept to parse json with comments  
        
        numpy_array_from_list (bool):
            Whether list of int or floats wich are loaded into numpy arrays.
        
        default_value : 
            The value returned if the path passed to load doesn't exist. 
            if allow to have a default objet at the first script run or 
            when the json has been deleted. 
        
        chunk_size (int):
            Chunk_size for the json file read.

            

    """
    """
        Herited from rapidjson.Decoder:

        number_mode (int) : Enable particular behaviors in handling numbers
        datetime_mode (int) : How should datetime, time and date instances be handled
        uuid_mode (int) : How should UUID instances be handled
        parse_mode (int) : Whether the parser should allow non-standard JSON extensions (nan, -inf, inf )
    """
    def __new__(
        cls,
        fp=None,
        *,
        autorized_classes=[],
        recognized_classes=[],
        updatables_classes=[],
        set_attributs=True,
        accept_comments=False,
        numpy_array_from_list=False,
        default_value=None,
        chunk_size=65536,
        #**argsDict
    ):
       
        if accept_comments:
            parse_mode = rapidjson.PM_COMMENTS
        else:
            parse_mode = rapidjson.PM_NONE
        self = super().__new__(cls, parse_mode=parse_mode)#, **argsDict)
        self.fp = fp
        self.set_attributs = set_attributs
        self._autorized_classes_strs = _get_autorized_classes_strings(autorized_classes)
        self._class_from_attributs_names = _get_recognized_classes_dict(recognized_classes)
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
                the object will be loaded from this file instead of from the 
                file passed at Decoder constructor.
            obj (optional):
                the obj will be update instead of the creation of a new object.
            
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
                the obj will be update instead of the creation of a new object.
           
        Return:
            created object or updated object if passed obj.
        """
        return self.__call__(fp_or_s=s, obj=obj)

    def set_default_value(self, value):
        """
        set the value returned if the path passed to load doesn't exist. 
        if allow to have a default objet at the first script run or 
        when the json has been deleted.   
        """
        self.default_value = value
        
    def set_autorized_classes(self, classes):
        """
        Set the classes (string with qualified name or classes) that
        serializejson is allowed to recreate from the __class__ 
        keyword in json. Otherwise the object will stay a dictonnary.   
        None : no class are recreated.
        []: only usual classes are recreated.
        [classe1,classe2]:usual classes and classe1,classe2 are recreated.
        "all": alls classes will be recreated with no verifications.\n

        .. warning::
                
                Do not load serializejsons from untrusted / unauthenticated 
                sources without carfuly set the autorized_classes parameter. 
                serializejson can execute arbitrary Python code if the load 
                parameter autorized_classes is "all" when loading json for 
                exemple with json containing 
                ``{"__class__":"eval","__init__":"do_anything()"}``\n
                use "all" only briefly when you are developping and you are 
                absolutly confident on your json files. 
                Never forget to remove it.         

        """
        self._autorized_classes_strs = _get_autorized_classes_strings(classes)

    def set_recognized_classes(self, classes):
        """
        Set the classes (string with qualified name or classes) that
        serializejons will try to recognize from keys names . 
        """
        self._class_from_attributs_names = _get_recognized_classes_dict(classes)


    def set_updatables_classes(self, updatables):
        """
        Set the classes (string with qualified name or classes) that
        serializejson will try to upadate if already in the passed obj.
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
        classStr = inst.get("__class__", None)
        if classStr:
            if classStr == "serializeJson.from_name":
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
                if classStr in self.updatableClassStrs:
                    ancestor = self.ancestors[-1]
                    self.node_has_descendants_to_recreate.add(ancestor)
                else:
                    return self._exploreDictToReCreateObjects(
                        inst
                    )  # idealement faudrait pouvoir eviter d'explorer, et aller directement rédydrater les descendant , le problème c'est que l'hydrattation n'est pas in place et les objet qui les contiennent de vont pas avoir leur champs mis à jour ... ex dans une liste
            else:
                return self._inst_from_dict(inst)
        # pour reconnaissant d'objet juste à partir des attributs
        elif self._class_from_attributs_names:
            class_from_attributs_names = self._class_from_attributs_names
            attributs_tuple = tuple(sorted(inst.keys()))
            if attributs_tuple in class_from_attributs_names:
                inst["__class__"] = class_from_attributs_names[attributs_tuple]
                recognized = True
            else:
                attributs_set = set(attributs_tuple)
                for attribut_names in class_from_attributs_names.keys():
                    if attributs_set.issuperset(attribut_names):
                        inst["__class__"] = class_from_attributs_names[attribut_names]
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
                    )  # pas de verification les objets recognized sont considérés comme autorized  #self._inst_from_dict(inst)
        return inst

    def __call__(self, fp_or_s, obj=None):
        """
        Args:
            fp(str,file-like):  file-like  or  path of the file containing the JSON to be decoded
            s (str,bytes)    : either str or bytes (UTF-8)  containing the JSON to be decoded
            obj              :  object to update (optional)


        Returns:
            a Python value

        Exemples :
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
        serializeParameters.set_attributs = self.set_attributs
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
        if self._autorized_classes_strs == "all" or class_str in self._autorized_classes_strs:
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
        raise TypeError("%s is not in autorized_classes" % inst["__class__"])

    def _exploreToUpdate(self, obj, loaded_node):

        # gère le cas où loaded_node est un dictionnaire ----------------------
        if isinstance(loaded_node, dict):
            obj__dict__ = None
            if hasattr(obj, "__dict__"):  # A REVOIR : ne marche pas avec les slots
                classStr = loaded_node.get("__class__")
                if (
                    (classStr is not None)
                    and (classStr in self.updatableClassStrs)
                    and (classStr == classStrFromClass(obj.__class__))
                ):
                    obj__dict__ = obj.__dict__
            elif isinstance(obj, dict) and ("dict" in self.updatableClassStrs):
                obj__dict__ = obj
            if obj__dict__:
                # update dans le cas où l'objet pré-existant est un objet (avec __dict__ pas encore __slot__) ou un dictionnaire --
                loaded_node_has_descendants_to_recreate = id(loaded_node) in self.node_has_descendants_to_recreate
                # suprime les attributs de l'objet qui ne sont pas dans loaded..
                only_in_obj = set(obj__dict__) - set(loaded_node)
                for key in only_in_obj:
                    if not key.startswith("_"):
                        del obj__dict__[key]
                for key, value in loaded_node.items():
                    if key not in ("__class__", "__init__"):
                        if key in obj__dict__:
                            value = self._exploreToUpdate(obj__dict__[key], value)
                        elif loaded_node_has_descendants_to_recreate:
                            if isinstance(value, dict):
                                value = self._exploreDictToReCreateObjects(value)
                            elif isinstance(value, list):
                                value = self._exploreListToReCreateObjects(value)
                        obj__dict__[key] = value
                return obj
            classStr = loaded_node.get("__class__")
            if (classStr in self.updatableClassStrs) and (classStr == classStrFromClass(obj.__class__)):
                if classStr == "set":
                    obj.clear()
                    obj.update(self._exploreDictToReCreateObjects(loaded_node))
            else:  # sinon remplace
                return self._exploreDictToReCreateObjects(loaded_node)

        # gère le cas où loaded_node est une liste  ---------------------------
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
        """This is called, if implemented, when a JSON array has been completely parsed, and can be used replace it with an arbitrary different value:

        Args:
            sequence : an instance implement the mutable sequence protocol

        Returns:
            a new value

        Exemples :
            >>> class TupleDecoder(Decoder):
            ...   def end_array(self, a):
            ...     return tuple(a)
            ...
            >>> td = TupleDecoder()
            >>> res = td('[{"one": [1]}, {"two":[2,3]}]')
            >>> isinstance(res, tuple)
            True
            >>> res[0]
            {'one': (1,)}
            >>> res[1]
            {'two': (2, 3)}
        """
        if len(sequence):
            if isinstance(sequence[0], int):
                dtype = int
            elif isinstance(sequence[0], float):
                dtype = float
            elif isinstance(sequence[0], numpy.ndarray):
                dtype = sequence[0].dtype
            else:
                return sequence
            try:
                array = numpy.array(sequence, dtype=dtype)
                self.converted_numpy_array_from_lists.add(id(array))
                return array
            except ValueError:
                pass
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
# --- INTERNES  -----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------





default_autorized_classes_strs = set(
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
        "numpy.dtype"
    ]
)
if use_numpy:
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
    _bool_int_and_float_types = set(
        (
            float,
            int,
            bool,
            numpy.bool_,
            numpy.int8,
            numpy.int16,
            numpy.int32,
            numpy.int64,
            numpy.uint8,
            numpy.uint16,
            numpy.uint32,
            numpy.uint64,
            numpy.float32,
            numpy.float64,
        )
    )
else:
    _numpy_types = set()

    _bool_int_and_float_types = set(
        (
            float,
            int,
            bool,
        )
    )
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
                raise Exception("serializeJson can append only to serialized lists")
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
                    raise Exception("serializeJson can append only to serialized lists")
            # fp = open(path, 'ab')
        else:
            fp = open(path, "wb")
    elif fp is None:
        raise Exception("fichier incorrect (file, str ou unicode)")
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


def _get_autorized_classes_strings(classes):

    # if classes == "default":
    #    global _autorized_classes_strs
    #     return _autorized_classes_strs
    if classes is None:
        _autorized_classes_strs = set()
    elif not classes or classes == "default":
        _autorized_classes_strs = default_autorized_classes_strs
    elif classes == "all":
        _autorized_classes_strs = "all"
    else:
        if not isinstance(classes, set):
            if isinstance(classes, (list, tuple)):
                classes = set(classes)
            else:
                classes = set([classes])
        _autorized_classes_strs = default_autorized_classes_strs.copy()
        for elt in classes:
            if not isinstance(elt, str):
                elt = classStrFromClass(elt)
            _autorized_classes_strs.add(elt)
    return _autorized_classes_strs


def _get_recognized_classes_dict(classes):
    if classes is None:
        return dict()
    if not isinstance(classes, (list, tuple)):
        classes = [classes]
    else:
        classes = classes
    _class_from_attributs_names = dict()
    for class_ in classes:
        if isinstance(class_, str):
            classToRecStr = class_
            classToRecClass = classFromClassStr(class_)
        else:
            classToRecStr = classStrFromClass(class_)
            classToRecClass = class_
        instanceVide = classToRecClass()
        serializedAttributs = tuple(
            sorted([attribut for attribut in instanceVide.__dict__.keys() if not attribut.startswith("_")])
        )
        _class_from_attributs_names[serializedAttributs] = classToRecStr
    return _class_from_attributs_names


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
        #s = io.FileIO.read(self, 1)
        #if s not in (b"[", "["):
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
            #print("read(1) : empty")
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
                    #print("read(2): ",s[in_chunk_start:i])
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
                        check = True #signale qu'on sort d'un truc et qu'il faudra checker 
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
                    else  :
                        in_chunk_start = (i + 1) % len(s)
                elif ch == square_close:  # ]
                    in_squares -= 1
                    check = True
                    if not in_squares : # on a ateint la fin de la liste json
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
                    #print("read(3): ",s[in_chunk_start : i + 1])
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
            #print("read(4): ",s[in_chunk_start:])
            return s[in_chunk_start:]
        return s


def _onlyOneDimNumbers(list_or_tuple):
    if len(list_or_tuple):
        type_first = type(list_or_tuple[0])
        if type_first in _bool_int_and_float_types:
            if use_numpy:
                try:
                    # ne suffit pas à s'assurer que tout elements de la meme nature
                    # en effet numpy.array([9, numpy.array([2]), 1]) donne
                    # array([9, 2, 1]) qui a pour dtype "int32"
                    np = numpy.array(
                        list_or_tuple, dtype=type_first
                    )  # type(list_or_tuple[0]) ne pemet pas de retourner True pour [1,math.nan]
                    if np.ndim == 1:
                        return True
                except ValueError:
                    pass
            else:
                return all(isinstance(i, type_first) for i in list_or_tuple)
    return False
