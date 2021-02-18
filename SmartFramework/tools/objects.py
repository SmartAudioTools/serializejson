from ..tools.dictionaries import remove
import inspect
import math
import _ctypes
import types
from collections import OrderedDict

try:
    import numpy
    from numpy import isnan

    use_numpy = True
except:
    from math import isnan

    use_numpy = False


def from_id(obj_id):
    """ Inverse of id() function. """
    return _ctypes.PyObj_FromPtr(obj_id)


def deepCompare(a, b, return_reason=False):
    checked = False
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
    if isinstance(a, (set, frozenset)):
        a = {e if e == e else math.nan for e in a}  # remplace les nan par des math.nan pour permetre comparaison
        b = {e if e == e else math.nan for e in b}  # remplace les nan par des math.nan pour permetre comparaison
    if isinstance(a, (list, tuple)):
        for a_elt, b_elt in zip(a, b):
            if not deepCompare(a_elt, b_elt):
                if return_reason:
                    return False, a_elt, b_elt
                return False
        if isinstance(a, tuple):
            if return_reason:
                return True, None, None
            return True
        checked = True
        # else:
        #    if return_reason:
        #        return True, None, None
        #    return True
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
            if a.__dict__ != b.__dict__:
                if return_reason:
                    return False, a.__dict__, b.__dict__
                return False
            # else:
            #    if return_reason:
            #        return True, None, None
            #    return True
        # else:
        #    if return_reason:
        #        return True, None, None
        #    return True
        checked = True
    elif hasattr(a, "__dict__"):
        if return_reason:
            return deepCompare(a.__dict__, b.__dict__, return_reason=True)
        return deepCompare(a.__dict__, b.__dict__)
        # if a.__dict__ != b.__dict__:
        #    if return_reason:
        #        return False, a.__dict__, b.__dict__
        #    return False
        # else:
        #    if return_reason:
        #        return True, None, None
        #    return True
        checked = True
    if isinstance(a, dict):
        if list(a.keys()) != list(b.keys()):
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
        # if return_reason:
        #    return True, None, None
        # return True
        checked = True

    if not checked and a != b:
        if return_reason:
            return False, None, None
        return False

    if return_reason:
        return True, None, None
    return True


def hasMethod(obj, method):
    return hasattr(obj, method) and inspect.ismethod(getattr(obj, method))


def class_has_method(class_, method):
    method = getattr(class_, method, None)
    if method is not None:
        return callable(method)
    return False


# ---- TESTS -------------------------------------------------


def isQWidget(obj):
    return hasattr(
        obj, "disconnect"
    )  # ATTENTION SI CHANGE, DOIT CHANGER EGALEMENT LE HACK (FAUSSE METHODE) DANS SmarFace/models.py  pyqtConfigure ne marche pas avec PySide2


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


def isInstance(obj):
    return hasattr(obj, "__new__") and not (
        isinstance(obj, builtInTypes) or inspect.isclass(obj) or inspect.isfunction(obj) or inspect.ismodule(obj)
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


def ismethod_or_methoddescriptor(object):
    # if isclass(object) or isfunction(object):
    if isinstance(object, (type, types.FunctionType)):
        return False
    if isinstance(object, types.MethodType):
        return True
    tp = type(object)
    return hasattr(tp, "__get__") and not hasattr(tp, "__set__")


def ismethod_methoddescriptor_or_function(object):
    # if isclass(object) or isfunction(object):
    if isinstance(object, type):
        return False
    if isinstance(object, (types.MethodType, types.FunctionType, types.BuiltinFunctionType)):
        return True
    tp = type(object)
    return hasattr(tp, "__get__") and not hasattr(tp, "__set__")


def isdatadescriptor(object):
    """Return true if the object is a data descriptor.

    Data descriptors have both a __get__ and a __set__ attribute.  Examples are
    properties (defined in Python) and getsets and members (defined in C).
    Typically, data descriptors will also have __name__ and __doc__ attributes
    (properties, getsets, and members have both of these attributes), but this
    is not guaranteed."""
    # if isclass(object) or ismethod(object) or isfunction(object):
    if isinstance(object, (type, types.MethodType, types.BuiltinMethodType)):
        return False
    tp = type(object)
    return hasattr(tp, "__get__") and hasattr(tp, "__set__")


# --- COMPARAISONS -------------------


def comp(obj1, obj2):
    """code a  l arrache, il faudrait passer du temps pour voir ca mieux"""
    if hasattr(obj1, "__dict__") and hasattr(obj2, "__dict__"):
        return obj1.__dict__ == obj2.__dict__
    else:
        return obj1 == obj2


# --- AJOUTE LES INIT ARGS AUX ATTRIBUTS ----------


def add_Args(dictLocals):
    """
    permet d'ajouter automatiquement les arguments (du init par ex) comme attribute de l'objet

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
