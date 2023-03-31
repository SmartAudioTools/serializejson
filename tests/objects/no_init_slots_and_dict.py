from .log import log

try:
    from SmartFramework.serialize.serializejson import getstate
except:
    from serializejson import getstate

#  without INIT -----------------


def sorted_dict(d):
    return {key: d[key] for key in sorted(d)}


class C_New_SaveNothing_slots_and_dict:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __getstate__(self):
        log("        __getstate__ : {}")
        return None  # {}


class C_New_SaveDict_RestoreNothing_slots_and_dict:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_New_SaveDict_RestoreDict_slots_and_dict:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4


class C_New_SaveDict_SetState_slots_and_dict_securized:  # sert a pouvoir executer code spécifique a la restauration
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __setstate__(self, state):
        if isinstance(
            state, tuple
        ):  # pour compatibilité pickle, qui passe un tuple avec (etat du __dict__ , etat des slots sous forme de dictionnaire)
            self.__dict__.update(state[0])
            log(
                "        __setstate__("
                + repr(sorted_dict({**state[0], **state[1]}))
                + ")"
            )
            state = state[1]
        else:
            log("        __setstate__(" + repr(sorted_dict(state)) + ")")

        for key, value in state.items():
            self.__setattr__(key, value)


class C_New_SaveDict_SetState_slots_and_dict:  # sert a pouvoir executer code spécifique a la restauration
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __setstate__(self, state):
        _dict, _slots = state
        self.__dict__.update(_dict)
        log("        __setstate__(" + repr(state) + ")")
        for key, value in _slots.items():
            self.__setattr__(key, value)


class C_New_GetState_RestoreState_slots_and_dict_auto_gestate:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __getstate__(self):
        return getstate(self, filter_=None)
        # __dict__ = {'par2': 'ValueSaved'}
        # __slots__= {'_par1': 'ValueSaved2'}
        # log('        __getstate__ : ' + repr((__dict__,__slots__)))
        # return __slots__
        # return (__dict__,__slots__) # pour compatibilité Pickle , mais merdique pour json


class C_New_GetState_RestoreState_slots_and_dict1:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __getstate__(self):
        # return getstate(self,filter_=None)
        __dict__ = {"par2": "ValueSaved"}
        __slots__ = {"_par1": "ValueSaved2"}
        log("        __getstate__ : " + repr((__dict__, __slots__)))
        return __slots__


class C_New_GetState_RestoreState_slots_and_dict2:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __getstate__(self):
        __dict__ = None
        __slots__ = {"_par1": "ValueSaved2"}
        log("        __getstate__ : " + repr((__dict__, __slots__)))
        # pour compatibilité Pickle , mais merdique pour json
        return (__dict__, __slots__)


class C_New_GetState_RestoreState_slots_and_dict3:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __getstate__(self):
        __dict__ = {"par2": "ValueSaved"}
        __slots__ = {}
        log("        __getstate__ : " + repr((__dict__, __slots__)))
        # pour compatibilité Pickle , mais merdique pour json
        return (__dict__, __slots__)


class C_New_GetState_SetState_slots_and_dict:
    __slots__ = ("_par4", "par3", "__dict__")

    def __init__(self, par1="defaut1", par2="defaut2", par3="defaut3", par4="defaut4"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3
        self._par4 = par4

    def __getstate__(self):
        state = "stateSaved"
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
