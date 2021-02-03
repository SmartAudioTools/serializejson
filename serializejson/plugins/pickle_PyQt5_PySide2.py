try:
    import qtpy

    API = qtpy.API_NAME
    from qtpy import QtGui, QtWidgets  # ,QtCore
except ModuleNotFoundError:
    try:
        from PyQt5 import QtGui, QtWidgets  # ,QtCore

        API = "PyQt5"
    except ModuleNotFoundError:
        try:
            from PySide2 import QtGui, QtWidgets  # ,QtCore

            API = "PySide2"
        except ModuleNotFoundError:
            API = None
if API:
    from apply import apply

    # from SmartFramework.serialize.tools import __setstate__
    # QtCore.QObject.__setstate__ = lambda self,state: __setstate__(self,state,setters = True)
    # permet à pickle de pouvoir déserialiser et de désactier le paramètre setters de serializejson.dumps!
    # par contre ça dégeulasse serializPython...
    # les QWidget héritent que QObject, mais pas les QBrush par exemple !  PyQt5.QtGui.QBrush.__base__ -> sip.simplewrapper

    # ---  QT GUI ------------------------------------------------------------

    def reduce_QPen(obj):
        args = [obj.color()]
        if obj.width() != 1.0 or obj.style() != 1:
            args.append(obj.width())
            if obj.style() != 1:
                args.append(
                    int(obj.style())
                )  # pour l'instant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
        return type(obj), tuple(args), None

    QtGui.QPen.__reduce__ = reduce_QPen

    def reduce_QBrush(obj):
        args = [obj.color()]
        if obj.style() != 1:
            args.append(
                int(obj.style())
            )  # pour l'instant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
        return type(obj), tuple(args), None

    QtGui.QBrush.__reduce__ = reduce_QBrush

    def reduce_QPolygon(obj):
        return type(obj), ([point for point in obj],), None

    QtGui.QPolygon.__reduce__ = reduce_QPolygon
    QtGui.QPolygonF.__reduce__ = reduce_QPolygon

    # --- QT WIDGETS  -------------------------------------------------------

    # avec apply pour pickle

    def reduce_QSpinBox(obj):
        state = {"value": obj.value()}
        return apply, (type(obj), None, state)

    QtWidgets.QSpinBox.__reduce__ = reduce_QSpinBox

    def reduce_QCheckBox(obj):
        if obj.isCheckable():
            state = {"checked": obj.isChecked()}
            return apply, (type(obj), None, state)
        else:
            return type(obj), tuple()

    QtWidgets.QCheckBox.__reduce__ = reduce_QCheckBox
    QtWidgets.QPushButton.__reduce = reduce_QCheckBox

    def reduce_QLineEdit(obj):
        state = {"text": obj.text()}
        return apply, (type(obj), None, state)

    QtWidgets.QLineEdit.__reduce__ = reduce_QLineEdit

    def reduce_QPlainTextEdit(obj):
        state = {"plainText": obj.toPlainText()}
        return apply, (type(obj), None, state)

    QtWidgets.QPlainTextEdit.__reduce__ = reduce_QPlainTextEdit

    def reduce_QWidget(obj):
        return type(obj), tuple(), None

    QtWidgets.QWidget.__reduce__ = reduce_QWidget
