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