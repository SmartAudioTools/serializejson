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
- serializes arbitrary python objects into a dictionary by adding `__class__` ,and eventually `__init__`, `__new__`, `__state__`, `__items__` keys.
- calls the same objects methods as pickle. Therefore almost all pickable objects are serializable with serializejson without any modification.
- for not already pickable object, you will allways be able to serialize it by adding methodes to the object or creating plugins for pickle or serializejson.
- generally 2x slower than pickle for dumping and 3x slower than pickle for loading (on your benchmark) except for big arrays (optimisation will soon be done).
- serializes and deserializes bytes and bytearray very quickly in base64, encoded and decoded in C++ directly from and into the JSON stream, with lossless `blosc <https://github.com/Blosc/python-blosc>`_ compression.
- serialize properties and attributes with getters and setters if wanted (unlike pickle).
- json data will still be directly loadable if you have transform some attributes in slots or properties in your code since your last serialization. (unlike pickle)
- can serialize `__init__(self,..)` arguments by name instead of positions, allowing to skip arguments with defauts values and making json datas robust to a change of `__init__` parameters order.
- serialized objects take generally less space than when serialized with pickle: for binary data, the 30% increase due to base64 encoding is in general largely compensated using the lossless `c-blosc2 <https://github.com/Blosc/c-blosc2>`_ compression, whose ``bytes_compression="smart"`` ladder trades size for speed by a single level number, from the fast default up to 59 % of pickle's size (see the benchmarks below).
- serialized objects are human-readable and easy to read. Unlike pickled data, your data will never become unreadable if your code evolves: you will always be able to modify your datas with a text editor (with find & replace for example if you change an attribut name).
- serialized objects are text and therefore versionable and comparable with versionning and comparaison tools.
- can safely load untrusted / unauthenticated sources if authorized_classes list parameter is set carefully with strictly necessary objects (unlike pickle).
- can update existing objects recursively instead of override them. serializejson can be used to save and restore in place a complete application state (⚠ not yet well tested).
- filters attribute starting with "_" by default (unlike pickle). You can keep them if wanted with `filter_ = False`.
- numpy arrays can be serialized as lists with automatic conversion in both ways or in a conservative way.
- supports circular references and serialize only once duplicated objects, lists and dictionaries, using "$ref" key an path to the first occurance in the json : `{"$ref": "root.xxx.elt"}`.
- accepts json with comment (// and /\* \*/) if `accept_comments = True`.
- can automatically recognize objects in json from keys names and recreate them, without the need of `__class__` key, if passed in `recognized_classes`.
- serializejson is easly interoperable outside of the Python ecosystem with this recognition of objects from keys names or with `__class__` translation between python and other language classes.
- dump and load support string path.
- can iteratively encode (with append) and decode (with iterator) a list in json file, which helps saving memory space during the process of serialization and deserialization and useful for logs.
- can encrypt with a password (``encryption_key="…"``) in the standard `age <https://age-encryption.org>`_ format, as binary or as ASCII armor (``encryption_in_base64``).
- runs in the browser under `Pyodide <https://pyodide.org>`_ (WebAssembly wheel), encryption included.

.. warning::

    **⚠** Do not load serializejson files from untrusted / unauthenticated sources without carefully setting the load authorized_classes parameter.

    **⚠** Never dump a dictionary with the `__class__` key, otherwise serializejson will attempt to reconstruct an object when loading the json.
    Be careful not to allow a user to manually enter a dictionary key somewhere without checking that it is not `__class__`.
    Due to current limitation of rapidjson we cannot we cannot at the moment efficiently detect dictionaries with the `__class__` key to raise an error.


Benchmarks against pickle
=========================

All charts below compare serializejson **with its default settings** (level 1
of the ``bytes_compression="smart"`` ladder: zigzag → bitshuffle → lz4 level
1, base64 and JSON envelope **included**) against ``pickle.dumps``
protocol 4, on REAL corpora (photographic and screenshot images, SQAM audio
references, and the whole set concatenated into a single 200 MB array as the
out-of-cache case).
Every value is a ratio serializejson / pickle: **below ×1 — the smaller the
bar, the bigger the advantage for serializejson**. They are produced by
``python tests/lance_benchmarks.py`` (median of ~50 trials, alternated in
the same process, **cache flushed before each trial** — the RAM regime is the
only one a real application gets on data it has just produced).

Pure in-memory conversion — with the **default** level 1 the serialized size is
**82 % of pickle's on geometric average** (up to 1.5× smaller on audio, but
14 to 24 % *larger* on the most photographic images, which no generic chain
compresses), and the whole ladder is one number away: its **last level brings
that to 59 %** of pickle's size, for about a quarter more CPU time. Pickle,
which is a simple memory copy, stays faster on CPU time alone in every case.
Every chart uses the same device: four time bars — writing then reading back,
first in RAM, then to and from the measuring machine's disk (NVMe PCIe 3,
~3.5 GB/s, transfer time included) — under an unfilled **blue frame whose top
edge is the size ratio**, as wide as the four bars together, so nothing is ever
hidden. One chart per ladder setting, since the size depends neither on the
direction nor on the device. The vertical scale is linear below ×1 and logarithmic
above it. The three charts are the default level, the smallest level of the
ladder, and its level 0, which drops compression altogether (plain base64) —
writing then becomes **faster than pickle** on most profiles, at the cost of a
payload one third larger:

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_memoire_smart.svg
   :alt: default smart level: size and speed ratios against pickle
   :width: 100%

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_memoire_min.svg
   :alt: smallest smart level: size and speed ratios against pickle
   :width: 100%

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_memoire_b64.svg
   :alt: no compression at all: size and speed ratios against pickle
   :width: 100%

