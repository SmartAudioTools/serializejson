from .log import log

try:
    from SmartFramework.serialize.serializejson import getstate
except:
    from serializejson import getstate

# with INIT -----------------


class C_SaveArgInit:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        log("        __getstate__ : {}")
        return {}


class C_SaveDict_SaveArgInit_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
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


class C_SaveDict_SaveArgInit_RestoreDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_SaveDict_SaveArgInit_SetState:  # sert a pouvoir executer code specifique en plus du init a la restauration et choisir quoi restaurer
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


class C_GetState_SaveArgInit_RestoreState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        state = {"keySaved": "ValueSaved"}
        log("        __getstate__ : " + repr(state))
        return state


class C_GetState_SaveArgInit_SetState:  # plus obligé de auvegarder l'state sous forme de dictionnaire !!!!
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initArgs = (self._par1, "savedArg2")
        reduce = self.__class__, initArgs, self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        state = "stateSaved"
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
