from qtpy import QtCore, QtGui, QtWidgets
objects = {
    "QtWidgets": {
        "QWidget": QtWidgets.QWidget(),
        #'QCheckBox': QtWidgets.QCheckBox(),
        #'QDoubleSpinBox': QtWidgets.QDoubleSpinBox(),
        #'QLineEdit': QtWidgets.QLineEdit(),
        #'QPlainTextEdit': QtWidgets.QPlainTextEdit(),
        # "QSpinBox": QtWidgets.QSpinBox(),
        "QPushButton": QtWidgets.QPushButton(),
    },
    "PyQt_pickable" : {
        "QByteArray": QtCore.QByteArray(),
        "QColor": QtGui.QColor(),
        ## "QChar": tuple_from_reducableQt,
        "QDate": QtCore.QDate(),
        "QDateTime": QtCore.QDateTime(),
        "QKeySequence": QtGui.QKeySequence(),
        ## "QLatin1Char": tuple_from_reducableQt,
        ## "QLatin1String": tuple_from_reducableQt,
        "QLine": QtCore.QLine(),
        "QLineF": QtCore.QLineF(),
        ##'QPen': tuple_from_QPen,
        ##'QBrush': tuple_from_QBrush,
        "QPoint": QtCore.QPoint(),
        "QPointF": QtCore.QPointF(),
        "QPolygon": QtGui.QPolygon(),
        # "QPolygonF": QtGui.QPolygonF(),
        "QRect": QtCore.QRect(),
        "QRectF": QtCore.QRectF(),
        "QSize": QtCore.QSize(),
        "QSizeF": QtCore.QSizeF(),
        ## "QMatrix": tuple_from_reducableQt,
        ## "QString": tuple_from_reducableQt,
        "QTime": QtCore.QTime(),
        "QTransform": QtGui.QTransform(),  # pas reducable dans documentation ?
        "QVector3D": QtGui.QVector3D(),  # pas reducable dans documentation ?
    }
}