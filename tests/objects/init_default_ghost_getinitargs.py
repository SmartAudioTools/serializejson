from .log import log

# with default INIT -------


class C_SaveNothing_DefaultInit_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        log("        __getinitargs__ SHOULD'NT BE CALLED with python new style objects")
        return ("__getinitargs__ SHOULD'NT BE CALLED with python new style objects",)

    def __getstate__(self):
        log("        __getstate__ : {}")
        return {}


class C_SaveDict_DefaultInit_RestoreNothing_getinitargs:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        log("        __getinitargs__ SHOULD'NT BE CALLED with python new style objects")
        return ("__getinitargs__ SHOULD'NT BE CALLED with python new style objects",)

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_SaveDict_DefaultInit_RestoreDict_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        log("        __getinitargs__ SHOULD'NT BE CALLED with python new style objects")
        return ("__getinitargs__ SHOULD'NT BE CALLED with python new style objects",)


class C_SaveDict_DefaultInit_SetState_getinitargs:  # sert a pouvoir executer code spécifique a la restauration
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        log("        __getinitargs__ SHOULD'NT BE CALLED with python new style objects")
        return ("__getinitargs__ SHOULD'NT BE CALLED with python new style objects",)

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")


class C_GetState_DefaultInit_RestoreState_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        log("        __getinitargs__ SHOULD'NT BE CALLED with python new style objects")
        return ("__getinitargs__ SHOULD'NT BE CALLED with python new style objects",)

    def __getstate__(self):
        state = {"keySaved": "ValueSaved"}
        log("        __getstate__ : " + repr(state))
        return state


class C_GetState_DefaultInit_SetState_getinitargs:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getinitargs__(self):
        log("        __getinitargs__ SHOULD'NT BE CALLED with python new style objects")
        return ("__getinitargs__ SHOULD'NT BE CALLED with python new style objects",)

    def __getstate__(self):
        log("        getstate")
        return "stateSaved"

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
