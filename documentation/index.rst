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




Method 1: Adding methods to object for custom serialization
-----------------------------------------------------------

    If you can add the required methods to you classes, this is the recommended method. 
    serializejson uses the same methods as pickle and has exactly the same behavior 
    as pickle if you use Encoder(attributes_filter = None) and Decoder(set_attributes = False).
    If you finally chose to use pickle instead of serializejson, your implemented methods will still be useful.
    
    Depending of strategy you choose for recreating or updating an object, you will need to implement 
    different methods:
       
    .. py:function:: object.__reduce__() 
    
        Code the `__reduce__()` method if you want to recreate your objects with `__init__()`.
        You have to return a tuple with: class, init_args_tuple and optionally state depending 
        on how you want to call `__init__()`. 
        
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
                         
        
        * Call `__init__()` with positional arguments and restore state from filtered attributes
        
            .. code-block:: python
            
                def __reduce__(self):
                        init_args_tuple = (1,) # tuple with 1 element need comma
                        return self.__class__, init_args_tuple, serializejson.filtered(self.__dict__)
        
        * Call `__init__()` with named arguments and restore state from filtered attributes 
        
            more robust if you change later the init args order, but you have to pip install apply
            
            .. code-block:: python
            
                def __reduce__(self):
                        init_kwargs_dictionary = {"arg3":3}
                        return  apply,
                                (self.__class__,None,init_kwargs_dictionary),
                                serializejson.filtered(self.__dict__)
    
    .. py:function:: object.__getstate__() 
    
    
        Code the `__getstate__()` method **without** `__reduce__()`
        if you do not want to call `__init__()` but only `__new__()` and you want to have 
        a different behavior then serialize `self.__dict__` and `self.__slots__`.
        The `__getstate__()` method must return the state of the class as an object that will itself be serialized.
        If `__setstate__()` is not available, the returned object must be a dictionary 
        (elements will be restored as attributes) or `None`, otherwise the object can be any serializable object

        
        .. warning::
        
            if `__reduce __ ()` is implemented, `__getstate __()` will not be called
        
                
        .. code-block:: python
        
            def __getstate__(self):
                state = serializejson.filtered(self.__dict__)
        

    
    .. py:function:: object.__setstate__(state)
    
        Code `__setstate__()` if you want to have other behavior than the default which 
        consists in just restoring attributes from state.
        takes as parameter the object describing the state of the class and 
        puts the instance back in the state it was in before serialization.
        can possibly execute initialization code.
        
        .. note::
        
            If `__setstate __()` is not available, all elements of `self.__dict__`, `self.__slots__` or returned by `__getstate__()` (which in this case must return a dict) will be restored as attributes. 
            
            * Passively if `set_attribute = False` (like pickle) 
            * actively with call of setters if `set_attribute = True` or `t_attribute = [..,your_object]`. In alphabetic order if `sort_keys=True` or in arbitrary order if `sort_keys=False`.    

            We recommend to add the `__setstate__()` method to your object: 
            
            * If you want to call setter in a different order than alphabetic order.
            * If you want to be robust to a attribute name change.
            * If you want to be robust to this set_attribute parameter change. 
            * If you want to avoid transitional states during setting of attribute one by one.
            * If you want the same behavior than pickle, for being able to comme back to pickle.
           
            
        * If there is restoring code depending of several elements of state, you should code `__setstate__()` to avoid transitional states during the restoration of attributes one by one.        
        * If there is restoring code and you want a 100 % compatibility with pickle, you should put this code in `__setstate__()` for not depending of `set_attributes = True`.
           
    
        .. code-block:: python
        
            def __setstate__(self, state):
                self.set_x(state["x"])
                self.set_y(state["y"])
                # other initialization code 
                ....
                ....

    .. _updatable-note-label:
    .. _example:
           
    .. note::
         
       
        **If you want to make the object updatable:**
        
        * Save all needed information outside of `__init__` args when dumping:
            
            * put all needed information for an update in state (returned by `__getstate__()` or in third position by `__reduce__()`), because `__init__()` will not be called when updating, and all init arguments will be discarded. 
            * minimize information redundancy for `__init__()` that is already in state (returned in second position by `__reduce__()`
            * you can remove calls to `__init__()` using `__getsate__()` instead of `__reduce__()`, if you don't need to execute code in `__init__()` anymore when creating objects, because all the required initialization code is already in `__setstate__()` or setters.

               
        * Allow restoration of this information:
        
            * In `__setstate__()` method called with the state.
            
                - If you want to call setter in a different order than alphabetic order.
                - If you want to be robust to a attribute name change or set_attribute parameter change. 
                - If you want to avoid transitional states during setting of attribute one by one.

            * Otherwise all the elements of the state dictionary will be restored as attributes. 
            
                - Passively if `set_attribute = False` (like pickle). 
                - Actively with call of setters, if set_attribute=True or `set_attribute=[your_object]` (in alphabetic order if `sort_keys=True` or in random order if `sort_keys=False`). ⚠ You must be sure to ever call load with `set_attributes = True` (or [...,object]) or add a plugin for these objects with `set_attributes = [object]`






Method 2: Adding plugins to serializejson
-----------------------------------------
    .. _add-plugins-label:

    You have the possibility to add plugins to the serializejson module if you do not want or cannot add methods to 
    the classes corresponding to the objects you want to serialize. 
    
    **1. Create serializejson/plugins/module_name.py** 
        with the same name as the module containing your object. 
        
    **2. Import this module in serializejson/plugins/__init__.py**
        .. code-block:: python
        
            from . import module_name
            
    **3. make imports in a try in your module_name.py** 
    
       .. code-block:: python
       
            try: 
                import module_name
            except ModuleNotFoundError: 
                pass 
        
    **4. Create functions named "tuple_from_XXX"**
        in module_name.py for each objects of your module, with XXX the name of the class. 
    
        .. autofunction:: serializejson.plugins.module_name.tuple_from_XXX

    **5. Automatically add parameters to Encoder, dump and dumps for control your plugins options**
       
           .. code-block:: python
           
                from serializejson import serialize_parameters
                def tuple_from_XXX(obj):
                    if serialize_parameters.module_name_option_name: 
                        init_args = ...
                        state = ...
                    else: 
                        init_args = ...
                        state = ...
                    return (obj.__class__,init_args,state)
                encoder_plugins_parameters_default_values = {"module_name_option_name": False}
            
        
        You can now use these options for Encoding: 
        
            .. code-block:: python
    
                import serializejson
                import module_name 
                obj = module_name.XXX()
                # Function API 
                print(serializejson.dumps(obj,module_name_option_name = True))
                # Class API
                encoder = serializejson.Encoder(module_name_option_name = True)
                print(encoder.dumps(obj))
                

                
        
    **5. Add "tuple_from_module_class_str" dictionary in your module_name.py** 
        if some of your classes are in submodules. 
        Otherwise this dictionary will be automatically constructed by serializejson 
        when loading plugins, considering that all object are in the root module. 
    
        .. code-block:: python
        
            tuple_from_module_class_str = {
                "module_name.submodule.XXX": tuple_from_XXX,
                "module_name.submodule.YYY": tuple_from_YYY,
            }    
        
    **6. Add a "set_attributes" list if you want to call objects attributes setters**
        like `set_attribute1`, `setattribute1` or `attribute1` property setter, when loading json add a with qualified names of concerned objects. 
        
        .. code-block:: python

            set_attributes = ["module_name.XXX","module_name.YYY"]

        
    **7. Share your plugin with serializejson developer**
    
        if your plugin is for a wild user library, for include in serializejson next release.



Versions
========
.. include:: ../CHANGELOG.rst


Future Versions (TODO)
======================
    * Add support for:
        - Tuple
        - dict with no-string keys
        - time.struct_time
        - collections.Counter
        - collections.OrderedDict
        - collections.defaultdict
        - namedtuples
        - dataclass
        - panda.dataframe
        
    * Add test for:
        - every Encoder and Decoder parameters combinaisons.
        - object update
        - circular references and duplicates
        
    * Optimization: 
        - bytes: need pybase64.b64encode directly to str and rapidjson.RawJSON improvements
        - numpy array: need pybase64.b64decode directly to bytearray.
        - circular references and duplicates: need rapidjson improvements (Encoder.default call for list an dictionaries)
        - list of numbers: speed up _onlyOneDimNumbers function with Cython ? 
        - json iterator: 
            - speed up _json_object_file_iterator function with Cython ?
            - improve rapidjson for something like raw_decode of the standard json library ? 
        