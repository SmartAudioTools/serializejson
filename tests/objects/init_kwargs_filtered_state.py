from apply import apply
from SmartFramework.tools.dictionaries import sorted_filtered


from .log import log

# with INIT -----------------


class C_InitKwargs_filter:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initKwargs = {"par1": self._par1, "par2": "savedArg2"}
        reduce = apply, (self.__class__, None, initKwargs)  # ,{}
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C_InitKwargs_SaveFilteredDict_RestoreNothing:  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initKwargs = {"par1": self._par1, "par2": "savedArg2"}
        reduce = (
            apply,
            (self.__class__, None, initKwargs),
            sorted_filtered(self.__dict__),
        )
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        log("        __setstate__ : pass")
        pass


class C_InitKwargs_SaveFilteredDict_RestoreDict:
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initKwargs = {"par1": self._par1, "par2": "savedArg2"}
        reduce = (
            apply,
            (self.__class__, None, initKwargs),
            sorted_filtered(self.__dict__),
        )
        log("        __reduce__ : " + repr(reduce))
        return reduce


class C__InitKwargs_SaveFilteredDict_SetState:  # sert a pouvoir executer code specifique en plus du init a la restauration et choisir quoi restaurer
    def __init__(self, par1="defaut1", par2="defaut2"):
        log("        __init__(" + par1 + "," + par2 + ")")
        self.par2 = par2
        self._par1 = par1

    def __reduce__(self):
        initKwargs = {"par1": self._par1, "par2": "savedArg2"}
        reduce = (
            apply,
            (self.__class__, None, initKwargs),
            sorted_filtered(self.__dict__),
        )
        log("        __reduce__ : " + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")
