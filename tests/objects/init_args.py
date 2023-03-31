from .log import log

try:
    from SmartFramework.serialize.serializejson import getstate
except:
    from serializejson import getstate
# with INIT -----------------


class C_InitArgs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs  # pas besoin de None ou {}
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitArgs_SaveDict_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_InitArgs_SaveDict_RestoreDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitArgs_SaveDict_SetState:  # sert a pouvoir executer code specifique en plus du init a la restauration et choisir quoi restaurer
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")


class C_InitArgs_GetState_RestoreState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, {"keySaved": "ValueSaved"}
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitArgs_GetState_SetStateDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, {"keySaved": "ValueSaved"}
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")


class C_InitArgs_GetState_SetState:  # plus obligé de auvegarder l'state sous forme de dictionnaire !!!!
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, "stateSaved"
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
