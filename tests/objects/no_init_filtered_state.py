from SmartFramework.tools.dictionaries import sorted_filtered
from .log import log

#  without INIT -----------------


class C_New_SaveNothing:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        log("        __getstate__ : {}")
        return {}


class C_New_SaveFilteredDict_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_New_SaveFilteredDict_RestoreDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state


class C_New_SaveFilteredDict_SetState:  # sert a pouvoir executer code spécifique a la restauration
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = sorted_filtered(self.__dict__)
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")
