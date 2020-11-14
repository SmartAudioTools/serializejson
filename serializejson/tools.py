from . import serialize_parameters
from SmartFramework.string.encodings import ascii_printables
from SmartFramework.tools.dictionnaires import filtered
from SmartFramework.tools.objects import isInstance, isCallable
from inspect import isclass
import types
from pybase64 import b64encode, b64decode
from apply import apply
import copyreg
from collections.abc import Iterable
import blosc

try:
    import numpy

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
except:
    _bool_int_and_float_types = set(
        (
            float,
            int,
            bool,
        )
    )


ascii_printables_ = ascii_printables  # sert juste à éviter warning


'''

def from_id(obj_id):
    """ Inverse of id() function. """
    return _ctypes.PyObj_FromPtr(obj_id)

'''
valid_char_for_var_name = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")


def _onlyOneDimSameTypeNumbers(list_or_tuple):
    if len(list_or_tuple):
        type_first = type(list_or_tuple[0])
        if type_first in _bool_int_and_float_types:
            return all(type(i) is type_first for i in list_or_tuple)
    return False


def compress(inst, compression):
    if compression == "blosc":
        return blosc.compress(inst)


def from_name(path, accept_dict_as_object=False, **variables):
    """fonction qui permet d'evaluer une expression pour acceder à une valeure à partir de son nom qualifié
    fonctionne comme eval, mais securisé en acceptant juste la qualification avec "." et l'indexation avec des []
    ATTENTION cette fonction n'a pas été testée à fond,il faudrait ecrire des tests!

    examples :
    variable.attribute
    variable["key"]
    variable['key']
    variable[variable2]

    variable.attribute.attribute
    variable.attribute["key"]
    variable.attribute['key']
    variable.attribute[variable2]

    variable["key"].attribute
    variable["key"]["key"]
    variable["key"]['key']
    variable["key"][variable2]

    par contre à priori ne marche pas avec :
    variable[variable2.attribute]


    """
    # return(ast.literal_eval(path))
    # return(eval(path,{},variables))
    # current = root
    current = None
    in_simple_quotes = False
    in_double_quotes = False
    in_squares = False
    # in_curly = False
    is_first = True
    # is_var = False
    in_var = False
    in_attribute = False
    first_ch_of_square = False
    backslash_escape = False
    element_chars = []
    for i, ch in enumerate(path):
        if in_squares:
            if first_ch_of_square:
                first_ch_of_square = False
                # if ch == "{":
                #    in_curly = True
                #    is_var = True
                # el
                if ch == '"':  # "
                    in_double_quotes = True
                elif ch == "'":
                    in_simple_quotes = True
                elif ch.isdigit():
                    in_number = True
                    element_chars.append(ch)
                else:
                    in_var = True
                    element_chars.append(ch)
                    # raise Exception("%s is not a valid path in json")
            else:

                # if in_curly:
                #    if ch == "}":
                #        in_curly = False
                #    else:
                #        element_chars.append(ch)
                # el
                if in_number:
                    if ch.isdigit():
                        element_chars.append(ch)
                    elif ch == "]":
                        in_squares = False
                        if element_chars:
                            index = int("".join(element_chars))
                            current = current[index]
                            is_first = False
                        element_chars = []
                    else:
                        raise Exception("%s is not a valid path in json")
                elif in_simple_quotes:
                    if backslash_escape:
                        # we must have just seen a backslash; reset that flag and continue
                        backslash_escape = False
                    elif ch == "\\":  # \
                        backslash_escape = True  # we are in a quote and we see a backslash; escape next char
                    elif ch == "'":
                        in_simple_quotes = False
                    else:
                        element_chars.append(ch)
                elif in_double_quotes:
                    if backslash_escape:
                        # we must have just seen a backslash; reset that flag and continue
                        backslash_escape = False
                    elif ch == "\\":  # \
                        backslash_escape = True  # we are in a quote and we see a backslash; escape next char
                    elif ch == '"':
                        in_double_quotes = False
                    else:
                        element_chars.append(ch)
                elif ch == "]":
                    if element_chars:
                        key = "".joint(element_chars)
                        if in_var:
                            key = variables[key]
                        current = current[key]
                        # is_first = False
                        element_chars = []
                    else:
                        raise Exception("%s is not a valid path in json")
                    in_squares = False
                    in_var = False

                elif in_var:
                    if ch in valid_char_for_var_name:
                        element_chars.append(ch)
                    else:
                        raise Exception("%s is not a valid path in json")
        # elif in_curly:
        #    if ch == '}':
        #        in_curly = False
        #    else :
        #        element_chars.append(ch)
        # elif ch == '{':
        #    in_curly = True
        #    is_curly = True

        elif ch == "[":

            # is_var = False
            if element_chars:
                element = "".join(element_chars)
                if is_first:
                    if in_var:
                        current = variables[element]
                    else:
                        raise Exception("firts element of path must be a name_of_variable")
                    is_first = False
                else:
                    if in_var:
                        element = variables[element]
                    if accept_dict_as_object and type(current) is dict and "__class__" in current:
                        current = current[element]
                    else:
                        current = current.__dict__[element]
                element_chars = []
            in_squares = True
            in_var = False
            first_ch_of_square = True

        elif ch == ".":
            if element_chars:
                element = "".join(element_chars)
                if is_first:
                    if in_var:
                        current = variables[element]
                    else:
                        raise Exception("firts element of path must be a name_of_variable")
                    is_first = False
                else:
                    if in_var:
                        element = variables[element]
                    if accept_dict_as_object and type(current) is dict and "__class__" in current:
                        current = current[element]
                    else:
                        current = current.__dict__[element]
                element_chars = []
            in_var = False
            in_attribute = True
        elif in_attribute:
            element_chars.append(ch)
        else:
            element_chars.append(ch)
            in_var = True

    if element_chars:  # on est sur le dernier element
        element = "".join(element_chars)
        if is_first:
            if in_var:
                current = variables[element]
            else:
                raise Exception("firts element of path must be a name_of_variable")
        else:
            if in_var:
                element = variables[element]
            if accept_dict_as_object and type(current) is dict and "__class__" in current:
                current = current[element]
            else:
                current = current.__dict__[element]
    return current


