from . import serialize_parameters
from SmartFramework.string.encodings import ascii_printables
from SmartFramework.tools.dictionaries import sorted_dict, sorted_filtered  # ,filtered
from SmartFramework.tools.objects import (
    isInstance,
    class_has_method,
    ismethod_methoddescriptor_or_function,
)  # ,hasMethod
from SmartFramework.tools.functions import cached_one_arg_func
from inspect import isclass, signature
import types
from pybase64 import b64decode
from apply import apply
from pickle import PicklingError
from copyreg import __newobj__, __newobj_ex__, dispatch_table
import blosc
from collections.abc import MutableSequence, Mapping
import sys
from importlib import import_module

try:
    import numpy

    use_numpy = True
except:
    use_numpy = False
ascii_printables_ = ascii_printables  # sert juste à éviter warning
not_memorized_types = (int, float)
# --- PLUGINS API -------------------------------

# encoding -------------
dispatch_table  # pickle plugins (used by serializejson if not serializejson plugin or methode)
serializejson_ = {}  # serializejson plugins
serializejson_builtins = {}  # serializejson plugins actives even if strict_pickle is True
encoder_parameters = {}  # encoder extra parameters for plugins, with their default value
getters = (
    {}
)  # getters for dumped classes. keys are string corresponding to the qualified name, values are True (for automatic getters detection) or dictionnary of {"attribut" : "getAttribut" }
property_types = {property}  # property types
blosc_compressions = {(name if name == "blosclz" else "blosc_" + name): name for name in blosc.cnames}
# encoding & decoding --------------

properties = (
    {}
)  # properties for loaded classes. keys are classes, values are True (for automtic properties detection) or list of ["attribut1","attribut2",..]}
# decoding ---------------------
authorized_classes = set()  # qualified names of classes autorized to be loaded
setters = (
    {}
)  # setters for loaded classes. keys are string corresponding to the qualified name, values are True (for automatic setters detection) or dictionnary of {"attribut" : "setAttribut" }
constructors = (
    {}
)  # custom construtors for loaded classes. keys are string corresponding to the class qualified name, value is the constructor
decoder_parameters = {}  # decoder extra parameters for plugins with their default value
consts = {}  # dictionnary associating const string to const values

