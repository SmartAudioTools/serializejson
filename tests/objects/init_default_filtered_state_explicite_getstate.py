from SmartFramework.tools.dictionaries import sorted_filtered


from .log import log

# with default INIT -------


class C_SaveNothing_DefaultInit:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        log("        __getstate__ : {}")
        return {}


class C_SaveDict_DefaultInit_RestoreNothing_filter:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_SaveDict_DefaultInit_RestoreDict_filter:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state


class C_SaveDict_DefaultInit_SetState_filter:  # sert a pouvoir executer code spécifique a la restauration
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), self.__getstate__()
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")