class encodedB64:  # J'ai abandonné l'idée de sub classer bytes, car il faisait une copie
    """class used as flag to know that a bytes as already been encoded in base64, we don't need to do it again"""

    # @profile
    def __init__(self, val):
        # pass
        self.encoded_bytes = b64encode(val)

    # def __new__(cls, val):
    #    return super().__new__(cls, memoryview(b64encode(val))) # on dirait que y'a une copie .;


class compressedBytes:
    """class used as flag to know that a bytes has already been compressed, we don't need to do it again"""

    def __init__(self, compressed_bytes):
        self.compressed_bytes = compressed_bytes


classFromClassStr_dict = {
    "base64.b64decode": lambda b64: b64decode(b64, validate=True)  # allow to accelerete base 64 decode
}


def classFromClassStr(string):
    listeModuleClass = string.rsplit(".", 1)
    if len(listeModuleClass) == 2:
        moduleStr, class_str = listeModuleClass
        module = __import__(moduleStr, fromlist=[class_str])
        return getattr(module, class_str)
    else:
        return __builtins__[string]


classStrFromClassDict = {}
# @profile
def classStrFromClass(class_):
    if class_ in classStrFromClassDict:
        return classStrFromClassDict[class_]
    module = class_.__module__
    # ce n'est pas une bonne idée de tenter de suprimer ou modifier "__main__" car il ne retrouvera pas le bon module , alors que le module pointé par __main__ contiendra toujour les definition de class_ , si c'est toujours lui qu'on execute .
    # if module == "__main__":
    #    import __main__
    #    if hasattr(__main__,"__file__"):
    #        module = name(__main__.__file__) # peut planter (notament dans console ou designer )
    if module == "builtins":
        if class_ is types.ModuleType:
            s = "types.ModuleType"
        else:
            s = class_.__qualname__
    else:
        s = module + "." + class_.__qualname__
    classStrFromClassDict[class_] = s
    return s


# CONVERSIONS NON RECURSIVES -------------------------------------------


