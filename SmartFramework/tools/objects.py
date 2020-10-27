# -*- coding: utf-8 -*-
from ..serialize import serializeParameters
from ..serialize.serializeQt import tuple_from_qt_classes  # serializableQt, tuple_fromQtInstance
from ..string.encodings import ascii_printables
from ..tools.dictionnaires import remove, filtered
from inspect import isclass
import types
import inspect
import pybase64
from pybase64 import b64encode
from base64 import b64decode
from apply import apply
import copyreg


try:
    import numpy
    from numpy import isnan
    use_numpy = True
except:
    from math import isnan
    use_numpy = False
import math
import _ctypes

try:
    from .. import numpyB64, bytesB64, bytearrayB64
except:
    from serializejson import numpyB64, bytesB64, bytearrayB64

try:
    import qtpy
except:
    pass

ascii_printables_ = ascii_printables  # sert juste à éviter warning
# from SmartFramework.serialize.objects.test_serializeJons_update import *

NoneType = type(None)
builtInTypes = (
    type(None),
    bool,
    memoryview,
    bytearray,
    bytes,
    complex,
    dict,
    float,
    frozenset,
    int,
    list,
    range,
    set,
    slice,
    str,
    tuple,
)


def from_id(obj_id):
    """ Inverse of id() function. """
    return _ctypes.PyObj_FromPtr(obj_id)


valid_char_for_var_name = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")


def from_name(path, accept_dict_as_object=False, **variables):
    """fonction qui permet d'evaluer une expression pour acceder à une valeure à partir de son nom qualifié
    fonctionne comme eval, mais securisé en acceptant juste la qualification avec "." et l'indexation avec des []
    ATTENTION cette fonction n'a pas été testée à fond,il faudrait ecrire des tests!

    exemples :
    variable.attribut
    variable["key"]
    variable['key']
    variable[variable2]

    variable.attribut.attribut
    variable.attribut["key"]
    variable.attribut['key']
    variable.attribut[variable2]

    variable["key"].attribut
    variable["key"]["key"]
    variable["key"]['key']
    variable["key"][variable2]

    par contre à priori ne marche pas avec :
    variable[variable2.attribut]


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
    in_attribut = False
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
                        raise Exception(
                            "firts element of path must be a name_of_variable"
                        )
                    is_first = False
                else:
                    if in_var:
                        element = variables[element]
                    if (
                        accept_dict_as_object
                        and type(current) is dict
                        and "__class__" in current
                    ):
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
                        raise Exception(
                            "firts element of path must be a name_of_variable"
                        )
                    is_first = False
                else:
                    if in_var:
                        element = variables[element]
                    if (
                        accept_dict_as_object
                        and type(current) is dict
                        and "__class__" in current
                    ):
                        current = current[element]
                    else:
                        current = current.__dict__[element]
                element_chars = []
            in_var = False
            in_attribut = True
        elif in_attribut:
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
            if (
                accept_dict_as_object
                and type(current) is dict
                and "__class__" in current
            ):
                current = current[element]
            else:
                current = current.__dict__[element]
    return current


class encodedB64(bytes):
    """class used as flag to know that a bytes as already been encoded in base64, we don't need to do it again"""

    def __new__(cls, val):
        return super().__new__(cls, b64encode(val))


