from .log import log

try:
    from SmartFramework.serialize.serializejson import getstate
except:
    from serializejson import getstate

#  without INIT -----------------


class C_New_SaveNothing_slots:
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        log("        __getstate__ : {}")
        return None  # {}


class C_New_SaveDict_RestoreNothing_slots:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_New_SaveDict_RestoreDict_slots:
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1


class C_New_SaveDict_SetState_slots:  # sert a pouvoir executer code spécifique a la restauration
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __setstate__(self, state):
        if isinstance(
            state, tuple
        ):  # pour compatibilité pickle, qui passe un tuple avec (etat du __dict__ , etat des slots)
            state = state[1]
        for key, value in state.items():
            self.__setattr__(key, value)
        log("        __setstate__(" + repr(state) + ")")


class C_New_GetState_RestoreState_slots:
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = {"par2": "ValueSaved"}
        log("        __getstate__ : " + repr(state))
        # return state
        return (None, state)  # pour compatibilité Pickle , mais merdique pour json


class C_New_GetState_RestoreState_slots_auto_getstate:
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        return getstate(self, filter_=None)
        # state = {'par2': 'ValueSaved'}
        # log('        __getstate__ : ' + repr(state))
        # return state
        # return (None,state) # pour compatibilité Pickle , mais merdique pour json


class C_New_GetState_RestoreState_slots:
    __slots__ = ("_par1", "par2")

    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = {"par2": "ValueSaved"}
        log("        __getstate__ : " + repr(state))
        # return state
        return (None, state)  # pour compatibilité Pickle , mais merdique pour json


class C_New_GetState_SetState_slots:
    __slots__ = ("_par1", "par2")

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
