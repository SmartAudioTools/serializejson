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