# @profile
def getstate(
    self,
    *,
    split_dict_slots=True,
    keep=None,
    add=None,
    remove=None,
    filter_="_",
    properties=False,
    getters=False,
    extra_getters=None,
    sort_keys=True,
    remove_default_values=False,
    default_values=None,
    lasts=None,
):
    """
    Generic __gestate__ method to retrieve the state of an object .

    Args:
        split_dict_slots : True if you want to stay compatible with pickle
        keep :   names of attributes/properties/getters to keep (and order if sort_keys is False)
        add :    names of attributes to add even if should be filtered by the filter
        remove:  names of attributes to remove even if not filtered by the filter
        filter\_: (bool or str) filter attributes starting with the given string. ("_" by default)

        properties :
                False: (default) no properties are saved
                True : all properties (or only thus in keep) are saved
                list or tuple : names of properties to save
        getters :
                False :(default) None getters are saved
                True : all getters (or only thus in keep) are saved. (getters are guessed with introspection)
                dict : dictionnary of "attribut": "getter". ex: {"a":"getA","b":"getB"}
                this option allow the finest control and is faster because getters are not guessed from instropection.

        extra_getters
                dictionnary of extra getters.    ex: {"c":"retrive_c"}
                useful when getters is True and not all gettters are guessed by introspection.

        sort_keys (True by default )
                whether sort the state alphabeticaly.
                Be careful, if False the restoration of the object attributes may be in an arbitrary order.

        remove_default_values :(False, True)
                whether attribut/properties/getter with same value as default value will be
                removed for lighter and more readable serialized files.
                If remove_default_values is True, add you still want to keep a attribut value even if same as his default value,
                use add = "attribut_name" parameter

        default_values : (None or dict)
                dict : dict of {"attribut":"attribut_default_value",...;}
                None :  serializejson will create an new instance of the object's
                class, calling __init__() without any argument to know the default values.
    """
    #            ,...,("x","y",None):"getXYZ"}
    #        With tuple as key ou can retrieve several attributes values from one getter.
    #        with None in this tuple you can skip values returned by this getter.
    #             list or tuple : names of attributs having getters to save. (getters are guessed with introspection)
    # or type(getters) in (list,tuple):
    #
    #    elif type(getters) in (list,tuple):
    #        getters = {getter:class_getters[getter] for getter in getters}

    if filter_ is True:
        filter_ = "_"
    _getattribute = self.__getattribute__
    _dict = getattr(self, "__dict__", {})
    has_slots = hasattr(self, "__slots__")

    if (properties is True) or (getters is True):
        slots, class_properties, class_getters, _ = slots_properties_getters_setters_from_class(type(self))
        if properties is True:
            properties = class_properties
        if getters is True:
            getters = class_getters
    else:
        if has_slots:
            slots = slots_from_class(type(self))
        if getters is False:
            getters = {}
    if extra_getters:
        getters.update(extra_getters)
    if split_dict_slots and (has_slots or properties or getters):  # ATTENTION PAS LE CAS SI PAS DE __SLOT__ ?
        state_dict = dict()
        state_slots = dict()
        splited_dict_slots = True
    else:
        state_dict = state_slots = dict()
        splited_dict_slots = False

    if keep is not None:
        for key in keep:
            if key in getters:
                state_slots[key] = _getattribute(getters[key])()
            elif key in properties:  # on commenc pas voir si existe sous forme de propriété
                state_slots[key] = _getattribute(
                    key
                )  # le stocker dans state_slots permet à pickle de restaurer des properties dans pickle._dumps.load_build :if slotstate:for k, v in slotstate.items():setattr(inst, k, v)
            elif key in slots:
                if hasattr(self, key):
                    state_slots[key] = _getattribute(key)
            elif key in _dict:  # optimisable pour eviter de lire deux fois
                state_dict[key] = _dict[key]
            else:
                state_slots[key] = _getattribute(
                    key
                )  # permet de marcher avec attribut référencés null part est accessible uniquement via self.__getattr__() ?

    else:
        if remove is None:
            remove = set()
        if add is None:
            add = set()

        # get poperties ------------------
        if properties:
            for key in properties:
                if key not in remove:
                    state_slots[key] = _getattribute(
                        key
                    )  # le stocker dans state_slots permet à pickle de restaurer des properties dans pickle._dumps.load_build :if slotstate:for k, v in slotstate.items():setattr(inst, k, v)
        # get getters -------------
        if getters:
            for key, getter_name in getters.items():
                if type(key) is tuple:
                    result = _getattribute(getter_name)()
                    for k, value in zip(key, result):
                        if k is not None and k not in remove:
                            state_slots[k] = value
                elif key not in remove:
                    try:
                        state_slots[key] = _getattribute(getter_name)()
                    except TypeError:
                        pass  # n'arrive pas à regler le pb avec inspect qui n'arrive pas à parser arguement du getter

        # get __slots__ attributs ----------------
        check_prop_getters = bool(state_slots)
        if has_slots:
            if remove or filter_ or check_prop_getters:
                for key in slots:
                    if (
                        key not in remove
                        and hasattr(self, key)
                        and ((key in add) or not (filter_ and key.startswith(filter_)))
                        and not (
                            check_prop_getters
                            and (key in state_slots or (key.startswith("_") and key[1:] in state_slots))
                        )
                    ):
                        state_slots[key] = _getattribute(key)
            else:
                for key in slots:
                    if hasattr(self, key):
                        state_slots[key] = _getattribute(key)
        # get __dict__ attributs -----------------
        if remove or filter_ or check_prop_getters:
            for key in _dict:
                if (
                    key not in remove
                    and ((key in add) or not (filter_ and key.startswith(filter_)))
                    and not (
                        check_prop_getters and (key in state_slots or (key.startswith("_") and key[1:] in state_slots))
                    )
                ):
                    state_dict[key] = _dict[key]
        else:
            if not state_slots or splited_dict_slots:
                state_dict = _dict  # no copie   A REVOIR , ON SPLIT DICT ET SLOT MEME SI PAS SPLITE A LA BASE
            else:
                state_dict.update(_dict)

    if remove_default_values is True:
        if default_values is None:
            default_values = default_state_from_class(type(self))
        for key, default_value in default_values.items():
            if key not in add:
                if key in state_dict:
                    if state_dict[key] == default_value:
                        if state_dict is _dict:
                            state_dict = _dict.copy()
                        del state_dict[key]
                elif splited_dict_slots and key in state_slots:
                    if state_slots[key] == default_value:
                        del state_slots[key]

    if sort_keys and state_dict:
        state_dict = sorted_dict(state_dict)
    if lasts is not None:
        for key in lasts:
            if key in state_dict:
                state_dict[key] = state_dict.pop(key)
    if splited_dict_slots and state_slots:
        if sort_keys:
            state_dict = sorted_dict(state_dict)
        if state_dict:
            return state_dict, state_slots  # peut planter si self n'a pas de __dict__ et  pas de __setstate__
        if state_slots:
            return None, state_slots

    return state_dict


# def getstate_factory(split_dict_slots = True, keep=None, add= None, remove=None, filter_="_", properties=False, getters=False, sort_keys = True, remove_default_values = False):
#    return lambda self :getstate(self ,split_dict_slots = split_dict_slots, keep=keep, add= add, remove=remove, filter_=filter_, properties=properties, getters=getters, sort_keys = sort_keys, remove_default_values = remove_default_values)


