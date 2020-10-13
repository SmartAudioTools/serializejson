# serializejson

serializejson is a python library for serialization (and deserialization) of complex Python objects in [JSON](http://json.org/) build upon [python-rapidjson](https://github.com/python-rapidjson/python-rapidjson)
	
**WARNING**:
serializejson can execute arbitrary Python code if the load parameter autorized_classes is "all" when loading json. 
Do not load serializejsons from untrusted / unauthenticated sources without carfuly set the autorized_classes parameter. 

- supports Python 3.4 or greater.
- serialize arbitrary python objects (bytes and bytearray are serialized in base64).
- call the sames objects methodes than pickle. therefore allmost all pickable objects are serializable with serializejson without any modification.
- serialized objects are human-readable. 
- only time slower than pickle and much more faster than jsonpickle.
- can safely load untrusted / unauthenticated sources if autorized_classes list parameter is set carfuly with stricly necessary objects (unlike pickle). 
- can update an existings objects instead of overide thems (serializejson can be used to save and restore in place a complet application state).
- filter attribut starting with "_" by default (unlike pickle).
- numpy arrays can be serialized in list with automatique conversion in both way or in a conservative way. 
- support circular references and serialize only once time duplicated object (if in a object attribut).
- try to call attributs setters and propreties setters when loading if set_attributs  = True.
- accept json with comment (// and /* */).
- can automaticly reconize objects in json and recreate them, without the need of "__class__" key, if passeds in recognized_classes.
- dump and load support string path. 

# Install
pip install git+https://github.com/SmartAudioTools/serializejson.git
	
# License
See serializejson/LICENSE for details about the serializejson license.

