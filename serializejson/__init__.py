"""
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
`python-rapidjson <https://github.com/python-rapidjson/python-rapidjson>`_,
`pybase64 <https://github.com/mayeut/pybase64>`_ and
`blosc <https://github.com/Blosc/python-blosc>`_  for optional `zstandard <https://github.com/facebook/zstd>`_ compression.

Some of the main features:

- supports Python 3.7 (maybe lower) or greater.
- serializes arbitrary python objects into a dictionary by adding `__class__` ,and eventually `__init__`, `__new__`, `__state__`, `__items__` keys.
- calls the same objects methods as pickle. Therefore almost all pickable objects are serializable with serializejson without any modification.
- for not already pickable object, you will allways be able to serialize it by adding methodes to the object or creating plugins for pickle or serializejson.
- generally 2x slower than pickle for dumping and 3x slower than pickle for loading (on your benchmark) except for big arrays (optimisation will soon be done).
- serializes and deserializes bytes and bytearray very quickly in base64 thanks to `pybase64 <https://github.com/mayeut/pybase64>`_ and lossless `blosc <https://github.com/Blosc/python-blosc>`_ compression.
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
- supports circular references and serialize only once duplicated objects, using "$ref" key an path to the first occurance in the json : `{"$ref": "root.xxx.elt"}` (⚠ not yet if the object is a list or dictionary).
- accepts json with comment (// and /\* \*/) if `accept_comments = True`.
- can automatically recognize objects in json from keys names and recreate them, without the need of `__class__` key, if passed in `recognized_classes`.
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

    #serialize in string
    object1 = set([1,2])
    dumped1 = serializejson.dumps(object1)
    loaded1 = serializejson.loads(dumped1)
    print(dumped1)
    >{
    >        "__class__": "set",
    >        "__init__": [1,2]
    >}


    #serialize in file
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
    import importlib.metadata as importlib_metadata
except ModuleNotFoundError:
    import importlib_metadata
try:
    __version__ = importlib_metadata.version("serializejson")
except:
    pass
import os
import io
import rapidjson
import gc
import blosc
import errno
from collections import deque
from pybase64 import b64decode, b64encode_as_string
from _collections_abc import list_iterator

try:
    import numpy
    from numpy import ndarray

    use_numpy = True
except ModuleNotFoundError:
    use_numpy = False
from . import serialize_parameters


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
    setters_names_from_class,
    slots_from_class,
    authorized_classes,
    Reference,
)


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
        "dict_non_str_keys",
        "collections.Counter",
        "collections.defaultdict",
        "collections.deque",
        "collections.OrderedDict",
    }
)

__all__ = ["dumps", "dump", "loads", "load", "append", "Encoder", "Decoder", "getstate", "class_from_class_str"]
no_default_value = []  # flag allowing to keep None as allowed value for Encoder default_value.


# --- FONCTIONS BASED API ----------------------


def dump(obj, file, **argsDict):
    """
    Dump an object into json file.

    Args:
        obj: object to dump.
        file (str or file-like): path or file.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    if isinstance(file, str):
        file = open(file, "wb")
    Encoder(**argsDict)(obj, file)


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
    return Encoder(**argsDict)(obj, return_bytes=False)


def dumpb(obj, **argsDict):
    """
    Dump object into json bytes.

    Args:
        obj: object to dump.
        **argsDict: parameters passed to the Encoder (see documentation).
    """
    return Encoder(**argsDict)(obj, return_bytes=False).encode("utf_8")


def append(obj, file=None, *, indent="\t", **argsDict):
    """
    Append an object into json file.

    Args:
        obj: object to dump.
        file (str or file-like):
            path or file. The file must be empty or containing a json list.
        indent: indent passed to Encoder.
        **argsDict: other parameters passed to the Encoder (see documentation).
    """
    file = _open_for_append(file, indent)
    Encoder(**argsDict)(obj, file)
    _close_for_append(file, indent)


def loads(json, *, obj=None, iterator=False, **argsDict):  # on ne peut pas en meme temps updater objet
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
    decoder = Decoder(**argsDict)
    if iterator:
        return decoder
    else:
        return decoder(json=json, obj=obj)


