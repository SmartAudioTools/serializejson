try:
    import qtpy
except ModuleNotFoundError:
    pass

def tuple_from_QPen(obj):
    args = [obj.color()]
    if obj.width() != 1.0 or obj.style() != 1:
        args.append(obj.width())
        if obj.style() != 1:
            args.append(
                int(obj.style())
            )  # pour l'objant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
    return (obj.__class__, tuple(args),None)


def tuple_from_QBrush(obj):
    args = [obj.color()]
    if obj.style() != 1:
        args.append(
            int(obj.style())
        )  # pour l'objant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
    return (obj.__class__, tuple(args),None)


# --- DATA -------------------------------------------------------


def tuple_from_reducableQt(obj):
    tuple_reduce = obj.__reduce__()
    if qtpy.API_NAME == "PySide2":  # PySide 2
        initargs = tuple_reduce[1]  # truc normal
    else:  # PyQt
        initargs = tuple_reduce[1][2]
    return (obj.__class__, initargs, None)


def tuple_from_QColor(obj):
    tuple_reduce = obj.__reduce__()
    if qtpy.API_NAME == "PySide2":  # PySide 2
        initargs = tuple_reduce[2][1]
    else:  # PyQt
        initargs = tuple_reduce[1][2]
    return (obj.__class__, initargs, None)


def tuple_from_QPolygon(obj):
    tuple_reduce = obj.__reduce__()
    if qtpy.API_NAME == "PySide2":  # PySide 2
        initargs = tuple_reduce[1][0]
    else:  # PyQt
        initargs = tuple_reduce[1][2]
    return (obj.__class__, initargs, None)


def tuple_from_QPolygonF(obj):
    #tuple_reduce = obj.__reduce__()
    state= []
    for point in obj:
        state.append(point.x())
        state.append(point.y())
    return (obj.__class__, (state,), None)


# --- WIDGETS  -------------------------------------------------------


def tuple_from_QSpinBox(obj):
    state = {"value": obj.value()}
    return (obj.__class__, tuple(), state)


def tuple_from_QCheckBox(obj):
    if obj.isCheckable():
        state = {"checked": obj.isChecked()}
    else:
        state = None
    return (obj.__class__, tuple(), state)


def tuple_from_QLineEdit(obj):
    state = {"text": obj.text()}
    return (obj.__class__,  tuple(), state)


def tuple_from_QPlainTextEdit(obj):
    state = {"plainText": obj.toPlainText()}
    return (obj.__class__,  tuple(), state)



tuple_from_module_class_str =  {
    "qtpy.QtCore.QByteArray": tuple_from_reducableQt,
    "qtpy.QtCore.QDate": tuple_from_reducableQt,
    "qtpy.QtCore.QDateTime": tuple_from_reducableQt,
    "qtpy.QtCore.QLine": tuple_from_reducableQt,
    "qtpy.QtCore.QLineF": tuple_from_reducableQt,
    "qtpy.QtCore.QPoint": tuple_from_reducableQt,
    "qtpy.QtCore.QPointF": tuple_from_reducableQt,
    "qtpy.QtCore.QRect": tuple_from_reducableQt,
    "qtpy.QtCore.QRectF": tuple_from_reducableQt,
    "qtpy.QtCore.QSize": tuple_from_reducableQt,
    "qtpy.QtCore.QSizeF": tuple_from_reducableQt,
    "qtpy.QtCore.QTime": tuple_from_reducableQt,
    "qtpy.QtGui.QBrush": tuple_from_QBrush,
    "qtpy.QtGui.QColor": tuple_from_QColor,
    "qtpy.QtGui.QKeySequence": tuple_from_reducableQt,
    "qtpy.QtGui.QPen": tuple_from_QPen,
    "qtpy.QtGui.QPolygon": tuple_from_QPolygon,
    "qtpy.QtGui.QPolygonF": tuple_from_QPolygonF,
    "qtpy.QtGui.QTransform": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "qtpy.QtGui.QVector3D": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "qtpy.QtWidgets.QCheckBox": tuple_from_QCheckBox,
    "qtpy.QtWidgets.QDoubleSpinBox": tuple_from_QSpinBox,
    "qtpy.QtWidgets.QLineEdit": tuple_from_QLineEdit,
    "qtpy.QtWidgets.QPlainTextEdit": tuple_from_QPlainTextEdit,
    "qtpy.QtWidgets.QPushButton": tuple_from_QCheckBox,
    "qtpy.QtWidgets.QSpinBox": tuple_from_QSpinBox
}
