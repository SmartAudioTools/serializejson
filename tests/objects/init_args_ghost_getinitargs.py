from .log import log

# with INIT -----------------


class C_SaveArgInit_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        initArgs = (self._par1, "savedArg2")
        log("        __getinitargs__ : " + repr(initArgs))
        return initArgs

    def __getstate__(self):
        log("        __getstate__ : {}")
        return {}


class C_SaveDict_SaveArgInit_getinitargs:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        initArgs = (self._par1, "savedArg2")
        log("        __getinitargs__ : " + repr(initArgs))
        return initArgs

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_SaveDict_SaveArgInit_RestoreDict_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        initArgs = (self._par1, "savedArg2")
        log("        __getinitargs__ : " + repr(initArgs))
        return initArgs


class C_SaveDict_SaveArgInit_SetState_getinitargs:  # sert a pouvoir executer code specifique en plus du init a la restauration et choisir quoi restaurer
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        initArgs = (self._par1, "savedArg2")
        log("        __getinitargs__ : " + repr(initArgs))
        return initArgs

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")


class C_GetState_SaveArgInit_RestoreState_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        initArgs = (self._par1, "savedArg2")
        log("        __getinitargs__ : " + repr(initArgs))
        return initArgs

    def __getstate__(self):
        state = {"keySaved": "ValueSaved"}
        log("        __getstate__ : " + repr(state))
        return state


class C_GetState_SaveArgInit_SetState_getinitargs:  # plus obligé de auvegarder l'state sous forme de dictionnaire !!!!
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        initArgs = (self._par1, "savedArg2")
        log("        __getinitargs__ : " + repr(initArgs))
        return initArgs

    def __getstate__(self):
        state = "stateSaved"
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