def setstate(
    self,
    state,
    properties=False,
    setters=False,
    extra_setters=None,
    restore_default_values=False,
    default_values=None,
    order=None,
):
    """
    Generic __setstate_ method to restore the state of an object .

    Args:
        self     object instance to restore.
        state    dictionnary containing the state of the object to restore.

        properties :
                False: (default) no properties are saved
                True : all properties (or only thus in keep) are saved
                list or tuple : names of properties to save
        setters :
                False :(default) None setters are called
                True : all getters are calaed (setters are guessed with introspection, parsing methodes with setXxx, set_xxx or setxxx name)
                dict : dictionnary of "attribut": "setter". ex: {"a":"setA","b":"setB",("c","d"):"setCD"}
                this option allow the finest control and is faster because getters are not guessed from instropection and it allow to call multi-attributs setters (ex : setCD restor "c" and "d")

        extra_setters
                dictionnary of extra setters.    ex: {"c":"restore_c"}
                useful when setters is True and not all settters are guessed by introspection.

        restore_default_values :(False, True)
                whether attribut/properties/setter not present in state
                will be restaured with there default value.
                Useful when __init__() is not called (update = True or object as not __reduce__() methode)
                and we have encoded with remove_default_values = True .

        default_values : (None or dict)
                dict : dict of {"attribut":"attribut_default_value",...;}
                None :  serializejson will create an new instance of the object's
                class, calling __init__() without any argument to know the default values.

        order  :
                None : attributs are restored in state dictionnary key's order
                list or tuple : attributs are restored in this order
                If a attribut belong to a multi-attributs setters  (like {("c","d"):"setCD"}), the setter will be called when one of the attribut occure .

    """

    """methode qu'on utilsera dans les object"""
    ## same as pickle
    ## Commenté pour eviter boucle infinie
    ## setstate = getattr(self, "__setstate__", None)
    ## if setstate is not None:
    ##     setstate(state)
    ##     return
    ##    data_driven (bool):
    ##        True : attributs are restored in state dictionnary key's order
    ##        False : attribut are restored in the fallowin order : __slots__,properties,setters, other state dictionnary key's order

    # on a un dictionnaire ou eventuellemnet un tuple  (__dict__,__state__) si serializé avec pickle
    passed_dict_setters = isinstance(setters, dict)
    if (
        isinstance(state, tuple) and len(state) == 2
    ):  # n'arrivera pas venant de json(sauf si on a mis strict_pickle = True) , mais arriver venant de pickle
        dict_state, state = state
        if dict_state:
            state.update(dict_state)

    if not type(state) is dict:
        raise Exception("try to restore object to a no dictionary state and without __setstate__ method")

    if restore_default_values:  # est-ce utile si pas d'update et qu'on vient de recrer l'objet  ?
        if default_values is None:
            default_values = default_state_from_class(type(self))
        for key, default_value in default_values.items():
            if key not in state:
                state[key] = default_value

    if setters is True or properties is True or hasattr(self, "__slots__"):
        slots, class_properties, _, class_setters = slots_properties_getters_setters_from_class(type(self))
        if setters is True:
            setters = class_setters
        if properties is True:
            properties = class_properties
        setattr_ = set(slots)
    else:
        if setters is False:
            setters = {}
        setattr_ = set()
    if extra_setters:
        setters.update(extra_setters)
    # if data_driven :
    if properties:
        setattr_.update(properties)
    if setters is False:
        setters = set()
    intern = sys.intern

    attribut_to_multi_attributs = {}
    if passed_dict_setters or extra_setters:
        for attribut in setters:
            if isinstance(attribut, tuple):
                for attr in attribut:
                    attribut_to_multi_attributs[attr] = attribut
    if order is None:
        for attribut, value in state.items():
            if attribut in setattr_:
                setattr(self, attribut, value)  # marche pour les attribut de __dict__, slots et properties
            elif attribut in attribut_to_multi_attributs:
                attributs = attribut_to_multi_attributs[attribut]
                if attributs:
                    values = []
                    for k in attributs:
                        values.append(state[k])
                        attribut_to_multi_attributs[attribut] = False
                    getattr(self, setters[attributs])(*values)
            elif attribut in setters:
                getattr(self, setters[attribut])(value)
            else:
                self.__dict__[intern(attribut)] = value
    else:
        for attribut in order:
            value = state.popitem(attribut)
            if attribut in setattr_:
                setattr(self, attribut, value)  # marche pour les attribut de __dict__, slots et properties
            elif attribut in attribut_to_multi_attributs:
                attributs = attribut_to_multi_attributs[attribut]
                if attributs:
                    values = []
                    for k in attributs:
                        if k == attribut:
                            values.append(value)  # attribut as already be poped , state[k] doesn't exciste anymore
                        else:
                            values.append(state[k])
                        attribut_to_multi_attributs[attribut] = False
                    getattr(self, setters[attributs])(*values)
            elif attribut in setters:
                getattr(self, setters[attribut])(value)
            else:
                self.__dict__[intern(attribut)] = value
        if state:
            raise Exception(f"{list(state.keys())} are not in __setstate__ order parameter")
    # else :
    #    sentinel = []
    #    for key in slots :
    #        value = state.pop(key,sentinel)
    #        if value is not sentinel:
    #            setattr(self,key,value)
    #    for key in properties :
    #        value = state.pop(key,sentinel)
    #        if value is not sentinel:
    #            setattr(self,key,value)
    #    for key in setters :
    #        if isinstance(key,tuple):
    #            values = ( state.pop(k) for k in key )
    #            getattr(self,setters[key])(*values)
    #        else :
    #            value = state.pop(key,sentinel)
    #            if value is not sentinel:
    #                getattr(self,setters[key])(value)
    #    for key, value in state.items():
    #        self.__dict__[intern(key)] =  value


