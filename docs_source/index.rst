.. toctree::
   :maxdepth: 3
   :caption: Contents:
   
.. include:: ../README.rst


Classes API 
===========

    Classes API is the preferred API if you have to encode or decode several 
    objects, allowing you to reuse the same Encoder and Decoder classes instancies for this
    objects. Function API internaly create Encoder or Decoder instances at each call. 
    It's non-negligeable cost if lot of smal objects are serialized one by one.  
        
    
    Moreover this API allow to get all encoded classes with Encoder.get_dumped_classes() 
    in order to pass them later to Decoder(authorized_classes = ... )
    
Encoder
-------
.. autoclass:: serializejson.Encoder
   :members:
   :member-order: bysource

Decoder
-------
.. autoclass:: serializejson.Decoder
   :members:
   :member-order: bysource

Functions API
=============
    Functions API are just convenient way to create Encoder or Decoder and call methods in a single instruction. 
    If you have to encode or decode several objects reuse instances of Encoder and Decoder instead of functions to avoid creation of Encoder or Decoder at each function call.
    The functions arguments are the same as for Encoder and Decoder constructor. See documentation of Encoder and Decoder for more precisions.

Encode
-------
    .. autofunction:: serializejson.dump
    .. autofunction:: serializejson.dumps
    .. autofunction:: serializejson.append

Decode
-------
    .. autofunction:: serializejson.load
    .. autofunction:: serializejson.loads




Custom object serialization
===========================


.. _Method-1-label:

