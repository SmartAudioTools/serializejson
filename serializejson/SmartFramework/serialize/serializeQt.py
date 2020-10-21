try:
    import qtpy
except:
    pass


def tuple_from_QPen(inst, classe):
    args = [inst.color()]
    if inst.width() != 1.0 or inst.style() != 1:
        args.append(inst.width())
        if inst.style() != 1:
            args.append(
                inst.style()
            )  # pour l'instant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
    return classe, tuple(args)


def tuple_from_QBrush(inst, classe):
    args = [inst.color()]
    if inst.style() != 1:
        args.append(inst.style())  # pour l'instant ne sais pas comment serialiser une enumeration Qt.SolidLine ect...
    return classe, tuple(args)


# --- DATA -------------------------------------------------------


def tuple_from_reducableQt(inst, classe):
    tuple_reduce = inst.__reduce__()
    if qtpy.API_NAME == "PySide2":  # PySide 2
        initargs = tuple_reduce[1]  # truc normal
    else:  # PyQt
        initargs = tuple_reduce[1][2]
    return (classe, initargs, None)


def tuple_from_QColor(inst, classe):
    tuple_reduce = inst.__reduce__()
    if qtpy.API_NAME == "PySide2":  # PySide 2
        initargs = tuple_reduce[2][1]
    else:  # PyQt
        initargs = tuple_reduce[1][2]
    return (classe, initargs, None)


def tuple_from_QPolygon(inst, classe):
    tuple_reduce = inst.__reduce__()
    if qtpy.API_NAME == "PySide2":  # PySide 2
        initargs = tuple_reduce[1][0]
    else:  # PyQt
        initargs = tuple_reduce[1][2]
    return (classe, initargs, None)


# --- WIDGETS  -------------------------------------------------------


def tuple_from_QSpinBox(inst, classe):
    state = {"value": inst.value()}
    return (classe, None, state)


def tuple_from_QCheckBox(inst, classe):
    if inst.isCheckable():
        state = {"checked": inst.isChecked()}
    else:
        state = None
    return (classe, None, state)


def tuple_from_QLineEdit(inst, classe):
    state = {"text": inst.text()}
    return (classe, None, state)


def tuple_from_QPlainTextEdit(inst, classe):
    state = {"plainText": inst.toPlainText()}
    return (classe, None, state)


tuple_from_qt_classes = {
    "QByteArray": tuple_from_reducableQt,
    "QCheckBox": tuple_from_QCheckBox,
    "QColor": tuple_from_QColor,
    # "QChar": tuple_from_reducableQt,
    "QDate": tuple_from_reducableQt,
    "QDateTime": tuple_from_reducableQt,
    "QDoubleSpinBox": tuple_from_QSpinBox,
    "QKeySequence": tuple_from_reducableQt,
    # "QLatin1Char": tuple_from_reducableQt,
    # "QLatin1String": tuple_from_reducableQt,
    "QLine": tuple_from_reducableQt,
    "QLineEdit": tuple_from_QLineEdit,
    "QLineF": tuple_from_reducableQt,
    "QPlainTextEdit": tuple_from_QPlainTextEdit,
    "QPen": tuple_from_QPen,
    "QBrush": tuple_from_QBrush,
    "QPoint": tuple_from_reducableQt,
    "QPointF": tuple_from_reducableQt,
    "QPolygon": tuple_from_QPolygon,
    "QPolygonF": tuple_from_QPolygon,
    "QPushButton": tuple_from_QCheckBox,
    "QRect": tuple_from_reducableQt,
    "QRectF": tuple_from_reducableQt,
    "QSize": tuple_from_reducableQt,
    "QSizeF": tuple_from_reducableQt,
    "QSpinBox": tuple_from_QSpinBox,
    # "QMatrix": tuple_from_reducableQt,
    # "QString": tuple_from_reducableQt,
    "QTime": tuple_from_reducableQt,
    "QTransform": tuple_from_reducableQt,  # pas reducable dans documentation ?
    "QVector3D": tuple_from_reducableQt,  # pas reducable dans documentation ?
}