class Reference:
    def __init__(self, obj, sup_str=""):
        self.obj = obj
        self.sup_str = sup_str


# --- INTERNAL ---------------------------------------

# --- Conversion Class <-> qualified name ------------------------

class_from_class_str_dict = constructors
class_from_class_str_dict["base64.b64decode"] = lambda string_b64: b64decode(
    string_b64, validate=True
)  # allow to accelerete base 64 decode


def class_from_class_str(
    string,
):  # il ne faut pas mettre en caching sinon ne peut pas bidouiller class_from_class_str_dict
    path_name = string.rsplit(".", 1)
    if len(path_name) == 2:
        path, name = path_name
        try:
            return getattr(import_module(path), name)
        except ModuleNotFoundError:
            path_name2 = path.rsplit(".", 1)
            if len(path_name2) == 2:
                path2, name2 = path_name2
                return getattr(getattr(import_module(path2), name2), name)
            raise
    else:
        return __builtins__[string]


@cached_one_arg_func
def module_str_from_class_str(class_str):
    stop = class_str.rfind(".")
    while stop != -1:
        class_str = class_str[:stop]
        if class_str in sys.modules:
            return class_str
        stop = class_str.rfind(".")
    # print(class_str)


@cached_one_arg_func
def class_str_from_class(class_):
    module = class_.__module__
    # ce n'est pas une bonne idée de tenter de suprimer ou modifier "__main__" car
    # il ne retrouvera pas le bon module , alors que le module pointé par __main__
    # contiendra toujour les definition de class_ , si c'est toujours lui qu'on execute .
    if module == "builtins":
        if class_ is types.ModuleType:
            return "types.ModuleType"
        else:
            return class_.__qualname__
    elif module is None:
        raise AttributeError(f"{class_.__name__}.__module__ is None")
    else:
        return f"{module}.{class_.__qualname__}"


# --- Introspection ------------------------------


@cached_one_arg_func
def default_state_from_class(class_):
    obj = class_()
    return getstate(
        obj, split_dict_slots=False, properties=True, getters=True, sort_keys=False, remove_default_values=False
    )


@cached_one_arg_func
def slots_properties_getters_setters_from_class(class_):
    slots = []
    properties = []
    getters = {}
    setters = {}
    property_types_ = tuple(property_types)
    for base_class in class_.__mro__:
        # slots
        # print(base_class)
        for slot in getattr(
            base_class, "__slots__", ()
        ):  # on utilise pas directement base_class.__slots__  car une classe de base n'a pas forcement redefinit __slots__
            if slot != "__dict__":
                slots.append(slot)
        for key, value in base_class.__dict__.items():
            # print(key)
            if isinstance(value, property_types_):
                if hasattr(value, "__set__") and hasattr(value, "__get__"):
                    # if inspect.isdatadescriptor(value):
                    properties.append(key)
            elif (
                key.startswith("set") and len(key) > 3 and ismethod_methoddescriptor_or_function(value)
            ):  # and callable(value):
                c = key[3]
                if c == "_":
                    attribut_name = key[4:]
                elif len(key) > 4 and key[4].isupper():
                    attribut_name = key[3:]
                else:
                    attribut_name = c.lower() + key[4:]
                if (
                    attribut_name not in setters
                ):  # on a peut etre definit deux setters set_x et setX dans deux classes de base différente, on gard la p
                    setters[attribut_name] = key
                    for getter_name in (attribut_name, "g" + key[1:], "is" + key[3:]):
                        getter_methode = getattr(base_class, getter_name, None)
                        if getter_methode is not None:
                            if getter_methode not in getters and ismethod_methoddescriptor_or_function(
                                getter_methode
                            ):  # and callable(getter_methode):
                                getters[attribut_name] = getter_name
                                break
    for property_ in properties:
        if property_ in setters:
            del setters[property_]
            if property_ in getters:
                del getters[property_]
    return slots, sorted(properties), sorted_dict(getters), sorted_dict(setters)


