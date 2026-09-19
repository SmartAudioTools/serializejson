Version 0.4.0
-------------
:Date: 2026-09-19

* optional authenticated encryption: ``encryption_key="password"`` on
  ``dump``/``dumps``/``dumpb``/``load``/``loads``/``Encoder``/``Decoder``
  writes and reads standard `age <https://age-encryption.org>`_ v1 files
  (scrypt passphrase, ChaCha20-Poly1305), decryptable by any age tool; any
  modified byte or wrong password raises ``DecryptionError``; ``dumps``
  returns the ASCII armored form; needs ``pip install serializejson[crypto]``
* position index: ``load(file, path="root['a'][0].b")`` reads one object of a
  json file without parsing the rest, ``serializejson.index()`` indexes a file
  already written and ``serializejson.paths()`` lists what it holds
* ``dump`` to a named file now writes that index by default, zstd compressed
  in a hidden sidecar file of the same name preceded by a dot, which leaves
  the json itself standard (``index="comment"`` appends it to the json as a
  comment line instead — one single file to move, but no other parser reads it
  any more; ``index=None`` writes none); files whose containers all stay under
  ``index_threshold`` keep no index at all
* Python 3.11 to 3.14 support (default ``object.__getstate__`` handled), numpy 2 support
* circular references and duplicates now handled for lists and dicts too (``$ref``),
  including physically shared ``__dict__`` (restored at load, beyond pickle)
* big speedups: per-class fast paths fully in C++ (encode and decode),
  SIMD parser, base64 written/read without intermediate strings,
  readable numpy arrays written straight from their buffer (``ArrayRows``)
* blosc2 compression in C without Python round trip; DETERMINISTIC internal
  multithreading via the bundled patched libblosc2 (same bytes whatever the
  thread count); parallel base64; chunked parallel fallback (``b64_blosc2p``)
* default compression switched to ``blosc2_zstd`` (old ``b64_blosc`` files
  still readable; new files need a blosc2-capable serializejson)
* homogeneous number lists written on a single line everywhere (dict values,
  nested lists), decided in C++
* fixes: segfault on 3.12/3.13 with deep/cyclic data, ``append()`` of objects,
  float subclasses written via ``repr()`` (numpy 2), docstring SyntaxWarnings

Version 0.3.4
-------------
:Date: 2023-06-11

* Restore ducumentation


Version 0.3.3
-------------
:Date: 2022-10-18

* Big speed improvement for bytes and numpy array serialization

Version 0.3.2
-------------
:Date: 2022-10-01

* API changed
* add better support for cicular reférences and duplicates with {"$ref": ...}

Version 0.2.0
-------------
:Date: 2021-02-18

* API changed
* can serialize dict with no-string keys
* add support for cicular reférences and duplicates with {"$ref": ...}


Version 0.1.0
-------------
:Date: 2020-11-28

* change description for pipy
* add license for pipy
* enable load of tuple, time.struct_time, Counter, OrderedDict and defaultdict

Version 0.0.4
-------------
:Date: 2020-11-24
	
* API changed
* add plugins support
* add bytes, bytearray and numpy.array compression with blosc zstd
* fix itertive append and decode (not fully tested).
* fix dump of numpy types without conversion to python types(not yet numpy.float64)
