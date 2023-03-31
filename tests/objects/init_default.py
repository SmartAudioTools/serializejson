try:
    from SmartFramework.serialize.serializejson import getstate
except:
    from serializejson import getstate


from .log import log

# with default INIT -------


class C_InitDefault_SaveNothing:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, ()  # , {}
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitDefault_SaveDict_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_InitDefault_SaveDict_RestoreDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitDefault_SaveDict_SetState:  # sert a pouvoir executer code spécifique a la restauration
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), getstate(self, filter_=None)
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")


class C_InitDefault_GetState_RestoreState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), {"keySaved": "ValueSaved"}
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitDefault_GetState_SetState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), "stateSaved"
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
