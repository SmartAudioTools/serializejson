from .log import log

# with default INIT -------


class C_SaveNothing_DefaultInit:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), {}
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        log("        __getstate__  SHOULD'NT BE CALLED when __reduce__")
        return "__getstate__  SHOULD'NT BE CALLED when __reduce__"


class C_GetState_DefaultInit_RestoreState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), {"keySaved": "ValueSaved"}
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        log("        __getstate__  SHOULD'NT BE CALLED when __reduce__")
        return "__getstate__  SHOULD'NT BE CALLED when __reduce__"


class C_GetState_DefaultInit_SetState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        reduce = self.__class__, (), "stateSaved"
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __getstate__(self):
        log("        __getstate__  SHOULD'NT BE CALLED when __reduce__")
        return "__getstate__  SHOULD'NT BE CALLED when __reduce__"

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
