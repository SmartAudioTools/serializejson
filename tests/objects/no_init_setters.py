from .log import log

#  without INIT -----------------


class C_New_SaveDict_RestoreDict_setters:
    def __init__(self, a="a", b="b", c="c", d="d", e="e", f="f"):
        log(
            "        __init__("
            + a
            + ","
            + b
            + ","
            + c
            + ","
            + d
            + ","
            + e
            + ","
            + f
            + ")"
        )
        self.__dict__["f"] = f
        self.__dict__["e"] = e
        self.d = d
        self.c = c
        self.b = b
        self.a = a

    def setb(self, value):
        log("setb(%s)" % value)
        self.b = value

    def set_c(self, value):
        log("set_c(%s)" % value)
        self.c = value

    def setD(self, value):
        log("setD(%s)" % value)
        self.d = value

    @property  # @pyqtProperty(int) en pyqt
    def e(self):
        log("getter e")
        return self.__dict__["e"]

    @e.setter  # idem en pyqt
    def e(self, value):
        log("setter e(%s)" % value)
        self.__dict__["e"] = value

    def getf(self):
        return self.__dict__["f"]

    def setf(self, value):
        log("f setter called")
        self.__dict__["f"] = value

    f = property(getf, setf)


class C_New_SaveDict_SetState_setters:  # sert a pouvoir executer code spécifique a la restauration
    def __init__(self, a="a", b="b", c="c", d="d", e="e", f="f"):
        log(
            "        __init__("
            + a
            + ","
            + b
            + ","
            + c
            + ","
            + d
            + ","
            + e
            + ","
            + f
            + ")"
        )
        self.__dict__["f"] = f
        self.__dict__["e"] = e
        self.d = d
        self.c = c
        self.b = b
        self.a = a

    def __setstate__(self, state):
        self.__dict__.update(state)
        log("        __setstate__(" + repr(state) + ")")

    def setb(self, value):
        print("seta() called")
        self.b = value

    def set_c(self, value):
        print("setb() called")
        self.c = value

    def setD(self, value):
        print("setc() called")
        self.d = value

    @property  # @pyqtProperty(int) en pyqt
    def e(self):
        return self.__dict__["e"]

    @e.setter  # idem en pyqt
    def e(self, value):
        print("e setter called")
        self.__dict__["e"] = value

    def getf(self):
        return self.__dict__["f"]

    def setf(self, value):
        print("f setter called")
        self.__dict__["f"] = value

    f = property(getf, setf)
