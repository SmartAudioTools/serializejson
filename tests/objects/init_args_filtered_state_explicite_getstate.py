from SmartFramework.tools.dictionaries import sorted_filtered


from .log import log

# with INIT -----------------


class C_SaveArgInit_filter:
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


class C_SaveDict_SaveArgInit_filter_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
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
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_SaveDict_SaveArgInit_RestoreDict_filter:
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
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state


class C_SaveDict_SaveArgInit_SetState_filter:  # sert a pouvoir executer code specifique en plus du init a la restauration et choisir quoi restaurer
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
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")
