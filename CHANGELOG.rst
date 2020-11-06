TODO
----
    * Add support for :
        - Tuple
        - dict with no-string keys
        - time.struct_time
        - collections.Counter
        - collections.OrderedDict
        - collections.defaultdict
        - namedtuples
        - dataclass
        - panda.dataframe
        
    * Add test for :
        - every Encoder and Decoder parameters
        - object update
        - circular referencies and duplicates 
        
    * Optimisation : 
        - bytes : need pybase64.b64encode directly to str and rapidjson.RawJSON improvements
        - numpy array : need pybase64.b64decode direclty to bytearray.
        - circular referencies and duplicates  : need rapidjson improvements (Encoder.default call for list an dictonnaries)
        - list of numbers : speed up _onlyOneDimNumbers fucntion with Cython ? 
        - json iterator : 
            - speed up  _json_object_file_iterator function with Cython ?
            - improve rapidjson for something like raw_decode of the standard json library ? 
        
        
Unreleased
----------
    * API changed
    * add plugins support
    * fix itertive append and decode (not fully tested).
    * fix dump of numpy types without conversion to python types(not yet numpy.float64)

Version 0.0.3
-------------
    :Date: 2020-10-23

Version 0.0.2
-------------
    :Date: 2020-10-22

Version 0.0.1
-------------
    :Date: 2020-10-22
