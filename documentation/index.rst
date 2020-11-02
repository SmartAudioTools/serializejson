.. toctree::
   :maxdepth: 3
   :caption: Contents:
   
.. include:: ../README.rst


Classes API 
===========

    Classes API is the prefered API if you have to encode or decode several 
    objects. 
    
    This API allow to get all encoded classes with Encoder.get_dumped_classes() 
    in order to pass them later to Decoder(autorized_classes = ... )
    
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
    Functions API are juste convenient way to create Encoder or Decoder and call methods in one instruction. 
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




Methode 1 : Add methods to object for custom serialization
----------------------------------------------------------

    Add methods to object if you can, it is the prefered methode. 
    serializejson use the same methods than pickle and as exactly the same behavior 
    as pickle if Encoder(attributs_filter = None) and Decoder(set_attributs = False).
    If you chose to comeback to pickle, your coded methods will still be useful.
    
    Depending of your strategie for the recreation and updating of an object you will implement 
    differents methods :
       
    .. py:function:: object.__reduce__() 
    
        Code __reduce__() methode if you want to recreated your object with __init__().
        You have to return a tuple with : class,init_args_tuple and optionaly state depending 
        how you want to call __init__(). 
        
        .. warning::
            
            Alternatively you can return a tuple with : callable returning instance of the desired class, callable arguments tuple, and optionaly state. 
            **In thise case the callable will be considered as the class by autorized_classes, updatable_classes and set_attributs parameters.**
            Except for "apply" in wich case, the first element of the tuple in second position is considered as the class. 
            **Never put "apply" in autorized_classes, it allow untrusted json to execute arbitrary code.**  

            
        **Just call __init__() with positionals arguments, without state restore.**
        
        .. code-block:: python
        
            def __reduce__(self):
                    init_args_tuple = (1,) # tuple with 1 element need comma
                    return self.__class__,init_args_tuple,None 
        
        **Just call __init__() with named arguments, without state restore.** 
        naming argument allow you to skeep first arguments if they have default
        values and is robust if you change later the init args order, but you 
        have to pip install apply
        
        .. code-block:: python
        
            def __reduce__(self):
                    init_kwargs_dictionnary = {"arg3":3}
                    return apply,(self.__class__,None,init_kwargs_dictionnary) 
                    
        **Just call __init__() with positionals arguments and named arguments, without state restore.** 
     
        
        **Call __init__() with positionals arguments and restore state from filtered attributs**
        
        .. code-block:: python
        
            def __reduce__(self):
                    init_args_tuple = (1,) # tuple with 1 element need comma
                    return self.__class__, init_args_tuple, serializejson.filtered(self.__dict__)
        
        **Call __init__() with named arguments and restore state from filtered attributs** 
        more robust if you change later the init args order, but you have to pip install apply
        
        .. code-block:: python
        
            def __reduce__(self):
                    init_kwargs_dictionnary = {"arg3":3}
                    return  apply,
                            (self.__class__,None,init_kwargs_dictionnary),
                            serializejson.filtered(self.__dict__)
    
    .. py:function:: object.__getstate__() 
    
    
        Code __getstate__() methode **without __reduce__()**
        if you doesn't want to call __init__() but only __new__() and you  want to have 
        a different behavior than serialize self.__dict__ and self.__slots__.
        __getstate__() must return the state of the class as an object that will itself be serialized.
        If __setstate__() is not available, the returned object must be a dictionary 
        (elements will be restored as attributes), otherwise the object can be any serializable object

        
        .. warning::
        
            if __reduce __ () is implemented, __getstate __ () will not be called
        
                
        .. code-block:: python
        
            def __getstate__(self):
                state = serializejson.filtered(self.__dict__)
        

    
    .. py:function:: object.__setstate__(state)
    
        Code __setstate__() if you want to have other behavior than the default which 
        consists juste restoring attributs from state.
        takes as parameter the object describing the state of the class and 
        puts the instance back in the state it was in before serialization.
        can possibly execute initialization code.
        
        .. note::
        
            If __setstate __() is not available, all elements of self.__dict__, self.__slots__ or returned by __getstate__ () (which in this case will have to return a dict) will be restored as attributes. 
            
            * Passively if set_attribut = False (like pickle) 
            * actively with call of setters if set_attribut = True or set_attribut =  [..,your_object]. In alphabetic order if sort_keys=True or in random order if sort_keys=False.    

            You should better add the __setate__() methode to your oject : 
            
            * If you want to call setter in a different order than alphabetic order.
            * If you want to be robust to a attribut name change.
            * If you want to be robust to this set_attribut parameter change. 
            * If you want to avoid transitional states during setting of attribut one by one.
            * If you want the same bahavior than pickle, for being able to comme back to pickle.
           
            
        * If there is restoring code depending of several elements of state, you should code __setstate__() to avoid  transitional states during the restoration of attributs one by one.        
        * If there is restoring code and you want a 100 % compatibilité with pickle,  you should put this code in __setstate__() for not depending of set_attributs = True.
           
    
        .. code-block:: python
        
            def __setstate__(self, state):
                self.set_x(state["x"])
                self.set_y(state["y"])
                # other initialization code 
                ....
                ....

     
    .. _updatable-note-label:
           
    .. note::
         
       
        **If you want to make the object updatable:**
        
        **Save all needed informations outside of __init__ args when dumping:**
        
        * put all needed informations for an update in state (returned by __getstate__() or in third position by __reduce__()), because __init__() will not be called when updating, and all init args will be discard. 
        * minimize informations redundancy for __init__() that is already in state  (returned in second position by __reduce__()       
        * you can remove call to __init__() using __getsate__() instead of __reduce__(), if you don't need  to execute code in __init__() anymore when object creation, because all needed intialisation code is already in __setstate__() or setters.

               
        **Allow restauration of this informations:**
       
        *  In  __setstate__()  methode called with the state.
        
            - If you want to call setter in a different order than alphabetic order.
            - If you want to be robust to a attribut name change or set_attribut parameter change. 
            - If you want to avoid transitional states during setting of attribut one by one.
               
        * Othewise the all elements of the state dictionary will be restored as attributes. 
        
            - Passively if set_attribut = False (like pickle). 
            - Actively with call of setters, if set_attribut=True or set_attribut=[your_object] (in alphabetic order if sort_keys=True or in random order if sort_keys=False).    
              ⚠ You must be sure to ever call load with set_attributs = True (or [...,object]) or add a plugin for thise object withs set_attribus = [object]






            
Methode 2 : Add plugins to serializejson
----------------------------------------
    
    Add plugins to serializejson, if you don't want or can't add methodes to 
    the object you want to serialize. 
    
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

    **5. Automaticaly add parameters to Encoder, dump and dumps for control your plugins options**
       
           .. code-block:: python
           
                from serializejson import serializeParameters
                def tuple_from_XXX(obj):
                    if serializeParameters.module_name_option_name : 
                        init_args = ...
                        state  = ...
                    else : 
                        init_args = ...
                        state  = ...
                    return (obj.__class__,init_args,state)
                encoder_plugins_parameters_default_values = {"module_name_option_name" : False}
            
        
        You can now use thise option for Encoding : 
        
            .. code-block:: python
    
                import serializejson
                import module_name 
                obj = module_name.XXX()
                encoder = Encoder(module_name_option_name = True)
                dumped = encoder.dumps(obj)
                print(dumped)
        
    **5. Add "tuple_from_module_class_str" dictionnary in your module_name.py** 
        if somme of your classes are in submodules. 
        Otherwise this dictionnary will be automaticaly constructed by serializejson 
        when loading plugins, considering that all object are in the root module. 
    
        .. code-block:: python
        
            tuple_from_module_class_str = {
                "module_name.submodule.XXX" :  tuple_from_XXX,
                "module_name.submodule.YYY" :  tuple_from_YYY,
            }    
        
    **6. Add a "set_attributs" list if you want to call objects attributs setters**
        like set_attribut1,setAttribut1 or attribut1 propertie setter, when loading json add a  with qualified names of concerned objects. 
        
        .. code-block:: python

            set_attributs = ["module_name.XXX","module_name.YYY"]

        
    **7. Share your plugin with serializejson developper**
    
        if your plugin is for a wild user library, for include in serializejson next release.



Versions
========
.. include:: ../CHANGELOG.rst
