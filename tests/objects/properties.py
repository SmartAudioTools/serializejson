from .log import log

# log = print
#  without INIT -----------------


class C_Property_decorator:
    def __init__(self):
        log("__init__")
        self._x = None

    @property  # @pyqtProperty(int) 	  en pyqt
    def x(self):
        log("get x", self._x)
        return self._x

    @x.setter  # idem 			  en pyqt
    def x(self, value):
        log("set x", value)
        self._x = value


class C_Property:
    def __init__(self):
        log("__init__")
        self._x = None

    def getx(self):
        log("get x", self._x)
        return self._x

    def setx(self, value):
        log("set x", value)
        self._x = value

    x = property(getx, setx)


class C_slots_properties_getters_setters:  # sert a pouvoir executer code spécifique a la restauration

    __slots__ = ("a", "c", "__dict__")

    def __init__(self, a="a", b="b", c="c", d="d", e="e", f="f", g="g", h="h", i="i"):
        log(f"__init__({a},{b},{c},{d},{e},{f},{g})")
        self.__dict__["g"] = g
        self.__dict__["f"] = f
        self.__dict__["e"] = e
        self.d = d
        self.c = c
        self.b = b
        self.a = a

    # def __setstate__(self, state):
    #    self.__dict__.update(state)
    #    log("        __setstate__(" + repr(state) + ")")

    def setb(self, value):
        log("seta() called")
        self.b = value

    def set_c(self, value):
        log("setb() called")
        self.c = value

    def setD(self, value):
        log("setc() called")
        self.d = value

    @property  # @pyqtProperty(int) en pyqt
    def e(self):
        return self.__dict__["e"].upper()

    @e.setter  # idem en pyqt
    def e(self, value):
        log("e setter called")
        self.__dict__["e"] = value.lower()

    def getf(self):
        return self.__dict__["f"].upper()

    def setf(self, value):
        log("f setter called")
        self.__dict__["f"] = value.lower()

    f = property(getf, setf)

    def getg(self):
        return self.__dict__["g"].upper()

    def setg(self, value):
        log("g setter called")
        self.__dict__["g"] = value.lower()
