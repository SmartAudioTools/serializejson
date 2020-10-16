import os
import io
import sys
from collections import deque
import rapidjson
from pybase64 import b64decode
import numpy
from numpy import frombuffer,unpackbits,uint8,ndarray,int32,int64
from numpy import dtype as numpy_dtype
import gc
from _collections_abc import list_iterator
from .SmartFramework.serialize import serializeParameters

# --- FONCTIONS FOR SERIALIZED OBJECTS IN BASE 64------------------------------   
#defaultIntType =  numpy_dtype("int_")
nb_bits = sys.maxsize.bit_length()+1

def bytearrayB64(b64):
    return bytearray(b64decode(b64,validate=True))

def bytesB64(b64):
    return b64decode(b64,validate=True) 
            
def numpyB64(str64,dtype = None,shapeOrLen = None):
    decodedBytes = b64decode(str64,validate=True)    # str64 -> bytes : decodage avec copie 
    if dtype in ("bool",bool) : 
        uintContaining8bits = frombuffer(decodedBytes,uint8)    # pas de copie ?
        uintContaining1bit  = unpackbits(uintContaining8bits) # copie
        if shapeOrLen is None : 
            return uintContaining1bit 
        else : 
            return ndarray(shapeOrLen,dtype,uintContaining1bit)      # a priori pas de recopie
    else : 
        if isinstance(dtype,list):
            dtype = [(str(champName),champType) for champName,champType in dtype]
        if shapeOrLen is None :
            #return nympy.frombuffer(decodedBytes)
            array = frombuffer(decodedBytes,dtype) # evite de faire une recopie 
        else :
            array = ndarray(shapeOrLen,dtype,decodedBytes) # evite de faire une recopie  ? a priori oui
        array.flags.writeable = True
        
        if nb_bits == 32 and serializeParameters.numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit : # pour pouvoir deserialiser les classifiers en python 32 bit ?
            if array.dtype in (int64, 'int64'):
                array = array.astype(int32)
            elif isinstance(dtype,list):
                newTypes = []
                for champ  in dtype :
                    champName,champType = champ
                    if champName  : 
                        champType = numpy_dtype(champType)
                        if champType in (int64, 'int64'):
                            newTypes.append((champName,int32))
                        else : 
                            newTypes.append((champName,champType)) 
                newDtype = numpy_dtype(newTypes,align = True)
                newN =  ndarray(len(array),newDtype) 
                for champName,champType in newTypes : 
                    if champName:
                        newN[champName][:] = array[champName]
                array = newN
        return array   
            #return numpy.ndarray(shape,dtype,bytearray(decodedBytes)) # obligé de mettre bytearray? sinon le tableau sera immutable , et si on force à l'etre avec flags.readonly = False on va changer la chaine de caractère sous jacent et potientiellement foutre la merde sur dictionnaire qui ont la meme clef?
        
    # str -> bytearray : copie ? 
    # bytearray -> nympy : pas de copie 
    #a.flags.writable = True # a priori dangereux , car va pouvoir modifier valeur d'une string... qui est sencé etre imutable .
fromB64 = numpyB64 # pour pouvoir ouvrir d'anciens fichiers serializés

 
from .SmartFramework.tools.objects import (
    instance,
    tupleFromInstance,
    classStrFromClass,
    encodedB64,
    classFromClassStr,
    from_name
)
not_duplicates_types = set([type(None), bool, int, float, str])




# --- FONCTIONS BASED API ----------------------


def dumps(
    obj,
    **argsDict
):
    return Encoder(**argsDict)(obj)
    
def dump(
    obj,
    fp,
    **argsDict
):
    if isinstance(fp, str):
        fp = open(fp, "wb")   
    Encoder(**argsDict)(obj,fp)

def loads(
    s,
    *,
    obj = None,
    iter = False, # on ne peut pas en meme temps updater objet 
    **argsDict
):
    decoder = Decoder(**argsDict)
    if iter : 
        return decoder
    else:
        return decoder(fp_or_s = s, obj = obj)
  