As soon as the bytes have to reach a storage device or a network, the saved
bytes also save time: the curves below show the **total** time ratio
(serialization + transfer at the given throughput). At the default level, the
break-even throughput is around 700 MB/s to 1.4 GB/s on the audio corpora and
below 500 MB/s on the images, so serializejson wins on a hard drive and on a
SATA SSD for everything that compresses, while pickle keeps the lead on a fast
NVMe and on data that does not compress:

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_ecriture_support.svg
   :alt: total write time ratio against storage throughput
   :width: 100%

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_lecture_support.svg
   :alt: total read time ratio against storage throughput
   :width: 100%

On realistic machines — pairing each CPU with a storage of the same class,
from a Raspberry Pi 5 on a microSD (or on an NVMe capped by its single
PCIe 2.0 lane) to a Ryzen 9 desktop on a PCIe 5 NVMe — the balance follows
the storage: the slower it is, the more the saved bytes pay back the compute
time. On the anchor profile, a screenshot corpus that barely compresses (96 %
of pickle's size at the default level), pickle stays ahead everywhere, from
×1.07 on the microSD Pi to ×2.64 on the PCIe 5 desktop — the slow machine is
where the gap almost closes, and a level of the ladder that actually shrinks
the payload turns it around. The chart is anchored on the corpus's largest
single profile, named in its title, with compute times scaled by each CPU's
approximate relative speed:

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_machines.svg
   :alt: total write and read time ratios on realistic machines
   :width: 100%

Against dedicated lossless image codecs on the image corpora, serializejson
does not predict in 2D so PNG compresses 1.6-2.2× smaller and lossless
JPEG XL 1.8-3.3× smaller — but the default level **encodes more than 20×
faster than both**, and decodes 8 to 10× faster than PNG (27 to 70× faster
than JPEG XL, whose times include the process launch):

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_codecs_images.svg
   :alt: serializejson against PNG and JPEG XL on the image corpora
   :width: 100%

The next two charts put each codec in the usual device — size frame over the
four time bars — with the codec, not pickle, as the reference:

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_codecs_png.svg
   :alt: serializejson against PNG: size and time ratios
   :width: 100%

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_codecs_jxl.svg
   :alt: serializejson against lossless JPEG XL: size and time ratios
   :width: 100%

Beyond big binary data, the repository's object catalog (every python type
category from ``tests/objects/basic_objects.py``) and the official
pyperformance ``bm_pickle`` workloads (myriads of small dicts, tuples and
lists — pickle's historical home turf) give the honest picture on small
objects: serializejson stays within ×1.3-2.0 of pickle when writing and
×1.4-2.4 when reading on the official workloads, with a few identified slow
paths on exotic categories. At those
sizes RAM and cache are not distinguishable — a few kilobytes stay in cache in
real life too — so the first two bars are cache times and the disk bars add
almost nothing:

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_types_objets.svg
   :alt: time ratios per python type category
   :width: 100%

.. image:: https://raw.githubusercontent.com/SmartAudioTools/serializejson/master/docs_source/images/benchmark_pyperformance.svg
   :alt: time ratios on the official pyperformance pickle workloads
   :width: 100%


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

**Encryption with a password**

``encryption_key`` encrypts in the `age <https://age-encryption.org>`_ v1
format (scrypt + ChaCha20-Poly1305), checked against age's official test
vectors: the file opens with ``age --decrypt`` as well. No extra package:
libsodium is linked into the C extension, the same on every platform.

.. code-block:: python

    serializejson.dump(state, "state.json", encryption_key="secret")
    state = serializejson.load("state.json", encryption_key="secret")

``encryption_in_base64`` chooses between the binary form and the ASCII armor
(base64 between ``-----BEGIN AGE ENCRYPTED FILE-----`` lines). By default
(``None``) ``dumps`` returns the armor, since its result is text, and files and
bytes stay binary, a third shorter; ``True`` forces the armor everywhere,
``False`` the binary form. Loading recognizes both forms by itself.

**In the browser (Pyodide)**

A WebAssembly wheel (``scripts/construit_wasm.sh``) is loaded by
``pyodide.loadPackage``. Encryption works there too, through the same
libsodium linked into the extension.

More examples and complete documentation `here <https://smartaudiotools.github.io/serializejson/>`_

License
=======

Copyright 2020 Baptiste de La Gorce

For noncommercial use or thirty-day limited free-trial period commercial use, this project is licensed under the `Prosperity Public License 3.0.0 <https://github.com/SmartAudioTools/serializejson/blob/master/LICENSE-PROSPERITY.rst>`_.

For non limited commercial use, this project is licensed under the `Patron License 1.0.0 <https://github.com/SmartAudioTools/serializejson/blob/master/LICENSE-PATRON.rst>`_.
To acquire a license please `contact me <mailto:contact@smartaudiotools.com>`_, or just `sponsor me on GitHub <https://github.com/sponsors/SmartAudioTools>`_ under the appropriate tier ! This funding model helps me making my work sustainable and compensates me for the work it took to write this crate!

Third-party contributions are licensed under `Apache License, Version 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_ and belong to their respective authors.