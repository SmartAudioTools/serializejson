""


""
try: 
    import my_module
except ModuleNotFoundError: 
    pass   

def tuple_from_XXX(obj):
    """  
        Args: 
            obj:  the object to serialize.
        
        Return: 
            (class, init_args, state)
        
            class(class or str): 
                the classe or fonction called for object creation you should use obj.__class__ or string "module.submodule.name"   
            
            init_args (tuple,dict or None):  
                - tuple: positionals arguments you want pass to __init__() or to the callable
                - dict : keysword arguments if you want pass to __init__() or to the callable (take litle more space)
                - None : if you don't want to call the __init__() but only __new__() when loading.  
            
            state (None, dict or object): 
                can be None, if the state is already restored calling __init__()
           
        Example:
        
            .. code-block:: python
            
                def tuple_from_XXX(obj):
                    init_args = (obj.attribut_1,obj.attribut_3)
                    state = {"attribut_3":obj.attribut_3}
                    return (obj.__class__, init_args, state)
   
    """      