def tupleFromInstance(inst):
    # recuperation de Class ,  initArgs et state
    # un peu comme le __reduce__ des newstyle object , mais contrairment à ce dernier peut retourner None
    # pour en deuxième position signifier qu'il n'y a pas d'appel à __init__() à faire lors du unpickling
    class_ = inst.__class__
    classStr = classStrFromClass(class_)

    # CAS PARTICULIERS----------------
    if classStr in tuple_from_module_class_str:
        return tuple_from_module_class_str[classStr](
            inst
        )  # 99.2 % du temps sur obj = bytes(numpy.arange(2**18,dtype=numpy.float64).data)

    # CAS GENERAL --------------------------------
    try:
        tupleReduce = inst.__reduce__()  # fait appel à __gestate__() si on n'a pas réimplementé __reduce__()
    except TypeError:  # arrive pour les QWidgets et les objets avec __slots__ sans getstate__
        initArgs = None
        try:
            state = inst.__getstate__()  #  for QWidgets with __getstate__
        except AttributeError:
            if hasattr(inst, "__slots__"):
                state = dict()
                if hasattr(inst, "__dict__"):  # on peut avoir __dict__ dans les __slots__ !
                    for base_class in class_.__mro__[:-1]:  # on ne prend pas le dernier qui est toujours (?) object
                        for slot in getattr(
                            base_class, "__slots__", ()
                        ):  # on utilise pas directement base_class.__slots__  car une classe de base n'a pas forcement redefinit __slots__
                            if hasattr(inst, slot):
                                if slot != "__dict__":
                                    state[slot] = inst.__getattribute__(slot)
                    state.update(inst.__dict__)
                else:
                    for base_class in class_.__mro__[:-1]:  # on ne prend pas le dernier qui est toujours (?) object
                        for slot in getattr(
                            base_class, "__slots__", ()
                        ):  # on utilise pas directement base_class.__slots__  car une classe de base n'a pas forcement redefinit __slots__
                            if hasattr(inst, slot):
                                state[slot] = inst.__getattribute__(slot)
            elif hasattr(inst, "__dict__"):
                state = inst.__dict__
    else:
        len_tupleReduce = len(tupleReduce)
        if tupleReduce[0] is class_:
            # le __reduce__ a ete reimplemente et se comporte normalement
            initArgs = tupleReduce[1]
            if len_tupleReduce > 2:
                state = tupleReduce[2]
                if len_tupleReduce > 3:
                    if tupleReduce[3] is not None:
                        initArgs = (list(tupleReduce[3]),)
                    if len_tupleReduce > 4:
                        dict_from_iter = dict(tupleReduce[4])
                        if dict_from_iter:
                            initArgs += (dict_from_iter,)
                            # else :
                        #    initArgs = (dict(tupleReduce[4]),)
            else:
                state = None
        elif tupleReduce[0] is apply:
            class_, initArgs, initKwargs = tupleReduce[1]
            initArgs = initKwargs
            if len_tupleReduce == 3:
                state = tupleReduce[2]
            else:
                state = None
        elif tupleReduce[0] is copyreg._reconstructor:
            # le __reduce__ n'a pas ete reimplemente => structure bizarre!
            # le initArgs est donc nul
            initArgs = None
            # le state n'est pas forcement present (si __getstate__() : pass)
            if len_tupleReduce > 2:
                state = tupleReduce[2]
            else:
                state = None
        else:
            class_ = tupleReduce[0]
            initArgs = tupleReduce[1]
            if len_tupleReduce > 2:
                state = tupleReduce[2]
            else:
                state = None
    if serialize_parameters.attributes_filter and type(state) is dict:
        state = filtered(state, filterChar=serialize_parameters.attributes_filter)
    return (class_, initArgs, state)


# rehydratation d'un objet

# @profile