def load(file, *, obj=None, iterator=False, **argsDict):
    """
    Load an object from a json file.

    Args:
        file (str or file-like):
            the json path or file-like object.
        obj (optional):
            if provided, the object `obj` will be updated and no new object will be created.
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
        return Decoder(**argsDict).load(file=file, obj=obj)


# --- CLASSES BASED API -------------------------------------------------------


class Encoder(rapidjson.Encoder):
    """
    class for serialization of python objects into json.

    Args:
        file (str or file-like):
            the json path or file-like object.
            When specified, the encoded result will be written there
            if you don't pricise file to`dump()` method later.

        attributes_filter (bool or set/list/tuple):
            Controls whether remove "private" attributs starting with "_" from the saved state
            for objects without plugin, __getstate__,__serializejson__ or reimplemented
            __reduce_ex__ or __reduce__ methodes.
            False: filter private attributes to none classes (if not filtered in __reduce__ or __gestate__ methodes)
            True : filter private attributes for all classes
            set/list/tuple : filter private attributes for this classes

            Use it temporarily.
            - In order to stay compatible with pickle,
            you sould better code one of the __getstate__, __reduce_ex__,
            __reduce__ or a pickle plugin, filtering attributes starting with "_".
            - Otherwise, in order to be independent of this parameter, code
            a _serializejson__ method or serializejson plugin.
            - In this method or plugin you can call the helping function :
            state = serialize.__gestate__(self,attributes_filter = True)

        properties (bool, None, set/list/tuple, dict ):
            Controls whether add properties to the saved state
            for objects without plugin, __getstate__,__serializejson__ or reimplemented
            __reduce_ex__ or __reduce__ methodes.
            - False: add properties to none classes (as pickle)
            - True : add properties for all classes
            - None : (default) add properties defined in serializejson.properties dict (added by plugins or manualy before encoder call)
            (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )
            - set/list/tuple :  add all properties for classes in this set/list/tuple, in addition to properties defined in serializejson.properties dict
            [class1, class2,..] (not secure if unstruted json, use it only for debuging)
            - dict :  add properties defined in dict, in addition to properties defined in serializejson.properties dict
            {class1 : ["propertie1","propertie1"], class2: True}

            Use it temporarily.
            - In order to stay compatible with pickle,
            you sould better code one of the __getstate__, __reduce_ex__,
            __reduce__ or a pickle plugin, retrieving values for properties
            and returning them in the same dictionnary than __slots__,
            as the second element of a state tuple.
            - Otherwise, in order to be independent of this parameter, code
            a _serializejson__ method or serializejson plugin retrieving values
            for properties and return them in the state dictionnary.
            - In this method or plugin you can call the helping function :
            state = serialize.__gestate__(self,split_dict_slots = True, properties = True or list of properties names)

        getters (bool or set/list/tuple):
            Controls whether add values retrieve with getters to the saved state
            for objects without plugin, __getstate__,__serializejson__ or reimplemented
            __reduce_ex__ or __reduce__ methodes.
            False: add getters to none classes
            True : add getters for all classes
            set/list/tuple : add getters for this classes
            - False: save no other getters than thus called in __getstate__ methodes, like pickle.
            - True : save getters for all objects
            - None : (default) save getters defined in serializejson.getter dict (added by plugins or manualy before encoder call)
            (see documentation section: ref:`"Add plugins to serializejson"<add-plugins-label>`. )
            - set/list/tuple : save getters for classes in set/list/tuple, in addition to getters defined in serializejson.setters dict
            [class1, class2,..] (not secure if unstruted json, use it only for debuging)
            - dict : save getters defined in dict, in addition to getters defined in serializejson.getters dict
            {class1 : {"attribut_name":"getter_name",...}, class2: True}

            Use it temporarily.
            - In order to stay compatible with pickle,
            you sould better code one of the __getstate__, __reduce_ex__,
            __reduce__ or a pickle plugin, retrieving values for getters
            and returning them in the state. And code a __setstate__ methode
            calling setters for this values .
            - Otherwise, in order to be independent of this parameter, code
            a _serializejson__ method or serializejson plugin retrieving values for getters
            and returning them in the state. And code a __setstate__ methode
            calling setters for this values or leave the Decpder's setters parameter as True.
            - In this method or plugin you can call the helping function :
            state = serialize.__gestate__(self,getters = True)
            with getters as True, the getters will be automaticaly guessed
            or
            state = serialize.__gestate__(self,getters = {"a":"getA","b":"getB"})
            with getters as a dict, for finest control.
            With tuple as key ou can retrieve several attributes values from one getter.


        remove_default_values (bool or set/list/tuple):
            Controls whether remove values same as their default value from the state in
            order to save memory space, for objects without plugin, __getstate__,
            __serializejson__ or reimplemented __reduce_ex__ or __reduce__ methodes.
            False: remove defaul values to none classes
            True : remove defaul values for all classes
            set/list/tuple : remove defaul values for this classes.

            Use it temporarily.
            - Since the default values will not be stored and may change between
            different versions of your code, never use it for long term storage.
            Be aware that in order to know the default value, serializejson will
            create an insistence of the object's class without any __init__ argument.
            - In order to stay compatible with pickle,
            you sould better code one of the __getstate__, __reduce_ex__,
            __reduce__ or a pickle plugin, removing values same as their default value.
            - Otherwise, in order to be independent of this parameter, code
            a _serializejson__ method or serializejson plugin removing values same as their default value.
            - In this method or plugin you can call the helping function :
            state = serialize.__gestate__(self,remove_default_values = True or dict {name : default_value,...})

        chunk_size:
            write the file in chunks of this size at a time.

        ensure_ascii:
            whether non-ascii str are dumped with escaped unicode or utf-8.

        indent (None, int or '\\\\t'):
            indentation width to produce pretty printed JSON.

            - None: Json in one line (quicker than with indent).
            - int: new lines and `indent` spaces for indent.
            - '\\\\t': new lines and tabulations for indent (take less space than int > 1).

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

        bytes_compression(None or str):
            Compression for bytes, bytesarray and numpy arrays:

            - `None` : no compression
            - `str` : compression name ("blosc_zstd"(by deault), b"blosclz", "blosc_lz4", "blosc_lz4hc" or "blosc_zlib") with maximum compression level 9.
            - `tuple` : (compression name, compression level) with compression level from 0 (no compression) to 9 (maximum compression)

            By default the "zstd" compression is used with compression level 1.
            For the highest compression (but with slower dumping) use "zstd" with compression level 9

        bytes_size_compression_threshold (int):
            bytes size threshold beyond compression is tried to reduce size of
            bytes, bytesarray and numpy array if `bytes_compression` is not None.
            The default value is 512, generaly beside the compression is not
            worth it due to the header size and the additional cpu cost.

        array_readable_max_size (int,None or dict):
            Defines the maximum array size for serialization in readable numbers.
            By default array_readable_max_size is set to 0, all arrays are encoded in base 64.

            - `int` : all arrays smaller than this size are serialized in readable numbers.
            - `None` : there is no maximum size and all arrays are serialized in readable numbers.
            - `dict` : for each typecode key, the value define the maximum size of this typecode arrays for serialization in readable numbers. If value is `None` there is no maximum and array of this typecode are all serialized in readable numbers. If you want only signed int arrays to be readable, then you should pass `array_readable_max_size = {"i":None}`

            .. note::
                serialization of int arrays can take much less space in readable,
                but is much slower than in base 64 for big arrays. If you have lot or large int arrays and
                performance matters, then you should stay with default value 0.


        numpy_array_readable_max_size (int,None or dict):
            Defines the maximum numpy array size for serialization in readable numbers.
            By default numpy_array_readable_max_size is set to 0, all numpy arrays are encoded in base 64.

            - `int` : all numpy arrays smaller than this size are serialized in readable numbers.
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

        strict_pickle (False by default)
            If True serialize with exactly the same behaviour than pickle:
            - disabling serializejson plugins for custom serialization.(no numpyB64)
            - disabling attributes_filter
            - disabling keys sorting
            - disabling numpy_array_to_list
            - disabling numpy_types_to_python_types
            - keeping __dict__ and __slots__ separated in a tuple if both, instead of merge them in a dictionnary
            (you should prepare __setstat__ methods to receive both a tuple or a dictionnary)
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
        file=None,
        *,
        strict_pickle=False,
        return_bytes=False,
        attributes_filter=True,
        properties=False,
        getters=False,
        remove_default_values=False,
        chunk_size=65536,
        ensure_ascii=False,
        indent="\t",
        single_line_init=True,
        single_line_new=True,
        single_line_list_numbers=True,
        sort_keys=False,
        bytes_compression=("blosc_zstd", 1),  #
        bytes_size_compression_threshold=512,
        array_use_arrayB64=True,  # le laisser ?
        array_readable_max_size=0,  #'int32':-1
        numpy_array_use_numpyB64=True,  # le laisser ?
        numpy_array_readable_max_size=-1,  #'int32':-1
        numpy_array_to_list=False,
        numpy_types_to_python_types=True,
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
            mapping_mode=rapidjson.MM_ONLY_DICTS
            # **argsDict
        )
        self.protocol = protocol
        self.attributes_filter = bool_or_set(attributes_filter)
        self.properties = _get_properties(properties)
        self.getters = _get_getters(getters)
        self.remove_default_values = bool_or_set(remove_default_values)
        self.file = file
        self.return_bytes = return_bytes
        if indent is None:
            self.single_line_list_numbers = False
            self.single_line_init = False
            self.single_line_new = False
        else:
            self.single_line_list_numbers = single_line_list_numbers
            self.single_line_init = single_line_init
            self.single_line_new = single_line_new
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
        self.array_use_arrayB64 = array_use_arrayB64
        self.array_readable_max_size = array_readable_max_size
        self.numpy_array_to_list = numpy_array_to_list
        self.numpy_array_use_numpyB64 = numpy_array_use_numpyB64
        self.numpy_array_readable_max_size = numpy_array_readable_max_size
        self.numpy_types_to_python_types = numpy_types_to_python_types
        self.strict_pickle = strict_pickle

        unexpected_keywords_arguments = set(plugins_parameters) - set(encoder_parameters)
        if unexpected_keywords_arguments:
            raise TypeError(
                "serializejson.Encoder got unexpected keywords arguments '"
                + ", ".join(unexpected_keywords_arguments)
                + "'"
            )
        self.plugins_parameters = encoder_parameters.copy()
        self.plugins_parameters.update(plugins_parameters)
        return self

    def dump(self, obj, file=None):
        """
        Dump object into json file.

        Args:
            obj: object to dump.
            file (optional str or file-like):
                the json path or file-like object.
                When specified, json is written into this file.
                Otherwise json is written into the file passed to `Encoder()` constructor.
        """
        if file is None:
            file = self.file
        if isinstance(file, str):
            file = open(file, "wb")
        self.__call__(obj, file=file, chunk_size=self.chunk_size)

    def dumps(self, obj):
        """
        Dump object into json string.
        """
        return self.__call__(obj, return_bytes=False)

    def dumpb(self, obj):
        """
        Dump object into json bytes.
        """
        return self.__call__(obj, return_bytes=True)

    def append(self, obj, file=None):
        """
        Append object into json file.

        Args:
            obj: object to dump.
            file (optional str or file-like): path or file. If provided, the object will be
                dumped into this file instead of being dumped into the file passed at the Encoder
                constructor. The file must be empty or contain a json list.
        """
        if file is None:
            file = self.file
        file = _open_for_append(file, self.indent)
        rapidjson.Encoder.__call__(self, obj, stream=file, chunk_size=self.chunk_size)
        _close_for_append(file, self.indent)

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
            return rapidjson.RawJSON('{"$ref": "%s"}' % self._get_path(inst, already_explored=set([id(locals())])))
        self._already_serialized.add(id_)
        type_inst = type(inst)
        if self.numpy_types_to_python_types and type_inst in _numpy_types:
            return _numpy_dtypes_to_python_types[type_inst](inst)
        if use_numpy and type_inst is ndarray and self.numpy_array_to_list:
            if self._dump_one_line or not self.single_line_list_numbers:
                return (
                    inst.tolist()
                )  # A REVOIR : pas génial... va tester si nombres tous du meme type et ne pas pas utiliser rapidjson.NM_NATIVE?
            if inst.dtype in _numpy_float_dtypes:
                number_mode = self.number_mode
            else:
                number_mode = rapidjson.NM_NATIVE  # permet décceler pas mal
            if inst.ndim == 1:
                return rapidjson.RawJSON(
                    rapidjson.dumps(
                        inst.tolist(),
                        ensure_ascii=False,
                        number_mode=number_mode,
                        iterable_mode=rapidjson.IM_ONLY_LISTS,
                        mapping_mode=rapidjson.MM_ONLY_DICTS,
                    )
                )
            return [
                rapidjson.RawJSON(
                    rapidjson.dumps(
                        elt.tolist(),
                        ensure_ascii=False,
                        number_mode=number_mode,
                        iterable_mode=rapidjson.IM_ONLY_LISTS,
                        mapping_mode=rapidjson.MM_ONLY_DICTS,
                    )
                )
                for elt in inst
            ]  # inst.tolist()
        if type_inst is tuple:
            # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tuple_from_instance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tuple_from_instance
            self.dumped_classes.add(tuple)
            dic = {"__class__": "tuple", "__new__": list(inst)}
        elif type_inst is Reference:
            return rapidjson.RawJSON(
                '{"$ref": "%s%s"}' % (self._get_path(inst.obj, already_explored=set([id(inst.__dict__)])), inst.sup_str)
            )
        else:
            dic = self._dict_from_instance(
                inst
            )  # 8.6 % (correspond au temps pour conversion en b64 avec pybase64.b64encode) du temps sur obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)

        if not self._dump_one_line:
            if self.single_line_init:
                args = dic.get("__init__", None)
                if isinstance(args, list):
                    dic[
                        "__init__"
                    ] = rapidjson.RawJSON(  # 91.2 % du temps avec obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)
                        rapidjson.dumps(
                            args,
                            ensure_ascii=self.ensure_ascii,
                            default=self._default_one_line,
                            sort_keys=self.sort_keys,
                            bytes_mode=self.bytes_mode,
                            number_mode=self.number_mode,
                            iterable_mode=rapidjson.IM_ONLY_LISTS,
                            mapping_mode=rapidjson.MM_ONLY_DICTS
                            # **self.kargs
                        )
                    )
            if self.single_line_new:
                args = dic.get("__new__", None)
                if type(args) is list:
                    dic[
                        "__new__"
                    ] = rapidjson.RawJSON(  # 91.2 % du temps avec obj = bytes(numpy.arange(2**20,dtype=numpy.float64).data)
                        rapidjson.dumps(
                            args,
                            ensure_ascii=self.ensure_ascii,
                            default=self._default_one_line,
                            sort_keys=self.sort_keys,
                            bytes_mode=self.bytes_mode,
                            number_mode=self.number_mode,
                            iterable_mode=rapidjson.IM_ONLY_LISTS,
                            mapping_mode=rapidjson.MM_ONLY_DICTS
                            # **self.kargs
                        )
                    )

            if self.single_line_list_numbers:
                for key, value in dic.items():
                    if (
                        key != "__class__"
                        and (key != "__init__" or not self.single_line_init)
                        and (key != "__new__" or not self.single_line_new)
                        and type(value) is list
                        and _onlyOneDimSameTypeNumbers(value)
                    ):

                        dic[key] = rapidjson.RawJSON(
                            rapidjson.dumps(
                                value,
                                ensure_ascii=self.ensure_ascii,
                                default=self._default_one_line,
                                bytes_mode=self.bytes_mode,
                                number_mode=self.number_mode,
                                iterable_mode=rapidjson.IM_ONLY_LISTS,
                                mapping_mode=rapidjson.MM_ONLY_DICTS
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
        if self.numpy_types_to_python_types and type_inst in _numpy_types:
            return _numpy_dtypes_to_python_types[type_inst](inst)
        if type_inst is tuple:
            # isinstance(inst,tuple) attrape les struct_time # je l'ai mis là plutot que dans tuple_from_instance car très spécifique à json et les tuples n'ont pas de réduce contrairement à set , qui lui est pour l'instant traité dans dict_from_instance -> tuple_from_instance
            self.dumped_classes.add(tuple)
            return {"__class__": "tuple", "__new__": list(inst)}
        if type_inst is Reference:
            return {"$ref": self._get_path(inst.obj, already_explored=set([id(inst.__dict__)])) + inst.sup_str}
        if type_inst is ndarray and self.numpy_array_to_list:
            return inst.tolist()
        return self._dict_from_instance(inst)

    def _dict_from_instance(self, inst):

        if type(inst) is dict:  # dictionnary with non string key
            d = {"__class__": "dict_non_str_keys"}
            init_dict = d
            for key, value in inst.items():
                # if type(key) is tuple :
                #    key = list(key)
                new_key = None
                type_key = type(key)
                if type_key is int:  # pas mis les float pour garder -inf et inf (nan ca déconne dans les dictionnaires)
                    new_key = str(key)
                elif type_key is str:
                    try:
                        rapidjson.loads(key)
                    except:
                        if key.endswith("'") and (
                            key.startswith("'") or key.startswith("b'") or key.startswith("b64'")
                        ):
                            new_key = f"'{key}'"
                        else:
                            new_key = key
                    else:
                        new_key = f"'{key}'"
                elif type_key is bytes:
                    try:
                        new_key = f"b'{key.decode('ascii_printables')}'"
                    except:
                        new_key = f"b64'{b64encode_as_string(key)}'"
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
        class_, initArgs, state, listitems, dictitems, newArgs = tuple_from_instance(inst, self.protocol)
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
                            and not (self.numpy_array_to_list and type_first is numpy.ndarray)
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
            if (type(state) is not dict) or (hasattr(inst, "__setstate__") and not all_keys_are_str(state)):
                dictionnaire["__state__"] = state
            else:
                dictionnaire.update(state)
        return dictionnaire

    def __call__(self, obj, file=None, chunk_size=65536, return_bytes=None):
        if return_bytes is None:
            return_bytes = self.return_bytes
        if type(obj) is list and self.single_line_list_numbers and _onlyOneDimSameTypeNumbers(obj):
            return rapidjson.dumps(
                obj,
                ensure_ascii=False,
                default=self._default_one_line,
                bytes_mode=self.bytes_mode,
                number_mode=self.number_mode,
                iterable_mode=rapidjson.IM_ONLY_LISTS,
                mapping_mode=rapidjson.MM_ONLY_DICTS,
                # return_bytes = return_bytes
                # **self.kargs
            )
        blosc.set_nthreads(1)  # slower but for determinist behaviour in order to be able to versining jsons
        serialize_parameters.strict_pickle = self.strict_pickle
        serialize_parameters.attributes_filter = self.attributes_filter
        serialize_parameters.properties = self.properties
        serialize_parameters.getters = self.getters
        serialize_parameters.remove_default_values = self.remove_default_values
        serialize_parameters.bytes_compression = self.bytes_compression
        serialize_parameters.bytes_compression_level = self.bytes_compression_level
        serialize_parameters.bytes_size_compression_threshold = self.bytes_size_compression_threshold
        serialize_parameters.array_use_arrayB64 = self.array_use_arrayB64
        serialize_parameters.array_readable_max_size = self.array_readable_max_size
        serialize_parameters.numpy_array_use_numpyB64 = self.numpy_array_use_numpyB64
        serialize_parameters.numpy_array_readable_max_size = self.numpy_array_readable_max_size
        serialize_parameters.__dict__.update(self.plugins_parameters)
        self.dumped_classes = set()
        self._already_serialized = set()
        self._already_serialized_id_dic_to_obj_dic = dict()
        self._root = obj
        encoded = rapidjson.Encoder.__call__(
            self, obj, stream=file, chunk_size=chunk_size
        )  # ,return_bytes = return_bytes)
        del self._already_serialized
        del self._already_serialized_id_dic_to_obj_dic
        return encoded

    # @profile
    def _searchSerializedParent(self, obj, already_explored=set()):  # ,list_deep = 10):
        root = self._root
        if obj is root:
            return ["root"]
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
                    if id_parent_test in self._already_serialized_id_dic_to_obj_dic:
                        parent_inst, parent_dict = self._already_serialized_id_dic_to_obj_dic[id_parent_test]
                        is_dict = False
                    else:
                        parent_inst = parent_test
                        is_dict = True
                    if self.sort_keys:
                        parent_test_keys = sorted(parent_test)
                    else:
                        parent_test_keys = parent_test.keys()
                    for key in parent_test_keys:  # sorted(parent_test):
                        value = parent_test[key]
                        if value is obj:
                            if is_dict:
                                pathElement = "['%s']" % key
                            else:
                                pathElement = "." + key
                            for elt in self._searchSerializedParent(parent_inst, already_explored):
                                pathElements.append(elt + pathElement)
                            break
                if type_parent_test is list and not type(parent_test[-1]) is list_iterator:
                    for key, value in enumerate(parent_test):
                        if value is obj:
                            for elt in self._searchSerializedParent(parent_test, already_explored):
                                pathElements.append(elt + "[%d]" % key)
                            break
        return pathElements

    def _get_path(self, obj, already_explored=set()):
        already_explored.add(id(locals()))
        pathElements = self._searchSerializedParent(obj, already_explored=already_explored)
        if not pathElements:
            # return f'impossible to find a path from root object for {obj}'
            raise Exception(f"impossible to find a path from root object for {obj}")
        return sorted(pathElements)[0]


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
            the `__class__` keywords in json, in addition to the usuals classes.
            Usual classes are : complex ,bytes, bytearray, Decimal, type, set,
            frozenset, range, slice, deque,  datetime, timedelta, date, time
            numpy.array, numpy.dtype.
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
    ):

        if accept_comments:
            parse_mode = rapidjson.PM_COMMENTS
        else:
            parse_mode = rapidjson.PM_NONE
        self = super().__new__(cls, parse_mode=parse_mode)  # , **argsDict)
        self.strict_pickle = strict_pickle
        if strict_pickle:
            setters = False
            properties = False
            numpy_array_from_list = False
            numpy_array_from_heterogenous_list = False
        self.file = file
        self.setters = _get_setters(setters)
        self.properties = _get_properties(properties)
        self._authorized_classes_strs = _get_authorized_classes_strings(authorized_classes)
        self._class_from_attributes_names = _get_recognized_classes_dict(recognized_classes)
        self.set_updatables_classes(updatables_classes)
        # self.accept_comments = accept_comments
        # self.numpy_array_from_list=numpy_array_from_list
        self.default_value = default_value
        self.chunk_size = chunk_size
        self.file_iter = None
        self._updating = False

        self.numpy_array_from_list = numpy_array_from_list
        self.numpy_array_from_heterogenous_list = numpy_array_from_heterogenous_list
        if numpy_array_from_heterogenous_list:
            self.numpy_array_from_list = True
            self.end_array = self._end_array_if_numpy_array_from_heterogenous_list
        elif numpy_array_from_list:
            self.end_array = self._end_array_if_numpy_array_from_list
        return self

    def load(self, file=None, obj=None):
        """
        Load object from json file.

        Args:
            file (optional str or file-like):
                the json path or file-like object.
                When specified, json is read  from this file.
                Otherwise json is read from the file passed to `Decoder()` constructor.

            obj (optional):
                If provided, the object `obj` will be updated and no new object will be created.

        Return:
            created object or updated object if passed obj.
        """

        if file is None:
            file = self.file
        if isinstance(file, str):
            # print("load",file)
            if not os.path.exists(file):
                if self.default_value is no_default_value:
                    raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file)
                return self.default_value
            file = _open_with_good_encoding(file)
        elif file is None:  # a priori pointeur vers ficheir
            raise ValueError('Encoder.load need a "file" path/file argument')
        return self.__call__(json=file, obj=obj)

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
        return self.__call__(json=json, obj=obj)

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
        updatableClassStrs = set()
        if updatables is not None:
            for updatable in updatables:
                if isinstance(updatable, str):
                    updatableClassStrs.add(updatable)
                else:
                    updatableClassStrs.add(class_str_from_class(updatable))
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
        # self._counter += 1
        # self._deserializeds.add()
        if self._updating:
            self.ancestors.pop()  # se retire lui meme
        class_str = inst.get("__class__", None)
        if class_str:
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
            if self.root:
                # try:
                inst_potential = from_name(
                    inst["$ref"], accept_dict_as_object=True, root=self.root
                )  # essaye de remplacer tout de suite si possible
                if not type(inst_potential) is dict:  # verifie que ce n'est pas un objet qui n'a pas encore été recré
                    return inst_potential
                if "__class__" not in inst_potential:
                    return inst_potential
                inst_potential_epured = {
                    key: inst_potential[key] for key in ["__class__", "__init__", "__new__"] if key in inst_potential
                }
                inst = self._inst_from_dict(inst_potential_epured)
                inst_potential["__class__"] = inst
                return inst
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
        return inst

    def __call__(self, json, obj=None):
        """
        Args:
            file(str,file-like): file-like or path of the file containing the JSON to be decoded
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
        serialize_parameters.strict_pickle = self.strict_pickle
        serialize_parameters.setters = self.setters
        serialize_parameters.properties = self.properties
        self.converted_numpy_array_from_lists = set()
        # self._counter = 0
        self._updating = False
        # for duplicates -----------
        self.root = None
        if isinstance(json, str):
            self.json_startswith_curly = json.startswith("{")
        elif isinstance(json, bytes):
            self.json_startswith_curly = json.startswith(b"{")
        else:
            self.json_startswith_curly = json.read(1) in ("{", b"{")
            json.seek(0)
        self.duplicates_to_replace = []
        # for updating ------------------
        if obj is None:
            self._updating = False
            loaded = rapidjson.Decoder.__call__(self, json, chunk_size=self.chunk_size)
        else:  # update
            self._updating = True
            self.ancestors = deque()
            self.ancestors.append(None)
            self.node_has_descendants_to_recreate = set()
            loaded_dict = rapidjson.Decoder.__call__(self, json, chunk_size=self.chunk_size)
            loaded = self._exploreToUpdate(obj, loaded_dict)
        # on restaure doublons qu'on a pu restaurer pendant deserialisation (dans une liste ou doublon referencant un parent)
        duplicates_to_replace = self.duplicates_to_replace
        if duplicates_to_replace:
            gc.collect()  # pas sur qu'indispensable mais dans le doute  https://docs.python.org/3/library/gc.html#gc.get_referrers
            while duplicates_to_replace:
                duplicate_to_replace = duplicates_to_replace.pop()
                referenced = from_name(duplicate_to_replace["__init__"], accept_dict_as_object=True, root=loaded)
                refs = gc.get_referrers(duplicate_to_replace)
                skip = (locals(), refs)
                for parent in refs:
                    if parent not in skip:
                        if type(parent) is dict:
                            for key, value in parent.items():
                                if value is duplicate_to_replace:
                                    parent[key] = referenced
                                    break
                        elif type(parent) is list:
                            for key, value in enumerate(parent):
                                if value is duplicate_to_replace:
                                    parent[key] = referenced
                                    break
                        elif hasattr(parent, "__slots__"):
                            for slot in parent.__slots__:
                                if hasattr(parent, slot) and getattr(parent, slot) is duplicate_to_replace:
                                    setattr(parent, slot, referenced)
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
        file = self.file
        if isinstance(file, str):
            if not os.path.exists(file):
                return [self.default_value]
            self.file_iter = _json_object_file_iterator(file, mode="rb")
        else:
            raise Exception("not yet able to load_iter on %s" % str(type(file)))
        return self

    def _inst_from_dict(self, inst):
        class_str = inst["__class__"]
        if class_str in self._authorized_classes_strs or not isinstance(class_str, str):
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
                inst["__class__"] == "dict_non_str_keys"
            ):  # je l'ai mis ici car trop specifique à json pour etre dans tools (qui est partagé avec serializePython et serializeRepr)
                return dict_non_str_keys(inst)
            return instance(**inst)
        raise TypeError("%s is not in authorized_classes" % inst["__class__"])

    # @profile
    def _exploreToUpdate(self, obj, loaded_node):

        # gère le cas où loaded_node est un dictionnaire ----------------------
        if isinstance(loaded_node, dict):
            obj_keys = None  # plutot que set vide un objet peut ne pas avoir d'attributes ni de slots initialisés
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
                    if hasattr(obj, "__dict__"):  # A REVOIR : ne marche pas avec les slots
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
                loaded_node_has_descendants_to_recreate = id(loaded_node) in self.node_has_descendants_to_recreate

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
                (isinstance(elt, ndarray) and elt.dtype is first_elt_dtype and elt.shape == first_elt_shape)
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
            if all((isinstance(elt, ndarray) and elt.shape == first_elt_shape) for elt in sequence):
                array = numpy.array(sequence)
                self.converted_numpy_array_from_lists.add(id(array))
                return array
        return sequence

    def __next__(self):
        try:
            return rapidjson.Decoder.__call__(self, self.file_iter, chunk_size=self.chunk_size)
        except rapidjson.JSONDecodeError as error:
            self.file_iter.close()
            if error.args[0] == "Parse error at offset 0: The document is empty.":
                raise StopIteration
            else:
                raise


# ----------------------------------------------------------------------------------------------------------------------------
# --- INTERNES -----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------
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


def dict_non_str_keys(dict_):
    d = dict()
    del dict_["__class__"]
    for key, value in dict_.items():
        try:
            key = loads(key)
        except:
            if key.endswith("'"):
                if key.startswith("'"):
                    key = key[1:-1]
                elif key.startswith("b'"):
                    key = key[2:-1].encode("ascii_printables")
                elif key.startswith("b64'"):
                    key = b64decode(key[4:])
        else:
            if type(key) is list:
                key = tuple(key)
        d[key] = value
    return d


def all_keys_are_str(dict_):
    for key in dict_:
        if type(key) != str:
            return False
    return True


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

    _numpy_dtypes_to_python_types = {numpy.bool_: bool}
    for numpy_type in _numpy_int_types:
        _numpy_dtypes_to_python_types[numpy_type] = int
    for numpy_type in _numpy_float_types:
        _numpy_dtypes_to_python_types[numpy_type] = float
else:
    _numpy_types = set()


NoneType = type(None)
remove_add_braces = {"set", "frozenset", "tuple", "collections.OrderedDict", "collections.Counter"}


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
        for attribute in [instanceVide.__dict__.keys()] + slots_from_class(class_):
            if not attribute.startswith("_"):
                serializedattributes.append(attribute)
        serializedattributes = tuple(sorted([serializedattributes]))
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
