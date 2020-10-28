from . import serializeParameters
from SmartFramework.string.encodings import ascii_printables
from SmartFramework.tools.dictionnaires import filtered
from SmartFramework.tools.objects import isInstance,isCallable
from inspect import isclass
import types
import pybase64
from pybase64 import b64encode
from apply import apply
import copyreg
try:
    import qtpy
except:
    pass




ascii_printables_ = ascii_printables  # sert juste à éviter warning
# from SmartFramework.serialize.objects.test_serializeJons_update import *


'''

def from_id(obj_id):
    """ Inverse of id() function. """
    return _ctypes.PyObj_FromPtr(obj_id)

'''
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


# CONVERSIONS NON RECURSIVES -------------------------------------------

# @profile

def tupleFromInstance(inst):
    # recuperation de Classe ,  initArgs et state
    # un peu comme le __reduce__ des newstyle object , mais contrairment à ce dernier peut retourner None
    # pour en deuxième position signifier qu'il n'y a pas d'appel à __init__() à faire lors du unpickling
    classe = inst.__class__
    classStr = classStrFromClass(classe)

    # CAS PARTICULIERS----------------
    if classStr in tuple_from_module_class_str:
        return tuple_from_module_class_str[classStr](inst)

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




import inspect
from . import plugins
# import plugins 
tuple_from_module_class_str = {}
for module_name,module in   plugins.__dict__.items():
    if not module_name.startswith("__"):
        if hasattr(module, 'tuple_from_module_class_str'):
            tuple_from_module_class_str.update(module.tuple_from_module_class_str)
        else: 
            for function_name,function in module.__dict__.items():
                if inspect.isfunction(function) and function_name.startswith("tuple_from_"):
                    classeStr = function_name[len("tuple_from_"):]
                    if module_name != "builtins":
                        classeStr = module_name+'.'+classeStr
                    tuple_from_module_class_str[classeStr] = function