@cached_one_arg_func
def slots_from_class(class_):
    slots = list()
    for base_class in class_.__mro__:
        for slot in getattr(
            base_class, "__slots__", ()
        ):  # on utilise pas directement base_class.__slots__  car une classe de base n'a pas forcement redefinit __slots__
            if slot != "__dict__":
                slots.append(slot)
    return slots


@cached_one_arg_func
def setters_names_from_class(class_):
    if class_.__base__ is None:
        setters = {}
    else:
        setters = setters_names_from_class(class_.__base__).copy()
    for key, value in class_.__dict__.items():
        if key.startswith("set") and len(key) > 3:
            c = key[3]
            if c == "_":
                attribut_name = key[4:]
            else:
                attribut_name = c.lower() + key[4:]
            setters[attribut_name] = key
    return setters


# --- Dump -------------------------------------------


# @profile
def tuple_from_instance(obj, protocol=4):
    # recuperation de Class ,  initArgs et state
    # un peu comme le __reduce__ des newstyle object , mais contrairment à ce dernier peut retourner None
    # pour en deuxième position signifier qu'il n'y a pas d'appel à __init__() à faire lors du unpickling

    # SERIALIZEJSON SPECIAL CASES -----------------------------------------------------------

    # builtins ------
    tuple_from_type = serializejson_builtins.get(obj.__class__)
    if tuple_from_type is not None:
        tuple_ = tuple_from_type(obj)
        if len(tuple_) < 6:
            tuple_ += (None,) * (6 - len(tuple_))
        return tuple_

    if not serialize_parameters.strict_pickle:
        # plugins  ------
        tuple_from_type = serializejson_.get(obj.__class__)
        if tuple_from_type is not None:
            tuple_ = tuple_from_type(obj)
            if len(tuple_) < 6:
                tuple_ += (None,) * (6 - len(tuple_))
            return tuple_
        # __serializejson__ method
        tuple_from_type = getattr(obj, "__serializejson__", None)
        if tuple_from_type is not None:
            tuple_ = tuple_from_type()
            if len(tuple_) < 6:
                tuple_ += (None,) * (6 - len(tuple_))
            return tuple_

    # PICKLE CASES  --------------------------------

    reduced = reduce(obj, protocol)
    return tuple_from_reduce(*reduced, obj=obj)


