r"""
serializejson
=============

+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **Authors**               | `Baptiste de La Gorce <contact@smartaudiotools.com>`_                                                                    |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **PyPI**                  | https://pypi.org/project/serializejson                                                                                   |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **Documentation**         | https://smartaudiotools.github.io/serializejson                                                                          |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **Sources**               | https://github.com/SmartAudioTools/serializejson                                                                         |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **Issues**                | https://github.com/SmartAudioTools/serializejson/issues                                                                  |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **Noncommercial license** | `Prosperity Public License 3.0.0 <https://github.com/SmartAudioTools/serializejson/blob/master/LICENSE-PROSPERITY.rst>`_ |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **Commercial license**    | `Patron License 1.0.0 <https://github.com/SmartAudioTools/serializejson/blob/master/LICENSE-PATRON.rst>`_                |
|                           | ⇒ `Sponsor me ! <https://github.com/sponsors/SmartAudioTools>`_ or `contact me ! <contact@smartaudiotools.com>`_         |
+---------------------------+--------------------------------------------------------------------------------------------------------------------------+


**serializejson**  is a python library for fast serialization and deserialization
of python objects in `JSON <http://json.org>`_  designed as a safe, interoperable and human-readable drop-in replacement for the Python `pickle <https://docs.python.org/3/library/pickle.html>`_ package.
Complex python object hierarchies are serializable, deserializable or updatable in once, allowing for example to save or restore a complete application state in few lines of code.
The library is build upon
`python-rapidjson <https://github.com/python-rapidjson/python-rapidjson>`_ and
`blosc <https://github.com/Blosc/python-blosc>`_  for optional `zstandard <https://github.com/facebook/zstd>`_ compression.

Some of the main features:

- supports Python 3.7 (maybe lower) or greater.
- serializes arbitrary python objects into a dictionary by adding `__class__` ,and eventually `__init__`, `__new__`, `__state__`, `__items__` keys.
- calls the same objects methods as pickle. Therefore almost all pickable objects are serializable with serializejson without any modification.
- for not already pickable object, you will allways be able to serialize it by adding methodes to the object or creating plugins for pickle or serializejson.
- generally 2x slower than pickle for dumping and 3x slower than pickle for loading (on your benchmark) except for big arrays (optimisation will soon be done).
- serializes and deserializes bytes and bytearray very quickly in base64, encoded and decoded in C++ directly from and into the JSON stream, with lossless `blosc <https://github.com/Blosc/python-blosc>`_ compression.
- serialize properties and attributes with getters and setters if wanted (unlike pickle).
- json data will still be directly loadable if you have transform some attributes in slots or properties in your code since your last serialization. (unlike pickle)
- can serialize `__init__(self,..)` arguments by name instead of positions, allowing to skip arguments with defauts values and making json datas robust to a change of `__init__` parameters order.
- serialized objects take generally less space than when serialized with pickle: for binary data, the 30% increase due to base64 encoding is in general largely compensated using the lossless `blosc <https://github.com/Blosc/python-blosc>`_ compression.
- serialized objects are human-readable and easy to read. Unlike pickled data, your data will never become unreadable if your code evolves: you will always be able to modify your datas with a text editor (with find & replace for example if you change an attribut name).
- serialized objects are text and therefore versionable and comparable with versionning and comparaison tools.
- can safely load untrusted / unauthenticated sources if authorized_classes list parameter is set carefully with strictly necessary objects (unlike pickle).
- can update existing objects recursively instead of override them. serializejson can be used to save and restore in place a complete application state (⚠ not yet well tested).
- filters attribute starting with "_" by default (unlike pickle). You can keep them if wanted with `filter_ = False`.
- numpy arrays can be serialized as lists with automatic conversion in both ways or in a conservative way.
- supports circular references and serialize only once duplicated objects, lists and dictionaries, using "$ref" key an path to the first occurance in the json : `{"$ref": "root.xxx.elt"}`.
- accepts json with comment (// and /\* \*/) if `accept_comments = True`.
- can automatically recognize objects in json from keys names and recreate them, without the need of `__class__` key, if passed in `recognized_classes`.
- serializejson is easly interoperable outside of the Python ecosystem with this recognition of objects from keys names or with `__class__` translation between python and other language classes.
- dump and load support string path.
- can iteratively encode (with append) and decode (with iterator) a list in json file, which helps saving memory space during the process of serialization and deserialization and useful for logs.

.. warning::

    **⚠** Do not load serializejson files from untrusted / unauthenticated sources without carefully setting the load authorized_classes parameter.

    **⚠** Never dump a dictionary with the `__class__` key, otherwise serializejson will attempt to reconstruct an object when loading the json.
    Be careful not to allow a user to manually enter a dictionary key somewhere without checking that it is not `__class__`.
    Due to current limitation of rapidjson we cannot we cannot at the moment efficiently detect dictionaries with the `__class__` key to raise an error.


Installation
============

**Last offical release**

.. code-block::

    pip install serializejson

**Developpement version unreleased**

.. code-block::

    pip install git+https://github.com/SmartAudioTools/serializejson.git

Examples
================

**Serialization with fonctions API**

.. code-block:: python

    import serializejson

    # serialize in string
    object1 = set([1,2])
    dumped1 = serializejson.dumps(object1)
    loaded1 = serializejson.loads(dumped1)
    print(dumped1)
    >{
    >        "__class__": "set",
    >        "__init__": [1,2]
    >}


    # serialize in file
    object2 = set([3,4])
    serializejson.dump(object2,"dumped2.json")
    loaded2 = serializejson.load("dumped2.json")

**Serialization with classes based API.**

.. code-block:: python

    import serializejson
    encoder = serializejson.Encoder()
    decoder = serializejson.Decoder()

    # serialize in string

    object1 = set([1,2])
    dumped1 = encoder.dumps(object1)
    loaded1 = decoder.loads(dumped1)
    print(dumped1)

    # serialize in file
    object2 = set([3,4])
    encoder.dump(object2,"dumped2.json")
    loaded2 = decoder.load("dumped2.json")

**Update existing object**

.. code-block:: python

    import serializejson
    object1 = set([1,2])
    object2 = set([3,4])
    dumped1 = serializejson.dumps(object1)
    print(f"id {id(object2)} :  {object2}")
    serializejson.loads(dumped1,obj = object2, updatables_classes = [set])
    print(f"id {id(object2)} :  {object2}")

**Iterative serialization and deserialization**

.. code-block:: python

    import serializejson
    encoder = serializejson.Encoder("my_list.json",indent = None)
    for elt in range(3):
        encoder.append(elt)
    print(open("my_list.json").read())
    for elt in serializejson.Decoder("my_list.json"):
        print(elt)
    >[0,1,2]
    >0
    >1
    >2

More examples and complete documentation `here <https://smartaudiotools.github.io/serializejson/>`_

License
=======

Copyright 2020 Baptiste de La Gorce

For noncommercial use or thirty-day limited free-trial period commercial use, this project is licensed under the `Prosperity Public License 3.0.0 <https://github.com/SmartAudioTools/serializejson/blob/master/LICENSE-PROSPERITY.rst>`_.

For non limited commercial use, this project is licensed under the `Patron License 1.0.0 <https://github.com/SmartAudioTools/serializejson/blob/master/LICENSE-PATRON.rst>`_.
To acquire a license please `contact me <mailto:contact@smartaudiotools.com>`_, or just `sponsor me on GitHub <https://github.com/sponsors/SmartAudioTools>`_ under the appropriate tier ! This funding model helps me making my work sustainable and compensates me for the work it took to write this crate!

Third-party contributions are licensed under `Apache License, Version 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_ and belong to their respective authors.
"""

try:
    import importlib.metadata as importlib_metadata  # New in version 3.8
except ModuleNotFoundError:
    import importlib_metadata
try:
    __version__ = importlib_metadata.version("serializejson")
except:
    pass
import os
import queue
import re
import threading
import time
import types
import warnings
import weakref
import io
try:
    # roue installée : le module compilé vit dans le paquet
    from . import rapidjson
except ImportError:
    # dépôt de développement : module compilé de rapidjson/, exposé sous le
    # même nom pour les imports « from serializejson import rapidjson »
    import rapidjson
    import sys as _sys

    _sys.modules[__name__ + ".rapidjson"] = rapidjson
import gc
import copyreg
import atexit
import errno
from copyreg import dispatch_table
from collections import deque, Counter, OrderedDict, defaultdict
from base64 import b64decode, b64encode
from _collections_abc import list_iterator

try:
    import numpy
    from numpy import ndarray

    use_numpy = True
except ModuleNotFoundError:
    use_numpy = False
from . import serialize_parameters
from . import indexation
from enum import Enum


# def add_authorized_classes(*classes):
#    if len(classes) == 0 and type(classes[0]) in (tuple,list,set):
#        classes = classes[0]
#    for elt in classes:
#        if not type(elt) is str:
#            elt = class_str_from_class(elt)
#        authorized_classes.add(elt)

from .tools import (
    getstate,
    setstate,
    instance,
    _type_values_cache,
    tuple_from_instance,
    class_str_from_class,
    class_from_class_str,
    from_name,
    _get_getters,
    _get_setters,
    _get_properties,
    encoder_parameters,
    _onlyOneDimSameTypeNumbers,
    _onlyOneDimNumbers,
    blosc_compressions,
    blosc2_compressions,
    bareme_smart,
    bareme_smart_defaut_ram,
    bareme_smart_defaut_fichier,
    bareme_smart_reserves,
    use_blosc2_cpp,
    use_blosc2_fork,
    serializejson_,
    serializejson_builtins,
    class_has_user_getstate,
    setters as _setters_registry,
    getters as _getters_registry,
    properties as _properties_registry,
    slots_properties_getters_setters_from_class,
    setters_names_from_class,
    slots_from_class,
    authorized_classes,
    Reference,
    constructors,
    rehydrate_getters,
)


# seuils de compression par ESPÈCE de charge (voir bytes_size_compression_
# threshold) : les tableaux numpy portent un dtype et une forme, leur contenu
# est assez régulier pour que la compression se paie dès 512 octets ; les
# bytes et bytearray nus sont des blocs opaques, le plus souvent DÉJÀ
# compressés (jpeg, zip, chiffré...) — ils ne sont compressés que sur demande
SEUILS_COMPRESSION_DEFAUT = {"numpy": 512, "bytes": None}
# seuil qu'aucune taille n'atteint : la traduction de « jamais compressé »
JAMAIS = 1 << 62


authorized_classes.update(
    {
        "bytes",
        "bytearray",
        "complex",
        "frozenset",
        "tuple",
        "type",
        "range",
        "set",
        "slice",
        "dict",
        "dict_non_str_keys",
        "collections.Counter",
        "collections.defaultdict",
        "collections.deque",
        "collections.OrderedDict",
    }
)

__all__ = [
    "dumps",
    "dump",
    "loads",
    "load",
    "append",
    "index",
    "paths",
    "wait_writes",
    "Encoder",
    "Decoder",
    "getstate",
    "class_from_class_str",
]
# flag allowing to keep None as allowed value for Encoder default_value.
no_default_value = []

# Py_TPFLAGS_HEAPTYPE : distingue les classes définies en Python des types natifs
_TPFLAGS_HEAPTYPE = 1 << 9


# --- FONCTIONS BASED API ----------------------


def dump(obj, file, **argsDict):
    """
    Dump an object into json file.

    Args:
        obj: object to dump.
        file (str or file-like): path or file.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    # on ne referme que ce qu'on a ouvert soi-même
    Encoder(**argsDict).dump(obj, file, close=isinstance(file, str))


# instances PAR DÉFAUT réutilisées par dumps/dumpb/loads (une par thread) :
# la construction d'un Encoder/Decoder à chaque appel coûtait ~11/7 µs — le
# plancher qui écrasait tout dump ou load d'objet modeste. L'état volatil
# (mémo, classes rencontrées, racine) est remis à zéro par l'appel lui-même ;
# le drapeau occupe couvre la RÉENTRANCE (un reduce/hook utilisateur qui
# rappelle dumps pendant un dump) : instance fraîche dans ce cas, comme avant.
# Les trois instances et le drapeau vivent dans UN seul objet (_EtatParDefaut),
# lui-même accroché à UN seul attribut threading.local : un dump/load normal
# ne paie qu'une résolution de fil (le coût réel de threading.local) au lieu
# d'une par instance et par bascule du drapeau — le reste n'est plus que de
# l'accès d'attribut Python ordinaire, sur un objet déjà en main.
class _EtatParDefaut:
    __slots__ = ("encoder_str", "encoder_bytes", "decoder", "occupe")

    def __init__(self):
        self.encoder_str = None
        self.encoder_bytes = None
        self.decoder = None
        self.occupe = False


_instances_par_defaut = threading.local()


def _etat_par_defaut():
    etat = getattr(_instances_par_defaut, "etat", None)
    if etat is None:
        etat = _EtatParDefaut()
        _instances_par_defaut.etat = etat
    return etat


def dumps(obj, **argsDict):
    """
    Dump object into json string.
    If you want to return a bytes for pickle  drop-in pickle remplacement,
    your should ether replace `pickle.dumps` calls by `serializejson.dumpb` calls
    or make an `from serializejson import dumpb as dumps` at the start of your script

    Args:
        obj: object to dump.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    etat = _etat_par_defaut()
    if not argsDict and not etat.occupe:
        encoder = etat.encoder_str
        if encoder is None:
            encoder = etat.encoder_str = Encoder(return_bytes=False)
        etat.occupe = True
        try:
            return encoder(obj)
        finally:
            etat.occupe = False
    # par la méthode, et non par __call__ : c'est elle qui refuse un index,
    # qui n'a de sens que dans un fichier
    return Encoder(**argsDict).dumps(obj)


