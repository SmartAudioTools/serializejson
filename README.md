# serializejson

**serializejson** is a python library for serialization (and deserialization) of complex Python objects in [JSON](http://json.org/) build upon [python-rapidjson](https://github.com/python-rapidjson/python-rapidjson) and [pybase64](https://github.com/mayeut/pybase64)
	
>**WARNING**:
serializejson can execute arbitrary Python code if the load parameter autorized_classes is "all" when loading json. 
Do not load serializejsons from untrusted / unauthenticated sources without carfuly set the autorized_classes parameter. 

- supports Python 3.7 (maybe lower) or greater.
- serialize arbitrary python objects (bytes and bytearray are very quikly serialized and deserializaed in base64).
- call the sames objects methodes than pickle. Therefore allmost all pickable objects are serializable with serializejson without any modification.
- serialized objects are human-readable. (Your datas will never be unreadable if your code evolved, you will allway be able to modify your datas with a text editor, unlike with pickle)
- serialized objects take generaly less space than with pickle and juste a little 30% more if big binaries data (numpy array, bytes, bytearray)
- only two time slower than pickle and much more faster than jsonpickle.
- can safely load untrusted / unauthenticated sources if autorized_classes list parameter is set carfuly with stricly necessary objects (unlike pickle). 
- can update an existings objects instead of overide thems (serializejson can be used to save and restore in place a complet application state).
- filter attribut starting with "_" by default (unlike pickle).
- numpy arrays can be serialized in list with automatique conversion in both way or in a conservative way. 
- support circular references and serialize only once duplicated object (WARNING :not yet if the object is a list or dictionnary).
- try to call attributs setters and propreties setters when loading if set_attributs  = True.
- accept json with comment (// and /* */).
- can automaticly recognize objects in json and recreate them, without the need of "`__class__`" key, if passeds in recognized_classes.
- dump and load support string path. 
- can iterativly encode (with append) and decode (with iterator) a list in json, saving memmory space during the process of serialization et deserialization.
- WARNING : tuple, time.struct_time, collections.Counter, collections.OrderedDict, collections.defaultdict, namedtuples and dataclass are not yet correctly serialized 



# Install
pip install git+https://github.com/SmartAudioTools/serializejson.git
	
# License
See serializejson/LICENSE for details about the serializejson license.