def tuple_from_reduce(func, args, state=None, listitems=None, dictitems=None, obj=None):
    initArgs = None
    newArgs = None
    if func is __newobj__ or func is __newobj_ex__:
        # a prirori les methode __reduce_ex__ et __reduce__ n'ont  pas ete reimplemente et correspondent aux methodes héritées de object
        if func is __newobj__:
            class_ = args[0]
            if serialize_parameters.strict_pickle:
                if not hasattr(class_, "__new__"):
                    raise PicklingError("args[0] from __newobj__ args has no __new__")
                if obj is not None and class_ is not obj.__class__:
                    raise PicklingError("args[0] from __newobj__ args has the wrong class")
            if len(args) > 1:
                newArgs = args[1:]  # le reduce n'a pas été réimplémenté , on doit pas utiliser d'initArgs
        else:  # func is __newobj_ex__
            class_, new_largs, new_kwargs = args
            if serialize_parameters.strict_pickle:
                if not hasattr(class_, "__new__"):
                    raise PicklingError("args[0] from {} args has no __new__".format(getattr(func, "__name__", "")))
                if obj is not None and class_ is not obj.__class__:
                    raise PicklingError(
                        "args[0] from {} args has the wrong class".format(getattr(func, "__name__", ""))
                    )
            if new_largs:
                # on met les new_largs dans new_kwargs
                new_parameters_names = list(signature(class_.__new__).parameters)
                for index, new_arg in new_largs:
                    new_kwargs[new_parameters_names[index]] = new_arg
            newArgs = new_kwargs
        if not serialize_parameters.strict_pickle:

            if type(state) is tuple:
                # ATTENTION en vrais rien ne nous dit qu'on a pas voulu retourne un autre tuple de longeur deux, si c'est le cas on a codé
                if not class_has_method(class_, "__getstate__") or not class_has_method(class_, "__setstate__"):
                    __dict__, state = state
                    if __dict__:
                        state.update(__dict__)  # fusionne slots et __dict__ dans un seul dictionnaire

            if type(state) is dict:
                if not class_has_method(
                    class_, "__getstate__"
                ):  # on devrait mettre ce qui suit pour être exacte mais couteux pour cas qui n'arrivera jamais : and ( class_.__reduce__ is object.__reduce__) and (class_.__reduce_ex__ is object.__reduce_ex__):
                    # le __reduce_ex__ a déjà recupéra les slots et attributs du __dict__

                    # add properties and getters (need obj)
                    _getters = serialize_parameters.getters

                    if _getters is True:
                        _getters = getters.get(class_, True)
                    elif type(_getters) is dict:
                        _getters = _getters.get(class_, False)
                    _properties = serialize_parameters.properties
                    if _properties is True:
                        _properties = properties.get(class_, True)
                    elif type(_properties) is dict:
                        _properties = _properties.get(class_, False)

                    if _getters is True or _properties is True:
                        (
                            class_slots,
                            class_properties,
                            class_getters,
                            class_setters,
                        ) = slots_properties_getters_setters_from_class(class_)
                        _getattribute = obj.__getattribute__
                        _dict = getattr(obj, "__dict__", None)
                        if _getters is True:
                            _getters = class_getters
                        if _properties is True:
                            _properties = class_properties
                    if _properties:
                        if state is _dict:
                            state = state.copy()
                        for key in _properties:
                            if "_" + key in state:
                                del state["_" + key]
                            state[key] = _getattribute(
                                key
                            )  # le stocker dans state_slots permet à pickle de restaurer des properties dans pickle._dumps.load_build :if slotstate:for k, v in slotstate.items():setattr(inst, k, v)
                    if _getters:
                        if state is _dict:
                            state = state.copy()
                        for key, getter_name in _getters.items():
                            try:
                                state[key] = _getattribute(getter_name)()
                            except TypeError:
                                pass

                    # remove default values (Je l'ai viré car il faut faire appel au __init__ et donc avoir recodé le reduce() pour pouvoir se permetre d'enlever les valeures par défaut)
                    ##remove_default_values = serialize_parameters.remove_default_values
                    ##if type(remove_default_values) is set :
                    ##    remove_default_values = (class_ in remove_default_values)
                    ##if remove_default_values:
                    ##    _dict = getattr(obj, "__dict__",None)
                    ##    default_values = default_state_from_class(class_)
                    ##    for key, default_value in default_values.items() :
                    ##        if key in state :
                    ##            if state[key] == default_value:
                    ##                if state is _dict:
                    ##                    state = _dict.copy()
                    ##               del(state[key])
                    attributes_filter = serialize_parameters.attributes_filter
                    if type(attributes_filter) is set:
                        attributes_filter = class_ in attributes_filter
                    state = sorted_filtered(state, attributes_filter)

    elif func is apply:
        class_, initLargs, initArgs = args
        # if initLargs is not None:
        #    raise PicklingError("args[2] from apply args must be None for pickle compatibility")
    else:
        class_ = func
        initArgs = args
    if dictitems and not isinstance(dictitems, dict):
        dictitems = dict(dictitems)
    if listitems and not isinstance(listitems, list):
        listitems = list(listitems)
    return class_, initArgs, state, listitems, dictitems, newArgs


def reduce(obj, protocol):
    # Check private dispatch table if any, or else copyreg.dispatch_table

    reduce_func = dispatch_table.get(obj.__class__)
    if reduce_func is not None:
        reduced = reduce_func(obj)
    else:
        # Check for a class with a custom metaclass; treat as regular class
        # try:
        #    issc = issubclass(t, type)
        # except TypeError: # t is not a class (old Boost; see SF #502085)
        #    issc = False
        # if issc:
        #    self.save_global(obj)
        #    return

        # Check for a __reduce_ex__ method, fall back to __reduce__
        reduce_func = getattr(obj, "__reduce_ex__", None)
        if reduce_func is not None:
            # try :
            reduced = reduce_func(protocol)  # fait appel à __gestate__() si on n'a pas réimplementé __reduce__()
            # except :
            #    reduced =  generic__reduce_ex__(obj)
        else:
            reduce_func = getattr(obj, "__reduce__", None)
            if reduce_func is not None:
                reduced = reduce_func()
            else:
                raise PicklingError("Can't pickle %r object: %r" % (type(obj).__name__, obj))

    if isinstance(reduced, str):
        raise ValueError("{} reduce's methode return a string. It is not yet suported by serializejson")  # A REVOIR !!!

    if serialize_parameters.strict_pickle:
        # Check for string returned by reduce(), meaning "save as global"
        if isinstance(reduced, str):
            return reduced
        # Assert that reduce_func() returned a tuple
        if not isinstance(reduced, tuple):
            raise PicklingError("%s must return string or tuple" % reduce_func)

        # Assert that it returned an appropriately sized tuple
        if not (2 <= len(reduced) <= 5):
            raise PicklingError("Tuple returned by %s must have " "two to five elements" % reduce_func)

        if not callable(reduced[0]):
            raise PicklingError(
                f"first element returned by {obj.__class__.__name__}.__reduce_ex__()  or {obj.__class__.__name__}.__reduce__() must be callable"
            )
    return reduced


