# from pybase64 import b64encode
# from ..tools import encodedB64

try:
    import qtpy

    def get_class(obj):
        class_ = obj.__class__
        return "qtpy." + class_.__module__[6:] + "." + class_.__name__


except ModuleNotFoundError:

    def get_class(obj):
        return obj.__class__


def tuple_from_QPen(obj):
    args = [obj.color()]
    if obj.width() != 1.0 or obj.style() != 1:
        args.append(obj.width())
        if obj.style() != 1:
            args.append(
                int(obj.style())
            )  # pour l'instant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
    return (get_class(obj), tuple(args), None)


def tuple_from_QBrush(obj):
    args = [obj.color()]
    if obj.style() != 1:
        args.append(
            int(obj.style())
        )  # pour l'instant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
    return (get_class(obj), tuple(args), None)


# --- DATA -------------------------------------------------------


def tuple_from_reducableQt(obj):
    tuple_reduce = obj.__reduce__()
    initargs = tuple_reduce[1][2]
    return (get_class(obj), initargs, None)


def tuple_from_QColor(obj):
    tuple_reduce = obj.__reduce__()
    initargs = tuple_reduce[1][2]
    return (get_class(obj), initargs, None)


def tuple_from_QPolygon(obj):
    # return (get_class(obj), obj.__reduce__()[1][2], None)  # donne une liste avec les points falten, qui n'est pas envoyable au construteur.....
    state = []
    for point in obj:
        state.append(point)
    return (get_class(obj), (state,), None)


def tuple_from_QPolygonF(obj):
    # data = obj.data()
    # data.setsize(16*obj.size())
    # state =  encodedB64(b64encode(data))
    # return ("serializejson.plugins.PyQt5.QPolygonF", (state,), None)
    state = []
    for point in obj:
        state.append(point)
    return (get_class(obj), (state,), None)


# --- WIDGETS  -------------------------------------------------------


def tuple_from_QSpinBox(obj):
    state = {"value": obj.value()}
    return (get_class(obj), tuple(), state)


def tuple_from_QCheckBox(obj):
    if obj.isCheckable():
        state = {"checked": obj.isChecked()}
    else:
        state = None
    return (get_class(obj), tuple(), state)


def tuple_from_QLineEdit(obj):
    state = {"text": obj.text()}
    return (get_class(obj), tuple(), state)


def tuple_from_QPlainTextEdit(obj):
    state = {"plainText": obj.toPlainText()}
    return (get_class(obj), tuple(), state)


def tuple_from_QWidget(obj):
    return (get_class(obj), tuple(), None)


set_attributes = {
    "qtpy.QtWidgets.QCheckBox",
    "qtpy.QtWidgets.QDoubleSpinBox",
    "qtpy.QtWidgets.QLineEdit",
    "qtpy.QtWidgets.QPlainTextEdit",
    "qtpy.QtWidgets.QPushButton",
    "qtpy.QtWidgets.QSpinBox",
    "PyQt5.QtWidgets.QCheckBox",
    "PyQt5.QtWidgets.QDoubleSpinBox",
    "PyQt5.QtWidgets.QLineEdit",
    "PyQt5.QtWidgets.QPlainTextEdit",
    "PyQt5.QtWidgets.QPushButton",
    "PyQt5.QtWidgets.QSpinBox",
    "PyQt5.QtWidgets.QWidget",
}


tuple_from_module_class_str = {
    "PyQt5.QtCore.QByteArray": tuple_from_reducableQt,
    "PyQt5.QtCore.QDate": tuple_from_reducableQt,
    "PyQt5.QtCore.QDateTime": tuple_from_reducableQt,
    "PyQt5.QtCore.QLine": tuple_from_reducableQt,
    "PyQt5.QtCore.QLineF": tuple_from_reducableQt,
    "PyQt5.QtCore.QPoint": tuple_from_reducableQt,
    "PyQt5.QtCore.QPointF": tuple_from_reducableQt,
    "PyQt5.QtCore.QRect": tuple_from_reducableQt,
    "PyQt5.QtCore.QRectF": tuple_from_reducableQt,
    "PyQt5.QtCore.QSize": tuple_from_reducableQt,
    "PyQt5.QtCore.QSizeF": tuple_from_reducableQt,
    "PyQt5.QtCore.QTime": tuple_from_reducableQt,
    "PyQt5.QtGui.QBrush": tuple_from_QBrush,
    "PyQt5.QtGui.QColor": tuple_from_QColor,
    "PyQt5.QtGui.QKeySequence": tuple_from_reducableQt,
    "PyQt5.QtGui.QPen": tuple_from_QPen,
    "PyQt5.QtGui.QPolygon": tuple_from_QPolygon,
    "PyQt5.QtGui.QPolygonF": tuple_from_QPolygonF,
    "PyQt5.QtGui.QTransform": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "PyQt5.QtGui.QVector3D": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "PyQt5.QtWidgets.QCheckBox": tuple_from_QCheckBox,
    "PyQt5.QtWidgets.QDoubleSpinBox": tuple_from_QSpinBox,
    "PyQt5.QtWidgets.QLineEdit": tuple_from_QLineEdit,
    "PyQt5.QtWidgets.QPlainTextEdit": tuple_from_QPlainTextEdit,
    "PyQt5.QtWidgets.QPushButton": tuple_from_QCheckBox,
    "PyQt5.QtWidgets.QSpinBox": tuple_from_QSpinBox,
    "PyQt5.QtWidgets.QWidget": tuple_from_QWidget,
}