def deepCompare(a, b, return_reason=False):
    if type(a) != type(b):
        if return_reason:
            return False, type(a), type(b)
        return False
    if use_numpy and isinstance(a, numpy.ndarray):

        if a.dtype != b.dtype:
            if return_reason:
                return False, a.dtype, b.dtype
            return False

        if a.shape != b.shape:
            if return_reason:
                return False, a.shape, b.shape
            return False

        a_nan_indexs = numpy.isnan(a)
        b_nan_indexs = numpy.isnan(a)
        if not numpy.array_equal(a_nan_indexs, b_nan_indexs):
            if return_reason:
                return False, None, None
            return False
        not_nan_indexs = ~a_nan_indexs
        if not numpy.array_equal(a[not_nan_indexs], b[not_nan_indexs]):
            if return_reason:
                return False, None, None
            return False
        if return_reason:
            return True, None, None
        return True
    if isinstance(b, (set, frozenset)):
        b = {e if e == e else math.nan for e in b}  # remplace les nan par des math.nan pour permetre comparaison
    if isinstance(a, (list, tuple)):
        for a_elt, b_elt in zip(a, b):
            if not deepCompare(a_elt, b_elt):
                if return_reason:
                    return False, a_elt, b_elt
                return False
        else:
            if return_reason:
                return True, None, None
            return True
    if isinstance(a, float) and isnan(a) and isnan(b):
        if return_reason:
            return True, None, None
        return True
    if hasattr(a, "__slots__"):
        for base_classe in a.__class__.__mro__[:-1]:  # on ne prend pas le dernier qui est toujours (?) object
            for slot in getattr(
                base_classe, "__slots__", ()
            ):  # on utilise pas directement base_classe.__slots__  car une classe de base n'a pas forcement redefinit __slots__
                if hasattr(a, slot):
                    if hasattr(b, slot):
                        if getattr(a, slot) != getattr(b, slot):
                            if return_reason:
                                return False, getattr(a, slot), getattr(b, slot)
                            return False
                    else:
                        if return_reason:
                            return False, getattr(a, slot), None
                        return False
                elif hasattr(b, slot):
                    if return_reason:
                        return False, None, getattr(b, slot)
                    return False

        if hasattr(a, "__dict__"):
            if a.__dict__ == b.__dict__:
                if return_reason:
                    return True, None, None
                return True
            else:
                if return_reason:
                    return False, a.__dict__, b.__dict__
                return False
        else:
            if return_reason:
                return True, None, None
            return True
    if hasattr(a, "__dict__"):
        if a.__dict__ == b.__dict__:
            if return_reason:
                return True, None, None
            return True
        else:
            if return_reason:
                return False, a.__dict__, b.__dict__
            return False
    if isinstance(a, dict):
        if a.keys() != b.keys():
            if return_reason:
                return False, a.keys(), b.keys()
            return False
        for key, value in a.items():
            if return_reason:
                same, raisonleft, raisonright = deepCompare(value, b[key], return_reason=True)
                if not same:
                    return False, a.keys(), b.keys()
            else:
                if not deepCompare(value, b[key]):
                    return False
        if return_reason:
            return True, None, None
        return True
    if a != b:
        if return_reason:
            return False, None, None
        return False
    if return_reason:
        return True, None, None
    return True


def hasMethod(obj, methode):
    return hasattr(obj, methode) and inspect.ismethod(getattr(obj, methode))


classFromClassStr_dict = {
        'base64.b64decode' : lambda b64 : pybase64.b64decode(b64,validate = True)
        }


def classFromClassStr(string):
    listeModuleClasse = string.rsplit(".", 1)
    if len(listeModuleClasse) == 2:
        moduleStr, classeStr = listeModuleClasse
        module = __import__(moduleStr, fromlist=[classeStr])
        return getattr(module, classeStr)
    else:
        return __builtins__[string]


classStrFromClassDict = {}
# @profile


def classStrFromClass(classe):
    if classe in classStrFromClassDict:
        return classStrFromClassDict[classe]
    if classe is types.ModuleType:
        s = "types.ModuleType"
    else:
        module = moduleStrFromClass(classe)
        # ce n'est pas une bonne idée de tenter de suprimer ou modifier "__main__" car il ne retrouvera pas le bon module , alors que le module pointé par __main__ contiendra toujour les definition de classe , si c'est toujours lui qu'on execute .
        # if module == "__main__":
        #    import __main__
        #    if hasattr(__main__,"__file__"):
        #        module = name(__main__.__file__) # peut planter (notament dans console ou designer )
        if module == "builtins":
            s = classe.__name__
        else:
            s = module + "." + classe.__name__
            if s == "numpy.core.multiarray.array":
                s = "numpy.array"
            elif s == "numpy.core.multiarray.frombuffer":
                s = "numpy.frombuffer"
    classStrFromClassDict[classe] = s
    return s


def moduleStrFromClass(classe):
    module = classe.__module__
    classeName = classe.__name__
    if module.startswith("PyQt"):
        if module.startswith("PyQt5"):
            module = "qtpy" + module[5:]
        else:
            if classeName in qtpy.QtCore.__dict__:
                module = "qtpy.QtCore"
            if classeName in qtpy.QtGui.__dict__:
                module = "qtpy.QtGui"
            if classeName in qtpy.QtWidgets.__dict__:
                module = "qtpy.QtWidgets"
    elif module.startswith("PySide2"):
        module = "qtpy" + module[7:]
    return module


# GETS (ne servent pas )------------------------------------


def getState(obj):
    classe, initArgs, state = tupleFromInstance(obj)
    return state