def generic__reduce_ex__(self, protocol=4):
    if hasattr(self, "__reduce_ex__") and self.__class__.__reduce_ex__ is not object.__reduce_ex__:
        return self.__reduce_ex__(protocol)
    if hasattr(self, "__reduce__") and self.__class__.__reduce__ is not object.__reduce__:
        return self.__reduce__()
    state, dictitems, listitems = None, None, None
    if hasattr(self, "__getstate__"):
        state = self.__getstate__()
    else:
        # state = getstate(self,filter_ = None,sort_keys = False)
        if hasattr(self, "__slots__"):
            slots = dict()
            for slot in slots_from_class(type(self)):
                if hasattr(self, slot):
                    slots[slot] = self.__getattribute__(slot)
            state = getattr(self, "__dict__", None), slots
        else:
            state = getattr(self, "__dict__", None)

    if isinstance(self, Mapping):
        dictitems = iter(self.items())
    if isinstance(self, MutableSequence):
        listitems = iter(self)

    if hasattr(self, "__getnewargs_ex__"):
        new_args, kwargs = self.__getnewargs_ex__()
        return __newobj_ex__, (self.__class__, new_args, kwargs), state, listitems, dictitems
    elif hasattr(self, "__getnewargs__"):
        new_args = self.__getnewargs__()
        return __newobj__, (self.__class__, *new_args), state, listitems, dictitems
    else:
        return __newobj__, (self.__class__,), state, listitems, dictitems


def _onlyOneDimSameTypeNumbers(list_or_tuple):
    if len(list_or_tuple):
        type_first = type(list_or_tuple[0])
        if type_first in _bool_int_and_float_types:
            return all(type(elt) is type_first for elt in list_or_tuple)
    return False


def _onlyOneDimNumbers(list_or_tuple):
    if len(list_or_tuple):
        return all(type(elt) in _bool_int_and_float_types for elt in list_or_tuple)
    return False


if use_numpy:
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
    _bool_int_and_float_types = set(
        (
            float,
            int,
            bool,
        )
    )


# --- Load -------------------------------------------------------


def const(self):
    return consts[self]
    # raise ValueError(f"{self} : {value} don't seems to be a const value")


# @profile
def instance(
    __class__=object, __init__=None, __state__=None, __new__=None, __initArgs__=None, __items__=None, **argsSup
):
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
    inst = None
    if type(__class__) is str:
        if (
            __class__ == "type"
        ):  # == ne permet pas de comparer numpy.dtype(), is fait planter array.array('i', [1, 2, 3])
            if __init__ == "NoneType":
                return type(None)
            elif __init__:
                return class_from_class_str(__init__)
            else:
                return type
        try:
            # acceleration en allant directement charcher la class_ à partir de la string dans un dictionnaire de cash
            class_ = class_from_class_str_dict[__class__]
        except:
            class_ = class_from_class_str_dict[__class__] = class_from_class_str(__class__)
    else:
        if type(__class__) is dict:
            # permet de gere le cas ou on donne directement un dictionnaire en premier argument
            return instance(**__class__)
        elif isclass(__class__):
            class_ = __class__
        elif isInstance(__class__):  # arrrive avec serializeRepr
            inst = __class__
            class_ = inst.__class__
        else:
            raise Exception(
                "erreure lors de la creation d'instance le premier parametre de Instance() n'est ni une classe , ni string representant un classe , ni une instance, ni un dictionnaire, ni un callable (fonction)"
            )

    if inst is None:

        if __new__ is not None or __init__ is None:
            __new__type = type(__new__)
            if __new__type in (list, tuple):
                inst = class_.__new__(class_, *__new__)
            elif __new__type is dict:
                inst = class_.__new__(class_, **__new__)
            elif __new__ is not None:
                inst = class_.__new__(class_, __new__)  # when braces have been removed during serialization
            else:
                inst = class_.__new__(class_)  # __init__ is None
            if (
                __init__ is not None
            ):  # EN VRAI N'ARRIVE JAMAIS AVEC PICKLE, pourrait arriver avec methode __serialisejson__ ou plugin
                __init__type = type(__init__)
                if __init__type in (list, tuple):
                    inst.__init__(*__init__)
                elif __init__type is dict:
                    inst.__init__(**__init__)
                else:
                    inst.__init__(__init__)  # when braces have been removed during serialization
        elif __init__ is not None:
            __init__type = type(__init__)
            if __init__type in (list, tuple):
                inst = class_(*__init__)
            elif __init__type is dict:
                inst = class_(**__init__)
            else:
                inst = class_(__init__)  # when braces have been removed during serialization

    if __items__:
        try:
            inst.update(__items__)
        except:
            inst.extend(__items__)

    if argsSup:
        __state__ = argsSup

    if __state__:
        if hasattr(inst, "__setstate__"):
            # j'ai du remplacer hasMethod(inst,"__setstate__") par hasattr(inst,"__setstate__") pour pouvoir deserialiser des sklearn.tree._tree.Tree en json "__setstate__" n'est pas reconnu comme étant une methdoe !? alors que bien là .
            inst.__setstate__(__state__)
        else:
            _setters = serialize_parameters.setters
            if _setters is True:
                _setters = setters.get(class_, True)
            elif type(_setters) is dict:
                _setters = _setters.get(class_, False)
            _properties = serialize_parameters.properties
            if _properties is True:
                _properties = properties.get(class_, True)
            elif type(_properties) is dict:
                _properties = _properties.get(class_, False)
            setstate(inst, __state__, setters=_setters, properties=_properties)
    return inst


