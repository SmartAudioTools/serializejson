from SmartFramework.tools.dictionnaires import filtered


def log(elt):
    pass


# with INIT -----------------

class C_InitArgs_SaveFilteredDict_RestoreNothing():  # ne sert pas à grand chose , sauf si on veut se garder la posibilitée de restaurer l'state plus tard
    def __init__(self, par1='defaut1', par2='defaut2'):
        log('        __init__(' + par1 + ',' + par2 + ')')
        self._par1 = par1
        self.par2 = par2

    def __reduce__(self):
        initArgs = (self._par1, 'savedArg2')
        reduce = self.__class__, initArgs, filtered(self.__dict__)
        log('        __reduce__ : ' + repr(reduce))
        return reduce

    def __setstate__(self, state):
        log('        __setstate__ : pass')
        pass


class C_InitArgs_SaveFilteredDict_RestoreDict():
    def __init__(self, par1='defaut1', par2='defaut2'):
        log('        __init__(' + par1 + ',' + par2 + ')')
        self._par1 = par1
        self.par2 = par2

    def __reduce__(self):
        initArgs = (self._par1, 'savedArg2')
        reduce = self.__class__, initArgs, filtered(self.__dict__)
        log('        __reduce__ : ' + repr(reduce))
        return reduce


class C_InitArgs_SaveFilteredDict_SetState():  # sert a pouvoir executer code specifique en plus du init a la restauration et choisir quoi restaurer
    def __init__(self, par1='defaut1', par2='defaut2'):
        log('        __init__(' + par1 + ',' + par2 + ')')
        self._par1 = par1
        self.par2 = par2

    def __reduce__(self):
        initArgs = (self._par1, 'savedArg2')
        reduce = self.__class__, initArgs, filtered(self.__dict__)
        log('        __reduce__ : ' + repr(reduce))
        return reduce

    def __setstate__(self, state):
        self.__dict__.update(state)
        log('        __setstate__(' + repr(state) + ')')