def load(
    fp,
    *,
    obj = None,
    iter = False,
    **argsDict
):
    """ de-serialise obj à partir de fichier f, qui peut etre un objet  file ou le nom de fichier"""
    if iter : 
        return Decoder(**argsDict)
    else:
        return Decoder(**argsDict).load(fp = fp, obj = obj)

def append(
    obj,
    fp=None,
    *,
    indent="\t",
    **argsDict
):
    fp = _open_for_append(fp, indent)
    Encoder(**argsDict)(obj,fp)
    _close_for_append(fp, indent)


# --- CLASSES BASED API -------------------------------------------------------


class Encoder(rapidjson.Encoder):
    """Class-based dumps()-like functionality."""

    def __new__(
        cls,
        fp=None,
        *,
        attributs_filter = '_',
        bytes_to_string=False,
        ensure_ascii=False,
        indent="\t",
        numpy_array_dumped_base64 = True,
        numpy_array_readable_max_size = 0, 
        numpy_array_to_list=False,
        numpy_types_to_python_types=True,
        single_line_init=True,
        single_line_list_numbers=True,
        sort_keys=True,
        use_numpyB64_bytesB64_bytearrayB64 = True,
        chunk_size=65536,
        add_id = False,
        **argsDict
    ):
        """
        Args:
            fp (string or file-like) : path or file-like object. When specified, the encoded result will be written there
            attributs_filter
            bytes_to_string
            ensure_ascii (bool) : whether the output should contain only ASCII characters
            indent (int or "\t") : 	      indentation width to produce pretty printed JSON
            numpy_array_dumped_base64
            numpy_array_readable_max_size
            numpy_array_to_list (bool): whether numpy array should be serialized as list
            numpy_types_to_python_types
            single_line_init
            single_line_list_numbers
            sort_keys (bool) : 	  whether dictionary keys should be sorted alphabetically
            use_numpyB64_bytesB64_bytearrayB64
            chunk_size (int) :	write the stream in chunks of this size at a time
            add_id 

            Herited from rapidjson.Encoder :

            skip_invalid_keys (bool) : whether invalid dict keys will be skipped
            number_mode (int) :	enable particular behaviors in handling numbers
            datetime_mode (int) : 	how should datetime, time and date instances be handled
            uuid_mode (int) : 	how should UUID instances be handled
            write_mode :	WM_COMPACT`, that produces the most compact JSON representation
                            WM_PRETTY` it will use RapidJSON's PrettyWriter
                            WM_single_line_list_numbers` arrays will be kept on a single line:
            bytes_mode :	BM_UTF8
                            BM_NONE
        """

        if not bytes_to_string:
            bytes_mode = rapidjson.BM_NONE
        else:
            bytes_mode = rapidjson.BM_UTF8
        self = super().__new__(
            cls,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            bytes_mode=bytes_mode,
            **argsDict
        )     
        self.attributs_filter = attributs_filter
        self.numpy_array_dumped_base64 = numpy_array_dumped_base64
        self.numpy_array_readable_max_size = numpy_array_readable_max_size
        self.use_numpyB64_bytesB64_bytearrayB64 = use_numpyB64_bytesB64_bytearrayB64
        self.fp = fp
        self.kargs = argsDict
        self.numpy_array_to_list = numpy_array_to_list
        if indent is None:
            self.single_line_list_numbers = False
            self.single_line_init = False
        else:
            self.single_line_list_numbers = single_line_list_numbers
            self.single_line_init = single_line_init
        self.numpy_types_to_python_types = numpy_types_to_python_types
        self.indent = indent
        self.dumped_classes = set()
        self.chunk_size = chunk_size
        self.add_id = add_id
        self._sort_keys = sort_keys # bug dans rapide json il enregistre self.sort_keys avec ensure_ascii
        return self

    def dump(self,obj,fp = None):
        if fp is None:
            fp = self.fp
        if isinstance(fp, str):
            fp = open(fp, "wb")        
        self.__call__(obj,stream=fp , chunk_size = self.chunk_size)
        
    def dumps(self,obj) :
       return self.__call__(obj)
        

    
        
    
    def append(self, obj, fp=None, *, chunk_size=65536):
        if fp is None:
            fp = self.fp
        fp = _open_for_append(fp, self.indent)
        rapidjson.Encoder.__call__(self, obj, stream=fp, chunk_size=chunk_size)
        _close_for_append(fp, self.indent)

    def get_dumped_classes(self):
        return self.dumped_classes

    def default(
        self, inst
    ):  # Equivalent au calback "default" qu'on peut passer à dump ou dumps
        """
        If implemented, this method is called whenever the serialization machinery finds a Python object that it does not recognize: if possible, the method should returns a JSON encodable version of the value, otherwise raise a TypeError:

        Args:
            obj : the Python object to be encoded

        Returns:
            a JSON-serializable value

        Raises :
            TypeError : the method MUST raise a TypeError if the value is not serializable, otherwisex it will be serialized as None .

        Exemples :
            if isinstance(obj, Point):
                return {'x': obj.x, 'y': obj.y}
            else:
                raise TypeError('%r is not JSON serializable' % obj)
        """
        id_ = id(inst)
        if id_ in self._already_serialized:
            return {
                "__class__": "serializeJson.from_name",
                "__init__": self._get_path(inst)
            }
        self._already_serialized.add(id_) 
        type_inst = type(inst)
        if type_inst in _numpy_types and self.numpy_types_to_python_types:
            if type_inst in _numpy_int_types :
                return int(inst)
            if type_inst in _numpy_float_types :
                return float(inst)
            if type_inst is numpy.bool_ : 
                return bool(numpy)
        if type_inst is encodedB64:
            return inst.decode("ascii")
        if ( type_inst is tuple):  
            # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tupleFromInstance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tupleFromInstance
            self.dumped_classes.add(tuple)
            if self._dump_one_line or not self.single_line_init:
                dic =  {"__class__": "tuple", "__init__": list(inst)}
            else : 
                dic = {
                "__class__": "tuple",
                "__init__": rapidjson.RawJSON(
                    rapidjson.dumps(
                        list(inst),
                        default=self.default_one_line,
                        ensure_ascii=False,
                        sort_keys=self._sort_keys,
                        bytes_mode=self.bytes_mode,
                        **self.kargs
                    )
                ),
            }
        elif type_inst is ndarray and self.numpy_array_to_list:
            if not self.single_line_list_numbers:
                return inst.tolist()
            if inst.ndim == 1:
                return rapidjson.RawJSON(rapidjson.dumps(inst.tolist()))
            return [
                rapidjson.RawJSON(rapidjson.dumps(elt.tolist())) for elt in inst
            ]  # inst.tolist()
        dic = self.dict_from_instance(inst)
        initArgs = dic.get("__init__", None)
        if (
            initArgs is not None and self.single_line_init
        ):  # and  dic["__class__"] in  _oneline_init_classess :
            dic["__init__"] = rapidjson.RawJSON(
                rapidjson.dumps(
                    initArgs,
                    default=self.default_one_line,
                    ensure_ascii=self.ensure_ascii,
                    sort_keys=self.sort_keys,
                    bytes_mode=self.bytes_mode,
                    **self.kargs
                )
            )
        if self.single_line_list_numbers:
            for key, value in dic.items():
                if (
                    key != "__class__"
                    and key != "__init__"
                    and type(value) in (list, tuple) and _onlyOneDimNumbers(value)
                ):
                  
                    dic[key] = rapidjson.RawJSON(
                                rapidjson.dumps(
                                    value,
                                    default=self.default_one_line,
                                    bytes_mode=self.bytes_mode,
                                    **self.kargs
                                )
                            )
        self._already_serialized_id_dic_to_obj_dic[id(dic)] = inst,dic  # important de metre dic avec sinon il va être detruit et son identifiant va être réutilisé ..
        if self.add_id : 
            dic["_id"] = id_
        return dic
        # raise TypeError('%r is not JSON serializable' % inst)
        
        
        
    def default_one_line(self,inst):
        type_inst = type(inst)
        if type_inst is encodedB64:
            return inst.decode("ascii")
        if type_inst in _numpy_types and self.numpy_types_to_python_types:
            if type_inst in _numpy_int_types:
                return int(inst)
            if type_inst in _numpy_float_types :
                return float(inst)
            if type_inst is numpy.bool_ :
                return bool(inst)
        if (
            type_inst is tuple
        ):  # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tupleFromInstance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tupleFromInstance
            self.dumped_classes.add(tuple)
            return {"__class__": "tuple", "__init__": [list(inst)]}
        if type_inst is ndarray and self.numpy_array_to_list:
            # return rapidjson.RawJSON(rapidjson.dumps(inst.tolist(), bytes_mode=dump_bytes_mode))
            return inst.tolist()
        return self.dict_from_instance(inst)
        
        
    def dict_from_instance(self,inst):
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
                    if type_first not in (tuple, list) and not (self.numpy_array_to_list and type_first is numpy.ndarray)  and ( (type_first is not dict) or "__class__" in initArgs[0]):
                        dictionnaire["__init__"] = initArgs[0]
                    else:
                        dictionnaire["__init__"] = list(initArgs) # initArgs is a tuple
                else:
                    dictionnaire["__init__"] = list(initArgs) # initArgs is a tuple
        if state:
            if type(state) is dict:
                dictionnaire.update(state)
            else:
                dictionnaire["__state__"] = state
        return dictionnaire
        
    def __call__(self, obj, stream = None, chunk_size = 65536):
        if type(obj) in (list, tuple) and self.single_line_list_numbers  and _onlyOneDimNumbers(obj):
            return rapidjson.dumps(
                    obj,
                    default=self.default_one_line,
                    bytes_mode=self.bytes_mode,
                    **self.kargs
                )
        serializeParameters.attributs_filter = self.attributs_filter
        serializeParameters.numpy_array_dumped_base64 = self.numpy_array_dumped_base64
        serializeParameters.numpy_array_readable_max_size = self.numpy_array_readable_max_size
        serializeParameters.use_numpyB64_bytesB64_bytearrayB64 = self.use_numpyB64_bytesB64_bytearrayB64
        self.dumped_classes = set()
        self._already_serialized = set()
        self._already_serialized_id_dic_to_obj_dic = dict()
        self._root = obj
        encoded = rapidjson.Encoder.__call__(self, obj, stream=stream, chunk_size=chunk_size)
        del(self._already_serialized)
        del(self._already_serialized_id_dic_to_obj_dic) 
        return encoded 
   
    def _searchSerializedParent(self,obj,already_explored = set()):#,list_deep = 10):
        root = self._root
        if obj == root :
            return ["root"]
        id_obj = id(obj)
        if id_obj in already_explored:
            return []
        already_explored = already_explored.copy()
        already_explored.add(id_obj)
        pathElements = list()
        for parent_test in gc.get_referrers(obj) :
            id_parent_test = id(parent_test)
            if id_parent_test not in already_explored :
                type_parent_test = type(parent_test)
                if type_parent_test is dict : 
                    if id_parent_test in self._already_serialized_id_dic_to_obj_dic : 
                        parent_inst,parent_dict = self._already_serialized_id_dic_to_obj_dic[ id_parent_test]
                        for key in sorted(parent_test): 
                            value = parent_test[key]
                            if value == obj:
                                pathElement=  "."  + key                                
                                for elt in self._searchSerializedParent(parent_inst,already_explored) :
                                    pathElements.append(elt + pathElement)    
                                break
                if type_parent_test is list and not type(parent_test[-1]) is list_iterator: 
                    for key , value in enumerate(parent_test): 
                        if value == obj:  
                            for elt in self._searchSerializedParent(parent_test,already_explored) : 
                                pathElements.append(elt + "[%d]"%key)
                            break
        return pathElements        
        
    def _get_path(self, obj):
        pathElements = self._searchSerializedParent(obj)
        return sorted(pathElements)[0] 

