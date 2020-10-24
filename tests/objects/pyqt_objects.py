from qtpy import QtCore, QtGui, QtWidgets
objects = {
    "QtWidgets": {
        "QWidget": QtWidgets.QWidget(),
        'QCheckBox': QtWidgets.QCheckBox(),
        'QDoubleSpinBox': QtWidgets.QDoubleSpinBox(),
        'QLineEdit': QtWidgets.QLineEdit(),
        'QPlainTextEdit': QtWidgets.QPlainTextEdit(),
        "QSpinBox": QtWidgets.QSpinBox(),
        "QPushButton": QtWidgets.QPushButton(),
    },
    "PyQt_pickable" : {
        "QByteArray": QtCore.QByteArray(),
        "QColor": QtGui.QColor(),
        ## "QChar": # n'a plus l'air d'exister dans PyQt5
        "QDate": QtCore.QDate(),
        "QDateTime": QtCore.QDateTime(),
        "QKeySequence": QtGui.QKeySequence(),
        ## "QLatin1Char": # n'a plus l'air d'exister dans PyQt5
        ## "QLatin1String"# n'a plus l'air d'exister dans PyQt5
        "QLine": QtCore.QLine(),
        "QLineF": QtCore.QLineF(),
        'QPen': QtGui.QPen(),
        'QBrush': QtGui.QBrush(),
        "QPoint": QtCore.QPoint(),
        "QPointF": QtCore.QPointF(),
        "QPolygon": QtGui.QPolygon(),
        "QPolygonF": QtGui.QPolygonF(),
        "QRect": QtCore.QRect(),
        "QRectF": QtCore.QRectF(),
        "QSize": QtCore.QSize(),
        "QSizeF": QtCore.QSizeF(),
        ## "QMatrix": # Support for the deprecated QMatrix class has been removed
        ## "QString": # n'a plus l'air d'exister dans PyQt5
        "QTime": QtCore.QTime(),
        "QTransform": QtGui.QTransform(),  # pas reducable dans documentation ?
        "QVector3D": QtGui.QVector3D(),  # pas reducable dans documentation ?
    }
}