def getInitArgs(obj):
    classe, initArgs, state = tupleFromInstance(obj)
    return initArgs


def getClass(obj):
    return obj.__class__


# TESTS -------------------------------------------------


def isQWidget(obj):
    return hasattr(
        obj, "disconnect"
    )  # ATTENTION SI CHANGE, DOIT CHANGER EGALEMENT LE HACK (FAUSSE METHODE) DANS SmarFace/models.py  pyqtConfigure ne marche pas avec PySide2


def isInstance(obj):
    return hasattr(obj, "__new__") and not (
        isinstance(obj, builtInTypes)
        or inspect.isclass(obj)
        or inspect.isfunction(obj)
        or inspect.ismodule(obj)
    )  # permet d'eliminer les types de base (int, float etc et les fonctions)
    # return hasattr(obj,'__new__') and ( str(obj.__class__)[1:6] == 'class' or  str(type(obj)) == "<type 'numpy.ndarray'>") and not inspect.isclass(obj) and not inspect.isfunction(obj) # permet d'eliminer les types de base (int, float etc et les fonctions)


def isClass(obj):
    return inspect.isclass(obj)


def isModule(obj):
    return inspect.ismodule(obj)
    # return type(obj) == types.ModuleType


def isFunction(obj):
    return inspect.isfunction(obj)


def isCallable(obj):
    return hasattr(obj, "__call__")  # retournera true aussi pour classe.. à revoir ?


# COMPARAISONS -------------------


def comp(obj1, obj2):
    """code a  l arrache, il faudrait passer du temps pour voir ca mieux"""
    if hasattr(obj1, "__dict__") and hasattr(obj2, "__dict__"):
        return obj1.__dict__ == obj2.__dict__
    else:
        return obj1 == obj2


# AJOUTE LES INIT ARGS AUX ATTRIBUTS ----------


def add_Args(dictLocals):
    """
    permet d'ajouter automatiquement les arguments (du init par ex) comme attribut de l'objet

    def __init__(self) :
        add_Args(locals())
    """
    self = dictLocals["self"]
    for key, value in dictLocals.items():
        if key != "self":
            self.__dict__["_" + key] = value

    # SAVE INIT ARGS TOOLS ---------------

    """
    truc pour sauvegarder automatiquement initArgs à  la creation de l'objet

    def __init__(self) :
        saveInitArgsDict(locals())       # sauve  init Arguments dans dictionnaire __initArgsDict__
    def __getinitargs__(self) :
        GenerateInitArgs(self)          # demande de restaurer avec __initArgsDict__ aussi bien avec Pickle que JSON
    def __getstate__(self)
        return filtreInitArgsDict(self) # filtre '__initArgsDict__' pour ne pas le sauver dans etat objet
    """


def saveInitArgsDict(dictLocals):  # a verifier
    self = dictLocals["self"]
    del dictLocals["self"]
    self.__initArgsDict__ = dictLocals


def generateInitArgs(self):
    import inspect

    initArgsNames = inspect.getargspec(self.__init__).args[1:]
    initArgsValues = []
    for name in initArgsNames:
        initArgsValues.append(self.__initArgsDict__[name])
    return tuple(initArgsValues)


def filtreInitArgsDict(self):
    return remove(self.__dict__, "__initArgsDict__")


# CONVERSIONS NON RECURSIVES -------------------------------------------

# @profile
def tupleFromInstance(inst):
    # recuperation de Classe ,  initArgs et state
    # un peu comme le __reduce__ des newstyle object , mais contrairment à ce dernier peut retourner None
    # pour en deuxième position signifier qu'il n'y a pas d'appel à __init__() à faire lors du unpickling
    classe = inst.__class__
    classeName = classe.__name__

    # CAS PARTICULIERS----------------
    if classeName in tuple_from_classeName:
        return tuple_from_classeName[classeName](inst, classe)

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
                    for base_classe in classe.__mro__[:-1]:  # on ne prend pas le dernier qui est toujours (?) object
                        for slot in getattr(
                            base_classe, "__slots__", ()
                        ):  # on utilise pas directement base_classe.__slots__  car une classe de base n'a pas forcement redefinit __slots__
                            if hasattr(inst, slot):
                                if slot != "__dict__":
                                    state[slot] = inst.__getattribute__(slot)
                    state.update(inst.__dict__)
                else:
                    for base_classe in classe.__mro__[:-1]:  # on ne prend pas le dernier qui est toujours (?) object
                        for slot in getattr(
                            base_classe, "__slots__", ()
                        ):  # on utilise pas directement base_classe.__slots__  car une classe de base n'a pas forcement redefinit __slots__
                            if hasattr(inst, slot):
                                state[slot] = inst.__getattribute__(slot)
            elif hasattr(inst, "__dict__"):
                state = inst.__dict__
    else:
        len_tupleReduce = len(tupleReduce)
        if tupleReduce[0] is classe:
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
            classe, initArgs, initKwargs = tupleReduce[1]
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
            classe = tupleReduce[0]
            initArgs = tupleReduce[1]
            if len_tupleReduce > 2:
                state = tupleReduce[2]
            else:
                state = None
    if serializeParameters.attributs_filter and type(state) is dict:
        state = filtered(state, filterChar=serializeParameters.attributs_filter)
    return (classe, initArgs, state)