valid_char_for_var_name = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")


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
                in_double_quotes = False
                in_simple_quotes = False
                in_number = False
                in_var = False
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
                        key = "".join(element_chars)
                        if in_var:
                            key = variables[key] if key in variables else __builtins__[key]
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
                        current = variables[element] if element in variables else __builtins__[element]
                    else:
                        raise Exception("firts element of path must be a name_of_variable")
                    is_first = False
                else:
                    if in_var:
                        element = variables[element] if element in variables else __builtins__[element]
                    current = _getattr(
                        current, element, accept_dict_as_object
                    )  # permet de marcher avec slot et properties,mais pas getters
                element_chars = []
            in_squares = True
            in_var = False
            first_ch_of_square = True

        elif ch == ".":
            if element_chars:
                element = "".join(element_chars)
                if is_first:
                    if in_var:
                        current = variables[element] if element in variables else __builtins__[element]
                    else:
                        raise Exception("firts element of path must be a name_of_variable")
                    is_first = False
                else:
                    if in_var:
                        element = variables[element] if element in variables else __builtins__[element]
                    current = _getattr(
                        current, element, accept_dict_as_object
                    )  # permet de marcher avec slot et properties,mais pas getters
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
                current = variables[element] if element in variables else __builtins__[element]
            else:
                raise Exception("firts element of path must be a name_of_variable")
        else:
            if in_var:
                element = variables[element] if element in variables else __builtins__[element]
            current = _getattr(
                current, element, accept_dict_as_object
            )  # permet de marcher avec slot et properties,mais pas getters
    return current


def _getattr(obj, attribut, accept_dict_as_object):
    if accept_dict_as_object and type(obj) is dict and "__class__" in obj:
        return obj[attribut]
    else:
        try:
            return getattr(obj, attribut)  # permet de marcher avec slot et properties,mais pas getters
        except:
            for methode in [f"get{attribut}", f"get_{attribut}", f"get{attribut[0].upper()}{attribut[1:]}"]:
                if hasattr(obj, methode):
                    return getattr(obj, methode)()
            raise


def _get_getters(extra_getters):
    if isinstance(extra_getters, bool):
        return extra_getters
    else:
        getters_ = getters.copy()
        if isinstance(extra_getters, dict):
            for class_, class_getters in extra_getters.items():
                getters_[class_] = class_getters
        if isinstance(extra_getters, (list, set, tuple)):
            for class_ in extra_getters:
                getters_[class_] = True
        elif extra_getters is not None:
            raise TypeError(
                "Encoder getters argument must be None, bool, list, tuple, set or dict, not '%s'" % type(extra_getters)
            )
        return getters_


def _get_setters(extra_setters):
    if isinstance(extra_setters, bool):
        return extra_setters
    elif extra_setters is None:
        return setters
    else:
        setters_ = setters.copy()
        if isinstance(extra_setters, dict):
            for class_, class_setters in extra_setters.items():
                setters_[class_] = class_setters
        if isinstance(extra_setters, (list, set, tuple)):
            for class_ in extra_setters:
                setters_[class_] = True
        else:
            raise TypeError(
                "Decoder setters argument must be None, bool, list, tuple, set or dict, not '%s'" % type(extra_setters)
            )
        return setters_


def _get_properties(extra_properties):
    if isinstance(extra_properties, bool):
        return extra_properties
    elif extra_properties is None:
        return properties
    else:
        properties_ = properties.copy()
        if isinstance(extra_properties, dict):
            for class_, class_properties in extra_properties.items():
                properties_[class_] = class_properties
        if isinstance(extra_properties, (list, set, tuple)):
            for class_ in extra_properties:
                properties_[class_] = True
        else:
            raise TypeError(
                "Decoder properties argument must be None, bool, list, tuple, set or dict, not '%s'"
                % type(extra_properties)
            )
        return properties_


# --- Import of plugins -------------------------------------------------------

from . import plugins  # needed for plugin regord
