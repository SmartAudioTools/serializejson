from .log import log

#  without INIT -----------------


class C_New_GetState_SetState_no_string_keys:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = {"keySaved": "ValueSaved", 1: 1}
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")


"""class C_New_GetState_RestoreState_no_string_keys:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = {"keySaved": "ValueSaved",1:1}
        log("        __getstate__ : " + repr(state))
        return state"""
