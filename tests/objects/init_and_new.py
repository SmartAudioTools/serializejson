from .log import log

try:
    from SmartFramework.serialize.serializejson import getstate
except:
    from serializejson import getstate

# with INIT -----------------
class C_Init_New:
    def __new__(cls, new_par1="new_par1", new_par2="new_par2"):
        log("        __new__(" + new_par1 + ")")
        obj = object.__new__(cls)
        obj.new_par1 = new_par1
        return obj

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1


class C_Init_New_Reduce:
    def __new__(cls, new_par1="new_par1", new_par2="new_par2"):
        log("        __new__(" + new_par1 + ")")
        obj = object.__new__(cls)
        obj.new_par1 = new_par1
        return obj

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs  # pas besoin de None ou {}
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_Init_New_Newargs:
    def __new__(cls, new_par1="new_par1", new_par2="new_par2"):
        log("        __new__(" + new_par1 + ")")
        obj = object.__new__(cls)
        obj.new_par1 = new_par1
        return obj

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getnewargs__(self):
        newargs = ("coucou",)
        log("        __getnewargs__ : " + repr(newargs))
        return newargs


class C_Init_New_Newargs_Reduce:
    def __new__(cls, new_par1="new_par1", new_par2="new_par2"):
        log("        __new__(" + new_par1 + ")")
        obj = object.__new__(cls)
        obj.new_par1 = new_par1
        return obj

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getnewargs__(self):
        newargs = ("coucou",)
        log("        __getnewargs__ : " + repr(newargs))
        return newargs

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs  # pas besoin de None ou {}
        log("        __reduce__ : " + repr(reduce))
        return reduce
