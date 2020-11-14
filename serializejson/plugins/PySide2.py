try:
    import qtpy

    def get_class(obj):
        class_ = obj.__class__
        return "qtpy." + class_.__module__[8:] + "." + class_.__name__


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
    initargs = tuple_reduce[1]  # truc normal
    return (get_class(obj), initargs, None)


def tuple_from_QColor(obj):
    tuple_reduce = obj.__reduce__()
    initargs = tuple_reduce[2][1]
    return (get_class(obj), initargs, None)


def tuple_from_QPolygon(obj):
    tuple_reduce = obj.__reduce__()
    initargs = tuple_reduce[1][0]
    return (get_class(obj), initargs, None)


def tuple_from_QPolygonF(obj):
    state = []
    for point in obj:
        state.append(point.x())
        state.append(point.y())
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
    "PySide2.QtWidgets.QCheckBox",
    "PySide2.QtWidgets.QDoubleSpinBox",
    "PySide2.QtWidgets.QLineEdit",
    "PySide2.QtWidgets.QPlainTextEdit",
    "PySide2.QtWidgets.QPushButton",
    "PySide2.QtWidgets.QSpinBox",
    "PySide2.QtWidgets.QWidget",
}


tuple_from_module_class_str = {
    "PySide2.QtCore.QByteArray": tuple_from_reducableQt,
    "PySide2.QtCore.QDate": tuple_from_reducableQt,
    "PySide2.QtCore.QDateTime": tuple_from_reducableQt,
    "PySide2.QtCore.QLine": tuple_from_reducableQt,
    "PySide2.QtCore.QLineF": tuple_from_reducableQt,
    "PySide2.QtCore.QPoint": tuple_from_reducableQt,
    "PySide2.QtCore.QPointF": tuple_from_reducableQt,
    "PySide2.QtCore.QRect": tuple_from_reducableQt,
    "PySide2.QtCore.QRectF": tuple_from_reducableQt,
    "PySide2.QtCore.QSize": tuple_from_reducableQt,
    "PySide2.QtCore.QSizeF": tuple_from_reducableQt,
    "PySide2.QtCore.QTime": tuple_from_reducableQt,
    "PySide2.QtGui.QBrush": tuple_from_QBrush,
    "PySide2.QtGui.QColor": tuple_from_QColor,
    "PySide2.QtGui.QKeySequence": tuple_from_reducableQt,
    "PySide2.QtGui.QPen": tuple_from_QPen,
    "PySide2.QtGui.QPolygon": tuple_from_QPolygon,
    "PySide2.QtGui.QPolygonF": tuple_from_QPolygonF,
    "PySide2.QtGui.QTransform": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "PySide2.QtGui.QVector3D": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "PySide2.QtWidgets.QCheckBox": tuple_from_QCheckBox,
    "PySide2.QtWidgets.QDoubleSpinBox": tuple_from_QSpinBox,
    "PySide2.QtWidgets.QLineEdit": tuple_from_QLineEdit,
    "PySide2.QtWidgets.QPlainTextEdit": tuple_from_QPlainTextEdit,
    "PySide2.QtWidgets.QPushButton": tuple_from_QCheckBox,
    "PySide2.QtWidgets.QSpinBox": tuple_from_QSpinBox,
    "PySide2.QtWidgets.QWidget": tuple_from_QWidget,
}