def dumpb(obj, **argsDict):
    """
    Dump object into json bytes.

    Args:
        obj: object to dump.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    etat = _etat_par_defaut()
    if not argsDict and not etat.occupe:
        encoder = etat.encoder_bytes
        if encoder is None:
            encoder = etat.encoder_bytes = Encoder(return_bytes=True)
        etat.occupe = True
        try:
            return encoder(obj)
        finally:
            etat.occupe = False
    return Encoder(**argsDict).dumpb(obj)


def append(obj, file=None, *, indent="\t", **argsDict):
    """
    Append an object into json file.

    The file stays a valid json list, byte-for-byte identical to what the
    direct serialization of the complete list would produce (appended
    elements are indented one level). It can be reloaded in one call with
    `load()`, or element by element with `for element in Decoder(file)`.

    Args:
        obj: object to dump.
        file (str or file-like):
            path or file. The file must be empty or containing a json list.
        indent: indent passed to Encoder.
        **argsDict: other parameters passed to the Encoder (see documentation).
    """
    # un append isolé n'indexe QUE si on le lui demande : l'encodeur ne
    # survit pas à l'appel, il ne peut donc rien accumuler d'un maillon à
    # l'autre, et l'index posé d'office coûterait un balayage du document
    # entier à chaque élément ajouté
    argsDict.setdefault("index", None)
    Encoder(indent=indent, **argsDict).append(obj, file, close=True)


def loads(json, *, obj=None, iterator=False, **argsDict):
    # on ne peut pas en meme temps updater objet
    """
    Load an object from a json string or bytes.

    Args:
        json:
            the json string or bytes.
        obj (optional):
            If provided, the object `obj` will be updated and no new object will be created.
        iterator:
            if `True` and the json corresponds to a list then the items will be read one by one which reduces RAM consumption.
        **argsDict:
            parameters passed to the Decoder (see documentation).

    Return:
        created object, updated object if `obj` is provided or elements iterator if `iterator` is `True`.
    """
    if iterator:
        return Decoder(**argsDict)
    etat = _etat_par_defaut()
    if not argsDict and not etat.occupe:
        decoder = etat.decoder
        if decoder is None:
            decoder = etat.decoder = Decoder()
        etat.occupe = True
        try:
            return decoder.loads(json, obj)
        finally:
            etat.occupe = False
    return Decoder(**argsDict).loads(json, obj)


def load(file, *, obj=None, iterator=False, path=None, **argsDict):
    """
    Load an object from a json file.

    Args:
        file (str or file-like):
            the json path or file-like object.
        obj (optional):
            if provided, the object `obj` will be updated and no new object will be created.
        iterator:
            if `True` and the json corresponds to a list then the items will be read one by one which reduces RAM consumption.
        path (optional str):
            path of the wanted object inside the json, in the `$ref` grammar
            (`"root['clients'][3].name"`). If the file has an index, only the
            bytes of that object are read and parsed.
        **argsDict:
            parameters passed to the Decoder (see documentation).

    Return:
        created object, updated object if passed obj or elements iterator if iterator is True.
    """

    if iterator:
        # le fichier passait à la trappe (Decoder() sans file) : l'itérateur
        # rendu n'avait rien à lire — défaut préexistant, jamais testé
        return Decoder(file, **argsDict)
    else:
        return Decoder(**argsDict).load(file=file, obj=obj, path=path)


def index(file, form=indexation.FORME_DEFAUT,
          threshold=indexation.SEUIL_DEFAUT):
    """
    Build (or rebuild) the position index of an existing json file.

    Args:
        file (str): the json path.
        form:
            `"sidecar"` (default) for a hidden file of the same name preceded
            by a dot, `"comment"` for a comment line added at the end of the
            json (see the `index` parameter of the Encoder).
        threshold:
            containers smaller than that many bytes are not indexed.

    Return:
        the index. It holds only `root` when no container reaches `threshold`,
        and nothing is then written on disk.
    """
    rapidjson.wait_writes()
    return indexation.construit(file, form, threshold)


def paths(file):
    """
    Return the sorted paths indexed in a json file, `None` if it has no index.

    Those are the paths `load(file, path=...)` reaches without reading the
    rest of the document; any other path stays loadable, through its closest
    indexed ancestor.
    """
    rapidjson.wait_writes()
    index_ = indexation.lit(file)
    return None if index_ is None else sorted(index_["paths"])


def wait_writes():
    """
    Wait until the files dumped in `"fast_release"` mode are on the disk.

    `load`, `index` and `paths` already do it for you: this is only needed
    before handing a file over to something else — another process, `os.stat`,
    a copy — or before an interpreter that would end without `atexit` running.
    Raise the `OSError` of a write that failed after `dump` returned.
    """
    rapidjson.wait_writes()


def jsonpath(obj):
    """return the json path of loaded object"""
    return id_to_path.get(id(obj), None)


# recette C dédiée des collections (voir class_plan) : classe EXACTE -> genre
# entier lu par le C (2 deque, 3 Counter, 4 OrderedDict, 5 defaultdict)
_collections_natives = {deque: 2, Counter: 3, OrderedDict: 4, defaultdict: 5}


# les seuls flux dont write() dépose les octets tels quels dans le descripteur.
# Volontairement une LISTE BLANCHE de classes, et non un test sur la présence
# de fileno() : un GzipFile, un LZMAFile, un SSLSocket en ont un et écrire
# dedans passerait à côté de la compression ou du chiffrement — silencieusement
_FLUX_A_DESCRIPTEUR = (io.BufferedWriter, io.BufferedRandom, io.FileIO)


# Un dump rendu sans attendre le disque ne doit pas être perdu si le programme
# se termine dans la foulée : rien ne survit à la fin de l'interpréteur.
atexit.register(rapidjson.wait_writes)


def _descripteur(fp):
    """Descripteur d'un flux qui écrit ses octets tels quels, sinon None.

    Écrire dans le descripteur évite de fabriquer un objet bytes par tranche —
    un tiers du temps — et surtout permet le thread d'écriture, puisque les
    octets déposés n'appartiennent alors à aucun objet python : dump n'attend
    plus le disque (voir rapidjson/fdwritestream.h pour les mesures).
    """
    if not isinstance(fp, _FLUX_A_DESCRIPTEUR):
        return None
    try:
        fd = fp.fileno()
    except (OSError, ValueError, AttributeError):
        return None
    # ce que l'appelant a déjà écrit dort peut-être dans le tampon python : il
    # doit partir AVANT nos octets, sinon le document sort dans le désordre
    fp.flush()
    return fd


# --- CLASSES BASED API -------------------------------------------------------


class Encoder(rapidjson.Encoder):
    """
    class for serialization of python objects into json.

    Args:
        file (str or file-like):
            The json path or file-like object.
            When specified, the encoded result will be written there
            if you don't pricise file to`dump()` method later.

        attributes_filter (bool or set/list/tuple):
            Controls whether remove "private" attributs starting with "_" from the saved state
            for objects without plugin, __getstate__,__serializejson__ or reimplemented
            __reduce_ex__ or __reduce__ methodes.

            - `False` : filter private attributes to none classes (if not filtered in __reduce__ or __gestate__ methodes)
            - `True` : filter private attributes for all classes
            - `set/list/tuple` : filter private attributes for this classes

            Use it temporarily.

            - In order to stay compatible with pickle,you sould better code one of the __getstate__, __reduce_ex__,__reduce__ or a pickle plugin, filtering attributes starting with "_".
            - Otherwise, in order to be independent of this parameter, code a _serializejson__ method or serializejson plugin.
            - In this method or plugin you can call the helping function : state = serialize.__gestate__(self,attributes_filter = True)

        properties (bool, None, set/list/tuple, dict ):
            Controls whether add properties to the saved state
            for objects without plugin, __getstate__,__serializejson__ or reimplemented
            __reduce_ex__ or __reduce__ methodes.

            - `False` : add properties to none classes (as pickle)
            - `True` : add properties for all classes
            - `None` : (default) add properties defined in serializejson.properties dict (added by plugins or manualy before encoder call) (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )
            - `set/list/tuple` :  add all properties for classes in this set/list/tuple, in addition to properties defined in serializejson.properties dict [class1, class2,..] (not secure if unstruted json, use it only for debuging)
            - `dict` :  add properties defined in dict, in addition to properties defined in serializejson.properties dict {class1 : ["propertie1","propertie1"], class2: True}

            Use it temporarily.

            - In order to stay compatible with pickle, you sould better code one of the __getstate__, __reduce_ex__, __reduce__ or a pickle plugin, retrieving values for properties and returning them in the same dictionnary than __slots__, as the second element of a state tuple.
            - Otherwise, in order to be independent of this parameter, code a _serializejson__ method or serializejson plugin retrieving values for properties and return them in the state dictionnary.
            - In this method or plugin you can call the helping function : state = serialize.__gestate__(self, properties = True or list of properties names)

        getters (bool or set/list/tuple):
            Controls whether add values retrieve with getters to the saved state
            for objects without plugin, __getstate__,__serializejson__ or reimplemented
            __reduce_ex__ or __reduce__ methodes.

            - `False` : save no other getters than thus called in __getstate__ methodes, like pickle.
            - `True` : save getters for all objects
            - `None` : (default) save getters defined in serializejson.getter dict (added by plugins or manualy before encoder call) (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )
            - `set/list/tuple` : save getters for classes in set/list/tuple, in addition to getters defined in serializejson.setters dict [class1, class2,..] (not secure if unstruted json, use it only for debuging)
            - `dict` : save getters defined in dict, in addition to getters defined in serializejson.getters dict {class1 : {"attribut_name":"getter_name",...}, class2: True}

            Use it temporarily.

            - In order to stay compatible with pickle, you sould better code one of the __getstate__, __reduce_ex__, __reduce__ or a pickle plugin, retrieving values for getters and returning them in the state. And code a __setstate__ methode calling setters for this values .
            - Otherwise, in order to be independent of this parameter, code a _serializejson__ method or serializejson plugin retrieving values for getters and returning them in the state. And code a __setstate__ methode calling setters for this values or leave the Decpder's setters parameter as True.
            - In this method or plugin you can call the helping function : state = serialize.__gestate__(self,getters = True or {"a":"getA","b":"getB"}).  With getters as True, the getters will be automaticaly guessed. Wit getters as a dict allow the finest control and is faster because getters are not guessed from introspection. With tuple as key in this dict, you can retrieve several attributes values from one getter.

        remove_default_values (bool or set/list/tuple):
            Controls whether remove values same as their default value from the state in
            order to save memory space, for objects without plugin, __getstate__,
            __serializejson__ or reimplemented __reduce_ex__ or __reduce__ methodes.

            - `False` : remove defaul values to none classes
            - `True` : remove defaul values for all classes
            - `set/list/tuple` : remove defaul values for this classes.

            Use it temporarily.

            - Since the default values will not be stored and may change between different versions of your code, never use it for long term storage. Be aware that in order to know the default value, serializejson will create an insistence of the object's class without any __init__ argument.
            - In order to stay compatible with pickle, you sould better code one of the __getstate__, __reduce_ex__, __reduce__ or a pickle plugin, removing values same as their default value.
            - Otherwise, in order to be independent of this parameter, code a _serializejson__ method or serializejson plugin removing values same as their default value.
            - In this method or plugin you can call the helping function : state = serialize.__gestate__(self,remove_default_values = True or dict {name : default_value,...})

        chunk_size:
            Write the file in chunks of this size at a time.

        disk_write_mode ("fast_release" or "blocking"):
            When the file has a file descriptor, chunks are written by a
            dedicated thread.

            - "fast_release" (default) : `dump` returns as soon as the object is
              serialized, without waiting for the disk. Reading the file back
              with serializejson waits for you; anything else (another process,
              `os.stat`) must call `serializejson.wait_writes()` first.
            - "blocking" : `dump` returns only once everything is on the disk,
              as it did before.

        ensure_ascii:
            Whether non-ascii str are dumped with escaped unicode or utf-8.

        indent (None, int or '\\\\t'):
            Indentation width to produce pretty printed JSON.

            - `None` : Json in one line (quicker than with indent).
            - `int` : new lines and `indent` spaces for indent.
            - '\\\\t' : new lines and tabulations for indent (take less space than int > 1).

        single_line_init:
            whether `__init__` args must be serialized in one line.

        single_line_new:
            whether `__new__` args must be serialized in one line.

        single_line_list_numbers:
            whether list of numbers of same type must be serialize in one line.

        sort_keys:
            whether dictionary keys should be sorted alphabetically.
            Since python 3.7 dictionary order is guaranteed to be insertion order.
            Some codes may now rely on this particular order, like the key order of the state returned by __gestate__.

        bytes_compression(None, str or tuple):
            Compression for bytes, bytesarray and numpy arrays:

            - `"smart"` (the DEFAULT) : the LEVEL alone is chosen, and it
              picks the fastest configuration reaching that size — codec AND
              preprocessing chain. See the ladder below.
            - `None` : no compression, use only base 64.
            - `str` : compression name, with the default compression level (1):
              "blosc2_zstd", "blosc2", "blosc2_lz4", "blosc2_lz4hc" or "blosc2_zlib"
              (compression done in C without any Python round trip, needs a
              loadable libblosc2 — the bundled deterministic fork or the
              python-blosc2 wheel).
            - `tuple` : (compression name, compression level) with compression level from 0 (no compression) to 9 (maximum compression)

            The "smart" ladder, measured on 06/08/2026 over a corpus of
            images and sounds, end to end (whole dumps/loads, JSON envelope
            and base64 included) — every figure is a RATIO to pickle, pickle
            being measured BESIDE each configuration (reference = median of
            17 measurements, each one the median of 9 cold trials) :

            ===== ===================== ======= ====== ======
            level chain                 size    dump   load
            ===== ===================== ======= ====== ======
            0     base64 only           x1.333  x0.43  x1.89
            1     zigzag chain, lz4 1   x0.955  x0.87  x2.12
            2     zigzag chain, lz4 9   x0.928  x0.92  x2.10
            3     smart chain, lz4 1    x0.866  x0.97  x2.71
            4     smart chain, lz4 9    x0.837  x1.05  x2.84
            5     zigzag chain, zstd 1  x0.769  x1.27  x2.28
            6     smart chain, zstd 1   x0.722  x1.49  x2.96
            ===== ===================== ======= ====== ======

            Each level is the FASTEST configuration reaching its size, and
            two rules kept the ladder honest: no level may cost more to DUMP
            than a smaller one, and two configurations within 1 % of size are
            a single level. That is what makes the ladder start at x0.955:
            compressing "a little" (no filter, or plain byte shuffle, with
            blosclz or lz4) turns out to cost MORE to dump than the zigzag
            chain, which is also smaller. The price of the high levels is
            paid when DUMPING (x0.43 to x1.49); loading varies much less
            (x1.89 to x2.96). `"smart"` without a level picks the level from
            the TARGET: level 1 for in-memory dumps (`dumps`/`dumpb`), the
            first one that compresses and the last whose dumping stays under
            pickle's — and level 6, the smallest, for file dumps
            (`dump`/`append`), whose compression happens in the writer
            thread AFTER dump has returned, so its cost no longer blocks the
            caller. Level 6 gives the bytes of the historical default
            ("blosc2_zstd" 1).
            Levels 7, 8 and 9 are deliberately FREE, reserved for future
            methods going below x0.7: past level 6, zstd 2 then 3 ask for
            1.8x then 2.8x the dump time to gain 1.9 % and 2.4 % of size —
            what has to change there is the format, not the setting.
            Writing the legacy python-blosc v1 formats ("blosc_zstd",
            "blosclz"...) was removed on 05/08/2026; every v1 file remains
            READABLE (the bundled libblosc2 fork reads v1 frames, python-blosc
            is no longer a dependency).

        bytes_compression_diff_dtypes ("smart", "zigzag", "delta", "raw", tuple of dtype, or None)
            Delta stage added before the entropy coder, reducing a lot the
            compressed size of smooth data (signals, gradients, sorted
            values, timestamps...).
            The default is `"smart"`: integer arrays go through the "smart"
            chain — blocked axis-0 arithmetic derivative (computed by a
            blosc2 PREFILTER while the library builds each 512 KB block),
            then a registered zigzag filter (folding negatives between
            positives so that ±ε share their bits), then blosc2's native
            bitshuffle, then the chosen codec at the chosen level ; at load
            the cumulative sum is fused in a blosc2
            POSTFILTER, per block, multithreaded. Non-integer dtypes
            (floats included, whose arithmetic differences would not
            round-trip exactly) go through the registered byte-delta filter
            (byte delta after shuffle), bit-exact for all dtypes. No
            sampling, no probing: the chain is applied directly, and the
            compression level pilots the codec level.
            Two lighter chains exist beside it. `"zigzag"` is the smart chain
            WITHOUT its derivative (zigzag then bitshuffle, for every dtype)
            — it loads about twice as fast as a byte shuffle, blosc2's
            bitshuffle being vectorized, and it reaches sizes neither of the
            two others reach: the ladder uses it for its lighter levels, the
            DEFAULT one included. Two more are only reachable by hand, no
            level of the ladder using them: `"delta"` is shuffle then the
            registered byte-delta filter, for every dtype, without the
            blocked derivative, the zigzag and the bitshuffle ; `"raw"`
            disables every filter, leaving the codec alone — the cheapest
            chain to LOAD.
            A tuple of dtypes keeps the historical opt-in behavior (delta
            only for those dtypes, via the byte-delta filter). `None` or an
            empty tuple disables the delta stage entirely (plain shuffle).
            Left at its default `"smart"`, the value is chosen by the
            `bytes_compression="smart"` ladder; any other value wins over it.
            Every frame ever written ("_diff", "_diffb", v1 python-blosc)
            remains readable.


        bytes_compression_threads (int,str):
            Number of threads used for the compression.
            With the bundled deterministic libblosc2 fork, the compressed
            bytes are IDENTICAL whatever the number of threads (the legacy
            chunked parallel write format "b64_blosc2p" is no longer
            written, but remains readable).

            - `int` : number of threads user for the compression
            - `"cpus"`: use as many thread than cpu
            - `"determinist"` (default): multithreaded ONLY through a
              deterministic path — the bundled libblosc2 fork (internal
              multithread with stable bytes) — otherwise one thread. The
              compressed bytes are identical whatever the thread count.

        bytes_size_compression_threshold (int or dict):
            bytes size threshold beyond compression is tried to reduce size of
            bytes, bytesarray and numpy array if `bytes_compression` is not None.

            - `int` : same threshold for numpy arrays and for plain bytes and
              bytearray.
            - `dict` (default) : one threshold per kind, `None` meaning never
              compressed. The default is `{"numpy": 512, "bytes": None}` :
              numpy arrays carry a dtype and a shape, and their content is
              regular enough for the compression to pay for itself from 512
              bytes on, whereas plain bytes and bytearray are opaque blobs,
              most often already compressed (jpeg, zip, encrypted...) — they
              are only compressed if you ask for it, with for instance
              `bytes_size_compression_threshold={"numpy": 512, "bytes": 512}`
              or simply `bytes_size_compression_threshold=512`.

        array_readable_max_size (int,None or dict):
            Defines the maximum array.array size for serialization in readable numbers.
            By default array_readable_max_size is set to 0, all non empty arrays are encoded in base 64.

            - `int` : all arrays smaller than or egal to this size are serialized in readable numbers.
            - `None` : there is no maximum size and all arrays are serialized in readable numbers.
            - `dict` : for each typecode key, the value define the maximum size of this typecode arrays for serialization in readable numbers. If value is `None` there is no maximum and array of this typecode are all serialized in readable numbers. If you want only signed int arrays to be readable, then you should pass `array_readable_max_size = {"i":None}`

            .. note::
                serialization of int arrays can take much less space in readable,
                but is much slower than in base 64 for big arrays. If you have lot or large int arrays and
                performance matters, then you should stay with default value 0.


        numpy_array_readable_max_size (int,None or dict):
            Defines the maximum numpy array size  (product of the array’s dimensions) for serialization in readable numbers.
            By default numpy_array_readable_max_size is set to 0, all non empty numpy arrays are encoded in base 64.

            - `int` : all numpy arrays smaller than or egal to size are serialized in readable numbers.
            - `None` : there is no maximum size and all numpy arrays are serialized in readable numbers.
            - `dict` : for each dtype key, the value define the maximum size  of this dtype arrays for serialization in readable numbers. If value is `None` there is no maximum and numpy array of this dtype are all serialized in readable numbers. If you want only numpy arrays int32 to be readable, then you should pass `numpy_array_readable_max_size = {"int32":None}`

            .. note::

                serialization in readable can take much less space in int32 if the values ar smaller or equal to 9999,
                but is much slower than in base 64 for big arrays. If you have lot or large numpy int32 arrays and
                performance matters, then you should stay with default value 0.

        numpy_array_to_list:
            whether numpy array should be serialized as list.

            .. warning::

                This should be used only for interoperability with other json libraries.
                If you want readable  values in your json, we recommend to use instead
                `numpy_array_readable_max_size` which is not destructive.

                With `numpy_array_to_list` set to `True`:

                - numpy arrays will be indistinctable from list in json.
                - `Decoder(numpy_array_from_list=True)` will recreate numpy array from lists of bool, int or float, if not an `__init__` args list, with the the risque of unwanted convertion of lists to numpy arrays.
                - dtype of the numpy array will be loosed if not bool, int32 or float64 and converted to the bool, int32 or float64 when loading
                - Empty numpy array will be converted to [] without any way to guess the dtype and will stay an empty list when loading event with `numpy_array_from_list = True`

        numpy_types_to_python_types:
             whether numpy integers and floats outside of a array must be convert to python types.
             It save space and generally don't affect

        index ("sidecar", "comment" or None):
            Where `dump` writes the position index that lets
            `load(file, path=...)` read one object without parsing the rest.

            - "sidecar" (default) : a hidden file of the same name preceded by
              a dot. The json itself stays standard, readable by any parser.
            - "comment" : a zstd compressed comment line added at the end of
              the json. One single file to move, but the file is no longer
              standard json — `json.load`, `JSON.parse` and `jq` all stop on
              that line.
            - `None` : no index at all.

            The index is only written where the bytes of the json land as they
            are, in a named file: asked for elsewhere (a string, an anonymous
            stream, a compressed file) it raises, left to its default it keeps
            quiet. Nothing is written when no container reaches
            `index_threshold`, and an index left there by a previous `dump` is
            then removed.

        index_threshold:
            Containers smaller than that many bytes are not indexed. Their
            path stays loadable, through the closest indexed ancestor.

        strict_pickle (False by default)
            If True serialize with exactly the same behaviour than pickle:

            - disabling serializejson plugins for custom serialization.(no numpyB64)
            - disabling attributes_filter
            - disabling keys sorting
            - disabling numpy_array_to_list
            - disabling numpy_types_to_python_types
            - keeping __dict__ and __slots__ separated in a tuple if both, instead of merge them in a dictionnary (you should prepare __setstat__ methods to receive both a tuple or a dictionnary)
            - making same checks than pickle
            - raising the sames Errors than pickle

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




    """

    def __new__(
        cls,
        file=None,
        *,
        strict_pickle=False,
        return_bytes=True,
        attributes_filter=True,
        properties=False,
        getters=False,
        remove_default_values=False,
        chunk_size=65536,
        disk_write_mode="fast_release",
        ensure_ascii=False,
        indent="\t",
        single_line_init=True,
        single_line_new=True,
        single_line_list_numbers=True,
        sort_keys=False,
        bytes_compression="smart",
        bytes_compression_diff_dtypes="smart",
        bytes_size_compression_threshold=SEUILS_COMPRESSION_DEFAUT,
        bytes_compression_threads="determinist",
        array_use_arrayB64=True,  # le laisser ?
        array_readable_max_size=0,  # 'int32':-1
        numpy_array_use_numpyB64=True,  # le laisser ?
        numpy_array_readable_max_size=0,  # 'int32':-1
        numpy_array_to_list=False,
        numpy_types_to_python_types=True,
        index=indexation.NON_PRECISE,
        index_threshold=indexation.SEUIL_DEFAUT,
        protocol=4,  # protocol pour pickle
        **plugins_parameters,
    ):

        # if not bytes_to_string:
        #   bytes_mode = rapidjson.BM_NONE
        # else:
        #    bytes_mode = rapidjson.BM_UTF8

        if strict_pickle:
            attributes_filter = False
            sort_keys = False
            numpy_array_to_list = False
            numpy_types_to_python_types = False

        self = super().__new__(
            cls,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            bytes_mode=rapidjson.BM_NONE,
            number_mode=rapidjson.NM_NAN,
            iterable_mode=rapidjson.IM_ONLY_LISTS,
            mapping_mode=rapidjson.MM_ONLY_DICTS,
            return_bytes=return_bytes,
            # mémo C++ des dicts/listes déjà écrits : doublons et références
            # circulaires émis en {"$ref": ...} sans repasser par Python
            memo_refs=True,
            # listes homogènes de nombres sur une seule ligne, décidé en C++,
            # partout (attributs, valeurs de dicts purs, sous-listes)
            single_line_numbers=bool(single_line_list_numbers) and indent is not None,
            # transmis au C++ pour les chemins rapides (tuple, date...) : le
            # __new__/__init__ compact doit suivre ces drapeaux
            single_line_init=bool(single_line_init),
            single_line_new=bool(single_line_new),
            strict_pickle=bool(strict_pickle)
            # **argsDict
        )
        self.use_tuple_for_numpy_shape = False
        self.protocol = protocol
        self.attributes_filter = bool_or_set(attributes_filter)
        self.properties = _get_properties(properties)
        self.getters = _get_getters(getters)
        self.remove_default_values = bool_or_set(remove_default_values)
        self.file = file
        if indent is None:
            self.single_line_list_numbers = False
            self.single_line_init = False
            self.single_line_new = False
        else:
            self.single_line_list_numbers = single_line_list_numbers
            self.single_line_init = single_line_init
            self.single_line_new = single_line_new
        # rapid json enregistre self.indent_char et self.indent_count , mais ne permet pas de savoir si indent = None ...
        self.indent = indent
        self._dump_one_line = indent is None
        self.dumped_classes = set()
        self.chunk_size = chunk_size
        if disk_write_mode not in ("fast_release", "blocking"):
            raise ValueError('disk_write_mode must be "fast_release" or "blocking"')
        self.disk_write_mode = disk_write_mode
        bytes_compression_level = None  # niveau non précisé : voir plus bas
        profils_cible = None
        if bytes_compression is not None:
            if isinstance(bytes_compression, (list, tuple)):
                bytes_compression, bytes_compression_level = bytes_compression
            if bytes_compression == "smart":
                # barème : le NIVEAU choisit la configuration la plus RAPIDE
                # qui atteint son poids — codec ET chaîne de prétraitement.
                # Une chaîne demandée explicitement (bytes_compression_diff_-
                # dtypes autre que le défaut « smart ») reste prioritaire
                if bytes_compression_level is None:
                    # niveau non précisé : le barreau dépend de la CIBLE
                    # (choix de Baptiste, 10/08/2026) — la RAM (dumps/dumpb)
                    # prend le moins cher à écrire, le fichier (dump/append)
                    # le plus petit, la compression partie au fil d'écriture
                    # ne bloquant plus l'appelant. L'instance est configurée
                    # RAM ; _applique_profil bascule à l'entrée des méthodes
                    # d'écriture
                    profils_cible = tuple(
                        (comp, niveau,
                         chaine if bytes_compression_diff_dtypes == "smart"
                         else bytes_compression_diff_dtypes)
                        for comp, niveau, chaine in
                        (bareme_smart[bareme_smart_defaut_ram],
                         bareme_smart[bareme_smart_defaut_fichier]))
                    bytes_compression_level = bareme_smart_defaut_ram
                if bytes_compression_level not in bareme_smart:
                    reserve = (" (reserved for future methods going below"
                               " x0.7)"
                               if bytes_compression_level
                               in bareme_smart_reserves else "")
                    raise Exception(
                        f"smart compression level {bytes_compression_level}"
                        f"{reserve} unknown: smart levels go from 0 (no"
                        " compression, base64 only) to"
                        f" {max(bareme_smart)} (smallest)"
                    )
                (bytes_compression, bytes_compression_level,
                 chaine) = bareme_smart[bytes_compression_level]
                if bytes_compression_diff_dtypes == "smart":
                    bytes_compression_diff_dtypes = chaine
            if bytes_compression_level is None:
                # niveau par défaut d'une compression NOMMÉE, défini ici et
                # nulle part ailleurs (un tuple explicite le remplace)
                bytes_compression_level = 1
            if bytes_compression in blosc_compressions:
                # noms v1 python-blosc : l'écriture a été retirée (05/08/2026),
                # la lecture des fichiers v1 demeure
                raise Exception(
                    f"{bytes_compression}: v1 python-blosc write support was"
                    " removed, use a blosc2_* compression (v1 files remain"
                    " readable)"
                )
            if bytes_compression not in blosc2_compressions:
                raise Exception(
                    f"{bytes_compression} compression unknown. Available values for bytes_compression are "
                    f"{', '.join(blosc2_compressions)}"
                )
            if bytes_compression_level == 0:
                # niveau 0 = AUCUNE compression : ni en-tête blosc2, ni copie
                # dans un tampon de compression — la charge part en base64
                # comme avec bytes_compression=None, aux mêmes performances
                bytes_compression = None
        self.bytes_compression = bytes_compression
        self.bytes_compression_threads = bytes_compression_threads
        self.bytes_compression_diff_dtypes = bytes_compression_diff_dtypes
        # (compression, niveau, chaîne) par cible — [0] RAM, [1] fichier —
        # quand le barreau « smart » est resté au choix de la cible, None si
        # l'utilisateur a fixé le niveau (ou une compression nommée)
        self._profils_cible = profils_cible
        # sans compression le niveau est inerte : 0, le niveau qui la désigne
        self.bytes_compression_level = (
            0 if bytes_compression is None else bytes_compression_level)
        self.bytes_size_compression_threshold = bytes_size_compression_threshold
        # un seuil PAR ESPÈCE, résolu ici une fois pour toutes : les greffons
        # lisent les deux entiers, jamais le paramètre brut. `None` (jamais
        # compressé) devient un seuil qu'aucune taille n'atteint
        if isinstance(bytes_size_compression_threshold, dict):
            inconnues = set(bytes_size_compression_threshold) - {"numpy",
                                                                 "bytes"}
            if inconnues:
                raise Exception(
                    f"unknown bytes_size_compression_threshold keys"
                    f" {sorted(inconnues)}: available keys are 'numpy' and"
                    " 'bytes'"
                )
            seuils = {**SEUILS_COMPRESSION_DEFAUT,
                      **bytes_size_compression_threshold}
        else:
            seuils = {"numpy": bytes_size_compression_threshold,
                      "bytes": bytes_size_compression_threshold}
        self._seuil_numpy = (JAMAIS if seuils["numpy"] is None
                             else seuils["numpy"])
        self._seuil_bytes = (JAMAIS if seuils["bytes"] is None
                             else seuils["bytes"])
        self.array_use_arrayB64 = array_use_arrayB64
        self.array_readable_max_size = array_readable_max_size
        self.numpy_array_to_list = numpy_array_to_list
        self.numpy_array_use_numpyB64 = numpy_array_use_numpyB64
        self.numpy_array_readable_max_size = numpy_array_readable_max_size
        self.numpy_types_to_python_types = numpy_types_to_python_types
        # forme refusée ici plutôt qu'au dump : l'erreur arriverait sinon
        # après l'écriture, sur un fichier déjà en place
        self._index_demande = index is not indexation.NON_PRECISE
        if not self._index_demande:
            index = indexation.FORME_DEFAUT
        elif index is not None and index not in indexation.FORMES:
            raise Exception(
                "index unknown: available values are None (no index), "
                + " and ".join(repr(f) for f in indexation.FORMES))
        self.index = index
        self.index_threshold = index_threshold
        self.strict_pickle = strict_pickle

        unexpected_keywords_arguments = set(plugins_parameters) - set(
            encoder_parameters
        )
        if unexpected_keywords_arguments:
            raise TypeError(
                "serializejson.Encoder got unexpected keywords arguments '"
                + ", ".join(unexpected_keywords_arguments)
                + "'"
            )
        self.plugins_parameters = encoder_parameters.copy()
        self.plugins_parameters.update(plugins_parameters)
        self._append_reset()
        return self

    def _applique_profil(self, fichier):
        # le barreau « smart » laissé au choix de la cible (niveau non
        # précisé) : bascule les trois attributs de compression vers le
        # profil RAM ou fichier, seulement quand il change — l'écriture d'un
        # attribut invalide la poussée amortie, la garder stable garde la
        # poussée
        profils = self._profils_cible
        if profils is not None:
            compression, niveau, chaine = profils[fichier]
            if (compression != self.bytes_compression
                    or niveau != self.bytes_compression_level):
                self.bytes_compression = compression
                self.bytes_compression_level = niveau
                self.bytes_compression_diff_dtypes = chaine

    def dump(self, obj, file=None, close=True):
        """
        Dump object into json file.

        Args:
            obj: object to dump.
            file (optional str or file-like):
                the json path or file-like object.
                When specified, json is written into this file.
                Otherwise json is written into the file passed to `Encoder()` constructor.
            close (optional bool):
               weither dump must close the file after dumping  (True by default).
        """
        self._applique_profil(True)
        if file is None:
            file = self.file
        self._append_reset()
        if isinstance(file, str):
            self.fp = open(file, "wb")
        else:
            self.fp = file
        fd = _descripteur(self.fp)
        # où ira l'index, calculé AVANT d'écrire : donnée à l'écrivain, cette
        # destination lui suffit à le ranger lui-même son dernier octet posé,
        # et dump rend la main sans avoir composé, dégonflé ni écrit le bloc
        ou = self._ou_ranger_index(file) if fd is not None else None
        self.__call__(obj, fp=self.fp, chunk_size=self.chunk_size,
                      fd=fd,
                      blocking_write=self.disk_write_mode == "blocking",
                      index_threshold=(self.index_threshold if self.index
                                       else 0),
                      index_range=ou)
        if close:
            self.fp.close()
            del self.fp
        if ou is None:
            self._index_apres_ecriture(file)

    def _ou_ranger_index(self, file):
        # l'écrivain ne range seul que là où tout est réuni : un index demandé,
        # d'une forme connue, et un fichier NOMMÉ dont les octets du json sont
        # ceux du fichier. Partout ailleurs c'est _index_apres_ecriture qui
        # décide — et qui crie, quand un index demandé n'a pas de place
        # un seuil nul n'est pas relevé à l'écriture (le C n'indexe qu'au-delà
        # de zéro) : c'est le balayage qui rend alors l'index, comme avant
        if self.index not in indexation.FORMES or self.index_threshold <= 0:
            return None
        chemin = self._chemin_index(file)
        if chemin is None:
            return None
        return (chemin, indexation.chemin_sidecar(chemin),
                self.index == "sidecar")

    @staticmethod
    def _chemin_index(file):
        # un index ne se range que là où les octets du json tombent TELS QUELS,
        # dans un fichier nommé : un GzipFile a bien un nom, mais ce que son
        # fichier contient n'est pas le document, et l'y indexer ne donnerait
        # que des positions fausses — silencieusement
        chemin = (file if isinstance(file, str)
                  else getattr(file, "name", None)
                  if isinstance(file, _FLUX_A_DESCRIPTEUR) else None)
        return chemin if isinstance(chemin, str) else None

    def _index_apres_ecriture(self, file):
        # ce qui reste à faire quand l'écrivain n'a pas pu s'en charger : le
        # json n'est pas parti droit dans un descripteur (flux python, fichier
        # compressé), et l'index se construit par BALAYAGE du document écrit,
        # exactement comme pour un fichier déjà là (serializejson.index)
        if self.index is None:
            return
        chemin = self._chemin_index(file)
        if chemin is None:
            # posé d'office, l'index se tait là où il n'a pas de place ;
            # demandé, il crie plutôt que de se perdre
            if self._index_demande:
                raise Exception("index needs a file path, not %r" % (file,))
            return
        # le json est relu depuis le disque : ce qui reste dans le tampon d'un
        # fichier encore ouvert n'y serait pas
        ouvert = getattr(self, "fp", file)
        if hasattr(ouvert, "flush"):
            ouvert.flush()
        rapidjson.wait_writes()
        indexation.construit(chemin, self.index, self.index_threshold)

    def dumps(self, obj):
        """
        Dump object into json string.
        """
        if self.index is not None and self._index_demande:
            raise Exception("index needs a file: use dump, not dumps")
        self._applique_profil(False)
        return self.__call__(obj, return_bytes=False)

    def dumpb(self, obj):
        """
        Dump object into json bytes.
        """
        if self.index is not None and self._index_demande:
            raise Exception("index needs a file: use dump, not dumpb")
        self._applique_profil(False)
        return self.__call__(obj, return_bytes=True)

    def close(self):
        # le crochet fermant de la liste dort dans le tampon C depuis le
        # dernier maillon : le fichier ne devient un json complet qu'ici, et
        # c'est donc ici, et seulement ici, que son index a un sens
        self._append_ferme()
        self._append_fd = None
        if self._append_a_ranger:
            self._index_apres_append()
        if hasattr(self, "fp"):
            self.fp.close()
            del self.fp
        # else :
        #    raise Exception("json file already closed")

    def _append_reset(self):
        # la liste en cours d'append est abandonnée : ni tampon, ni rang, ni
        # entrées d'index en attente. Appelé à la construction, et partout où
        # l'encodeur repart de zéro (dump, clear)
        self._append_ferme()
        self._index_append_oublie()
        self._append_a_ranger = False
        self._append_pour = None
        self._append_rang = None
        self._append_index_tenu = False
        self._append_chemin = None
        self._append_fd = None

    def _index_apres_append(self):
        self._append_a_ranger = False
        if self.index is None:
            self._index_append_oublie()
            return
        chemin = self._append_chemin
        if chemin is None:
            self._index_append_oublie()
            # posé d'office, l'index se tait là où il n'a pas de place ;
            # demandé, il crie plutôt que de se perdre — append le passait
            # jusqu'ici sous silence
            if self._index_demande:
                raise Exception("index needs a file path, not %r"
                                % (self._append_pour,))
            return
        rapidjson.wait_writes()
        if self._append_index_tenu:
            self._index_append_range(
                (chemin, indexation.chemin_sidecar(chemin),
                 self.index == "sidecar"),
                self.index_threshold,
                self.disk_write_mode == "blocking")
        else:
            # rien n'a été relevé en écrivant : la liste avait déjà des
            # maillons dont on ignore le nombre, ou le seuil est nul. L'index
            # se refait alors par BALAYAGE du document, et seulement s'il a
            # été demandé — un balayage à chaque append coûterait le document
            # entier par maillon ajouté
            self._index_append_oublie()
            if self._index_demande:
                indexation.construit(chemin, self.index, self.index_threshold)

    def _index_incremental(self):
        # un index tenu maillon par maillon suppose une forme connue, un seuil
        # et un fichier nommé dont les octets du json sont ceux du fichier
        return (self.index in indexation.FORMES
                and self.index_threshold > 0
                and self._append_chemin is not None)

    def clear(self, close=False):
        """
        Empty the json file (truncate to zero length) and reset the encoder.

        Useful to restart from scratch a file filled with `append()`.

        Args:
            close (optional bool):
                whether the file must be closed after clearing (False by
                default : the file stays open, ready for `append()`).
        """
        self._reset()
        self._update_serialize_parameters()
        self._append_reset()

        # self.file = open(self.file, "rb+")
        if isinstance(self.file, str):
            path = self.file
            if os.path.exists(path):
                self.fp = open(path, "rb+")
                self.fp.truncate(0)
            else:
                self.fp = open(path, "wb+")
        else:
            self.fp.truncate(0)
        if close:
            self.fp.close()
            del self.fp

    # @profile
    def append(self, obj, file=None, close=False):
        """
        Append object into json file.

        The file stays a valid json list, byte-for-byte identical to what
        the direct serialization of the complete list would produce. It can
        be reloaded in one call with `load()`, or element by element with
        `for element in Decoder(file)`.

        Args:
            obj: object to dump.
            file (optional str or file-like): path or file. If provided, the object will be
                dumped into this file instead of being dumped into the file passed at the Encoder
                constructor. The file must be empty or contain a json list.
            close :
                - `True` the file will be closed afterappend and reopen at the next append
                - `False` (by default) the file will be kepped open for the next append.
                You will have to manually close se file with encoder.close()


        """
        self._applique_profil(True)
        if file is None:
            file = self.file
        # la liste se poursuit tant qu'on ajoute au MÊME fichier : c'est ce
        # qui permet de tenir le rang des maillons, donc leur index, sans
        # relire le document — changer de cible repart de zéro
        suite = self._append_pour is file
        reprise = self._append_fd is not None and suite
        if reprise:
            # le tampon C tient la liste ouverte : le crochet fermant y dort
            # encore, et le maillon qui vient l'écrase. Rien à rouvrir, rien à
            # relire, rien à tronquer — c'est tout ce qui sépare cette voie du
            # détour python qu'elle remplace
            fp, fd = self.fp, self._append_fd
        else:
            ouvert = suite and hasattr(self, "fp")
            # l'append précédent peut encore être en vol : le fichier ne se
            # rouvre, ne se mesure et ne se tronque qu'une fois posé
            rapidjson.wait_writes()
            fp, vide = _open_for_append(self.fp if ouvert else file,
                                        self.indent, queue=not ouvert)
            self.fp = fp
            if not suite:
                self._append_pour = file
                self._append_chemin = self._chemin_index(file) or \
                    self._chemin_index(fp)
                # le rang d'un maillon ne se devine pas dans une liste qu'on
                # n'a pas remplie soi-même : son index passera par le balayage,
                # et ses $ref n'ont pas de chemin absolu composable
                self._append_rang = 0 if vide else None
                self._append_index_tenu = vide
                self._index_append_oublie()
            fd = _descripteur(fp)
        # La comptabilité d'append s'écrit DANS le __dict__, jamais par
        # `self.x = ...` : le `__setattr__` de la classe invalide la poussée
        # amortie des paramètres globaux, qui se rejouait donc à chaque
        # maillon — os.cpu_count() compris. 7,6 µs par append au lieu de
        # 2,9 (20 000 maillons de 57 octets). Aucun de ces attributs n'est
        # lu par les greffons ni par le C : rien à pousser.
        d = self.__dict__
        d["_append_a_ranger"] = True
        # chaque append est un dump indépendant : le protocole du tp_call C
        # (poussée amortie, mémo des doublons) se rejoue à chaque appel
        # le rang sert D'ABORD aux $ref : c'est lui qui donne « root[3] », la
        # racine des chemins du maillon. Il vaut donc dès qu'on connaît la
        # place, index tenu ou non — l'index, lui, a son propre témoin
        rang = -1 if self._append_rang is None else self._append_rang
        if fd is None:
            # flux dont les octets ne sont pas ceux du fichier (utf-16, gzip) :
            # l'ancienne voie, décalage d'indentation compris. Les positions
            # relevées ne seraient pas celles du fichier : pas d'index tenu
            d["_append_index_tenu"] = False
            self.__call__(obj, fp=_wrap_append_indent(fp, self.indent),
                          append=(rang, b"", b"", 0))
            _close_for_append(fp, self.indent)
        else:
            # le maillon est indenté d'un cran de plus que le document, et
            # suivi du crochet qui referme la liste — le fichier reste un json
            # valide entre deux appends
            # une fois faux, il le reste : un index à trous vaudrait moins que
            # pas d'index du tout
            d["_append_index_tenu"] = (self._append_index_tenu
                                       and self._index_incremental())
            plat = self.indent is None
            # la virgule qui sépare deux maillons : quand le fichier vient
            # d'être rouvert, `_open_for_append` l'a déjà écrite
            debut = b"" if not reprise else b"," if plat else \
                b",\n" + _append_indent_unit(self.indent).encode()
            fin = (b"]", 0) if plat else (b"\n]", 1)
            self.__call__(obj, fp=fp, chunk_size=self.chunk_size, fd=fd,
                          blocking_write=self.disk_write_mode == "blocking",
                          index_threshold=(self.index_threshold
                                           if self._append_index_tenu else 0),
                          append=(rang, debut) + fin)
            d["_append_fd"] = fd
            if rang < 0 and self._ref_impossible():
                # ce maillon porte un doublon ou un cycle, et ses « $ref » ont
                # été composés sans savoir où il tombe dans la liste : ils
                # désignent le maillon, quand la relecture les cherche depuis
                # la racine du document. On le retire, on compte enfin les
                # maillons déjà là — un balayage du fichier, qui ne se paie que
                # dans ce cas et une seule fois — et on le réécrit à son rang.
                self._append_ferme()
                self._append_fd = None
                # le maillon fautif est compté lui aussi : son rang est le
                # nombre de maillons moins un
                combien, depart = _bornes_maillons(fp)
                d["_append_rang"] = combien - 1
                fp.truncate(depart)
                fp.seek(depart)
                self.__call__(obj, fp=fp, chunk_size=self.chunk_size, fd=fd,
                              blocking_write=self.disk_write_mode == "blocking",
                              index_threshold=0,
                              append=(self._append_rang, b"") + fin)
                d["_append_fd"] = fd
        if self._append_rang is not None:
            d["_append_rang"] = self._append_rang + 1
        if close:
            self.close()

    def get_dumped_classes(self):
        """
        Return the all dumped classes.
        In order to reuse them as `authorize_classes` argument when loading with a ``serializejson.Decoder``.
        """
        return self.dumped_classes

    # @profile
    @staticmethod
    def _echappe_chemin_ref(path):
        # échappement JSON d'un chemin $ref composé en RawString : une clé de
        # dict peut contenir guillemets, antislashs ou contrôles — insérée
        # brute, elle rendait le document invalide (même règle que le C)
        if '"' not in path and "\\" not in path and path.isprintable():
            return path
        morceaux = []
        for ch in path:
            if ch == '"':
                morceaux.append('\\"')
            elif ch == "\\":
                morceaux.append("\\\\")
            elif ch == "\t":
                morceaux.append("\\t")
            elif ch == "\n":
                morceaux.append("\\n")
            elif ch == "\r":
                morceaux.append("\\r")
            elif ch < " ":
                morceaux.append("\\u%04x" % ord(ch))
            else:
                morceaux.append(ch)
        return "".join(morceaux)

    def default(self, inst):
        # Equivalent au calback "default" qu'on peut passer à dump ou dumps
        id_ = id(inst)
        if id_ in self._already_serialized:
            if not isinstance(inst, Enum):
                # identifiant de chemin enregistré à la première écriture, la
                # chaîne n'est construite que maintenant, pour les vrais $ref ;
                # _get_path (remontée gc.get_referrers) reste en secours pour
                # les encodages qui ne passent pas par le traqueur C++
                path_id = self._already_serialized[id_]
                if path_id is None:
                    path = self._get_path(
                        inst, already_explored=set([id(locals())])
                    )
                else:
                    path = self.json_path_from_id(path_id)
                if path is not None:
                    return rapidjson.RawString(
                        f'{{"$ref": "{self._echappe_chemin_ref(path)}"}}')
        else:
            self._already_serialized[id_] = self.json_path_id()
            self._already_serialized_keep_alive.append(inst)
        type_inst = type(inst)
        if self.numpy_types_to_python_types and type_inst in _numpy_types:
            return _numpy_dtypes_to_python_types[type_inst](inst)
        if use_numpy and type_inst is ndarray and self.numpy_array_to_list:
            if self._dump_one_line or not self.single_line_list_numbers:
                return (
                    inst.tolist()
                )  # A REVOIR : pas génial... va tester si nombres tous du meme type et ne pas pas utiliser rapidjson.NM_NATIVE?
            if inst.ndim in (1, 2) and inst.dtype.char in _array_rows_dtype_chars:
                # écrit directement depuis le buffer, entièrement côté C++ :
                # ni tolist(), ni aucun aller-retour Python par élément
                return rapidjson.ArrayRows(numpy.ascontiguousarray(inst))
            if inst.dtype in _numpy_float_dtypes:
                number_mode = self.number_mode
            else:
                number_mode = rapidjson.NM_NATIVE  # permet décceler pas mal
            # repli (float16, ndim > 2...) : sous-arbres compacts via SingleLine
            if inst.ndim == 1:
                return rapidjson.SingleLine(inst.tolist(), number_mode)
            return [rapidjson.SingleLine(elt.tolist(), number_mode) for elt in inst]
        if type_inst is tuple:
            # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tuple_from_instance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tuple_from_instance
            self.dumped_classes.add(tuple)
            dic = {"__class__": "tuple", "__new__": list(inst)}
        elif type_inst is Reference:
            # cible objet : mémo Python ; cible dict/liste : mémo C++ ;
            # remontée gc en dernier secours
            path_id = self._already_serialized.get(id(inst.obj))
            if path_id is None:
                path_id = self.json_path_id_of(inst.obj)
            if path_id is None:
                path = self._get_path(
                    inst.obj, already_explored=set([id(inst.__dict__)])
                )
            else:
                path = self.json_path_from_id(path_id)
            if path is None:
                raise ValueError(
                    "serializejson : Reference to an object that is not in "
                    f"the document (type {type(inst.obj).__name__}) — it must "
                    "be serialized before being referenced"
                )
            return rapidjson.RawString(
                '{"$ref": "%s%s"}'
                % (self._echappe_chemin_ref(path), inst.sup_str))
        else:
            dic = self._dict_from_instance(
                inst
            )  # 8.6 % (correspond au temps pour conversion en b64) du temps sur obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)

        # plus d'emballage SingleLine ici (retiré le 06/08/2026) : la mise en
        # ligne des listes __init__/__new__ d'une enveloppe est une règle du
        # WRITER (single_line_init/new appliqués par la branche dict du C aux
        # dicts d'état, mêmes octets) — SingleLine ne sert plus qu'aux
        # sous-arbres qui portent un number_mode propre (repli numpy).
        # Les listes homogènes de nombres sont quant à elles mises sur une
        # ligne par le C++ lui-même (single_line_numbers), où qu'elles soient
        # self._already_serialized_id_dic_to_obj_dic[id(dic)] = (
        # inst,
        #    dic,
        # )  # important de metre dic avec sinon il va être detruit et son identifiant va être réutilisé.
        # if self.add_id:
        #    dic["_id"] = id_
        return dic
        # raise TypeError('%r is not JSON serializable' % inst)

    # Les doublons et cycles de dicts/listes sont gérés par le mémo C++ du
    # rapidjson du dépôt (memo_refs=True) : plus aucun aller-retour Python par
    # conteneur. Les hooks default_dict/default_list de l'Encoder C++ restent
    # disponibles pour d'autres usages.

    def class_plan(self, class_):
        # Chemin rapide par classe, consulté par le C++ UNE fois par classe et
        # par dump : None -> chemin Python complet (default/reduce) ; sinon
        # (nom_de_classe, filtrer_underscores) -> les objets de cette classe
        # sont écrits entièrement en C++ ({"__class__": nom, attributs du
        # __dict__ triés}, mémo des doublons et rigueur du __dict__ partagé
        # compris). Les conditions reproduisent exactement le chemin Python
        # par défaut : au moindre doute, None.
        try:
            if self.strict_pickle or self.remove_default_values:
                return None
            if not isinstance(class_, type):
                return None
            # recette __serializejson__ : la méthode est appelée par objet
            # (seul Python restant), l'emballage s'écrit en C. Mêmes
            # exclusions que tuple_from_instance : le registre plugins
            # (serializejson_) prime sur la méthode — classes du registre en
            # voie Python pour l'instant ; Enum a son traitement dans
            # default() ; les noms remove_add_braces ont un déballage à part
            registry_fn = serializejson_.get(class_)
            if registry_fn is not None:
                # le registre plugins PRIME sur la méthode (ordre de
                # tuple_from_instance). Seul array.array est mis en recette :
                # les autres entrées (datetime.datetime, ndarray, scalaires
                # et dtype numpy) ont une branche C dédiée ou un traitement
                # default() en amont que la recette court-circuiterait
                if class_.__module__ == "array" and class_.__name__ == "array":
                    # tuple[0] des plugins est la CLASSE : le nom émis est
                    # précalculé ici, le C l'utilise quand tuple[0] n'est
                    # pas une chaîne
                    return (None, registry_fn,
                            bool(self.numpy_array_to_list), "array.array")
                return None
            # recette builtins à forme chaîne : type / function / module —
            # leur fonction du tableau builtins rend déjà (nom_str, args,
            # état), exactement la forme que la branche recette C émet.
            # bytes et bytearray aussi depuis le 05/08 au soir : leurs formes
            # (chaîne ascii seule, ou [charge, étiquette]) sont écrites par
            # la recette C à l'identique du chemin Python — seul Python
            # restant : l'appel du plugin par objet
            builtin_fn = serializejson_builtins.get(class_)
            if builtin_fn is not None:
                if class_ is type:
                    # marqueur "type" : le C mémoïse classe -> nom au premier
                    # passage recette, puis écrit l'enveloppe sans python
                    return (None, builtin_fn,
                            bool(self.numpy_array_to_list), "type")
                if class_ in (types.FunctionType, bytes, bytearray):
                    return (None, builtin_fn, bool(self.numpy_array_to_list))
                return None
            # set / frozenset : recette privée « éléments à plat » — la
            # branche recette C écrit alors {"__class__": "set",
            # "__init__": [éléments]}, la même forme que le chemin Python
            # (reduce puis déballage remove_add_braces)
            if class_ is set:
                # 4e élément "set"/"frozenset" : le C compose lui-même le
                # tuple recette (nom, list(obj), None) sans appel python
                return (None, _recette_set, bool(self.numpy_array_to_list),
                        "set")
            if class_ is frozenset:
                return (None, _recette_frozenset,
                        bool(self.numpy_array_to_list), "frozenset")
            method = getattr(class_, "__serializejson__", None)
            if method is not None:
                if (
                    issubclass(class_, Enum)
                    or class_str_from_class(class_) in remove_add_braces
                ):
                    return None
                return (None, method, bool(self.numpy_array_to_list))
            # recette __getstate__ : pour une classe au __getstate__
            # UTILISATEUR et au reduce hérité d'object, l'état vient de la
            # méthode (appelée par objet) et l'enveloppe s'écrit en C —
            # ni getters/properties ni tri/filtre ne s'appliquent (le chemin
            # Python les réserve aux classes SANS __getstate__). Le plan à
            # 5 éléments porte le nom émis et la présence d'un __setstate__
            # (état tuple et clés non-str en dépendent)
            if (
                class_has_user_getstate(class_)
                and class_.__reduce_ex__ is object.__reduce_ex__
                and class_.__reduce__ is object.__reduce__
                and class_ not in dispatch_table
                and not hasattr(class_, "__getnewargs__")
                and not hasattr(class_, "__getnewargs_ex__")
                and not issubclass(class_, (list, tuple, dict, set, frozenset))
                and not issubclass(class_, Enum)
                and self.protocol >= 2
            ):
                return (
                    None,
                    class_.__getstate__,
                    bool(self.numpy_array_to_list),
                    class_str_from_class(class_),
                    hasattr(class_, "__setstate__"),
                )
            # collections deque/Counter/OrderedDict/defaultdict (classes
            # EXACTES) : recette C dédiée — l'enveloppe {__class__,
            # __init__[, __items__]} est composée entièrement en C, miroir
            # du reduce à listitems/dictitems que la recette générale ne
            # porte pas (plan (nom_de_classe, entier) — un bool n'est jamais
            # un entier exact, pas de collision avec le plan attributs).
            # deque à maxlen : repli voie python décidé par objet, côté C
            if class_ in _collections_natives and class_ not in dispatch_table:
                return (class_str_from_class(class_),
                        _collections_natives[class_])
            # recette __reduce__ réimplémenté : un adaptateur minuscule
            # appelle obj.__reduce_ex__(protocole) et reforme le tuple pour
            # la branche recette C (classe, args, état). Formes hors recette
            # (callable autre que la classe, listitems/dictitems) : None,
            # que le C traduit en repli voie Python. Enum est exclu (son
            # traitement des doublons dans default() est particulier)
            if (
                (
                    class_.__reduce_ex__ is not object.__reduce_ex__
                    or class_.__reduce__ is not object.__reduce__
                )
                and class_ not in dispatch_table
                and class_ not in serializejson_builtins
                and not issubclass(class_, Enum)
                and class_str_from_class(class_) not in remove_add_braces
                and self.protocol >= 2
            ):

                def _reduce_recipe(obj, _protocol=self.protocol):
                    reduced = obj.__reduce_ex__(_protocol)
                    if (
                        not isinstance(reduced, tuple)
                        or len(reduced) < 2
                        or reduced[0] is not obj.__class__
                        or (len(reduced) > 3 and reduced[3] is not None)
                        or (len(reduced) > 4 and reduced[4] is not None)
                    ):
                        return None
                    return (
                        obj.__class__,
                        reduced[1],
                        reduced[2] if len(reduced) > 2 else None,
                    )

                return (
                    None,
                    _reduce_recipe,
                    bool(self.numpy_array_to_list),
                    class_str_from_class(class_),
                )
            # recette __getnewargs__/__getnewargs_ex__ (reduce hérité
            # d'object) : l'adaptateur rend le 6-uplet de tuple_from_instance
            # tel quel — la décomposition (forme __newobj__, état trié/filtré,
            # getters/properties) reste celle de la voie Python, seule
            # l'ÉMISSION passe en C (mêmes règles que _default_one_line)
            if (
                (
                    hasattr(class_, "__getnewargs__")
                    or hasattr(class_, "__getnewargs_ex__")
                )
                and class_.__reduce_ex__ is object.__reduce_ex__
                and class_.__reduce__ is object.__reduce__
                and class_ not in dispatch_table
                and not issubclass(class_, Enum)
                and class_str_from_class(class_) not in remove_add_braces
                and self.protocol >= 2
            ):

                def _getnewargs_recipe(obj, _protocol=self.protocol):
                    return tuple_from_instance(obj, _protocol)

                return (
                    None,
                    _getnewargs_recipe,
                    bool(self.numpy_array_to_list),
                    class_str_from_class(class_),
                )
            if not (class_.__flags__ & _TPFLAGS_HEAPTYPE):
                # types natifs (tuple, dict, bytes...) : chemins dédiés
                return None
            if (
                class_ in serializejson_builtins
                or class_ in serializejson_
                or class_ in dispatch_table
                or class_ is Reference
                or class_ is dotdict
                or hasattr(class_, "__serializejson__")
                or class_.__reduce_ex__ is not object.__reduce_ex__
                or class_.__reduce__ is not object.__reduce__
                or class_has_user_getstate(class_)
                or hasattr(class_, "__getnewargs__")
                or hasattr(class_, "__getnewargs_ex__")
            ):
                return None
            slots_names = None
            if hasattr(class_, "__slots__"):
                if class_.__dictoffset__ != 0:
                    # __slots__ ET __dict__ (parent sans slots, ou "__dict__"
                    # dans les slots) : fusion d'états, voie Python
                    return None
                # mêmes noms que le __getstate__ par défaut (héritage et name
                # mangling compris), triés une fois pour toutes : le C écrit
                # dans cet ordre. Un slot au nom porteur de l'enveloppe
                # (improbable mais légal pour __init__ etc.) : voie Python
                slots_names = tuple(sorted(copyreg._slotnames(class_)))
                if any(name in _reserved_state_keys for name in slots_names):
                    return None
            # getters/properties : gating PAR CLASSE, mêmes résolutions que la
            # voie Python (tools.reduce) — le plan ne tombe que si CETTE classe
            # a réellement des getters/properties effectifs, au lieu de couper
            # le chemin C pour toutes les classes dès que le drapeau global est
            # posé
            _getters = self.getters
            if _getters is True:
                _getters = _getters_registry.get(class_, True)
            elif type(_getters) is dict:
                _getters = _getters.get(class_, False)
            _properties = self.properties
            if _properties is True:
                _properties = _properties_registry.get(class_, True)
            elif type(_properties) is dict:
                _properties = _properties.get(class_, False)
            if _getters is True or _properties is True:
                (
                    _,
                    class_properties,
                    class_getters,
                    _,
                ) = slots_properties_getters_setters_from_class(class_)
                if _getters is True:
                    _getters = class_getters
                if _properties is True:
                    _properties = class_properties
            if _getters or _properties:
                return None
            attributes_filter = self.attributes_filter
            if type(attributes_filter) is set:
                attributes_filter = class_ in attributes_filter
            class_str = class_str_from_class(class_)
            self.dumped_classes.add(class_str)
            return (class_str, bool(attributes_filter), slots_names)
        except Exception:
            return None

    # @profile
    def _default_one_line(self, inst):
        type_inst = type(inst)
        if self.numpy_types_to_python_types and type_inst in _numpy_types:
            return _numpy_dtypes_to_python_types[type_inst](inst)
        if type_inst is tuple:
            # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tuple_from_instance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tuple_from_instance
            self.dumped_classes.add(tuple)
            return {"__class__": "tuple", "__new__": list(inst)}
        if type_inst is Reference:
            return {
                "$ref": self._get_path(
                    inst.obj, already_explored=set([id(inst.__dict__)])
                )
                + inst.sup_str
            }
        if use_numpy and type_inst is ndarray and self.numpy_array_to_list:
            return inst.tolist()
        return self._dict_from_instance(inst)

    def _dict_from_instance(self, inst):

        if type(inst) is dict:  # dictionnary with non string key
            # nom court depuis le 04/08/2026 (décision de format) ; les
            # fichiers portant l'ancien nom "dict_non_str_keys" restent lus
            d = {"__class__": "dict"}
            init_dict = d
            for key, value in inst.items():
                # if type(key) is tuple :
                #    key = list(key)
                new_key = None
                type_key = type(key)
                if type_key is int:
                    # pas mis les float pour garder -inf et inf (nan ca déconne dans les dictionnaires)
                    new_key = str(key)
                elif type_key is str:
                    if key in ("__class__", "$ref"):
                        # clés réservées du format : toujours échappées —
                        # nue, la clé utilisateur écraserait l'étiquette de
                        # l'enveloppe ou serait relue comme objet/référence
                        init_dict[f"'{key}'"] = value
                        continue
                    # une clé str s'échappe si elle serait RELUE comme autre
                    # chose (json valide, ou forme quotée) — décidé par un
                    # préfiltre exact sur le premier caractère, la sonde
                    # rapidjson.loads (1,2 µs) ne restant que pour les rares
                    # clés commençant par [, { ou " (mesuré : la sonde par
                    # clé pesait un tiers du temps d'écriture de ces dicts)
                    premier = key[0] if key else ""
                    if premier == "'":
                        requote = key.endswith("'")
                    elif premier == "b":
                        requote = key.endswith("'") and (
                            key.startswith("b'") or key.startswith("b64'"))
                    elif premier in "-0123456789":
                        requote = (_cle_nombre_json.match(key) is not None
                                   or key == "-Infinity")
                    elif premier in "tfnNI":
                        requote = key in ("true", "false", "null", "NaN",
                                          "Infinity")
                    elif premier in '[{"':
                        try:
                            rapidjson.loads(key)
                        except Exception:
                            requote = False
                        else:
                            requote = True
                    else:
                        requote = False
                    new_key = f"'{key}'" if requote else key
                elif type_key is bytes:
                    try:
                        new_key = f"b'{key.decode('ascii_printables')}'"
                    except:
                        new_key = f"b64'{b64encode(key).decode('ascii')}'"
                elif type_key is tuple:
                    key = list(key)
                if new_key is None:
                    new_key = rapidjson.dumps(
                        key,
                        default=self._default_one_line,
                        ensure_ascii=self.ensure_ascii,
                        sort_keys=self.sort_keys,
                        bytes_mode=self.bytes_mode,
                        number_mode=rapidjson.NM_NATIVE,
                        iterable_mode=rapidjson.IM_ONLY_LISTS,
                        # mapping_mode=rapidjson.MM_ONLY_DICTS
                        # **self.kargs
                    )
                init_dict[new_key] = value
            return d
        # if type(inst) is OrderedDict :
        #    if not self.sort_keys :  # on a besoin d'avoir accès à self.sort_keys et specifique à serializejson
        #        return {
        #                "__class__" : "collections.OrderedDict",
        #                "__items__" : dict(inst)
        #                }
        #    else :
        #        return {
        #                "__class__" : "collections.OrderedDict",
        #                "__items__" : list(inst.items())
        #                }
        if type(inst) is dotdict:
            return dict(inst)
        class_, initArgs, state, listitems, dictitems, newArgs = tuple_from_instance(
            inst, self.protocol
        )
        if type(class_) is not str:
            class_ = class_str_from_class(class_)
        self.dumped_classes.add(class_)
        dictionnaire = {"__class__": class_}
        for args, method in ((newArgs, "__new__"), (initArgs, "__init__")):
            if args is not None:
                if type(args) is dict:
                    dictionnaire[method] = args
                else:
                    if class_ in remove_add_braces:
                        if args:
                            dictionnaire[method] = args[0]
                        else:
                            dictionnaire[method] = []
                    elif len(args) == 1:
                        type_first = type(args[0])
                        if (
                            type_first not in (tuple, list)
                            and not (
                                self.numpy_array_to_list and type_first is numpy.ndarray
                            )
                            and ((type_first is not dict) or "__class__" in args[0])
                        ):
                            dictionnaire[method] = args[0]
                        else:
                            dictionnaire[method] = list(args)  # args is a tuple
                    else:
                        dictionnaire[method] = list(args)  # args is a tuple
        if listitems:
            dictionnaire["__items__"] = listitems
        elif dictitems:
            dictionnaire["__items__"] = dictitems
        if state:
            if (
                (type(state) is not dict)
                or (
                    hasattr(inst, "__setstate__")
                    and not all_keys_are_str(state)
                )
                or _state_has_reserved_key(state)
            ):
                dictionnaire["__state__"] = state
            else:
                if state is getattr(inst, "__dict__", None):
                    # rigueur des doublons : ce state est le VRAI __dict__ de
                    # l'objet. S'il a déjà été écrit ailleurs (directement, ou
                    # aplati dans un objet qui le partage), on le référence au
                    # lieu de l'aplatir une seconde fois — et au chargement
                    # l'assignation restaure le partage physique (ce que même
                    # pickle ne préserve pas). Sinon on l'enregistre sous
                    # "<chemin de l'objet>.__dict__" pour la suite du dump.
                    path_id = self.json_path_id_of(state)
                    if path_id is not None:
                        dictionnaire["__dict__"] = rapidjson.RawString(
                            '{"$ref": "%s"}' % self._echappe_chemin_ref(
                                self.json_path_from_id(path_id))
                        )
                        return dictionnaire
                    self.memo_state_dict(state)
                dictionnaire.update(state)
        return dictionnaire

    # (pas de __call__ Python : le tp_call C de rapidjson.Encoder exécute
    # tout le protocole — poussée amortie via _update_serialize_parameters
    # sur défaut de garde, équivalents C de _reset/_clean, return_bytes par
    # appel, chunk_size implicite pour les flux)

    # attributs volatils re-posés à chaque dump : ils ne participent pas aux
    # paramètres globaux, leur écriture ne doit pas invalider la poussée
    _volatile_attrs = frozenset(("dumped_classes", "_already_serialized",
                                 "_already_serialized_keep_alive", "_root"))

    def __setattr__(self, name, value):
        # invalide la poussée amortie des paramètres globaux : le prochain
        # appel repoussera (voir _update_serialize_parameters)
        super().__setattr__(name, value)
        if name not in Encoder._volatile_attrs and getattr(
                serialize_parameters, "_owner", None) is self:
            serialize_parameters._owner = None

    def _update_serialize_parameters(self):
        # amorti : ne repousse les paramètres globaux (et les threads blosc)
        # que si un autre Encoder/Decoder a poussé entre-temps ou si un
        # attribut de celui-ci a changé (invalidation par __setattr__).
        # Mesuré : cette poussée valait 2,2 µs sur les 3,3 µs d'un dump
        # minuscule — le coût fixe par appel dominait les micro-benchmarks
        if getattr(serialize_parameters, "_owner", None) is self:
            return
        # résolution des valeurs symboliques :
        #   "cpus"       -> autant de threads que de coeurs, sans garantie
        #                    d'octets stables hors fork ;
        #   "determinist" (défaut) -> multithread UNIQUEMENT quand une voie
        #                    déterministe existe : le fork libblosc2 livré
        #                    (multithread interne à octets stables), sinon 1.
        #                    blosc v1 reste à 1 (son multithread ne garantit
        #                    pas les octets).
        threads = self.bytes_compression_threads
        if threads == "cpus":
            resolved = os.cpu_count() or 1
        elif threads == "determinist":
            resolved = min(8, os.cpu_count() or 1) if use_blosc2_fork else 1
        else:
            resolved = threads
        if use_blosc2_cpp:
            rapidjson.blosc_set_nthreads(resolved)
        # écriture native C des petits bytes/bytearray : le C écrit lui-même
        # l'enveloppe (mêmes octets que la recette) STRICTEMENT sous ce
        # seuil ; 0 dès que l'utilisateur a remplacé un greffon bytes — le C
        # ne court-circuite jamais un greffon. Sans compression, le greffon
        # n'écrirait que de l'ascii ou du b64 : toute taille passe en natif
        recette_bytes = serializejson_builtins.get(bytes)
        recette_bytearray = serializejson_builtins.get(bytearray)
        if (getattr(recette_bytes, "__name__", "") == "serializejson_bytes"
                and getattr(recette_bytearray, "__name__", "")
                == "serializejson_bytearray"):
            self.__dict__["_bytes_natif_seuil"] = (
                self._seuil_bytes if self.bytes_compression else JAMAIS)
        else:
            self.__dict__["_bytes_natif_seuil"] = 0
        # écriture native C des dicts à clés non-str : le C compose lui-même
        # l'enveloppe {"__class__": "dict", ...} et ne rappelle python que
        # pour les clés exotiques (tuple, frozenset, float non fini...), via
        # _cle_json. Désactivé si sort_keys (l'enveloppe python passe alors
        # par le tri du writer) ou si une sous-classe a redéfini une des
        # recettes que le C court-circuiterait
        cls = type(self)
        if (not self.sort_keys
                and cls.default is Encoder.default
                and cls._dict_from_instance is Encoder._dict_from_instance
                and cls._default_one_line is Encoder._default_one_line
                and "default" not in self.__dict__
                and "_dict_from_instance" not in self.__dict__
                and "_default_one_line" not in self.__dict__):
            self.__dict__["_cle_json"] = self._cle_json
        else:
            self.__dict__["_cle_json"] = None
        serialize_parameters.__dict__.update(self.__dict__)
        serialize_parameters.__dict__.update(self.plugins_parameters)
        # les plugins lisent les valeurs RÉSOLUES (ni le "determinist"
        # symbolique, ni le seuil par espèce, ne doivent leur parvenir)
        serialize_parameters.bytes_compression_threads = resolved
        serialize_parameters.bytes_size_compression_threshold = \
            self._seuil_bytes
        serialize_parameters.numpy_size_compression_threshold = \
            self._seuil_numpy
        serialize_parameters._owner = self
        serialize_parameters._decoder_owner = None

    def _cle_json(self, key):
        # encodage d'une clé de dict non portée par le C (tuple, frozenset,
        # float non fini, objet...), à l'IDENTIQUE du repli de
        # _dict_from_instance : tuple aplati en liste, puis dumps une-ligne
        if type(key) is tuple:
            key = list(key)
        return rapidjson.dumps(
            key,
            default=self._default_one_line,
            ensure_ascii=self.ensure_ascii,
            sort_keys=self.sort_keys,
            bytes_mode=self.bytes_mode,
            number_mode=rapidjson.NM_NATIVE,
            iterable_mode=rapidjson.IM_ONLY_LISTS,
        )

    def _reset(self):
        self.dumped_classes = set()
        # mémo des objets déjà écrits : id -> chemin json enregistré à la
        # première écriture (json_path() du traqueur C++), ou None si inconnu
        self._already_serialized = dict()
        # référence forte sur ce qui est mémorisé, le temps du dump : sinon un
        # objet temporaire détruit peut laisser son id être réutilisé et faire
        # croire à un doublon (même rôle que le memo de pickle)
        self._already_serialized_keep_alive = []
        # self._already_serialized_id_dic_to_obj_dic = dict()

    # @profile
    # ,list_deep = 10):
    def _searchSerializedParent(self, obj, already_explored=set(), attribut=None):
        root = self._root
        if obj is root:
            return [(["root"], False)]
        id_obj = id(obj)
        if id_obj in already_explored:
            return []
        already_explored = already_explored.copy()
        already_explored.add(id_obj)
        already_explored.add(id(locals()))
        pathElements = list()
        refs = gc.get_referrers(obj)
        already_explored.add(id(refs))
        # potential_parents = [parent_test for parent_test in gc.get_referrers(obj)if ((id(parent_test) not in already_explored) and isinstance(parent_test,(dict,list)))  ]
        # print(len(potential_parents))
        for parent_test in refs:
            id_parent_test = id(parent_test)
            if id_parent_test not in already_explored:
                type_parent_test = type(parent_test)
                if type_parent_test is dict:
                    if self.sort_keys:
                        parent_test_keys = sorted(parent_test)
                    else:
                        parent_test_keys = parent_test.keys()
                    for key in parent_test_keys:  # sorted(parent_test):
                        value = parent_test[key]
                        if value is obj:

                            for elt, is_attribut in self._searchSerializedParent(
                                parent_test, already_explored, attribut=obj
                            ):
                                if is_attribut:
                                    pathElements.append((elt, False))
                                else:
                                    pathElements.append((elt + [f"['{key}']"], False))

                            break
                elif (
                    type_parent_test is list
                    and not type(parent_test[-1]) is list_iterator
                ):
                    for key, value in enumerate(parent_test):
                        if value is obj:
                            for elt, _ in self._searchSerializedParent(
                                parent_test, already_explored
                            ):
                                pathElements.append((elt + ["[%d]" % key], False))
                            break
                elif id_parent_test in self._already_serialized:

                    if hasattr(parent_test, "__dict__"):
                        dic = self._dict_from_instance(parent_test)
                        for i, (key, value) in enumerate(dic.items()):
                            if value is attribut:
                                for elt, _ in self._searchSerializedParent(
                                    parent_test, already_explored
                                ):
                                    pathElements.append((elt + [".", (i), key], True))
                                    break
                    if hasattr(parent_test, "__slots__"):
                        dic = self._dict_from_instance(parent_test)
                        for i, (key, value) in enumerate(dic.items()):
                            if value is obj:
                                for elt, _ in self._searchSerializedParent(
                                    parent_test, already_explored
                                ):
                                    pathElements.append((elt + [".", (i), key], True))
                                    break

        return pathElements

    def _get_path(self, obj, already_explored=set()):
        already_explored.add(id(locals()))
        pathElements = self._searchSerializedParent(
            obj, already_explored=already_explored
        )
        if not pathElements:
            return None
            # return f'impossible to find a path from root object for {obj}'
            # raise Exception("impossible to find a path from root object for %s" % obj)
            # print("!",pathElements)
            # return pathElements[0][0]

        return "".join([e for e in sorted(pathElements)[0][0] if isinstance(e, str)])


class Decoder(rapidjson.Decoder):
    """
    Decoder for loading objects serialized in json files or strings.

    Args:
        file (string or file-like):
            the json path or file-like object.
            When specified, the decoder will read json from this file
            if you don't pricise file to`load()` method later.

        authorized_classes (set/list/tuple):
            Define the classes that serializejson is authorized to recreate from
            the `__class__` keywords in json, in addition to default authorized classes
            and classes autorized by plugins.

            default authorize classes are :
            array.array,bytearray,bytes,range,set,slice,time.struct_time,tuple,
            type,frozenset,collections.Counter,collections.OrderedDict,
            collections.defaultdict,collections.deque,complex,datetime.date,
            datetime.datetime,datetime.time,datetime.timedelta,decimal.Decimal,
            numpy.array,numpy.bool_,numpy.dtype,numpy.float16,numpy.float32,
            numpy.float64,numpy.frombuffer,numpy.int16,numpy.int32,numpy.int64,
            numpy.int8,numpy.ndarray,numpy.uint16,numpy.uint32,numpy.uint64,
            numpy.uint8,numpyB64.

            authorized_classes must be a set/list/tuple of classes or strings
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

        unauthorized_classes_as_dict (False by default)
            Controls whether unauthorized classes should be decoded as dict
            without raising a TypeError (or as dotdict if dotdict parameter is True,
            see the "dotdict" parameter for further explanation).

        recognized_classes (set/list/tuple):
            Classes (string with qualified names or classes) that
            serializejson will try to recognize from keys names.
            A classe will be recognized if keys names of a json dictionnary is
            a superset of the classe's default attributs names.
            Classe's default attributs name are slots and attributs names in __dict__ not starting with "_"
            after initialisation (serializejson will create an instance of each class passed in recognized_classes in order to determine
            this attributs)
            The instance will be instancied with new (with no argement), and __init__ will not be called .
            If you want execute some initialization code, you must add  a
            __setstate__() methode to your object or setter/properties with setters/properties Encoder's parameters
            activated.


        updatables_classes (set/list/tuple):
            Classes (string with qualified names or classes) that
            serializejson will try to update if already in the provided object `obj` when calling `load` or `loads`.
            Objects will be recreated for other classes.


        properties (bool, None, set/list/tuple, dict ):
            Controls whether `load` will call properties's setters instead of
            put them in self.__dict__ when the object as no `__setstate__` method
            and properties are merged with attributes in the state dictionnary
            when dumping (merged if strict_pickle is False) .
            - False: call properties setters for none classes (as pickle)
            - True : (default) call properties setters for all classes
            - None : call only properties setters defined in serializejson.properties dict (added by plugins or manualy before decoder call)
            (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )
            - set/list/tuple : call all properties setters for classes in this set/list/tuple, in addition to properties defined in serializejson.properties dict
            [class1, class2,..] (not secure if unstruted json, use it only for debuging)
            - dict : call properties setters defined in dict, in addition to properties defined in serializejson.properties dict
            {class1 : ["propertie1","propertie1"], class2: True}


            .. warning::
                **The properties's setters are called in the json order !**
                - in alphabetic order  if `sort_keys = True` or if the object has not __getstate__ method.
                - in the order returned by the __getstate__ method  if `sort_keys = False`
                - Be carefull if you rename an attribute because properties setters calls order can change.
                - If `properties = True` (or is a list) then serializejson load will differ from pickle that don't call attribute's setters.

                **It is best to add the __setate__() method to your object:**
                - If you want to stay compatible with pickle with the same behavior.
                - If you want to call properties setters in a different order than alphabetic order and don't want to code a __getstate__ method given the order.
                - If you want to call properties setters in a order robust to an attribute name change.
                - If you want to be robust to this `properties` parameter change.
                - If you want to avoid transitional states during setting of attribute one by one.
                In this method you can call the helping function :
                serialize.__setstate__(self,properties = True)


        setters  (bool,None,set/list/tuple,dict):
            Controls whether `load` will try to call `setxxx`,`set_xxx` or `setXxx` methods
            or `xxx` property setter for each attributes of the serialized objects
            when the object as no `__setstate__` method.
            - False: call no other setters than thus called in __setstate__ methodes, like pickle.
            - True : (default) explore and call all setters for all objects (not secure if unstruted json, use it only for debuging)
            - None : call only setters defined in serializejson.setters dict (added by plugins or manualy before decoder call)
            (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )
            - set/list/tuple : explore and call setters classes in set/list/tuple, in addition to setters defined in serializejson.setters dict
            [class1, class2,..] (not secure if unstruted json, use it only for debuging)
            - dict : call setters defined in dict, in addition to setters defined in serializejson.setters dict
            {class1 : {"attribut_name":"setter_name",...}, class2: True}

            .. warning::
                **The attribute's setters are called in the json order !**
                - in alphabetic order  if `sort_keys = True` or if the object has not __getstate__ method.
                - in the order returned by the __getstate__ method  if `sort_keys = False`
                - Be carefull if you rename an attribute because setters calls order can change.
                - If `set_attribute = True` (or is a list) then serializejson load will differ from pickle that don't call attribute's setters.

                **It is best to add the __setate__() method to your object:**
                - If you want to stay compatible with pickle with the same behavior.
                - If you want to call setters in a different order than alphabetic order and don't want to code a __getstate__ method given the order.
                - If you want to call setters in a order robust to an attribute name change.
                - If you want to be robust to this `setters` parameter change.
                - If you want to avoid transitional states during setting of attribute one by one.
                In this method you can call the helping function :
                serialize.__setstate__(self,setters = True or dict {name : setter_name,...})

        strict_pickle (False by default)
            If True serialize with exactly the same behaviour than pickle:
            - disabling properties setters
            - disabling setters
            - disabling numpy_array_from_list

        accept_comments (bool):
            Controls whether serializejson accepts to parse json with comments.

        numpy_array_from_list (bool):
            Controls whether list of bool, int or floats with same types elements should be loaded into numpy arrays.

        numpy_array_from_heterogenous_list (bool):
            Controls whether list of bool, int or floats with same or heterogenous types elements should be loaded into numpy arrays.

        default_value:
            The value returned if the path passed to `load` doesn't exist.
            It allows to have a default object at the first run of the script or
            when the json has been deleted, without raising of FileNotFoundError.

        chunk_size (int):
            Chunk size used when reading the json file.

        dotdict (bool):
            load dicts as serializejson.dotdict, a dict subclasse with acces to key names with a dot as object attributes enabled.
            A dotdict will be serialized as dict again when dumping.
            dotdict allows you to more easily access the elements of a deserialized dictionary, with the same '.' acces syntax as for an object, allowing you if you wish, to later transform the dictionaries in your jsons into real objects with the addition of the "__class__" field, without having to modify your code.

        add_jsonpath
            If True, the source json path will be added to the loaded object as `_jsonpath` attribut.
            If False (by default), nothing will be added to the loaded object, but you can still retrieve the source json path with the "serializejson.jsonpath" function which will find the path from the object identifier

        rehydrate (bool):
            If True (by default), each object is constructed (or adopted) as soon as its
            `__class__`/`__init__` are read, BEFORE its attributes and children:
            the json is never held as a tree of dicts. If False, objects are built
            when their dict closes (children created by an `__init__` are then duplicated). With `obj` passed to
            `load`/`loads`, the living objects found at the same place in `obj`
            (attribute, key, index) and of the same class are updated in place
            instead of recreated ; the others are created. Children created by
            an `__init__` are adopted, not duplicated. `updatables_classes`
            restricts the adoption to the given classes.
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
        file=None,
        *,
        authorized_classes=None,
        unauthorized_classes_as_dict=False,
        recognized_classes=None,
        updatables_classes=None,
        setters=True,
        properties=True,
        default_value=no_default_value,
        accept_comments=False,
        numpy_array_from_list=False,
        numpy_array_from_heterogenous_list=False,
        chunk_size=65536,
        strict_pickle=False,
        dotdict=False,
        add_jsonpath=False,
        rehydrate=True,
    ):
        # PREMIÈRE instruction : locals() ne contient alors que les paramètres,
        # plus la cellule __class__ que pose l'appel à super(). Ils servent à
        # refabriquer un décodeur identique pour les tranches d'un chargement
        # par chemin (voir _fabrique_decodeur) — les recopier un à un se serait
        # périmé au premier paramètre ajouté. Pris tel quel, sans le filtrer
        # ici : le tri coûtait 1,5 µs à CHAQUE construction, pour un service
        # rendu à un appel sur mille
        parametres = locals()

        if accept_comments:
            parse_mode = rapidjson.PM_COMMENTS
        else:
            parse_mode = rapidjson.PM_NONE
        self = super().__new__(
            cls,
            parse_mode=parse_mode,
            # parse natif des nombres : ints/floats créés directement en C++
            # (pleine précision, identique à float()) ; seuls les entiers qui
            # débordent 64 bits repassent par une chaîne (exactitude garantie
            # par le fork rapidjson, kParseBigIntsAsStringsFlag)
            number_mode=rapidjson.NM_NATIVE | rapidjson.NM_NAN,
        )  # , **argsDict)
        self._parametres = parametres
        self.strict_pickle = strict_pickle
        if strict_pickle:
            setters = False
            properties = False
            numpy_array_from_list = False
            numpy_array_from_heterogenous_list = False
            add_jsonpath = False
        self.file = file
        self.setters = _get_setters(setters)
        self.properties = _get_properties(properties)
        self._authorized_classes_strs = _get_authorized_classes_strings(
            authorized_classes
        )
        self.unauthorized_classes_as_dict = unauthorized_classes_as_dict
        self._class_from_attributes_names = _get_recognized_classes_dict(
            recognized_classes
        )
        self.set_updatables_classes(updatables_classes)
        # self.accept_comments = accept_comments
        # self.numpy_array_from_list=numpy_array_from_list
        self.default_value = default_value
        self.chunk_size = chunk_size
        self.dotdict = dotdict
        self.add_jsonpath = add_jsonpath
        self.file_iter = None
        self._avance = None
        self._iter_fini = True  # __iter__ (re)met l'itération en route
        self._iter_ema = None
        self._updating = False
        self._rehydrate = rehydrate
        if rehydrate:
            self.construct = self._construct  # lu par le C (PyHandler)

        self.numpy_array_from_list = numpy_array_from_list
        self.numpy_array_from_heterogenous_list = numpy_array_from_heterogenous_list
        if numpy_array_from_heterogenous_list:
            self.numpy_array_from_list = True
            self.end_array = self._end_array_if_numpy_array_from_heterogenous_list
        elif numpy_array_from_list:
            self.end_array = self._end_array_if_numpy_array_from_list
        return self

    def load(self, file=None, obj=None, path=None):
        """
        Load object from json file.

        Args:
            file (optional str or file-like):
                the json path or file-like object.
                When specified, json is read  from this file.
                Otherwise json is read from the file passed to `Decoder()` constructor.

            obj (optional):
                If provided, the object `obj` will be updated and no new object will be created.

            path (optional str):
                path of the wanted object inside the json, in the `$ref`
                grammar. Without index, or without any indexed ancestor, the
                whole document is read and the path walked in the result.

        Return:
            created object or updated object if passed obj.
        """

        # un dump rend la main avant que le disque ait tout reçu : relire sans
        # attendre donnerait un document tronqué
        rapidjson.wait_writes()
        if file is None:
            file = self.file
        if path is not None:
            return self._load_path(file, path)
        chemin_source = None
        if isinstance(file, str):
            chemin_source = file
            # print("load",file)
            if not os.path.exists(file):
                if self.default_value is no_default_value:
                    raise FileNotFoundError(
                        errno.ENOENT, os.strerror(errno.ENOENT), file
                    )
                return self.default_value
            with _open_with_good_encoding(file) as fichier:
                # tout le document d'un coup : le parseur va ~4 fois plus vite
                # sur des octets que sur un flux (mesuré). Qui veut économiser
                # la mémoire sur un très gros json a `iterator=True`.
                file = fichier.read()
                if "b" in getattr(fichier, "mode", ""):
                    # un index en fin de fichier (index="comment") ne fait pas
                    # partie du document : le parseur buterait dessus
                    fin = rapidjson._index_fin(file)
                    if fin != len(file):
                        file = file[:fin]
        elif file is None:  # a priori pointeur vers fichier
            raise ValueError('Encoder.load need a "file" path/file argument')

        loaded = self._appel(file, obj)
        if chemin_source:
            if self.add_jsonpath:
                loaded._jsonpath = chemin_source
            id_to_path[id(loaded)] = chemin_source
        return loaded

    def _fabrique_decodeur(self):
        # un décodeur neuf par tranche : les tranches se chargent en cascade
        # quand elles se référencent, un décodeur en cours de parse ne peut
        # donc pas se prêter
        args = dict(self._parametres)
        for nom in ("cls", "file", "__class__"):
            args.pop(nom, None)
        return Decoder(**args)

    def _load_path(self, file, path):
        # chargement d'un seul objet : par l'index s'il y en a un, sinon par
        # le document entier — même résultat, seul le temps change. Un cycle
        # de références entre tranches ramène aussi au document entier
        if isinstance(file, str):
            try:
                loaded = indexation.charge(
                    file, path, self._fabrique_decodeur)
            except indexation.Circulaire:
                loaded = NotImplemented
            if loaded is not NotImplemented:
                return loaded
        loaded = rapidjson._resolve_ref_path(path, self.load(file))
        if loaded is None:
            raise KeyError("%s not found in %s" % (path, file))
        return loaded

    def loads(self, json, obj=None):
        """
        Load object from json string or bytes.

        Args:
            s:
                the json string.
            obj (optional):
                If provided, the object `obj` will be updated and no new object will be created.

        Return:
            created object or updated object if passed obj.
        """
        return self._appel(json, obj)

    def _appel(self, json, obj):
        if not self._rehydrate:
            return self.__call__(json=json, obj=obj)
        # obj est l'homologue vivant de la racine, adopté par le crochet
        # construct au fil du parse ; passé au C il basculerait sur la voie
        # update (document entier en dicts, puis _exploreToUpdate)
        self._live_root = obj
        try:
            return self.__call__(json=json, obj=None)
        finally:
            self._live_root = None

    def set_default_value(self, value=no_default_value):
        """
        Set the value returned if the path passed to load doesn't exist.
        It allows to have a default object at the first run of the script or
        when the json has been deleted, without raising of FileNotFoundError.
        encoder.set_default_value() without any argument will remove the default_value
        and reactivate the raise of FileNotFoundError.
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
        self.updatableClassStrs = _UpdatableClasses(updatables)

    # court-circuit du start_object Python par le C++ (racine posée par lui) ;
    # False par défaut : les chemins itérateur et update le laissent inactif
    _fast_start_object = False
    _fast_plain_end_object = False
    # mode rehydrate : crochet lu par le C, homologue vivant de la racine
    construct = None
    _live_root = None

    def _construct(self, class_str, args, slot, ancestor, keys, stateless):
        # Appelé par le C (mode rehydrate) quand une enveloppe n'a pas de plan
        # C (classe sans plan, constructeur enregistré, clé '~') : rend
        # l'objet de cette enveloppe, ou None pour laisser le C continuer
        # comme sans le mode (classe non autorisée : end_object tranchera).
        # `keys` : chaîne des clés depuis `ancestor` (instance déjà
        # construite, None = racine vivante) jusqu'à l'objet ; None = pas
        # d'homologue vivant possible. `stateless` : enveloppe sans clé
        # d'état, l'adoption exige alors que `ancestor` soit un argument du
        # constructeur (un enfant Qt anonyme parenté par son __init__) — sans
        # cette ancre, une enveloppe-valeur serait figée à sa valeur vivante
        if class_str not in self._authorized_classes_strs:
            return None
        try:
            cls = constructors[class_str]
        except KeyError:
            cls = constructors[class_str] = class_from_class_str(
                class_str
            )
        if keys is not None:
            if ancestor is None and not keys:
                if self._live_root is not None:
                    return self._live_root
            elif not stateless or _anchored(args, ancestor):
                live = self._live_root if ancestor is None else ancestor
                for key in keys:
                    if live is None:
                        break
                    live = _descend(live, key)
                if type(live) is cls and (
                    not self.updatableClassStrs
                    or class_str in self.updatableClassStrs
                ):
                    return live
        # construction sans état, par la voie classique (mêmes formes
        # d'arguments : liste, dict, scalaire déballé)
        if args is not None and class_str in remove_add_braces:
            args = (args,)
        if slot == 1:
            return instance(class_str, __new__=args)
        return instance(class_str, __init__=args)

    # classes dont la charge __init__/__new__[0] est du base64 : le parseur
    # C++ la décode directement depuis son tampon de parse, sans matérialiser
    # la chaîne Python intermédiaire (0 -> bytes, 1 -> bytearray)
    _b64_payload_classes = {"bytes": 0, "bytearray": 1, "numpyB64": 1}

    # repli PAR CLÉ du décodage C des dicts à clés non-str : le C décode
    # lui-même les formes courantes (str, 'quotée', b'...', b64'...',
    # booléens, nombres) et ne rappelle ceci que pour les exotiques
    # (tuples, frozensets, imbrications) — posé en attribut de classe pour
    # que le C le résolve une fois par chargement
    _decode_cle_exotique = None  # rempli après la définition de _decode_cle

    # cache PARTAGÉ des valeurs de type (tools._type_values_cache) : le C
    # résout {"__class__": "type", "__init__": "x.y"} par simple lecture du
    # dict — il ne sert que les HITS ; le premier passage d'un nom reste en
    # python (instance()), qui remplit le cache et porte la machinerie
    # d'import
    _type_values_cache = _type_values_cache

    def decode_class_plan(self, class_str):
        # Chemin rapide de décodage, consulté par le C++ UNE fois par classe et
        # par chargement : None -> end_object Python complet ; la CLASSE -> les
        # objets {"__class__": nom, attributs...} sans clé spéciale sont
        # instanciés directement en C++ (cls.__new__ puis assignation du dict
        # d'attributs). Les conditions calquent _inst_from_dict/instance()/
        # setstate : au moindre doute, None.
        try:
            if self._updating or class_str not in self._authorized_classes_strs:
                return None
            if class_str in constructors or class_str in remove_add_braces:
                return None
            if class_str == "type":
                # branche SPÉCIALE de instance() (type à un argument rendrait
                # la classe de l'argument !) — servie par le cache des valeurs
                # de type côté C, jamais par un plan constructeur
                return None
            class_ = class_from_class_str(class_str)
            if not isinstance(class_, type):
                return None
            if not (class_.__flags__ & _TPFLAGS_HEAPTYPE):
                # classes C (Decimal, datetime, deque...) : plan
                # « constructeur seul » (classe, 2) — le C n'y recourt que
                # pour l'enveloppe stricte {__class__, __init__} et appelle
                # classe(*args), la forme exacte de instance() ; toute autre
                # enveloppe (attributs, __state__, kwargs) reste python
                return (class_, 2)
            if hasattr(class_, "__setstate__"):
                return (class_, 2)
            by_setattr = False
            if hasattr(class_, "__slots__"):
                if class_.__dictoffset__ != 0:
                    return None
                # classe à __slots__ purs : restauration par setattr (le
                # setstate Python fait de même via set(slots))
                by_setattr = True
            _setters = self.setters
            if _setters is True:
                _setters = _setters_registry.get(class_, True)
            elif type(_setters) is dict:
                _setters = _setters.get(class_, False)
            if _setters is True:
                _setters = setters_names_from_class(class_)
            if _setters:
                return (class_, 2)
            _properties = self.properties
            if _properties is True:
                _properties = _properties_registry.get(class_, True)
            elif type(_properties) is dict:
                _properties = _properties.get(class_, False)
            if _properties is True:
                _properties = slots_properties_getters_setters_from_class(class_)[1]
            if _properties:
                return (class_, 2)
            if by_setattr:
                return (class_, True)
            return class_
        except Exception:
            return None

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
        # self._counter += 1
        # self._deserializeds.add()
        if self._updating:
            self.ancestors.pop()  # se retire lui meme
        class_str = inst.get("__class__", None)
        if class_str is not None:
            if self._updating:
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
        elif "$ref" in inst and len(inst) == 1:
            # les cibles HORS d'une tranche chargée par chemin ne se résolvent
            # pas ici : leur marqueur est laissé intact jusqu'à la post-passe,
            # qui seule sait aller les chercher dans le fichier
            if self.root and not inst["$ref"].startswith(indexation.HORS):
                # try:
                inst_potential = from_name(
                    inst["$ref"], accept_dict_as_object=True, root=self.root,
                    materialize=self._materialize,
                )  # essaye de remplacer tout de suite si possible
                if inst is inst_potential:
                    raise Exception('{"$ref": "%s"} pointing to himself' % inst["$ref"])
                if type(inst_potential) is dict and "__class__" in inst_potential:
                    # objet pas encore recréé : créé par anticipation
                    return self._materialize(inst_potential)
                return inst_potential
            self.duplicates_to_replace.append(inst)
        elif self._class_from_attributes_names:
            class_from_attributes_names = self._class_from_attributes_names
            attributes_tuple = tuple(sorted(inst))
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
                        # idealement faudrait pouvoir eviter d'explorer, et aller directement rédydrater les descendant , le problème c'est que l'hydrattation n'est pas in place et les objet qui les contiennent de vont pas avoir leur champs mis à jour ... ex dans une liste
                        return self._exploreDictToReCreateObjects(inst)
                else:
                    # pas de verification les objets recognized sont considérés comme authorized  #self._inst_from_dict(inst)
                    return instance(**inst)
        if self.dotdict:
            return dotdict(inst)
        return inst

    # (pas de __call__ Python : le tp_call C de rapidjson.Decoder exécute le
    # protocole — garde amortie, attributs volatils, json_startswith_curly,
    # drapeaux du chemin rapide, queue des doublons. Il ne rappelle le Python
    # que sur les trois chemins rares ci-dessous.)

    def _push_decode_parameters(self):
        # poussée des paramètres globaux, sur défaut de la garde amortie
        # (voir Encoder._update_serialize_parameters) — appelée par le C
        serialize_parameters.strict_pickle = self.strict_pickle
        serialize_parameters.setters = self.setters
        serialize_parameters.properties = self.properties
        serialize_parameters._decoder_owner = self
        serialize_parameters._owner = None

    def _call_update(self, json, obj):
        # mise à jour d'un objet existant — appelée par le C, qui a déjà posé
        # les attributs volatils et json_startswith_curly
        self._updating = True
        self.ancestors = deque()
        self.ancestors.append(None)
        self.node_has_descendants_to_recreate = set()
        loaded_dict = rapidjson.Decoder._decode(
            self, json, chunk_size=self.chunk_size
        )
        loaded = self._exploreToUpdate(obj, loaded_dict)
        if self.duplicates_to_replace:
            self._resolve_duplicates(loaded)
        del self.duplicates_to_replace
        del self.ancestors
        del self.node_has_descendants_to_recreate
        self._updating = False
        return obj

    def _materialize(self, dict_):
        # instance d'un objet dont le dict d'enveloppe est encore en
        # construction (cible d'un $ref, ou traversé par lui) : créée depuis
        # __class__/__init__/__new__ et rangée sous "__class__", où sa
        # fermeture la retrouve pour lui appliquer son état
        inst = dict_["__class__"]
        if isinstance(inst, str):
            inst = dict_["__class__"] = self._inst_from_dict({
                key: dict_[key]
                for key in ("__class__", "__init__", "__new__")
                if key in dict_
            })
        return inst

    def _resolve_duplicates(self, loaded):
        # on restaure les doublons qu'on n'a pas pu restaurer pendant la
        # deserialisation (references en avant, ou json commencant par une
        # liste pour lequel root n'est pas connu pendant le parse) — appelée
        # par le C quand duplicates_to_replace n'est pas vide
        # cible de chaque marqueur {"$ref": ...}, en suivant les eventuelles
        # chaines de $ref pointant sur d'autres marqueurs
        placeholders = {}
        for placeholder in self.duplicates_to_replace:
            # résolveur C d'abord (grammaire de l'encodeur) ; from_name en
            # repli — une cible ne peut pas être None, l'ambiguïté est nulle
            referenced = rapidjson._resolve_ref_path(placeholder["$ref"],
                                                     loaded)
            if referenced is None:
                referenced = from_name(
                    placeholder["$ref"], accept_dict_as_object=True,
                    root=loaded
                )
            if referenced is placeholder:
                raise Exception(
                    '{"$ref": "%s"} pointing to himself' % placeholder["$ref"]
                )
            placeholders[id(placeholder)] = referenced
        for id_, referenced in placeholders.items():
            followed = {id_}
            while id(referenced) in placeholders:
                if id(referenced) in followed:
                    raise Exception('{"$ref": ...} circular chain of references')
                followed.add(id(referenced))
                referenced = placeholders[id(referenced)]
            placeholders[id_] = referenced
        # puis remplacement de toutes leurs occurrences par UN parcours de
        # l'arbre charge — deterministe, au lieu de gc.collect() suivi d'un
        # gc.get_referrers() par marqueur (couteux : tout le tas a chaque fois)
        _replace_ref_placeholders(loaded, placeholders)
        return loaded

    def __iter__(self):
        # une itération précédente encore en vol rendrait son fil orphelin
        # sur l'ancien fichier : l'arrêter avant de rouvrir
        self._avance_arrete()
        self._updating = False
        file = self.file
        if isinstance(file, str):
            if not os.path.exists(file):
                # iter() exige un ITÉRATEUR : la liste nue d'origine levait
                # TypeError (défaut préexistant, jamais testé)
                return iter([self.default_value])
            self.file_iter = _json_object_file_iterator(file, mode="rb")
        else:
            raise Exception("not yet able to load_iter on %s" % str(type(file)))
        # rang du maillon rendu : il donne la racine de ses « $ref », écrits
        # depuis celle du FICHIER quand on ne rend ici que le maillon
        self._ref_rang = 0
        # lecture d'avance ADAPTATIVE : la voie directe mesure ses décodages,
        # et le fil (_LectureAvance) ne s'engage que si leur moyenne dépasse
        # le seuil — les listes de petits maillons ne paient ni fil ni
        # va-et-vient (mesuré : ~13 µs par maillon, ×6,7 sur des scalaires)
        self._iter_fini = False
        self._iter_ema = None  # None : premier maillon = chauffe des caches
        return self

    def _avance_arrete(self):
        # arrêt du fil de lecture d'avance, en attendant sa fin réelle :
        # file_iter ne doit pas être remplacé sous un décodage en vol
        avance = self._avance
        if avance is not None:
            self._avance = None
            avance.finalize.detach()
            avance.arrete()
            avance.fil.join()

    def _inst_from_dict(self, inst):
        class_str = inst["__class__"]
        if not isinstance(class_str, str):
            # instance déjà construite (mode rehydrate, ou $ref matérialisé) :
            # instance() l'adopte et lui applique l'état
            return instance(**inst)
        if class_str in self._authorized_classes_strs:
            for key in ("__init__", "__new__", "__items__"):
                if key in inst:
                    if (
                        self.numpy_array_from_list
                        and isinstance(inst[key], numpy.ndarray)
                        and id(inst[key]) in self.converted_numpy_array_from_lists
                    ):
                        inst[key] = inst[key].tolist()
                    if key != "__items__" and class_str in remove_add_braces:
                        inst[key] = (inst[key],)

            if (
                class_str in ("dict", "dict_non_str_keys")
            ):  # je l'ai mis ici car trop specifique à json pour etre dans tools (qui est partagé avec serializePython et serializeRepr)
                return dict_non_str_keys(inst)
            return instance(**inst)
        if self.unauthorized_classes_as_dict:
            class_str = inst["__class__"]
            self.not_authorized_classes.add(class_str)
            if self.dotdict:
                warnings.warn(
                    f"{class_str} not in authorized_classes leaved as docdict",
                    Warning,
                )
                return dotdict(inst)
            warnings.warn(
                f"{class_str} not in authorized_classes leaved as dict", Warning
            )
            return inst
        raise TypeError(f"{inst['__class__']} is not in authorized_classes")

    # @profile
    def _exploreToUpdate(self, obj, loaded_node):

        # gère le cas où loaded_node est un dictionnaire ----------------------
        if isinstance(loaded_node, dict):
            # plutot que set vide un objet peut ne pas avoir d'attributes ni de slots initialisés:
            obj_keys = None
            obj_class = obj.__class__
            if obj_class is dict and ("dict" in self.updatableClassStrs):
                is_dict = True
                obj_keys = set(obj)
                obj
            else:  # s'assure que c'est une instance
                is_dict = False
                class_str = loaded_node.get("__class__")
                if (
                    (class_str is not None)
                    and (class_str in self.updatableClassStrs)
                    and (class_str == class_str_from_class(obj_class))
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
                    if hasattr(obj, "__dict__"):
                        # A REVOIR : ne marche pas avec les slots
                        obj_keys = set(obj.__dict__)
                    if hasattr(obj, "__slots__"):
                        if obj_keys is None:
                            obj_keys = set()
                        for slot in slots_from_class(obj_class):
                            if hasattr(obj, slot):
                                obj_keys.add(slot)
            if obj_keys is not None:
                if not is_dict:

                    setters = serialize_parameters.setters

                    if type(setters) is dict:
                        setters = setters.get(obj_class, False)
                    if setters is True:
                        setters = setters_names_from_class(obj_class)

                # update dans le cas où l'objet pré-existant est un objet (avec __dict__ pas encore __slot__) ou un dictionnaire --
                loaded_node_has_descendants_to_recreate = (
                    id(loaded_node) in self.node_has_descendants_to_recreate
                )

                # suprime les attributes de l'objet qui ne sont pas dans loaded..
                only_in_obj = obj_keys - set(loaded_node)
                for key in only_in_obj:
                    if is_dict:
                        del obj[key]
                    elif not key.startswith("_"):
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
                        elif setters and key in setters:
                            obj.__getattribute__(setters[key])(value)
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
                (
                    isinstance(elt, ndarray)
                    and elt.dtype is first_elt_dtype
                    and elt.shape == first_elt_shape
                )
                for elt in sequence
            ):
                array = numpy.array(sequence, dtype=first_elt_dtype)
                self.converted_numpy_array_from_lists.add(id(array))
                return array
        return sequence

    def _end_array_if_numpy_array_from_heterogenous_list(self, sequence):
        if _onlyOneDimNumbers(sequence):
            array = numpy.array(sequence)
            self.converted_numpy_array_from_lists.add(id(array))
            return array
        if len(sequence) and isinstance(sequence[0], ndarray):
            first_elt = sequence[0]
            first_elt_shape = first_elt.shape
            if all(
                (isinstance(elt, ndarray) and elt.shape == first_elt_shape)
                for elt in sequence
            ):
                array = numpy.array(sequence)
                self.converted_numpy_array_from_lists.add(id(array))
                return array
        return sequence

    def __next__(self):
        avance = self._avance
        if avance is None:
            if self._iter_fini:
                # fin déjà livrée : le protocole exige de continuer à
                # lever StopIteration
                raise StopIteration
            # voie directe, chronométrée : le fil de lecture d'avance ne
            # vaut que si le décodage d'un maillon est assez long pour que
            # son recouvrement paie le va-et-vient de fils
            debut = time.perf_counter()
            try:
                maillon = self._decode_maillon()
            except StopIteration:
                self._iter_fini = True
                raise
            ema = self._iter_ema
            if ema is None:
                # le PREMIER décodage remplit les caches (mesuré : il peut
                # dépasser le seuil à lui seul sur des maillons minuscules)
                # — il chauffe, il ne compte pas
                self._iter_ema = 0.0
            else:
                self._iter_ema = ema = (
                    ema + (time.perf_counter() - debut)) * 0.5
                if ema >= _SEUIL_LECTURE_AVANCE:
                    # le fil attaque le maillon SUIVANT dès maintenant,
                    # pendant que l'appelant travaille sur celui-ci
                    self._avance = _LectureAvance(self)
            return maillon
        categorie, charge = avance.resultats.get()
        if categorie == "ok":
            # maillon livré : le jeton rendu lance le décodage du SUIVANT
            # pendant que l'appelant travaille sur celui-ci
            avance.jeton.release()
            return charge
        if categorie == "fin":
            self._avance = None
            self._iter_fini = True
            avance.finalize.detach()
            raise charge  # le StopIteration levé par le fil
        # erreur d'un maillon : relancée chez l'appelant, itération
        # poursuivable s'il la ravale (comme la voie directe d'avant)
        avance.jeton.release()
        raise charge

    def _decode_maillon(self):
        # décode UN maillon depuis file_iter — appelé par le fil de lecture
        # d'avance (_LectureAvance), jamais par l'appelant directement.
        # état volatil par décodage : ce chemin appelle _decode BRUT, sans le
        # tp_call C qui pose ces attributs — l'itération n'avait aucun test,
        # elle a cassé silencieusement pendant la migration ($ref/root), et
        # est réparée ici (04/08/2026)
        self.converted_numpy_array_from_lists = set()
        self.not_authorized_classes = set()
        self._updating = False
        self.root = None
        self.duplicates_to_replace = []
        # False : la racine n'est pas supposée connue pendant le parse — les
        # $ref éventuels passent par les marqueurs, résolus après coup (le
        # chemin général, correct que l'objet appendé soit dict, liste ou
        # scalaire)
        self.json_startswith_curly = False
        try:
            loaded = rapidjson.Decoder._decode(
                self, self.file_iter, chunk_size=self.chunk_size
            )
        except rapidjson.JSONDecodeError as error:
            self.file_iter.close()
            if error.args[0].endswith("The document is empty."):
                raise StopIteration
            else:
                raise
        if self.duplicates_to_replace:
            # le maillon a été écrit à sa PLACE dans le document : ses chemins
            # « $ref » partent de la racine du fichier (« root[3]['x'] »), et
            # c'est bien ce qu'il faut pour le relire en entier. Rendu seul, il
            # est sa propre racine : les ramener sur lui, comme le fait
            # `rebase_refs` pour une tranche chargée par l'index
            prefixe = "root[%d]" % self._ref_rang
            for marqueur in self.duplicates_to_replace:
                interne = indexation._sous_chemin(marqueur["$ref"], prefixe)
                if interne is not None:
                    marqueur["$ref"] = "root" + interne
            loaded = self._resolve_duplicates(loaded)
        self._ref_rang += 1
        return loaded


# le C prend en charge le protocole des __call__ (poussée amortie, attributs
# volatils, drapeaux du chemin rapide) : il lui faut les types et le module
# des paramètres globaux
rapidjson.register_serializejson(Encoder, Decoder, serialize_parameters)

# ----------------------------------------------------------------------------------------------------------------------------
# --- INTERNES -----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------


# moyenne mobile de décodage par maillon au-delà de laquelle l'itération
# engage le fil de lecture d'avance : en deçà, le va-et-vient de fils
# (~13 µs mesurés par maillon) mange le recouvrement possible ; au-delà,
# il en coûte au pire ~8 % quand rien ne recouvre (appelant sans travail),
# contre un décodage entièrement masqué quand l'appelant rend le GIL
# (entrées-sorties, numpy, décompression ≥ 1 Mio du pool)
_SEUIL_LECTURE_AVANCE = 500e-6


class _LectureAvance:
    """Fil de lecture d'avance d'une itération (pendant, côté lecture, du fil
    d'écriture d'append) : décode le maillon SUIVANT pendant que l'appelant
    travaille sur le courant. Un seul maillon d'avance : __next__ rend le
    jeton au moment où il livre un maillon, ce qui autorise le décodage du
    suivant. Le fil ne tient le décodeur que par référence FAIBLE hors
    décodage : une itération abandonnée (break, itérateur jeté) laisse le
    décodeur mourir, son finaliseur réveille le fil qui se termine et ferme
    le fichier — pas de fuite de fil ni de descripteur."""

    def __init__(self, decodeur):
        self.resultats = queue.SimpleQueue()  # ("ok"|"exc"|"fin", charge)
        self.jeton = threading.Semaphore(1)   # 1 décodage d'avance autorisé
        self.stop = False
        self.file_iter = decodeur.file_iter   # pour fermer sans le décodeur
        self.fil = threading.Thread(
            target=self._boucle,
            args=(weakref.ref(decodeur),),
            daemon=True,
            name="serializejson-lecture-avance",
        )
        self.finalize = weakref.finalize(decodeur, self.arrete)
        self.fil.start()

    def arrete(self):
        self.stop = True
        self.jeton.release()

    def _boucle(self, ref):
        while True:
            self.jeton.acquire()
            if self.stop:
                break
            decodeur = ref()
            if decodeur is None:
                break
            try:
                # la voie brute ne pousse pas les paramètres globaux (le
                # tp_call C n'est pas traversé) : les poser ici — sans quoi
                # l'itération lisait ceux du DERNIER encodeur/décodeur
                # appelé (défaut préexistant). Poussée par VALEURS, sans
                # s'inscrire comme propriétaire : _decoder_owner est une
                # référence FORTE, et une itération abandonnée ne mourrait
                # jamais (fil et fichier fuités) ; valeurs déjà en place =
                # aucune écriture, les amortissements des autres tiennent
                if (
                    serialize_parameters.strict_pickle
                    is not decodeur.strict_pickle
                    or getattr(serialize_parameters, "setters", None)
                    is not decodeur.setters
                    or getattr(serialize_parameters, "properties", None)
                    is not decodeur.properties
                ):
                    serialize_parameters.strict_pickle = \
                        decodeur.strict_pickle
                    serialize_parameters.setters = decodeur.setters
                    serialize_parameters.properties = decodeur.properties
                    serialize_parameters._decoder_owner = None
                    serialize_parameters._owner = None
                maillon = decodeur._decode_maillon()
            except StopIteration as fin:
                self.resultats.put(("fin", fin))
                break
            except BaseException as erreur:
                self.resultats.put(("exc", erreur))
                del decodeur
                continue
            self.resultats.put(("ok", maillon))
            # aucune référence forte gardée entre deux décodages : c'est ce
            # qui permet au finaliseur du décodeur de nous réveiller
            del decodeur, maillon
        self.file_iter.close()  # idempotent (déjà fermé sur fin normale)


# types dans lesquels un marqueur {"$ref": ...} ne peut pas se trouver :
# inutile de les explorer
_leaf_types = (str, int, float, bool, type(None), bytes, bytearray, complex)


def _replace_ref_placeholders(root, placeholders):
    # Remplace en place, dans les dicts, listes, attributs et slots de l'arbre
    # chargé, les marqueurs {"$ref": ...} (clé : id du marqueur) par leur cible.
    # Parcours itératif (pas de limite de récursion) protégé des cycles.
    from types import ModuleType, FunctionType, BuiltinFunctionType

    visited = set()
    stack = [root]
    while stack:
        node = stack.pop()
        id_node = id(node)
        if id_node in visited:
            continue
        visited.add(id_node)
        type_node = type(node)
        if type_node is dict:
            for key, value in node.items():
                replacement = placeholders.get(id(value))
                if replacement is not None:
                    node[key] = replacement
                elif type(value) not in _leaf_types:
                    stack.append(value)
        elif type_node is list:
            for index, value in enumerate(node):
                replacement = placeholders.get(id(value))
                if replacement is not None:
                    node[index] = replacement
                elif type(value) not in _leaf_types:
                    stack.append(value)
        elif type_node is tuple:
            # un marqueur directement dans un tuple n'est pas remplaçable
            # (immuable), comme avec l'ancien mécanisme ; on explore son contenu
            for value in node:
                if type(value) not in _leaf_types:
                    stack.append(value)
        elif isinstance(node, (type, ModuleType, FunctionType, BuiltinFunctionType)):
            # ne pas se promener dans les classes, modules et fonctions :
            # aucun marqueur ne peut s'y trouver
            continue
        else:
            node_dict = getattr(node, "__dict__", None)
            if type(node_dict) is dict:
                # le __dict__ entier peut être un marqueur {"$ref": ...}
                # différé (clé "__dict__" assignée par instance())
                replacement = placeholders.get(id(node_dict))
                if replacement is not None:
                    node.__dict__ = replacement
                    node_dict = replacement
                stack.append(node_dict)
            if hasattr(node, "__slots__"):
                for slot in slots_from_class(type_node):
                    if hasattr(node, slot):
                        value = getattr(node, slot)
                        replacement = placeholders.get(id(value))
                        if replacement is not None:
                            setattr(node, slot, replacement)
                        elif type(value) not in _leaf_types:
                            stack.append(value)


class dotdict(dict):
    """dot notation access to dictionary attributes"""

    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError()

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def bool_or_set(value):
    if value is None:
        return set()
    if isinstance(value, (bool, set)):
        return value
    if isinstance(value, (list, tuple)):
        return set(value)
    else:
        raise TypeError


def bool_or_dict(value):
    if value is None:
        return dict()
    if isinstance(value, (bool, dict)):
        return value
    if isinstance(value, (set, list, tuple)):
        return {key: True for key in value}
    else:
        raise TypeError


# décodage des clés non-str : un Décodeur PAR THREAD, réutilisé (en
# construire un par clé — l'ancien loads(key) — coûtait 6 à 9 µs par clé,
# l'essentiel du x66 mesuré sur les dicts à clés spéciales), et chemins
# directs pour les clés scalaires, qui évitent le parseur complet
_decodeur_de_cles = threading.local()


def _decode_cle(key):
    premier = key[0] if key else ""
    if premier == "'":
        if key.endswith("'"):
            return key[1:-1]
    elif premier == "b":
        if key.endswith("'"):
            if key.startswith("b'"):
                return key[2:-1].encode("ascii_printables")
            if key.startswith("b64'"):
                return b64decode(key[4:])
    elif key == "true":
        return True
    elif key == "false":
        return False
    elif premier.isdigit() or premier in "-NI":
        # nombres (int, float, NaN, Infinity) : mêmes résultats que le
        # parseur — l'encodeur a produit ces clés par dumps, formes
        # canoniques garanties
        try:
            return int(key)
        except ValueError:
            try:
                return float(key)
            except ValueError:
                pass
    decodeur = getattr(_decodeur_de_cles, "instance", None)
    if decodeur is None:
        decodeur = _decodeur_de_cles.instance = Decoder()
    try:
        key = decodeur(key)
    except Exception:
        return key
    if type(key) is list:
        return tuple(key)
    return key


def dict_non_str_keys(dict_):
    d = dict()
    del dict_["__class__"]
    for key, value in dict_.items():
        d[_decode_cle(key)] = value
    return d


# branchement du repli par clé pour le décodage C (voir Decoder)
Decoder._decode_cle_exotique = staticmethod(_decode_cle)


# nombre JSON exact (la sonde d'échappement des clés s'y réfère : underscores
# et formes python non-json comme .5 ou +5 NE matchent PAS, fidèle à loads)
_cle_nombre_json = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


# recettes privées des sets pour la branche recette C de l'encodeur : les
# éléments à PLAT en position __init__ (le C écrit les éléments de la
# séquence, ce qui rend exactement la forme déballée — remove_add_braces —
# du chemin Python)
def _recette_set(inst):
    return "set", list(inst), None


def _recette_frozenset(inst):
    return "frozenset", list(inst), None


# noms PORTEURS d'une enveloppe d'objet : un attribut ainsi nommé ne peut
# pas être aplati à côté de l'étiquette (il l'écraserait au rechargement) —
# l'état part alors sous "__state__". Filtre premier caractère : seules les
# clés commençant par "_" ou "$" paient le test d'appartenance.
_reserved_state_keys = frozenset(
    ("__class__", "__init__", "__new__", "__state__", "__items__",
     "__dict__", "$ref")
)


def _state_has_reserved_key(state):
    for key in state:
        if type(key) is str and key and key[0] in "_$" \
                and key in _reserved_state_keys:
            return True
    return False


def all_keys_are_str(dict_):
    for key in dict_:
        if type(key) != str:
            return False
    return True


if use_numpy:
    _numpy_float_dtypes = set(
        (numpy.dtype("float16"), numpy.dtype("float32"), numpy.dtype("float64"))
    )
    # dtypes que rapidjson.ArrayRows sait écrire directement depuis le buffer
    _array_rows_dtype_chars = frozenset("bhilqBHILQfd?")

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

    _numpy_dtypes_to_python_types = {numpy.bool_: bool}
    for numpy_type in _numpy_int_types:
        _numpy_dtypes_to_python_types[numpy_type] = int
    for numpy_type in _numpy_float_types:
        _numpy_dtypes_to_python_types[numpy_type] = float
else:
    _numpy_types = set()


NoneType = type(None)
remove_add_braces = {
    "set",
    "frozenset",
    "tuple",
    "collections.OrderedDict",
    "collections.Counter",
}


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


def _append_indent_unit(indent):
    return " " * indent if isinstance(indent, int) else indent


class _AppendIndenter:
    # décale d'un niveau chaque ligne de l'élément appendé (depuis le
    # 04/08/2026) : les octets du fichier restent IDENTIQUES à la
    # sérialisation directe de la liste complète. Sûr : dans du JSON, un
    # saut de ligne réel n'existe que dans la mise en forme (jamais dans le
    # contenu des chaînes, où il est échappé en \\n)
    def __init__(self, fp, unit):
        self._fp = fp
        self._unit = unit
        self._unit_bytes = unit.encode()

    def write(self, data):
        if isinstance(data, bytes):
            return self._fp.write(
                data.replace(b"\n", b"\n" + self._unit_bytes)
            )
        return self._fp.write(data.replace("\n", "\n" + self._unit))

    def __getattr__(self, name):
        return getattr(self._fp, name)


def _wrap_append_indent(fp, indent):
    if indent is None:
        return fp
    return _AppendIndenter(fp, _append_indent_unit(indent))


def _open_for_append(fp, indent, queue=True):
    """Ouvre le fichier et le place là où le prochain maillon s'écrit.

    Rend `(fp, vide)` : `vide` dit que la liste n'avait aucun maillon, seul
    cas où l'appelant connaisse le RANG de ce qu'il ajoute — donc où il puisse
    en tenir l'index sans relire le document.

    `queue` fait chercher une queue d'index de la forme "comment" : elle est
    retirée avant d'ajouter, sans quoi le document ne finirait plus par « ] »
    et l'append échouerait. Inutile aux appends suivants, la queue ne pouvant
    revenir tant que la liste n'est pas refermée.
    """
    length = 0
    remove_last_square_close = True
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
            remove_last_square_close = True

        else:
            fp = open(path, "wb+")  # pour test_iterator.py
            remove_last_square_close = False
    elif fp is None:
        raise Exception("Incorrect file (file, str ou unicode)")
    if remove_last_square_close:
        if queue:
            _tronque_queue_index(fp)
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

    # ce qui reste du document une fois le crochet fermant retiré : « [ » seul
    # veut dire une liste sans aucun maillon, donc un prochain maillon de rang 0
    vide = length == 0 or fp.tell() <= 1
    if length == 0:
        if indent is None:
            fp.write(b"[")
        else:
            fp.write(b"[\n" + _append_indent_unit(indent).encode())
    elif length > 2:
        if indent is None:
            try:
                fp.write(b",")
            except TypeError:
                fp.write(",")
        else:
            unit = _append_indent_unit(indent)
            try:
                fp.write(b",\n" + unit.encode())
            except TypeError:
                fp.write(",\n" + unit)
    return fp, vide


def _bornes_maillons(fp):
    """(nombre de maillons, position du dernier) d'une liste json déjà écrite.

    Sans rien désérialiser : la machine à états du découpage incrémental —
    `_scan_appended`, celle qui sert déjà au Decoder à rendre les éléments un
    par un — donne les bornes de chaque élément de premier niveau. Elle rend
    `ret_start == -1` au crochet qui referme la liste, et lève `shedule_break`
    à chaque fin d'élément ; un élément à cheval sur deux tampons est rendu en
    plusieurs morceaux, d'où le `courant` qui n'en retient que le premier.

    Ne sert qu'à rattraper un maillon écrit sans connaître son rang (voir
    `Encoder.append`) : c'est un balayage complet du fichier.
    """
    fp.flush()
    fp.seek(0)
    etat = (False, 0, 0, False, False, False)
    combien = 0
    dernier = -1
    courant = -1
    base = 0
    while True:
        tampon = fp.read(1 << 16)
        if not tampon:
            return combien, dernier
        depuis = 0
        while True:
            (debut, _fin, *etat, depuis, coupe) = rapidjson._scan_appended(
                tampon, depuis, *etat)
            if debut < 0:
                return combien, dernier
            if courant < 0:
                courant = base + debut
            if coupe:
                combien += 1
                dernier = courant
                courant = -1
            if depuis == 0:
                break
        base += len(tampon)


def _tronque_queue_index(fp):
    # un index rangé en "comment" ajoute une ligne DERRIÈRE le document : le
    # fichier ne finit plus par « ] » et l'append le refusait. La queue est
    # retirée, l'index qu'elle porte devenant faux dès le maillon suivant
    chemin = getattr(fp, "name", None)
    if not isinstance(chemin, str):
        return
    fp.flush()
    queue = rapidjson._index_queue(chemin)
    if queue is not None:
        fp.seek(queue[0])
        fp.truncate()


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


class _UpdatableClasses(set):
    # noms qualifiés des classes à mettre à jour en place, ET les classes
    # elles-mêmes : le nom écrit dans un json peut différer de celui que bâtit
    # class_str_from_class (un greffon Qt écrit "QtWidgets.QSpinBox" là où la
    # classe se nomme "PySide6.QtWidgets.QSpinBox") — un nom absent est
    # résolu en classe avant de conclure
    def __init__(self, updatables):
        super().__init__()
        self.classes = set()
        for updatable in updatables or ():
            if isinstance(updatable, str):
                self.add(updatable)
                try:
                    self.classes.add(class_from_class_str(updatable))
                except Exception:
                    pass
            else:
                self.add(class_str_from_class(updatable))
                self.classes.add(updatable)

    def __contains__(self, class_str):
        if set.__contains__(self, class_str):
            return True
        if not self.classes or not isinstance(class_str, str):
            return False
        try:
            cls = constructors[class_str]
        except KeyError:
            try:
                cls = class_from_class_str(class_str)
            except Exception:
                return False
        return cls in self.classes


def _descend(live, key):
    # un pas de la chaîne des clés sur les objets vivants (mode rehydrate) ;
    # une clé '~…' est un lecteur virtuel posé par un greffon
    if isinstance(key, int):
        if isinstance(live, (list, tuple)) and -len(live) <= key < len(live):
            return live[key]
        return None
    if key[:1] == "~":
        getter = rehydrate_getters.get(key)
        return None if getter is None else getter(live)
    if isinstance(live, dict):
        return live.get(key)
    value = getattr(live, key, None)
    if isinstance(value, (types.MethodType, types.BuiltinMethodType)):
        # clé d'état servie par un accesseur (Qt : centralWidget, geometry) :
        # une clé d'état est un attribut de données, jamais une méthode
        try:
            return value()
        except TypeError:
            return None
    return value


def _anchored(args, ancestor):
    if ancestor is None or args is None:
        return False
    if isinstance(args, dict):
        args = args.values()
    elif not isinstance(args, (list, tuple)):
        return False
    return any(value is ancestor for value in args)


def _get_authorized_classes_strings(classes):
    if not type(classes) in (set, list, tuple):
        if classes is None:
            classes = set()
        else:
            classes = [classes]
    _authorized_classes_strs = authorized_classes.copy()
    for elt in classes:
        if not type(elt) is str:
            elt = class_str_from_class(elt)
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
            classToRecClass = class_from_class_str(class_)
        else:
            classToRecStr = class_str_from_class(class_)
            classToRecClass = class_
        serializedattributes = []
        instanceVide = classToRecClass()
        for attribute in list(instanceVide.__dict__.keys()) + slots_from_class(class_):
            if not attribute.startswith("_"):
                serializedattributes.append(attribute)
        serializedattributes = tuple(sorted(serializedattributes))
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
        self.ranges = None
        # s = io.FileIO.read(self, 1)
        # if s not in (b"[", "["):
        #    raise Exception('the json data must start with "["')
        if "b" in mode:
            self.interesting = set(b'\\"{}[]')
            self.separators = set(b", \t\n\r")
            self.chars = list(b'\\"{}[]')
            if isinstance(fp, str):
                self._arme_index(fp)
        else:
            self.interesting = set('\\"{}[]')
            self.separators = set(", \t\n\r")
            self.chars = list('\\"{}[]')

    _MOTIF_MAILLON = re.compile(r"root\[\d+\]$")

    def _arme_index(self, chemin):
        # les frontières « root[i] » de l'index évitent le scan des maillons
        # indexés : chacun part au parseur en UNE lecture contiguë (le wrapper
        # C prend le bytes rendu tel quel, quelle que soit sa longueur). On
        # fait à l'index la même confiance que load(file, chemin_objet) :
        # lit() rend None si l'index ne couvre plus le document (fichier
        # réécrit ou appendé sans index) — scan intégral dans ce cas
        try:
            index_ = indexation.lit(chemin)
        except Exception:
            return
        if not index_:
            return
        bornes = sorted(tuple(v) for k, v in index_["paths"].items()
                        if self._MOTIF_MAILLON.match(k))
        if not bornes:
            return      # rien d'assez gros pour être indexé : scan intégral
        # lit() garantit root == [0, fin] : le document commence à 0. Ne
        # reste qu'à vérifier que sa racine est bien une liste (un dict
        # racine ne s'itère pas — le scan rendra ce qu'il rendait avant)
        if io.FileIO.read(self, 1) != b"[":
            io.FileIO.seek(self, 0)
            return
        self.in_squares = 1
        self.ranges = deque(bornes)

    def read(self, size=-1):
        if self.shedule_break:
            self.shedule_break = False
            # print("read(1): empty")
            return ""
        # tampon bytes : machine à états portée en C (~200x plus rapide que
        # la boucle Python ci-dessous, conservée pour le mode texte)
        if self.in_chunk_start == 0:
            ranges = self.ranges
            if ranges is not None and not (
                    self.in_quotes or self.in_curlys or self.in_simple
                    or self.in_object):
                # entre deux maillons : caler les lectures sur le prochain
                # maillon indexé, et le rendre d'un bloc quand on est dessus
                pos = io.FileIO.tell(self)
                while ranges and ranges[0][1] <= pos:
                    ranges.popleft()    # déjà passé (rattrapé par le scan)
                if ranges:
                    debut, fin = ranges[0]
                    if pos == debut:
                        ranges.popleft()
                        self.shedule_break = True
                        return io.FileIO.read(self, fin - debut)
                    if pos < debut and (size < 0 or size > debut - pos):
                        size = debut - pos  # ne pas mordre sur le maillon
            s = self.s = io.FileIO.read(self, size)
        else:
            s = self.s
        if not s:
            return s
        etait_simple = self.in_simple
        if isinstance(s, bytes):
            res = self._scan_c(s)
        else:
            res = self._read_python(s)
        if res is None:
            return ""       # fin de la liste json
        if res:
            return res
        if etait_simple and not self.in_simple:
            # vide parce que le tampon COMMENÇAIT par le terminateur d'une
            # valeur simple continuée (« null » coupé pile avant sa
            # virgule) : ce vide EST la fin du maillon pour le parseur —
            # le scan ne pose pas shedule_break dans ce cas, exprès
            return res
        # tranche vide alors que le tampon ne l'était pas : il ne restait
        # que des séparateurs (cas systématique devant un maillon indexé,
        # dont la lecture est calée juste avant son début ; possible aussi,
        # rarissime, quand un chunk ordinaire finit pile entre deux
        # maillons — le parseur prenait alors ce vide pour la fin du
        # fichier). Relire : chaque tour consomme un tampon non vide
        return self.read(size)

    def _scan_c(self, s):
        (
            ret_start,
            ret_end,
            self.in_quotes,
            self.in_curlys,
            self.in_squares,
            self.in_simple,
            self.in_object,
            self.backslash_escape,
            self.in_chunk_start,
            shedule_break,
        ) = rapidjson._scan_appended(
            s,
            self.in_chunk_start,
            self.in_quotes,
            self.in_curlys,
            self.in_squares,
            self.in_simple,
            self.in_object,
            self.backslash_escape,
        )
        if shedule_break:
            self.shedule_break = True
        if ret_start == -1:
            return None     # fin de la liste json
        return s[ret_start:ret_end]

    def _read_python(self, s):
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
        for i in range(in_chunk_start, len(s)):
            ch = s[i]
            # dans une chaîne, le caractère qui suit un antislash est
            # consommé QUEL QU'IL SOIT (l'ancien scanner ne consommait le
            # drapeau que sur les caractères « intéressants » : une chaîne
            # finissant par \\n avalait son guillemet fermant)
            if in_quotes and backslash_escape:
                backslash_escape = False
                continue
            if in_simple:
                if ch in separators or ch in ("]", 93):
                    if in_chunk_start < i:
                        # on prevoit d'arreter au read suivant sinon , va de tout facon arreter et on ne pourra pas remeter self.shedule_break à False
                        self.shedule_break = True
                    # self.seek(chunk_start + i + 1)
                    self.in_chunk_start = (i + 1) % len(s)
                    self.in_quotes = False
                    self.in_curlys = 0
                    self.in_squares = in_squares
                    self.in_simple = False
                    self.in_object = False
                    self.backslash_escape = False
                    # print("read(2): ",s[in_chunk_start:i])
                    return s[in_chunk_start:i]
            elif ch in interesting:
                check = False
                if in_quotes:
                    if ch == backslash:
                        # we are in a quote and we see a backslash; escape next char:
                        backslash_escape = True
                    elif ch == doublecote:
                        in_quotes = False
                        # signale qu'on sort d'un truc et qu'il faudra checker
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
                    if in_squares > 1:
                        in_object = True
                    else:
                        in_chunk_start = (i + 1) % len(s)
                elif ch == square_close:  # ]
                    in_squares -= 1
                    check = True
                    if not in_squares:  # on a ateint la fin de la liste json
                        return None
                if check and not in_quotes and not in_curlys and in_squares < 2:
                    if in_chunk_start < (i + 1):
                        # on prevoit d'arreter au read suivant sinon , va de tout facon arreter et on ne pourra pas remeter self.shedule_break à False
                        self.shedule_break = True
                    # self.seek(chunk_start + i + 1)
                    self.in_chunk_start = (i + 1) % len(s)
                    self.in_quotes = False
                    self.in_curlys = False
                    self.in_squares = in_squares
                    self.in_simple = False
                    self.in_object = False
                    self.backslash_escape = False
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


id_to_path = dict()
