serializejson
=============

    **serializejson** is a python library for serialization and deserialization of complex Python objects in 
    `JSON <http://json.org>`_ build upon `python-rapidjson <https://github.com/python-rapidjson/python-rapidjson>`_ and `pybase64 <https://github.com/mayeut/pybase64>`_
    
    .. warning::
    	⚠ serializejson can execute arbitrary Python code if the load parameter autorized_classes is "all" when loading json. 
    	Do not load serializejsons from untrusted / unauthenticated sources without carfuly set the autorized_classes parameter.**
    
    - supports Python 3.7 (maybe lower) or greater.
    - serializes arbitrary python objects into a dictionary by adding "__class__" ,and eventually "__init__" and "__state__" keys. 
    - serializes and deserializes bytes and bytearray very quickly in base64 tanks to `pybase64 <https://github.com/mayeut/pybase64>`_.
    - calls the same objects methods as pickle. Therefore almost all pickable objects are serializable with serializejson without any modification.
    - serialized objects are human-readable. Your datas will never be unreadable if your code evolved, you will always be able to modify your datas with a text editor, unlike with pickle.
    - serialized objects take generally less space than with pickle and just a little 30% more if big binaries data (numpy array, bytes, bytearray)
    - only two times slower than pickle and much faster than jsonpickle.
    - can safely load untrusted / unauthenticated sources if autorized_classes list parameter is set carefully with strictly necessary objects (unlike pickle).
    - can update existing objects recursively instead of override them (serializejson can be used to save and restore in place a complete application state).
    - filters attribute starting with "_" by default (unlike pickle).
    - numpy arrays can be serialized in list with automatique conversion in both ways or in a conservative way. 
    - supports circular references and serialize only once duplicated objects (WARNING :not yet if the object is a list or dictionary).
    - try to call attribute setters and properties setters when loading if set_attributs  = True.
    - accepts json with comment (// and /* */).
    - can automatically recognize objects in json from keys names and recreate them, without the need of "__class__" key, if passed in recognized_classes. It allows loading foreign json serialized with others libraries who only save objects attributes. 
    - dumps and loads support string path. 
    - can iteratively encode (with append) and decode (with iterator) a list in json, saving memory space during the process of serialization et deserialization.
    - WARNING : tuple, time.struct_time, collections.Counter, collections.OrderedDict, collections.defaultdict, namedtuples and dataclass are not yet correctly serialized 
    

Install
=======
    .. code-block::
    
    	pip install git+https://github.com/SmartAudioTools/serializejson.git

License
=======
    serializejson is licensed under the MIT license.
    
    The MIT License (MIT)
    
    Copyright (c) 2020 Baptiste de La Gorce
    
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
    
Examples
================

serialization with fonctions API 
--------------------------------
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

serialization with classes based API. 
-------------------------------------
    (quicker than fonctions API if reuse of Encoder/Decoder for serveral objects).
    
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

update existing object 
----------------------
    .. code-block:: python
    
    	import serializejson 
    	object1 = set([1,2])
    	object2 = set([3,4])
    	dumped1 = serializejson.dumps(object1)
    	print(f"id {id(object2)} :  {object2}")
    	serializejson.loads(dumped1,obj = object2, updatables_classes = [set])
    	print(f"id {id(object2)} :  {object2}")

iterative serialization and deserialization
-------------------------------------------
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
    	


