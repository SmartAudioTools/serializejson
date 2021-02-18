try:
    import qtpy

    API = qtpy.API_NAME
    from qtpy import QtGui, QtWidgets, QtCore
except ModuleNotFoundError:
    try:
        from PyQt5 import QtGui, QtWidgets, QtCore
    except ModuleNotFoundError:
        try:
            from PySide2 import QtGui, QtWidgets, QtCore
        except ModuleNotFoundError:
            API = None
if API:
    import sys

    sys.modules["QtCore"] = QtCore
    sys.modules["QtGui"] = QtGui
    sys.modules["QtWidgets"] = QtWidgets

    try:
        from SmartFramework.serialize.tools import (
            setters,
            property_types,
            getstate,
            setstate,
            authorized_classes,
            Reference,
            constructors,
            const,
            consts,
        )
        from parse import parse
    except:
        from serializejson.tools import (
            setters,
            property_types,
            getstate,
            setstate,
            authorized_classes,
            Reference,
            constructors,
            const,
            consts,
        )
    from SmartFramework.image.image_conversion import QImage_to_bytes_width_height_format
    import ctypes

    import sys

    property_types.add(QtCore.Property)

    if API.startswith("PyQt"):

        def serializejson_reducableQt(self):
            tuple_reduce = self.__reduce__()
            initargs = tuple_reduce[1][2]
            return type_str(self), initargs, None

    else:

        def serializejson_reducableQt(self):
            tuple_reduce = self.__reduce__()
            initargs = tuple_reduce[1]  # truc normal
            return (type_str(self), initargs, None)

    authorized_classes.update(
        {
            "PyQt5.QtCore.QByteArray",
            "PyQt5.QtCore.QDate",
            "PyQt5.QtCore.QDateTime",
            "PyQt5.QtCore.QLine",
            "PyQt5.QtCore.QLineF",
            "PyQt5.QtCore.QMargins",
            "PyQt5.QtCore.QPoint",
            "PyQt5.QtCore.QPointF",
            "PyQt5.QtCore.QRect",
            "PyQt5.QtCore.QRectF",
            "PyQt5.QtCore.QSize",
            "PyQt5.QtCore.QSizeF",
            "PyQt5.QtCore.QTime",
            "PyQt5.QtCore.Qt.WindowFlags",
            "PyQt5.QtGui.QBitmap",
            "PyQt5.QtGui.QBrush",
            "PyQt5.QtGui.QColor",
            "PyQt5.QtGui.QImage",
            "PyQt5.QtGui.QIcon",
            "PyQt5.QtGui.QImage.fromData",
            "PyQt5.QtGui.QKeySequence",
            "PyQt5.QtGui.QPen",
            "PyQt5.QtGui.QPixmap",
            "PyQt5.QtGui.QPolygon",
            "PyQt5.QtGui.QPolygonF",
            "PyQt5.QtGui.QTransform",
            "PyQt5.QtGui.QVector3D",
            "PyQt5.QtWidgets.QApplication",
            "PyQt5.QtWidgets.QCheckBox",
            "PyQt5.QtWidgets.QDoubleSpinBox",
            "PyQt5.QtWidgets.QGridLayout",
            "PyQt5.QtWidgets.QLineEdit",
            "PyQt5.QtWidgets.QPlainTextEdit",
            "PyQt5.QtWidgets.QPushButton",
            "PyQt5.QtWidgets.QSpinBox",
            "PyQt5.QtWidgets.QWidget",
            "PyQt5.sip._unpickle_type",
            "PySide2.QtCore.QByteArray",
            "PySide2.QtCore.QDate",
            "PySide2.QtCore.QDateTime",
            "PySide2.QtCore.QLine",
            "PySide2.QtCore.QLineF",
            "PySide2.QtCore.QMargins",
            "PySide2.QtCore.QPoint",
            "PySide2.QtCore.QPointF",
            "PySide2.QtCore.QRect",
            "PySide2.QtCore.QRectF",
            "PySide2.QtCore.QSize",
            "PySide2.QtCore.QSizeF",
            "PySide2.QtCore.QTime",
            "PySide2.QtCore.Qt.WindowFlags",
            "PySide2.QtGui.QBitmap",
            "PySide2.QtGui.QBrush",
            "PySide2.QtGui.QColor",
            "PySide2.QtGui.QImage",
            "PySide2.QtGui.QIcon",
            "PySide2.QtGui.QImage.fromData",
            "PySide2.QtGui.QKeySequence",
            "PySide2.QtGui.QPen",
            "PySide2.QtGui.QPixmap",
            "PySide2.QtGui.QPolygon",
            "PySide2.QtGui.QPolygonF",
            "PySide2.QtGui.QTransform",
            "PySide2.QtGui.QVector3D",
            "PySide2.QtWidgets.QApplication",
            "PySide2.QtWidgets.QCheckBox",
            "PySide2.QtWidgets.QDoubleSpinBox",
            "PySide2.QtWidgets.QGridLayout",
            "PySide2.QtWidgets.QLineEdit",
            "PySide2.QtWidgets.QPlainTextEdit",
            "PySide2.QtWidgets.QPushButton",
            "PySide2.QtWidgets.QSpinBox",
            "PySide2.QtWidgets.QWidget",
            "qtpy.QtCore.QByteArray",
            "qtpy.QtCore.QDate",
            "qtpy.QtCore.QDateTime",
            "qtpy.QtCore.QLine",
            "qtpy.QtCore.QLineF",
            "qtpy.QtCore.QMargins",
            "qtpy.QtCore.QPoint",
            "qtpy.QtCore.QPointF",
            "qtpy.QtCore.QRect",
            "qtpy.QtCore.QRectF",
            "qtpy.QtCore.QSize",
            "qtpy.QtCore.QSizeF",
            "qtpy.QtCore.QTime",
            "qtpy.QtCore.Qt.WindowFlags",
            "qtpy.QtGui.QBitmap",
            "qtpy.QtGui.QBrush",
            "qtpy.QtGui.QColor",
            "qtpy.QtGui.QIcon",
            "qtpy.QtGui.QImage",
            "qtpy.QtGui.QImage.fromData",
            "qtpy.QtGui.QKeySequence",
            "qtpy.QtGui.QPen",
            "qtpy.QtGui.QPixmap",
            "qtpy.QtGui.QPixmap.fromImage",
            "qtpy.QtGui.QPolygon",
            "qtpy.QtGui.QPolygonF",
            "qtpy.QtGui.QTransform",
            "qtpy.QtGui.QVector3D",
            "qtpy.QtWidgets.QApplication",
            "qtpy.QtWidgets.QCheckBox",
            "qtpy.QtWidgets.QDoubleSpinBox",
            "qtpy.QtWidgets.QGridLayout",
            "qtpy.QtWidgets.QLineEdit",
            "qtpy.QtWidgets.QPlainTextEdit",
            "qtpy.QtWidgets.QPushButton",
            "qtpy.QtWidgets.QSpinBox",
            "qtpy.QtWidgets.QWidget",
            "Connection",
            "qtpy.QtGui.QFont",
            "qtpy.QtCore.QAbstractEventDispatcher",
            "qtpy.QtWidgets.QCommonStyle",
            "qtpy.QtGui.QPalette",
            "qtpy.QtGui.QCursor",
            "qtpy.QtCore.Qt.Alignment",
            "qtpy.QtGui.QRegion",
            "qtpy.QtWidgets.QSizePolicy",
            "qtpy.QtCore.Qt.WindowStates",
            "qtpy.QtCore.Qt.InputMethodHints",
            "qtpy.QtCore.QLocale",
            "qtpy.QtWidgets.QMainWindow.DockOptions",
            "qtpy.QtCore.Qt.TextInteractionFlags",
            "qtpy.QtWidgets.QLabel",
            "qtpy.QtCore.QLocale.NumberOptions",
            "qtpy.QtWidgets.QMainWindow",
            "QtCore.QByteArray",
            "QtCore.QDate",
            "QtCore.QDateTime",
            "QtCore.QLine",
            "QtCore.QLineF",
            "QtCore.QMargins",
            "QtCore.QPoint",
            "QtCore.QPointF",
            "QtCore.QRect",
            "QtCore.QRectF",
            "QtCore.QSize",
            "QtCore.QSizeF",
            "QtCore.QTime",
            "QtCore.Qt.WindowFlags",
            "QtGui.QBitmap",
            "QtGui.QBrush",
            "QtGui.QColor",
            "QtGui.QIcon",
            "QtGui.QImage",
            "QtGui.QImage.fromData",
            "QtGui.QKeySequence",
            "QtGui.QPen",
            "QtGui.QPixmap",
            "QtGui.QPixmap.fromImage",
            "QtGui.QPolygon",
            "QtGui.QPolygonF",
            "QtGui.QTransform",
            "QtGui.QVector3D",
            "QtWidgets.QApplication",
            "QtWidgets.QCheckBox",
            "QtWidgets.QDoubleSpinBox",
            "QtWidgets.QGridLayout",
            "QtWidgets.QLineEdit",
            "QtWidgets.QPlainTextEdit",
            "QtWidgets.QPushButton",
            "QtWidgets.QSpinBox",
            "QtWidgets.QWidget",
            "Connection",
            "QtGui.QFont",
            "QtCore.QAbstractEventDispatcher",
            "QtWidgets.QCommonStyle",
            "QtGui.QPalette",
            "QtGui.QCursor",
            "QtCore.Qt.Alignment",
            "QtGui.QRegion",
            "QtWidgets.QSizePolicy",
            "QtCore.Qt.WindowStates",
            "QtCore.Qt.InputMethodHints",
            "QtCore.QLocale",
            "QtWidgets.QMainWindow.DockOptions",
            "QtCore.Qt.TextInteractionFlags",
            "QtWidgets.QLabel",
            "QtCore.QLocale.NumberOptions",
            "QtWidgets.QMainWindow",
        }
    )

    # --- QT CORE  -------------------------------------------------------

    QtCore.QByteArray.__serializejson__ = serializejson_reducableQt
    QtCore.QDate.__serializejson__ = serializejson_reducableQt
    QtCore.QDateTime.__serializejson__ = serializejson_reducableQt
    QtCore.QLine.__serializejson__ = serializejson_reducableQt
    QtCore.QLineF.__serializejson__ = serializejson_reducableQt
    QtCore.QPoint.__serializejson__ = serializejson_reducableQt
    QtCore.QPointF.__serializejson__ = serializejson_reducableQt
    QtCore.QRect.__serializejson__ = serializejson_reducableQt
    QtCore.QRectF.__serializejson__ = serializejson_reducableQt
    QtCore.QSize.__serializejson__ = serializejson_reducableQt
    QtCore.QSizeF.__serializejson__ = serializejson_reducableQt
    QtCore.QTime.__serializejson__ = serializejson_reducableQt

    def serializejson_QOBject(self):
        parent = self.parent()
        if parent is not None:
            init = {"parent": parent}
        else:
            init = tuple()
        return (
            type_str(self),
            init,
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=["parent"],
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtCore.QObject.__serializejson__ = serializejson_QOBject

    def serializejson_no_parent(self):
        return (
            type_str(self),
            tuple(),
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=["parent"],
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtWidgets.QCommonStyle.__serializejson__ = serializejson_no_parent
    QtCore.QLocale.__serializejson__ = serializejson_no_parent
    QtGui.QRegion.__serializejson__ = serializejson_no_parent
    QtWidgets.QSizePolicy.__serializejson__ = serializejson_no_parent
    QtCore.Qt.WindowFlags.__serializejson__ = serializejson_no_parent
    QtCore.Qt.WindowStates.__serializejson__ = serializejson_no_parent
    QtCore.Qt.Alignment.__serializejson__ = serializejson_no_parent
    QtWidgets.QMainWindow.DockOptions.__serializejson__ = serializejson_no_parent
    QtCore.Qt.TextInteractionFlags.__serializejson__ = serializejson_no_parent
    QtCore.QLocale.NumberOptions.__serializejson__ = serializejson_no_parent

    def serializejson_positionnal_parent(self):
        return (
            type_str(self),
            (self.parent(),),
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=["parent"],
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    def serializejson_QLayout(self):
        widgets = []
        for i in range(self.count()):
            widgets.append(self.itemAt(i).widget())
        state = getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=["parent"],
            filter_=True,
            properties=True,
            getters=True,
            sort_keys=True,
            remove_default_values=False,
        )
        state["widgets"] = widgets
        return type_str(self), (self.parent(),), state

    def QLayout_setWidgets(self, widgets):
        for widget in widgets:
            self.addWidget(widget)

    QtWidgets.QLayout.setWidgets = QLayout_setWidgets
    QtWidgets.QLayout.__serializejson__ = serializejson_QLayout

    def serializejson_QGridLayout(self):
        widgets = []
        for i in range(self.count()):
            item = self.itemAt(i)
            widgets.append([item.widget()] + list(self.getItemPosition(i)) + [item.alignment()])
        state = getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=["parent"],
            filter_=True,
            properties=True,
            getters=True,
            sort_keys=True,
            remove_default_values=False,
        )
        state["widgets"] = widgets
        return type_str(self), (self.parent(),), state

    def QGridLayout_setWidgets(self, widgets):
        for widget in widgets:
            self.addWidget(widget)

    QtWidgets.QGridLayout.setWidgets = QGridLayout_setWidgets
    QtWidgets.QGridLayout.__serializejson__ = serializejson_QGridLayout

    def serializejson_QCoreApplication(self):
        remove = ["parent", "eventDispatcher"]
        if self.overrideCursor() is None:
            remove.append("overrideCursor")
        return (
            type_str(self),
            (sys.argv,),
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=remove,
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtCore.QCoreApplication.__serializejson__ = serializejson_QCoreApplication

    def serializejson_QMargins(self):
        return type_str(self), (self.left(), self.top(), self.right(), self.bottom())

    QtCore.QMargins.__serializejson__ = serializejson_QMargins

    def serializejson_InputMethodHints(self):
        return type_str(self), (int(self),)

    QtCore.Qt.InputMethodHints.__serializejson__ = serializejson_InputMethodHints
    # ---  QT GUI ------------------------------------------------------------

    QtGui.QPalette.__serializejson__ = serializejson_no_parent
    QtGui.QIcon.__serializejson__ = serializejson_no_parent

    def serializejson_QPen(self):
        # ne sauvegarde pas le brush si n'apporte rien de plus que la couleure
        brush = self.brush()
        if brush.style() == 1 and not brush.texture().size().width() and brush.transform() == QtGui.QTransform():
            remove = "brush"
        else:
            remove = None
        state = getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=remove,
            filter_=True,
            properties=True,
            getters=True,
            sort_keys=True,
            remove_default_values=False,
        )
        return type_str(self), tuple(), state

    QtGui.QPen.__serializejson__ = serializejson_QPen

    def serializejson_QBrush(self):
        return (
            type_str(self),
            tuple(),
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove="texture",
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtGui.QBrush.__serializejson__ = serializejson_QBrush

    # def serializejson_QIcon(self):
    #    return type(self), tuple(), getstate(self,split_dict_slots = False, keep=None, add= None, remove = None, filter_= True, properties=True, getters=True, sort_keys = True, remove_default_values = False)
    # QtGui.QIcon.__serializejson__ = serializejson_QIcon

    def QIcon__eq__(self, other):
        availableSizes = self.availableSizes()
        if availableSizes != other.availableSizes():
            return False
        elif not availableSizes:
            return True
        else:  # meme availableSizes
            return False  # il faudrait comparer plus en profondeur

    QtGui.QIcon.__eq__ = QIcon__eq__

    def serializejson_QFont(self):
        return (
            type_str(self),
            tuple(),
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=None,
                filter_=True,
                properties=True,
                getters=True,
                extra_getters={"letterSpacingType": "letterSpacingType"},
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtGui.QFont.__serializejson__ = serializejson_QFont

    def QFont_setstate(self, state):
        setstate(
            self,
            state,
            properties=True,
            setters=True,
            extra_setters={("letterSpacingType", "letterSpacing"): "setLetterSpacing"},
            restore_default_values=False,
        )

    QtGui.QFont.__setstate__ = QFont_setstate

    def serializejson_QCursor(self):
        return (
            type_str(self),
            tuple(),
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=None,
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtGui.QCursor.__serializejson__ = serializejson_QCursor

    def serializejson_QPixmap(self):
        ba = QtCore.QByteArray()
        buff = QtCore.QBuffer(ba)
        buff.open(QtCore.QIODevice.WriteOnly)
        ok = self.save(buff, "png")
        assert ok
        data = ba.data()  # fait une copie ?
        return type_str(self), tuple(), {"data": data}
        # return type_str(self), None, None #getstate(self,split_dict_slots = False, keep=None, add= None, remove=None, filter_= True, properties=True, getters=True, sort_keys = True, remove_default_values = False)

    QtGui.QPixmap.__serializejson__ = serializejson_QPixmap
    setters[QtGui.QPixmap] = {"data": "loadFromData"}

    def serializejson_QBitmap(self):
        ba = QtCore.QByteArray()
        buff = QtCore.QBuffer(ba)
        buff.open(QtCore.QIODevice.WriteOnly)
        ok = self.save(buff, "PBM")
        assert ok
        data = ba.data()  # fait une copie ?
        return f"QtGui.QBitmap.fromData", (
            data,
        )  # rien à partir de la fonction fromData ne permet de savoir qu'elle est une methode de QImage , ni à quel module ell

    QtGui.QBitmap.__serializejson__ = serializejson_QBitmap
    setters[QtGui.QBitmap] = {"data": "loadFromData"}

    def serializejson_QImage(self):
        return (
            type_str(self),
            QImage_to_bytes_width_height_format(self),
            None,
        )  # FASTER  and no destructive !!! no specific compression (will compress with bytes compression)

    QtGui.QImage.__serializejson__ = serializejson_QImage

    def serializejson_QPolygon(self):
        return type_str(self), ([point for point in self],), None

    QtGui.QPolygon.__serializejson__ = serializejson_QPolygon
    QtGui.QPolygonF.__serializejson__ = serializejson_QPolygon

    # --- QT WIDGETS  -------------------------------------------------------

    # avec etat dans state pour permetre update avec serializejson :

    QtGui.QKeySequence.__serializejson__ = serializejson_reducableQt
    QtGui.QTransform.__serializejson__ = serializejson_reducableQt
    QtGui.QVector3D.__serializejson__ = serializejson_reducableQt
    QtGui.QColor.__serializejson__ = serializejson_reducableQt

    # def serializejson_QWidget(self):
    #    return type_str(self), {"parent": self.parent()}, getstate(self,split_dict_slots = False, keep=None, add= None, remove = ["parent","minimumSize"], filter_= True, properties=True, getters=True, sort_keys = True, remove_default_values = False)
    # QtWidgets.QWidget.__serializejson__ = serializejson_QWidget

    def serializejson_QWidget(self):
        parent = self.parent()
        if parent is not None:
            init = {"parent": parent}
        else:
            init = tuple()
        remove = ["parent", "cursor"]
        if self.layout() is None:
            remove.append("layout")
        return (
            type_str(self),
            init,
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=remove,
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtWidgets.QWidget.__serializejson__ = serializejson_QWidget

    def serializejson_QSpinBox(self):
        state = {"value": self.value()}
        return type_str(self), tuple(), state

    QtWidgets.QSpinBox.__serializejson__ = serializejson_QSpinBox
    QtWidgets.QDoubleSpinBox.__serializejson__ = serializejson_QSpinBox
    setters[QtWidgets.QSpinBox] = True  # get_properties(QtWidgets.QSpinBox) {'value' : 'setValue'}
    setters[QtWidgets.QDoubleSpinBox] = True  # {'value' : 'setValue'}

    def serializejson_QCheckBox(self):
        return (
            type_str(self),
            {"parent": self.parent()},
            getstate(
                self,
                split_dict_slots=False,
                keep=None,
                add=None,
                remove=["parent", "cursor", "windowFlags"],
                filter_=True,
                properties=True,
                getters=True,
                sort_keys=True,
                remove_default_values=False,
            ),
        )  # ["checked"])

        # if self.isCheckable():
        #    state = {"checked": self.isChecked()}
        #    return type_str(self),tuple(), state
        # else:
        #    return type_str(self), tuple()

    # QtWidgets.QCheckBox.__serializejson__ = serializejson_QCheckBox
    # QtWidgets.QPushButton.__serializejson__ = serializejson_QCheckBox
    # setters[QtWidgets.QCheckBox]   = {'checked' : 'setChecked'}
    setters[QtWidgets.QPushButton] = True  # {'checked' : 'setChecked'}

    def serializejson_QLineEdit(self):
        state = {"text": self.text()}
        return type_str(self), tuple(), state

    QtWidgets.QLineEdit.__serializejson__ = serializejson_QLineEdit
    setters[QtWidgets.QLineEdit] = {"text": "setText"}

    def serializejson_QPlainTextEdit(self):
        state = {"plainText": self.toPlainText()}
        return type_str(self), tuple(), state

    QtWidgets.QPlainTextEdit.__serializejson__ = serializejson_QPlainTextEdit
    setters[QtWidgets.QPlainTextEdit] = {"plainText": "setPlainText"}

    # allow translation PyQt5 -> qtpy and PySide2 -> qtpy if qtpy avaible
    def type_str(self):
        return f"{str(self.__class__)[len(API)+9:-2]}"

    # ENUMS -----------------

    def serializejson_Enum(value):
        return "const", (qt_const_name[(type(value), value)],)

    qt_const_name = dict()
    qt_const_type = type(QtCore.Qt.CheckState)
    # for module,module_name in ((QtGui,'QtGui'),): #(QtCore.Qt,'QtCore.Qt')
    for key, value in QtCore.Qt.__dict__.items():
        type_value = type(value)
        if type_value is qt_const_type:
            pass
            value.__serializejson__ = serializejson_Enum
        if type(type_value) is qt_const_type:
            str_ = f"QtCore.Qt.{key}"
            qt_const_name[(type(value), value)] = str_
            consts[str_] = value

    for module, module_name in ((QtGui, "QtGui"), (QtWidgets, "QtWidgets")):
        for class_name, class_ in module.__dict__.items():
            if hasattr(class_, "__dict__"):
                for key, value in class_.__dict__.items():
                    type_value = type(value)
                    if type_value is qt_const_type:
                        pass
                        value.__serializejson__ = serializejson_Enum
                    if type(type_value) is qt_const_type:
                        try:
                            str_ = f"{module_name}.{class_name}.{key}"
                            qt_const_name[(type(value), value)] = str_
                            consts[str_] = value
                        except:
                            pass
                        else:
                            pass
                            # print('ok')
    constructors["const"] = const

    # SERIALISATION DES CONNECTIONS -----------------------------------------------

    # hack pour enregistrer les connections
    old_connect = QtCore.pyqtBoundSignal.connect

    def new_connect(signal, slot, save=None):
        value = old_connect(signal, slot)
        if save is True or (
            save is None and sys._getframe(1).f_code.co_name != "__init__"
        ):  # sauve la connection si elle a été crée en dehors d'un __init__
            signal_object, signal_name, slot_object, slot_name, signature = connection_infos(signal, slot)
            signal_parents = get_parents(signal_object)
            slot_parents = get_parents(slot_object)
            for commun_parent in signal_parents:
                if commun_parent in slot_parents:
                    break
            else:
                print("No Commun Qt Parent for ", signal_object, signal_parents, slot_object, slot_parents)
            if "~connections" not in commun_parent.__dict__:
                commun_parent.__dict__["~connections"] = []
            commun_parent.__dict__["~connections"].append(
                Connection(signal_object, signal_name, slot_object, slot_name, signature)
            )
        return value

    # QtCore.pyqtBoundSignal.connect = new_connect

    class Connection:
        def __init__(self, signal_object, signal, slot_object, slot, signature=None):
            # self.id = id
            self.signal_object = signal_object
            self.signal_name = signal
            self.slot_object = slot_object
            self.slot_name = slot
            self.signature = signature

        def __serializejson__(self):
            signal_name_sig = "." + self.signal_name
            if self.signature is not None:
                signal_name_sig += "[" + self.signature + "]"
            return (
                "Connection",
                None,
                {
                    "signal": Reference(self.signal_object, signal_name_sig),  # #Reference(signal),
                    "slot": Reference(
                        self.slot_object, "." + self.slot_name
                    ),  # Reference([self.slot_object,self.slot_name]),
                },
            )

        def __setstate__(self, state):
            # serialize_parameters.decoder.
            signal = state["signal"]
            slot = state["slot"]
            signal.connect(slot, save=False)
            self.signal_object, self.signal_name, self.slot_object, self.slot_name, self.signature = connection_infos(
                signal, slot
            )

    constructors["Connection"] = Connection
    signature_str_from_qt = {
        "": None,
        "bool": "bool",
        "int": "int",
        "double": "float",
        "QString": "str",
        "PyQt_PyObject": "object",
    }
    signature_from_srt = {"bool": bool, "int": int, "float": float, "str": str, "object": object}

    def connection_infos(signal, slot):
        signal_str = signal.__str__()
        signal_name, _, hex_id = parse("<bound PYQT_SIGNAL {} of {} object at {}>", signal_str).fixed
        signal_object = ctypes.cast(int(hex_id, 16), ctypes.py_object).value
        signal_str = signal.signal
        signature = signature_str_from_qt.get(signal_str[signal_str.rfind("(") + 1 : -1], "object")

        if isinstance(slot, QtCore.pyqtBoundSignal):
            slot_str = slot.__str__()
            slot_name, _, hex_id = parse("<bound PYQT_SIGNAL {} of {} object at {}>", slot_str).fixed
            slot_object = ctypes.cast(int(hex_id, 16), ctypes.py_object).value
        else:
            slot_object = slot.__self__
            slot_name = slot.__name__
        return (signal_object, signal_name, slot_object, slot_name, signature)

    def get_parents(obj):
        parents = [obj]
        parent = obj.parent()
        while parent is not None:
            parents.append(parent)
            parent = parent.parent()
        return parents

    # -----------------------------------------------------------------------------
