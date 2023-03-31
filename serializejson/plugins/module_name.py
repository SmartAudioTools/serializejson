""


""
try:
    import module_name
except ModuleNotFoundError:
    pass


def XXX_serializejson(obj):
    """
    Args:
        obj:  the object to serialize.

    Return:
        (class, init_args, state,list_items ,dict_items,new_args)
        
        Variable length tuple with one to six elements. 
        Only the first 'class' element is required, other are set to None by default.       

        class(class or str):
            the class or function called for object creation you should use `obj.__class__` or string `"module.submodule.name"`

        init_args (tuple,dict or None):
            - tuple: positional arguments you want pass to `__init__()` or to the callable
            - dict : keysword arguments you want pass to `__init__()` or to the callable (take little more space)
            - None : if you don't want to call the `__init__()` but only `__new__()` when loading.

        state (None, dict or object):
            can be None, if the state is already restored calling `__init__()`

        list_items (list or None):
            list of items for class with list interface.
        
        dict_items (dict or None):
            dictionnary of items for class with dictionnary interface.
        
        new_args (tuple,dict or None):
            - tuple: positional arguments you want pass to `__new__()` methode.
            - dict : keysword arguments you want pass to `__new__()` methode.
            - None : if you don't want to call the `__init__()` but only `__new__()` when loading.
  
        
    Example:

        .. code-block:: python

            def tuple_from_XXX(obj):
                init_args = (obj.attribute_1,obj.attribute_3)
                state = {"attribute_3":obj.attribute_3}
                return (obj.__class__, init_args, state)

    """