Method 1: Adding pickle methods to object for custom serialization
------------------------------------------------------------------

    If you can add the required methods directly to you classes code, this is the recommended method.
    If you finally chose to use pickle instead of serializejson, your implemented methods will still be useful.
    serializejson uses the same methods as pickle and has exactly the same behavior 
    as pickle if you use Encoder(strict_pickle = True) and Decoder(strict_pickle = True).
    
    Depending of strategy you choose for recreating or updating an object, you will need to implement 
    different methods:
       
    .. py:function:: object.__reduce__()  
    
        Code the `__reduce__()` method if you want to recreate your objects with `__init__()`.
        (or object.__reduce_ex__ if __reduce_ex__ as already be reimplemented in a base class, to overwrite it, python trying to call __reduce_ex__ first)
        You have to return a tuple with: class, init_args_tuple and optionally state.
        If state is a dictionary and `sort_keys=False`, elements will be restored in same order than given by __reduce__()
        given you the possibility to fine tuning the order elements are restored . 
        For predictable behavior, be careful to always sort state as you want, manually 
        or in alphabetic order with serializejson.sorted_filtered_attributs(self)
        If your object contains __slots__ and not __setstate__, 
        state myst be a tuple (__dict__to_restore,__slots__dict_to_restore) for being able to 
        seriazlie and deserialize your object with pickle.
        The convenient function serializejson.sorted_filtered_attributs(self), filter, sorte and split __slot__ and __dict__ if needed for you . 
        
        
        .. warning::
            
            Alternatively you can return a tuple with a callable returning instance of the desired class, a callable arguments tuple, and optionally a state. 
            **In this case the callable will be considered as the class by authorized_classes, updatable_classes and set_attributes parameters.**
            Except for "apply", in which case the first element of the tuple in second position is considered as the class. 
            
            **Never put "apply" in authorized_classes, it would allow untrusted json to execute arbitrary code.**

            
        * Call `__init__()` with positional arguments, without state restore.
            
            .. code-block:: python
            
                def __reduce__(self):
                        init_args_tuple = (1,) # tuple with 1 element need comma
                        return self.__class__,init_args_tuple 
        
        * Call `__init__()` with named arguments, without state restore.
        
            naming argument allows you to skip the first arguments if they have default
            values and is robust if you change later the init arguments order, but you will
            have to install the python module `apply <https://pypi.org/project/apply>`_
            
            .. code-block:: python
            
                def __reduce__(self):
                    init_kwargs_dictionary = {"arg3":3}
                    return apply,(self.__class__,None,init_kwargs_dictionary)
                         
        
        * Call `__init__()` with positional arguments and restore state from attributes filtered and sorted alphabetically.
        
        
            .. code-block:: python
            
            
                def __reduce__(self):
                    init_args_tuple = (1,) # tuple with 1 element need comma
                    state = serializejson.getstate(self)
                    return self.__class__, init_args_tuple, state
        
        * Call `__init__()` with named arguments and restore state from attributes filtered and sorted alphabetically.
        
            more robust if you change later the init args order, but you have to pip install apply
            
            .. code-block:: python
            
                def __reduce__(self):
                    init_kwargs_dictionary = {"arg3":3}
                    state = serializejson.getstate(self)
                    return  apply,
                            (self.__class__,None,init_kwargs_dictionary),
                            state
    
    .. py:function:: object.__getstate__() 
    
        Code the `__getstate__()` method **without** `__reduce__()`
        if you do not want to call `__init__()` but only `__new__()` and you want to have 
        a different behavior than serialize `self.__dict__` and `self.__slots__`  filtered (if `attributes_filter` is left at its default value \"_\") and sorted alphabetically .
        The `__getstate__()` method must return the state of the class as an object that will itself be serialized.
        If `__setstate__()` is not available, the returned object must be `None` or a dictionary.
        Otherwise the object can be any serializable object.
        If state is a dictionary and `sort_keys=False` (by default), elements will be restored in same order than given by __getstate__()
        given you the possibility to fine tuning the order elements are restored . 
        For predictable behavior, be careful to always sort state as you want, manually 
        or in alphabetic order.
        
        .. code-block:: python
        
            def __getstate__(self):
                return {"attribut_1" : "value_1","attribut_2" : "value_2",....}

                  
        You can use the helping function `serializejson.getstate(self)` in your `__getstate__` methode in order to select attribut to keep, add or remove, automaticaly sort_keys, filter attribut with "_", retrieve slots, properties, getters , and remove attribut with same value as default value. 
       
        .. code-block:: python
        
            def __getstate__(self):
                return serializejson.getstate(self)
        
        
        .. autofunction:: serializejson.getstate
        
        .. warning::   
     
            if `__reduce __ ()` is implemented and don't call `__getstate __()` himself, `__getstate __()` will not be called
        
    
    .. py:function:: object.__setstate__(state)
    
        Code `__setstate__()` if you want to have other behavior than the default which 
        consists in just restoring attributes from state.
        Takes as parameter the object describing the state of the class and 
        puts the instance back in the state it was in before serialization.
        Can possibly execute initialization code.
        
        .. code-block:: python
        
            def __setstate__(self, state):
                self.set_x(state["x"])
                self.set_y(state["y"])
                # other initialization code 
                ....
                ....
         
        You can use the helping function serializejson.setstate(self) in order to automaticaly call propertie's setters and setters.
            
        .. code-block:: python
        
            def __setstate__(self, state):
                serializejson.setstate(self,state,properties = True, setters = True)
                
        .. autofunction:: serializejson.setstate
        
        .. note::
        
            If `__setstate __()` is not available, all elements of `self.__dict__`, `self.__slots__` 
            or returned by `__getstate__()` or `__reduce__()` (which in this case must return a dict) will be restored as attributes. 
            
            * Passively if Encoder or load have parameters `setters = False` and `properties = False` or `strict_pickle = True`  (like pickle) 
            * actively with call of properties setters  if `properties = True` or `properties = [..,your_object]`. 
            * actively with call of setters if `setters = True` or `setters = [..,your_object]`. 
            * In order given by __gestate__() or __reduce__() (if `sort_keys=False`),
            * Otherwise in alphabetic order (event if `sort_keys=False`).    

            We recommend to add the `__setstate__()` method to your object: 
            
            * If you want to call setter in a different order than alphabetic order and you don't want to code __state__() or _reduce__() for that purpose.
            * If you want to be robust to a attribute name change.
            * If you want to be robust to the dump's set_attribute parameter change. 
            * If you want to avoid transitional states during setting of attribute one by one.
            * If you want the same behavior than pickle, for being able to comme back to pickle.
            * If there is restoring code depending of several elements of state, you should code `__setstate__()` to avoid transitional states during the restoration of attributes one by one.        
            * If there is restoring code and you want a 100 % compatibility with pickle, you should put this code in `__setstate__()` for not depending of `setters = True` and `properties = True`.
               
        
Method 2: Adding plugin to pickle for custom serialization
-----------------------------------------------------------
    If you can't or won't add __reduce__, __gestate__ or __setstate__ methodes directly into your object code,
    you have to write a module that you will import after serializejson (or pickle if you want to use pickle), 
    named for exemple "pickle_Module.py" if you want to patch obects of "Module".  
    
    In this module, you can either : 
    
    * add dynamicaly __reduce__, __gestate__ or __setstate__ methodes to your objet by monkey patching :
    
        See ref:`"Method 1"<Method-1-label>` for methods details. This will allow all inheriting object to benefit of this methods and to be directly serializable
    
        .. code-block:: python
        
            import MyModule
            def MyObject__reduce__(self):
                return self.__class__,("init_arg1","init_arg1"),None
            # Method dynamicaly added to your objet by monkey patching 
            MyModule.MyObject.__reduce__  = MyObject__reduce__ 
    
    * add `__reduce__` to the `copyreg.dispatch_table` dictionnary :
    
        This function will be called by pickle or serializejson to serialialize this specific class type, all inheriting classes **will not** benefit of this plugin. If you want to use it for inheriting classes, you have to add this `__reduce__` fonction for each of your inheriting classes in `dispatch_table`.
         
        .. code-block:: python
        
            from copyreg import dispatch_table
            import MyModule
            def MyObject__reduce__(self):
                return self.__class__,("init_arg1","init_arg1"),None
            dispatch_table[MyModule.MyObject] = MyObject__reduce__
            

Method 3: Adding plugins to serializejson for custom serialization
------------------------------------------------------------------
    .. _add-plugins-label:

    If you don't care about making your object pickable or if your object is already pickable
    but want a different behavior than pickle for serializejson (because serialization in json is to verbose or not easly readable)
    you have the possibility to add plugins specifialy for serializejson's serialization.
    
    **1. Create a plugin module `serializejson_module_name.py`** 
         with module_name the name of of the module containing your object. 
         and import it after serializejson in your code. 
        
        .. code-block:: python
         
            import serializejson
            import serializejson_module_name 

            
    **3. make imports in in your `serializejson_module_name.py`** 
    
       .. code-block:: python
       
            try: 
                import module_name
            except ModuleNotFoundError: 
                pass 
            else : 
                from serializejson import (
                        # encoding -------------
                        dispatch_table,      # pickle plugins 
                                             # (used if not serializejson plugin or methode)
                        serializejson_,      # serializejson plugins  
                        encoder_parameters,  # encoder extra parameters for plugins, 
                                             # with their default value
                        getters = {}         # getters for dumped classes.  
                                             # keys are classe.
                                             # values are True (for automatic getters detection) 
                                             # or dictionnary of {"attribut" : "getAttribut" }
                        # encoding and decoding -------
                        properties = {}      # properties for dumped and loaded classes. 
                                             # keys are classes
                                             # values are True (for automatic properties detection) 
                                             # or list of ["attribut1","attribut2",..]}
                        # decoding ---------------------
                        authorized_classes,  # qualified names of classes autorized to be loaded  
                        setters,             # setters for loaded classes. 
                                             # keys are classes.
                                             # values are True (for automatic setters detection) 
                                             # or dictionnary of {"attribut" : "setAttribut" }
                        constructors,        # custom construtors for loaded classes. 
                                             # keys are string corresponding to the class qualified name,
                                             # value is the constructor 
                        decoder_parameters,  # decoder extra parameters for plugins 
                                             # with their default value
                        )  
                        
                        
    **5. Authorize automaticaly classes to be loaded without having to precise it in the Decoder's or load's `authorized_classes` parameter.** 
        
        .. warning::
        
            be very carreful to automaticaly authorize only inoffensive object that can't be used alone or in combinaison of other authorized objects for malicious code! 
      

        .. code-block:: python
        
            authorized_classes.update({
                    "MyModule.XXX",
                    "MyModule.YYY",
                    "MyModule.ZZZ",
                    })
        
        
    **4. Create functions named `XXX_serializejson`**
        in serializejson_module_name.py for each objects of your module, with XXX the name of the class. 
        This functions must return all needed info for your object's serialization in a tuple. 
    
        .. autofunction:: serializejson.plugins.module_name.XXX_serializejson


       **. add dynamicaly this function as `__serializejson__` method to your class by monkey patching.** This will allow all inheriting object to benefit of this methods and to be directly serializable
        
            .. code-block:: python
            
                import MyModule
                def XXX_serializejson(self):
                    return self.__class__,{"init_arg1" : 1,"init_arg1" : 2},None
                MyModule.XXX.__serializejson__  = XXX_serializejson # Method dynamicaly added to your objet by monkey patching 
        
            .. note:: 
            
                You can add this methode directly in your object's code , but 
                it will make your object's code depending of serializejson if you use serializejson's functions like `serializejson.__gestate__`.                 
                
                
        **. or add `XXX_serializejson` to the `serializejson_` dictionnary.** This function will be called by pickle or serializejson to serialialize this specific class type, all inheriting classes **will not** benefit of this plugin. If you want to use it for inheriting classes, you have to add this `XXX_serializejson` fonction for each of your inheriting classes in `serializejson_` dictionnary.
    
            
            .. code-block:: python
            
                import MyModule
                def XXX_serializejson(self):
                    return self.__class__,{"init_arg1" : 1,"init_arg1" : 2},None
                serializejson_[MyModule.XXX] = XXX_serializejson
                
    **5. Define class  properties and attributs getters and setters**

        .. code-block:: python
        
        
            properties[MyClass] = True # for automatic detection 
            # or 
            properties[MyClass] = {'property1','property2',...}
        
        
            getters[MyClass] = True # for automatic detection 
            # or 
            setters[MyClass] = {'attribut_name':'getter_name',...}
            
            
            setters[MyClass] = True # for automatic detection 
            # or 
            setters[MyClass] = {'attribut_name':'setter_name',...}
        
    **5. Automatically add new parameters to Encoder/dump/dumps or Decoder/load/loads for control your plugins options if needed**
       
           
           .. code-block:: python
           
                from serializejson import serialize_parameters, encoder_parameters,
                
                def XXX_serializejson(self):
                    if serialize_parameters.module_name_encoder_option_name: 
                        init_args = ...
                        state = ...
                    else: 
                        init_args = ...
                        state = ...
                    return (self.__class__,init_args,state)
                MyModule.XXX.__serializejson__  = XXX_serializejson
                encoder_parameters["module_name_encoder_option_name"] = False # record parameter and set default value 
                
                
                def XXX_setstate(self,state)
                    if serialize_parameters.module_name_decoder_option_name: 
                        init_args = ...
                        state = ...
                    else: 
                        init_args = ...
                        state = ...
                    return (self.__class__,init_args,state)    
                MyModule.XXX.__setstate__  = XXX_setstate
                encoder_parameters["module_name_decoder_option_name"] = False # record parameter and set default value 
        
        You can now use thesse optionss for encoding en decoding: 
        
            .. code-block:: python
    
                import serializejson
                import module_name 
                obj = module_name.XXX()
                # Function API 
                dumped = serializejson.dumps(obj,module_name_encoder_option_name = True)
                print(dumped)
                
                # Class API
                encoder = serializejson.Encoder(module_name_encoder_option_name = True)
                print(encoder.dumps(obj))
                
                # Function API 
                print(serializejson.loads(dumped,module_name_decoder_option_name = True))
                # Class API
                decoder = serializejson.Decoder(module_name_decoder_option_name = True)
                print(encoder.loads(dumped))
            
    **5. Customise the constructor, if needed** 
  
          By default the json "__class__" field correspond to the class .
          but sometimes you want to use a different constructor without changing the json "__class__" field 

            .. code-block:: python
    
              
                constructors['my_module.XXX'] = constuctor # class or function called for object creation you should use `self.__class__` or string `"module.submodule.name"`

            
          Or sometimes want to customize both serialized __class__ name and constructor : 
            
            .. code-block:: python
            
                import MyModule
                def XXX_serializejson(self):
                    return "custom_name",{"init_arg1" : 1,"init_arg1" : 2},None
                MyModule.XXX.__serializejson__  = XXX_serializejson 
                constructors['custom_name'] = constuctor # class or function called for object creation you should use `self.__class__` or string `"module.submodule.name"`

                    
    **7. Share your plugin with serializejson developer**
    
        if your plugin is for a wild user library, for include in serializejson next release.
        Avoiding you to manualy import it after `import serializejson` each time you want to use it. 



Object Update
=============



    **Updating an object** consists in restoring its state recursively.

    * Neither `__new__()` or  `__init__()` will be called.
    * All childrens of `updatables_classes` will be updated, otherwise will be recreated.
    * If the object has a `__setstate__()` method, this method will be called with the state.
    * Otherwise all the elements of the state dictionary will be restored as attributes. Passively if `set_attribute = False` (like pickle). Actively if `set_attribute=True` or `set_attribute=[your object's class]`, with call of setters (in alphabetic order if `sort_keys=True` or in random order if `sort_keys=False`).

    .. warning::

        You must make sure to have all the needed information in the state and not in the `__init__` args that will be discarded when updating.
        See documentation section: ref:`"If you want to make the object updatable"<updatable-note-label>`.



    .. _updatable-note-label:
    .. _example:
           

       
    **If you want to make the object updatable:**
    
    * Save all needed information outside of `__init__` args when dumping:
        
        * put all needed information for an update in state (returned by `__getstate__()` or in third position by `__reduce__()`), because `__init__()` will not be called when updating, and all init arguments will be discarded. 
        * minimize information redundancy for `__init__()` that is already in state (returned in second position by `__reduce__()`
        * you can remove calls to `__init__()` using `__getsate__()` instead of `__reduce__()`, if you don't need to execute code in `__init__()` anymore when creating objects, because all the required initialization code is already in `__setstate__()` or setters.

           
    * Allow restoration of this information:
    
        * In `__setstate__()` method called with the state.
        
            - If you want to call setter in a different order than alphabetic order or the order given by __reduce__() or __getstate__()
            - If you want to be robust to a attribute name change or set_attribute parameter change. 
            - If you want to avoid transitional states during setting of attribute one by one.

        * Otherwise all the elements of the state dictionary will be restored as attributes. 
        
            - Passively if `set_attribute = False` (like pickle). 
            - Actively with call of setters, if set_attribute=True or `set_attribute=[your_object]` (in alphabetic order or in the order given by __reduce__() or __getstate__()). ⚠ You must be sure to ever call load with `set_attributes = True` (or [...,object]) or add a plugin for these objects with `set_attributes = [object]`



Versions
========
.. include:: ../CHANGELOG.rst


Future Versions (TODO)
======================
    * Add support for:
        - dict with __class__ key (detecte and raise exception or construct speciale object for reconstruction)
        - panda.dataframe
        - singletons (__reduce__ returning a string) 
        - Metaclasses
        
    * Add test for:
        - every Encoder and Decoder parameters combinaisons.
        - object update
        - circular references and duplicates 
        - PySide2 
        
    * Optimization: 
        - bytes: need pybase64.b64encode directly to str and rapidjson.RawJSON improvements
        - numpy array: need pybase64.b64decode directly to bytearray.
        - circular references and duplicates: need rapidjson improvements (Encoder.default call for list an dictionaries)
        - list of numbers: speed up _onlyOneDimNumbers function with Cython ? 
        - json iterator: 
            - speed up _json_object_file_iterator function with Cython ?
            - improve rapidjson for something like raw_decode of the standard json library ? 
    
    * Improvements :
        - replace id check for duplicates by weakd_ref ? because id can be reused 
        - allow alternatives compressors for images ?
        