class Decoder(rapidjson.Decoder):
    """Class-based loads()-like functionality."""

    def __new__(
        cls,
        fp=None,
        *,
        autorized_classes=[],
        set_attributs  = True,
        recognized_classes=None,
        accept_comments=False,
        numpy_array_from_list=False,
        default_value=None,
        chunk_size=65536,
        updatables_classes = [],
        **argsDict
    ):
        """
        Args:
            autorized_classes
            recognized_classes
            accept_comments
            numpy_array_from_list



            Herited from rapidjson.Decoder:

            number_mode (int) :	Enable particular behaviors in handling numbers
            datetime_mode (int) : How should datetime, time and date instances be handled
            uuid_mode (int) :	How should UUID instances be handled
            parse_mode (int) :	Whether the parser should allow non-standard JSON extensions (nan, -inf, inf )
        """
        if accept_comments:
            parse_mode = rapidjson.PM_COMMENTS
        else:
            parse_mode = rapidjson.PM_NONE
        self = super().__new__(cls, parse_mode=parse_mode, **argsDict)
        self.fp = fp
        self.set_attributs = set_attributs
        self._autorized_classes_strs = _get_autorized_classes_strings(autorized_classes)
        self._class_from_attributs_names = _get_recognized_classes_dict(
            recognized_classes
        )
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

    def load(self, fp = None, obj = None ):
        if fp is None:
            fp = self.fp
        if isinstance(fp, str):
            #print("load",fp)
            if not os.path.exists(fp):
                return self.default_value
            fp_or_s = _open_with_good_encoding(fp)
        elif fp is not None:
            fp_or_s = fp
        else :
            raise ValueError(
                'Encoder.__call__() need a "s" string/bytes or "fp" path/file argument'
            )
        return self.__call__(fp_or_s = fp_or_s, obj = obj)
        
    def loads(self, s, obj = None ):
        return self.__call__(fp_or_s = s, obj = obj )
        
    def set_default_value(self, value):
        self.default_value = value

    def set_recognized_classes(self, classes):
        self._class_from_attributs_names = _get_recognized_classes_dict(classes)

    def set_autorized_classes(self, classes):
        self._autorized_classes_strs = _get_autorized_classes_strings(classes)


    def set_updatables_classes(self, updatables):
        updatableClassStrs = set()
        for updatable in updatables:
            if isinstance(updatable, str):
                updatableClassStrs.add(updatable)
            else:
                updatableClassStrs.add(classStrFromClass(updatable))
        self.updatableClassStrs = updatableClassStrs
        
    def start_object(self):
        dict_ = dict()
        if self.root is None and self.json_startswith_curly: # en vrai c'est pas forcement le root ,si par exeple le root est une liste ...
            self.root = dict_
        if self._updating  :
            id_ = id(dict_)
            self.ancestors.append(id_)
        return dict_

    def end_object(self, inst):
        self._counter += 1
        #self._deserializeds.add()
        if self._updating :
            self.ancestors.pop()  # se retire lui meme
        classStr = inst.get("__class__",None)
        if classStr:
            if classStr == "serializeJson.from_name":
                #inst["devrait"] = "pas etre là" #permetait de verifier que le dictionnaire a bien été remplacé par un objet 
                if self.root: 
                    try : 
                        inst_potential = from_name(inst["__init__"],accept_dict_as_object = True, root=self.root) # essaye de remplacer tout de suite si possible 
                        if (not type(inst_potential) is dict) or ("__class__" not in inst_potential ): # verifi que ce n'est pas un objet qui n'a pas encore été recré 
                            return inst_potential 
                    except :    
                        pass
                self.duplicates_to_replace.append(inst)
            elif self._updating:
                if classStr in self.updatableClassStrs:
                    ancestor = self.ancestors[-1]
                    self.node_has_descendants_to_recreate.add(ancestor)
                else:
                    return self._exploreDictToReCreateObjects(inst)  # idealement faudrait pouvoir eviter d'explorer, et aller directement rédydrater les descendant , le problème c'est que l'hydrattation n'est pas in place et les objet qui les contiennent de vont pas avoir leur champs mis à jour ... ex dans une liste
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
                    if inst["__class__"] in self.updatables_classes_strs:
                        ancestor = self.ancestors[-1]
                        self.node_has_descendants_to_recreate.add(ancestor)
                    else:
                        return self._exploreDictToReCreateObjects(inst)  # idealement faudrait pouvoir eviter d'explorer, et aller directement rédydrater les descendant , le problème c'est que l'hydrattation n'est pas in place et les objet qui les contiennent de vont pas avoir leur champs mis à jour ... ex dans une liste
                else:
                    return instance(**inst)  # pas de verification les objets recognized sont considérés comme autorized  #self._inst_from_dict(inst)
        return inst


    def __call__(self, fp_or_s, obj=None ):
        """
        Args:
            fp(str,file-like):  file-like  or  path of the file containing the JSON to be decoded
            s (str,bytes)    :	either str or bytes (UTF-8)  containing the JSON to be decoded
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
        if isinstance(fp_or_s ,str):
            self.json_startswith_curly = fp_or_s.startswith("{")              
        else : 
            self.json_startswith_curly = (fp_or_s.read(1) == "{")
            fp_or_s.seek(0)
            
        self.duplicates_to_replace = []
        if obj is None : 
            self._updating = False
            loaded = rapidjson.Decoder.__call__(self, fp_or_s, chunk_size=self.chunk_size)
        else : # update
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
                if type(parent) is dict :
                    for key, value in parent.items(): 
                        if value == duplicate_to_replace:
                            parent[key] = from_name(value["__init__"],accept_dict_as_object = True, root=loaded)
                            break
                elif type(parent) is list : 
                    for key , value in enumerate(parent):
                        if value == duplicate_to_replace:
                            parent[key] = from_name(value["__init__"],accept_dict_as_object = True, root=loaded) 
                            break
        # clean ---------------
        del(self.duplicates_to_replace)
        if self._updating:
            del(self.ancestors)
            del(self.node_has_descendants_to_recreate)
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
            if self.numpy_array_from_list and "__init__" in inst and isinstance(inst["__init__"],numpy.ndarray) and id(inst["__init__"]) in self.converted_numpy_array_from_lists: 
                inst["__init__"]  = inst["__init__"].tolist()
            return instance(**inst)
        raise TypeError("%s is not in autorized_classes" % inst["__class__"])

    def _exploreToUpdate(self, obj, loaded_node):
        
        # gère le cas où loaded_node est un dictionnaire ----------------------
        if isinstance(loaded_node, dict):
            obj__dict__ = None
            if hasattr(obj, '__dict__'):
                classStr = loaded_node.get('__class__')
                if (classStr is not None) and (classStr in self.updatableClassStrs) and (classStr == classStrFromClass(obj.__class__)):
                    obj__dict__ = obj.__dict__
            elif isinstance(obj, dict) and ("dict" in self.updatableClassStrs):
                obj__dict__ = obj      
            if obj__dict__:    
                # update dans le cas où l'objet pré-existant est un objet (avec __dict__ pas encore __slot__) ou un dictionnaire --
                loaded_node_has_descendants_to_recreate = (id(loaded_node) in self.node_has_descendants_to_recreate)
                # suprime les attributs de l'objet qui ne sont pas dans loaded..
                only_in_obj = set(obj__dict__) - set(loaded_node)
                for key in only_in_obj:
                    if not key.startswith("_"):
                        del(obj__dict__[key])
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
            else : # sinon remplace 
                return self._exploreDictToReCreateObjects(loaded_node)
            
        # gère le cas où loaded_node est une liste  ---------------------------
        if isinstance(loaded_node, list):
            if isinstance(obj, list) and ("list" in self.updatableClassStrs): 
                # update dans le cas où l'objet pré-existant est une liste 
                len_obj = len(obj)
                del(obj[len(loaded_node):])
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
            else : # sinon replace
                return self._exploreListToReCreateObjects(loaded_node)

        # gère les autres cas 
        return loaded_node # replace

    def _exploreDictToReCreateObjects(self, loaded_node):
        if id(loaded_node) in self.node_has_descendants_to_recreate:
            for key, value in loaded_node.items():
                if isinstance(value, dict):  # and "__class__" in value
                    loaded_node[key] = self._exploreDictToReCreateObjects(value)
                elif isinstance(value, list):
                    loaded_node[key] = self._exploreListToReCreateObjects(value)
        if "__class__" in loaded_node:
            return instance(**loaded_node)
        else :
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
            elif isinstance (sequence[0], numpy.ndarray):
                dtype = sequence[0].dtype
            else : 
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
            return rapidjson.Decoder.__call__(
                self, self.fp_iter, chunk_size=self.chunk_size
            )
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
        "SmartFramework.bytesB64",
        "SmartFramework.bytearrayB64",
        "SmartFramework.numpyB64",
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
    ]
)   
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
_bool_int_and_float_types  = set(
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
        if bytes_ == b'\xef\xbb\xbf': # normalement ne devrait pas arriver les json ne devraient jamais commencer par un BOM , mais parfoit si le fichier à été créer à la main dans un editeur de text, il peut y'en avoir un (exemple : personnel.json ).
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
        if not isinstance(classes , set):
            if isinstance(classes, (list, tuple)):
                classes = set(classes)
            else :
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
            sorted(
                [
                    attribut
                    for attribut in instanceVide.__dict__.keys()
                    if not attribut.startswith("_")
                ]
            )
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
        self.shedule_stop = False
        self.in_chunk_start = 0
        self.s = None
        s = io.FileIO.read(self, 1)
        if s not in (b"[", "["):
            raise Exception(
                'the json data must start with "["'
            )
        if "b" in mode:
            self.interesting = set(b'\\"{}[]')
            self.separators = set(b", \t\n\r")
            self.chars = list(b'\\"{}[]')
        else:
            self.interesting = set('\\"{}[]')
            self.separators = set(", \t\n\r")
            self.chars = list('\\"{}[]')

    def read(self, size=-1):
        if self.shedule_stop:
            self.shedule_stop = False
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
                if ch in separators or  ch in ("]", 93):
                    if in_chunk_start < i:
                        self.shedule_stop = True  # on prevoit d'arreter au read suivant sinon , va de tout facon arreter et on ne pourra pas remeter self.shedule_stop à False
                    # self.seek(chunk_start + i + 1)
                    self.in_chunk_start = (i + 1) % len(s)
                    self.in_quotes = False
                    self.in_curlys = False
                    self.in_squares = False
                    self.in_simple = False
                    self.in_object = False
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
                        check = True
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
                    if in_squares:  # inSquare peut commence à -1 si in_square_braclets
                        in_object = True
                elif ch == square_close:  # ]
                    in_squares -= 1
                    check = True
                if check and not in_quotes and not in_curlys and not in_squares:
                    if in_chunk_start < (i + 1):
                        self.shedule_stop = True  # on prevoit d'arreter au read suivant sinon , va de tout facon arreter et on ne pourra pas remeter self.shedule_stop à False
                    # self.seek(chunk_start + i + 1)
                    self.in_chunk_start = (i + 1) % len(s)
                    self.in_quotes = False
                    self.in_curlys = False
                    self.in_squares = False
                    self.in_simple = False
                    self.in_object = False
                    return s[in_chunk_start: i + 1]
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
            return s[in_chunk_start:]
        return s

def _onlyOneDimNumbers(list_or_tuple):
    if len(list_or_tuple) :
        type_first = type(list_or_tuple[0])
        if type_first in _bool_int_and_float_types:
            try:
                # ne suffit pas à s'assurer que tout elements de la meme nature
                # en effet numpy.array([9, numpy.array([2]), 1]) donne
                # array([9, 2, 1]) qui a pour dtype "int32"
                np = numpy.array(list_or_tuple, dtype=type_first) # type(list_or_tuple[0]) ne pemet pas de retourner True pour [1,math.nan] 
                if np.ndim == 1 :
                    return True 
            except ValueError:
                pass
    return False




