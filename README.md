#serializejson

serializejson is a library for the two-way conversion of complex Python objects and [JSON](http://json.org/) build upon [python-rapidjson](https://github.com/python-rapidjson/python-rapidjson)
	
**WARNING**:
serializejson can execute arbitrary Python code if the load parameter autorized_classes is "all" when loading json. 
Do not load serializejsons from untrusted / unauthenticated sources without carfuly set the autorized_classes parameter. 

Install from github for the latest changes:
    pip install git+https://github.com/SmartAudioTools/serializejson.git

- serializejson supports Python 3.4 or greater.
- serializejson can serialize arbitrary python objects (including bytes whick will be serialized in base64) 
- serialisejson call the sames objects methodes than pickle. allmost all pickable objects are serializable with serializejson
- serialized objects are human-readable
- serializejson can safely load untrusted / unauthenticated sources if autorized_classes list parameter is set carfuly with stricly necessary objects. (unlike pickle)
- serializejson can update an existing object instead of overide it (unlike pickle)
- serializejson can be used to save and restore a complet application state. 
- serializejson is only time slower than pickle and much more faster than jsonpickle
- serializejson filter attribut starting with "_" by default (unlik pickle)

# License
See serializejson/LICENSE for details about the serializejson license.

