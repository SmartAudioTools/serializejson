from qtpy import QtCore, QtGui, QtWidgets
from PyQt5 import sip

sip._unpickle_type.__module__ = "PyQt5.sip"
authorized_classes = ["sip._unpickle_type"]
objects = {
    "QtWidgets": {
        "QWidget": QtWidgets.QWidget(),
        "QCheckBox": QtWidgets.QCheckBox(checked=True),
        "QDoubleSpinBox": QtWidgets.QDoubleSpinBox(value=10.0),
        "QLineEdit": QtWidgets.QLineEdit("coucou"),
        "QPlainTextEdit": QtWidgets.QPlainTextEdit("coucou"),
        "QSpinBox": QtWidgets.QSpinBox(value=20),
        "QPushButton": QtWidgets.QPushButton(),
    },
    "PyQt_pickable": {
        "QByteArray": QtCore.QByteArray(bytes(range(256))),
        "QColor": QtGui.QColor(10, 20, 30, 40),
        # "QChar": # n'a plus l'air d'exister dans PyQt5
        "QDate": QtCore.QDate(2020, 10, 31),
        "QDateTime": QtCore.QDateTime(2020, 10, 31, 20, 30),
        "QKeySequence": QtGui.QKeySequence(),
        # "QLatin1Char": # n'a plus l'air d'exister dans PyQt5
        # "QLatin1String"# n'a plus l'air d'exister dans PyQt5
        "QLine": QtCore.QLine(QtCore.QPoint(0, 1), QtCore.QPoint(2, 3)),
        "QLineF": QtCore.QLineF(QtCore.QPointF(0.0, 1.1), QtCore.QPointF(2.2, 3.3)),
        "QPen": QtGui.QPen(),
        "QBrush": QtGui.QBrush(),
        "QPoint": QtCore.QPoint(0, 1),
        "QPointF": QtCore.QPointF(0.0, 1.1),
        "QPolygon": QtGui.QPolygon([QtCore.QPoint(0, 1), QtCore.QPoint(2, 3)]),
        "QPolygonF": QtGui.QPolygonF(
            [QtCore.QPointF(0.0, 1.1), QtCore.QPointF(2.2, 3.3)]
        ),
        "QRect": QtCore.QRect(0, 1, 2, 3),
        "QRectF": QtCore.QRectF(0.0, 1.1, 2.2, 3.3),
        "QSize": QtCore.QSize(10, 20),
        "QSizeF": QtCore.QSizeF(10.5, 20.5),
        # "QMatrix": # Support for the deprecated QMatrix class has been removed
        # "QString": # n'a plus l'air d'exister dans PyQt5
        "QTime": QtCore.QTime(20, 30),
        "QTransform": QtGui.QTransform(),  # pas reducable dans documentation ?
        "QVector3D": QtGui.QVector3D(),  # pas reducable dans documentation ?
    },
}