def tuple_from_ndarray(inst, classe):
    import numpy

    instCont = numpy.ascontiguousarray(inst)
    if instCont.dtype.fields is None:
        instContdtype = str(instCont.dtype)
    else:
        instContdtype = instCont.dtype.descr
    if (
        (instCont.size <= serializeParameters.numpy_array_readable_max_size)
        or (
            instCont.dtype == "int32"
            and max(instCont.min(), instCont.max(), key=abs) <= 9999
        )
        or (
            instCont.dtype == "int16"
            and max(instCont.min(), instCont.max(), key=abs) <= 9
        )
    ):
        return (numpy.array, (instCont.tolist(), instContdtype), None)
    elif instCont.ndim == 1:
        if serializeParameters.numpy_array_use_numpyB64:
            if instCont.dtype == bool:
                return (
                    numpyB64,
                    (
                        encodedB64(numpy.packbits(instCont.astype(numpy.uint8))),
                        "bool",
                        len(instCont),
                    ),
                    None,
                )
            else:
                return (numpyB64, (encodedB64(instCont), instContdtype), None)
        else:
            return (numpy.frombuffer, (bytearray(instCont), instContdtype), None)
    else:

        if serializeParameters.numpy_array_use_numpyB64:
            if instCont.dtype == bool:
                return (
                    numpyB64,
                    (
                        encodedB64(numpy.packbits(instCont.astype(numpy.uint8))),
                        "bool",
                        instCont.shape,
                    ),
                    None,
                )
            else:
                return (
                    numpyB64,
                    (encodedB64(instCont), instContdtype, instCont.shape),
                    None,
                )
        else:
            import numpy

            return (
                numpy.ndarray,
                (instCont.shape, instContdtype, bytearray(instCont)),
                None,
            )


def tuple_from_dtype(inst, classe):
    initArgs = (str(inst),)
    return (classe, initArgs, None)


def tuple_from_bytearray(inst, classe):
    if serializeParameters.bytearray_use_bytearrayB6:
        return (bytearrayB64, (encodedB64(inst),), None)
    else:
        return (bytearray, (bytes(inst),), None)


# @profile


def tuple_from_bytes(inst, classe):
    if inst.isascii():
        try:
            # string = inst.decode("utf_8")
            # return (bytes,(string,"utf_8"),None)
            string = inst.decode("ascii_printables")
            return (bytes, (string, "ascii"), None)
        except:
            pass
    return (b64decode, (encodedB64(inst),), None)



def tuple_from_bool(inst,classe):
    return (classe, (bool(inst),), None)


def tuple_from_int(inst, classe):
    return (classe, (int(inst),), None)


def tuple_from_float(inst, classe):
    return (classe, (float(inst),), None)


def tuple_from_datetime(inst, classe):
    return (
        classe,
        (
            inst.year,
            inst.month,
            inst.day,
            inst.hour,
            inst.minute,
            inst.second,
            inst.microsecond,
        ),
        None,
    )


def tuple_from_complex(inst, classe):
    return (classe, (inst.real, inst.imag), None)


def tuple_from_type(inst, classe):
    return ("type", (classStrFromClass(inst),), None)


def tuple_from_module(inst, classe):
    state = dict()
    toRemove = ["__builtins__", "__file__", "__package__", "__name__", "__doc__"]
    for key, value in inst.__dict__.items():
        if key not in toRemove:
            state[key] = value
    return (classe, None, state)


