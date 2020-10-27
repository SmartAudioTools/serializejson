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


Oject's methods to code for serialization
=========================================
    serializejson use the same methods than pickle and as exactly the same behavior 
    as pickle if Encoder(attributs_filter = None) and Decoder(set_attributs = False)
    If you chose to comeback to pickle, your coded methods will still be useful.
    
    Depending of your strategie for the recreation of an object you will implement 
    differents methods. 
    
    .. py:function:: object.__reduce__() 
    
        Code __reduce__() methode if you want to recreated your object with __init__().
        You have to return a tuple with class,init_args_tuple and optionaly state
        
        **Just call __init__ with positionals arguments, without state restore.**
        
        .. code-block:: python
        
            def __reduce__(self):
                    return self.__class__,init_args_tuple,None 
        
        **Just call __init__ with named arguments without state restore.** 
        more robust if you change later the init args order, but you have to pip install apply
        
        .. code-block:: python
        
            def __reduce__(self):
                    return apply,(self.__class__,None,init_kwargs_dictionnary) 
        
        **Call __init__ with positionals arguments and state restore from filtered attributs**
        
        .. code-block:: python
        
            def __reduce__(self):
                    return self.__class__, init_args_tuple, serializejson.filtered(self.__dict__)
        
        **Call __init__ with named arguments and state restore from filtered attributs** 
        more robust if you change later the init args order, but you have to pip install apply
        
        .. code-block:: python
        
            def __reduce__(self):
                    return apply,(self.__class__,None,init_kwargs_dictionnary) , serializejson.filtered(self.__dict__)
    
    
    .. py:function:: object.__getstate__() 
    
    
        Code __getstate__() methode **without __reduce__()**
        if you doesn't want to call __init__ but only __new__() and you  want to have 
        a different behavior than serialize self.__ dict__.
        __getstate__ must return the state of the class as an object that will itself be serialized.
        If __setstate __ () is not available, the returned object must be a dictionary 
        (elements will be restored as attributes), otherwise the object can be any serializable object
        
        .. code-block:: python
        
            def __getstate__(self):
                state = serializejson.filtered(self.__dict__)
        
        
        .. warning::
        
            if __reduce __ () is implemented, __getstate __ () will not be called
        
        
    
    
    .. py:function:: object.__setstate__()
    
        Code __setstate__() if you want to have other behavior than the default which 
        consists juste restoring attributs from state.
        takes as parameter the object describing the state of the class and 
        puts the instance back in the state it was in before serialization.
        can possibly execute initialization code.
        
        .. code-block:: python
        
            def __setstate__(self, state):
                self.set_x(state["x"])
                self.set_y(state["y"])
                # other initialization code 
                ....
                ....
                
        .. note::
        
            If __setstate __ () is not available, all elements of the dictionary __dict__ 
            or returned by __getstate__ (which in this case will have to return a dict) 
            will be restored as attributes



Versions
========
.. include:: ../CHANGELOG.rst