def instance(__class__=object, __init__=None, __state__=None, __initArgs__=None, **argsSup):
    """créer une instance d'un objet :
    instance(dictionnaire)
    instance(**dictionnaire)
    instance(class_,__init__,__state__)
    instance(class_,__init__,**attributesDict)
    instance(class_(*__init__),__state__)
    instance(class_(*__init__),**attributesDict)
    instance(__class__=...,__init__=...,attribute1 = ..., attribute2 = ...)
    """
    if __initArgs__ is not None:
        __init__ = __initArgs__  # pour retro-compatibilité avec anciens json
    # class_,initArgs,state      = __class__,__init__,__state__
    inst = None
    # class_str = None
    if __class__ == "type":
        if __init__ == "NoneType":
            return type(None)
        else:
            return classFromClassStr(__init__)
    try:
        # acceleration en allant directement charcher la class_ à partir de la string dans un dictionnaire de cash
        class_ = classFromClassStr_dict[__class__]
        class_str = __class__
    except KeyError:
        # if __class__ == 'module':
        #    inst = types.ModuleType.module('nom_module')
        if isinstance(__class__, str):
            class_ = classFromClassStr_dict[__class__] = classFromClassStr(__class__)
            class_str = __class__
        elif isinstance(
            __class__, dict
        ):  # permet de gere le cas ou on donne directement un dictionnaire en premier argument
            return instance(**__class__)
        else:
            if isclass(__class__):
                class_ = __class__
                class_str = classStrFromClass(__class__)
            elif isInstance(__class__):  # arrrive avec serializeRepr
                inst = __class__
                class_str = classStrFromClass(inst.__class__)
            elif isCallable(__class__):
                class_ = __class__
                class_str = classStrFromClass(__class__)
            else:
                raise Exception(
                    "erreure lors de la creation d'instance le premier parametre de Instance() n'est ni une classe , ni string representant un classe , ni une instance, ni un dictionnaire, ni un callable (fonction)"
                )

    if inst is None:
        __init__type = type(__init__)
        if __init__ is None:
            inst = class_.__new__(class_)
        elif __init__type in (list, tuple):
            inst = class_(*__init__)
        elif __init__type is dict:
            inst = class_(**__init__)
        else:
            inst = class_(__init__)  # when braces have been removed during serialization

    if argsSup:
        __state__ = argsSup

    if __state__:
        if hasattr(
            inst, "__setstate__"
        ):  # j'ai du remplacer hasMethod(inst,"__setstate__") par hasattr(inst,"__setstate__") pour pouvoir deserialiser des sklearn.tree._tree.Tree en json "__setstate__" n'est pas reconnu comme étant une methdoe !? alors que bien là .
            inst.__setstate__(__state__)
        else:
            if type(__state__) is dict:
                set_attributes = serialize_parameters.set_attributes
                if set_attributes is True or (
                    (set_attributes is not False) and (class_str in set_attributes)
                ):  # si la variable global setattributes = True , il tente de faire appel aux setters (NON TESTE)
                    for key, value in __state__.items():
                        attributeSetmethod = "set_" + key
                        if hasattr(inst, attributeSetmethod):
                            method = inst.__getattribute__(attributeSetmethod)
                            method(value)
                        else:
                            attributeSetmethod = "set" + key[0].upper() + key[1:]
                            if hasattr(inst, attributeSetmethod):
                                method = inst.__getattribute__(attributeSetmethod)
                                method(value)
                            else:
                                inst.__setattr__(
                                    key, value
                                )  # permet de gerer à la fois les cas ou key est une propriétée, un attriut dans __dict__ ou dans __slot__
                else:
                    if hasattr(inst, "__slots__"):
                        for key, value in __state__.items():
                            inst.__setattr__(
                                key, value
                            )  # ATTENTION va aussi restaure  propriétés alors qu'on ne le souhaite pas forcement...
                    else:
                        inst.__dict__.update(__state__)  # ou copy(state) ou deep(copy) ?
            else:
                raise Exception("try to restore object to a no dictionary state and without __setstate__ method")
    return inst


# --- Import of plugins -------------------------------------------------------
import inspect
from . import plugins

# import plugins
tuple_from_module_class_str = {}
default_set_attributes = set()
encoder_plugins_parameters_default_values = {}
decoder_plugins_parameters_default_values = {}

for module_name, module in plugins.__dict__.items():
    if not module_name.startswith("__"):
        if hasattr(module, "encoder_plugins_parameters_default_values"):
            encoder_plugins_parameters_default_values.update(module.encoder_plugins_parameters_default_values)
        if hasattr(module, "decoder_plugins_parameters_default_values"):
            decoder_plugins_parameters_default_values.update(module.decoder_plugins_parameters_default_values)
        if hasattr(module, "set_attributes"):
            default_set_attributes.update(module.set_attributes)
        if hasattr(module, "tuple_from_module_class_str"):
            tuple_from_module_class_str.update(module.tuple_from_module_class_str)
        else:
            for function_name, function in module.__dict__.items():
                if inspect.isfunction(function) and function_name.startswith("tuple_from_"):
                    class_str = function_name[len("tuple_from_") :]
                    if module_name != "builtins":
                        class_str = module_name + "." + class_str
                    tuple_from_module_class_str[class_str] = function
encoder_plugins_parameters_keys = set(encoder_plugins_parameters_default_values)
decoder_plugins_parameters_keys = set(decoder_plugins_parameters_default_values)


def _get_set_attributes_classes_strings(set_attributes):
    if isinstance(set_attributes, bool):
        return set_attributes
    elif isinstance(set_attributes, Iterable):
        set_attributes_with_defaults = default_set_attributes.copy()
        for elt in set_attributes:
            if not isinstance(str):
                elt = classFromClassStr(elt)
            set_attributes_with_defaults.add(elt)
        return set_attributes_with_defaults
    else:
        raise TypeError(
            "Decoder set_attributes argument must be a bool, list, tuple or set, not '%s'" % type(set_attributes)
        )


def tuple_from_compressedBytes(inst):
    inst = inst.compressed_bytes
    if inst.isascii():
        try:
            string = inst.decode("ascii_printables")
            return (bytes, (string, "ascii"), None)
        except:
            pass
    # if serialize_parameters.bytes_use_bytesB64:
    #    return (bytesB64, (encodedB64(inst),), None)
    return ("base64.b64decode", (encodedB64(inst),), None)


tuple_from_module_class_str[classStrFromClass(compressedBytes)] = tuple_from_compressedBytes