tuple_from_classeName = {
    "bool_" : tuple_from_bool,
    "ndarray": tuple_from_ndarray,
    "dtype": tuple_from_dtype,
    "bytearray": tuple_from_bytearray,
    "bytes": tuple_from_bytes,
    "int8": tuple_from_int,
    "int16": tuple_from_int,
    "int32": tuple_from_int,
    "int64": tuple_from_int,
    "uint8": tuple_from_int,
    "uint16": tuple_from_int,
    "uint32": tuple_from_int,
    "uint64": tuple_from_int,
    "float16": tuple_from_float,
    "float32": tuple_from_float,
    "float64": tuple_from_float,
    "datetime": tuple_from_datetime,
    "complex": tuple_from_complex,
    "type": tuple_from_type,
    "module": tuple_from_module,
}
tuple_from_classeName.update(tuple_from_qt_classes)


# rehydratation d'un objet

# @profile
def instance(__class__=object, __init__=None, __state__=None, __initArgs__=None, **argsSup):
    """créer une instance d'un objet :
    instance(dictionnaire)
    instance(**dictionnaire)
    instance(classe,__init__,__state__)
    instance(classe,__init__,**attributsDict)
    instance(classe(*__init__),__state__)
    instance(classe(*__init__),**attributsDict)
    instance(__classe__=...,__init__=...,attribut1 = ..., attribut2 = ...)
    """
    if __initArgs__ is not None:
        __init__ = __initArgs__  # pour retro-compatibilité avec anciens json
    # classe,initArgs,state      = __class__,__init__,__state__
    classe = None
    if __class__ == "type":
        if __init__ == "NoneType":
            return type(None)
        else:
            return classFromClassStr(__init__)
    try:
        # acceleration en allant directment charcher la classe à partir de la string dans un dictionnaire de cash
        classe = classFromClassStr_dict[__class__]
    except KeyError:
        # if __class__ == 'module':
        #    inst = types.ModuleType.module('nom_module')
        if isinstance(__class__, str):
            classe = classFromClassStr_dict[__class__] = classFromClassStr(__class__)
        elif isinstance(
            __class__, dict
        ):  # permet de gere le cas ou on donne directement un dictionnaire en premier argument
            return instance(**__class__)
        else:
            if isclass(__class__):
                classe = __class__
            elif isInstance(__class__):
                inst = __class__
            elif isCallable(__class__):
                classe = __class__
            else:
                raise Exception(
                    "erreure lors de la creation d'instance le premier parametre de Instance() n'est ni une classe , ni string representant un classe , ni une instance, ni un dictionnaire, ni un callable (fonction)"
                )

    if classe is not None:
        __init__type = type(__init__)
        if __init__ is None:
            inst = classe.__new__(classe)
        elif __init__type in (list, tuple):
            inst = classe(*__init__)
        elif __init__type is dict:
            inst = classe(**__init__)
        else:
            inst = classe(__init__)  # when braces have been removed during serialization

    if __state__ or argsSup:
        if __state__ and type(__state__) == dict:
            __state__.update(argsSup)
        elif argsSup:
            __state__ = argsSup
        if __state__:
            if hasattr(
                inst, "__setstate__"
            ):  # j'ai du remplacer hasMethod(inst,"__setstate__") par hasattr(inst,"__setstate__") pour pouvoir deserialiser des sklearn.tree._tree.Tree en json "__setstate__" n'est pas reconnu comme étant une methdoe !? alors que bien là .
                inst.__setstate__(__state__)
            else:
                if type(__state__) is dict:
                    if (
                        serializeParameters.set_attributs
                    ):  # si la variable global setAttributs = True , il tente de faire appel aux setters (NON TESTE)
                        for key, value in __state__.items():
                            attributSetMethode = "set_" + key
                            if hasattr(inst, attributSetMethode):
                                methode = eval("inst." + attributSetMethode)
                                methode(value)
                            else:
                                attributSetMethode = "set" + key[0].upper() + key[1:]
                                if hasattr(inst, attributSetMethode):
                                    methode = eval("inst." + attributSetMethode)
                                    methode(value)
                                else :
                                    inst.__setattr__(
                                        key, value
                                    )  # permet de gerer à la fois les cas ou key est une propriétée, un attriut dans __dict__ ou dans __slot__
                    else:
                        if hasattr(inst, "__slots__"):
                            for key, value in __state__.items():
                                inst.__setattr__(key, value)
                        else:
                            inst.__dict__.update(__state__)  # ou copy(state) ou deep(copy) ?
                else:
                    raise Exception("try to restore object to a no dictionary state and without __setstate__ method")
    return inst
