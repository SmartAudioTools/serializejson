from .log import log


def sorted_dict(d):
    return {key: d[key] for key in sorted(d)}


class BaseClass:
    __slots__ = ("_par1", "par2")

    def __init__(self):
        pass


#  without INIT -----------------


class C_New_SaveNothing_subclass(BaseClass):
    __slots__ = ("par3",)

    def __init__(self, par1="defaut1", par2="defaut2", par3="default3"):
        log("        __init__(" + par1 + "," + par2 + "," + par3 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3

    def __getstate__(self):
        log("        __getstate__ : {}")
        return None  # {}


class C_New_SaveDict_RestoreNothing_subclass(
    BaseClass
):  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    __slots__ = ("par3",)

    def __init__(self, par1="defaut1", par2="defaut2", par3="default3"):
        log("        __init__(" + par1 + "," + par2 + "," + par3 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_New_SaveDict_RestoreDict_subclass(BaseClass):
    __slots__ = ("par3",)

    def __init__(self, par1="defaut1", par2="defaut2", par3="default3"):
        log("        __init__(" + par1 + "," + par2 + "," + par3 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3


class C_New_SaveDict_SetState_subclass(BaseClass):
    # sert a pouvoir executer code spécifique a la restauration
    __slots__ = ("par3",)

    def __init__(self, par1="defaut1", par2="defaut2", par3="default3"):
        log("        __init__(" + par1 + "," + par2 + "," + par3 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3

    def __setstate__(self, state):
        if isinstance(
            state, tuple
        ):  # pour compatibilité pickle, qui passe un tuple avec (etat du __dict__ , etat des slots)
            state = state[1]
            log("        __setstate__(" + repr(sorted_dict(state)) + ")")
        else:

            log("        __setstate__(" + repr(state) + ")")
        for key, value in state.items():
            self.__setattr__(key, value)


"""class C_New_GetState_RestoreState():
    __slots__ = ('_par1', 'par2')
    def __init__(self, par1='defaut1', par2='defaut2'):
        log('        __init__(' + par1 + ',' + par2 + ')')
        self.par2 = par2
        self._par1 = par1

    def __getstate__(self):
        state = {'par2': 'ValueSaved'}
        log('        __getstate__ : ' + repr(state))
        #return state
        #return (None,state) # pour compatibilité Pickle , mais merdique pour json 
"""


class C_New_GetState_SetState_subclass(BaseClass):
    __slots__ = ("par3",)

    def __init__(self, par1="defaut1", par2="defaut2", par3="default3"):
        log("        __init__(" + par1 + "," + par2 + "," + par3 + ")")
        self.par2 = par2
        self._par1 = par1
        self.par3 = par3

    def __getstate__(self):
        state = "stateSaved"
        log("        __getstate__ : " + repr(state))
        return state

    def __setstate__(self, state):
        self._par1 = state
        log("        __setstate__(" + repr(state) + ")")
