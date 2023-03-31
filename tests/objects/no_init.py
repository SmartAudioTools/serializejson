from .log import log

#  without INIT -----------------


class C_New_SaveNothing:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        log("        __getstate__ : {}")
        return None  # {}


class C_New_SaveDict_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_New_SaveDict_RestoreDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1


class C_New_SaveDict_SetState:  # sert a pouvoir executer code spécifique a la restauration
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")


class C_New_GetState_RestoreState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = {"keySaved": "ValueSaved"}
        log("        __getstate__ : " + repr(state))
        return state


class C_New_GetState_SetState:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = "stateSaved"
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")


class C_New_GetState_SetState_tuple:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = (self._par1, self.par2)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1, self.par2 = state
        log("        __setstate__(" + repr(state) + ")")
