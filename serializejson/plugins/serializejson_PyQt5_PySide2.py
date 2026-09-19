try:
    import qtpy

    API = qtpy.API_NAME
    from qtpy import QtGui, QtWidgets, QtCore

    if not hasattr(QtCore, "SignalInstance"):
        QtCore.SignalInstance = QtCore.pyqtBoundSignal  # qtpy < ?


except ImportError:
    try:
        from PyQt5 import QtGui, QtWidgets, QtCore

        QtCore.Signal = QtCore.pyqtSignal
        QtCore.SignalInstance = QtCore.pyqtBoundSignal
        QtCore.Slot = QtCore.pyqtSlot
        QtCore.Property = QtCore.pyqtProperty
        API = "PyQt5"

        # from PyQt5.QtCore import QT_VERSION_STR as __version__
    except ImportError:
        try:
            from PySide2 import QtGui, QtWidgets, QtCore

            API = "PySide2"
        except ImportError:
            API = None
if API:
    import enum
    import sys

    sys.modules["QtCore"] = QtCore
    sys.modules["QtGui"] = QtGui
    sys.modules["QtWidgets"] = QtWidgets

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
        class_str_from_class,
        encoder_parameters,
        rehydrate_getters,
        serialize_parameters,
    )

    property_types.add(QtCore.Property)

    # ARBRE QT (mot-cle d'encodeur qt_tree=True) ---------------------------------
    #
    # Par defaut un QObject n'ecrit que ses attributs python : un enfant Qt
    # anonyme (QPushButton("ok", self)) ou une fenetre non tenue par un
    # attribut n'est pas dans le document. Avec qt_tree=True, l'arbre Qt cree
    # par python est ecrit sous des cles virtuelles, dans l'ordre des
    # dependances : "~windows" (fenetres de premier niveau, application) et
    # "~children" (enfants QWidget) EN TETE de l'etat, pour que tout ce qui
    # les reference ensuite (attributs, layouts, connexions) ne soit qu'un
    # $ref ; "~layout" (layout anonyme du widget) apres les attributs ;
    # "~connections" en dernier. Ces cles ne sont jamais posees sur l'objet
    # (setstate les saute) : leurs valeurs ont agi en se construisant. En
    # mode rehydrate, les lecteurs rehydrate_getters retrouvent l'homologue
    # vivant d'une cle virtuelle ; un enfant anonyme est identifie par son
    # RANG parmi les enfants crees par python (comme un element de liste).
    # QTimer et QAction ecrivent leur etat Qt (voir qt_state). Non couverts :
    # autres QObject non-widgets (etat Qt non ecrit), arbres uic,
    # sort_keys=True (casserait l'ordre des cles).
    encoder_parameters["qt_tree"] = False

    if API == "PySide6":
        from shiboken6 import Shiboken

        created_by_python = Shiboken.createdByPython
    elif API == "PySide2":
        import shiboken2

        created_by_python = shiboken2.createdByPython
    else:
        # PyQt : pas d'introspection ; les objets internes de Qt sont nommes
        # "qt_..." (qt_spinbox_lineedit, qt_scrollarea_viewport...)
        def created_by_python(obj):
            return not obj.objectName().startswith("qt_")

    def qt_children(widget):
        # enfants QWidget crees par python, dans l'ordre de creation
        return [
            child
            for child in widget.children()
            if isinstance(child, QtWidgets.QWidget) and created_by_python(child)
        ]

    def qt_layout(widget):
        layout = widget.layout()
        if layout is not None and created_by_python(layout):
            return layout
        return None

    def qt_windows(app):
        # fenetres de premier niveau creees par python ; topLevelWidgets est
        # un ensemble, l'ordre est rendu stable par (classe, nom, titre)
        windows = [
            widget
            for widget in QtWidgets.QApplication.topLevelWidgets()
            if widget.parent() is None
            and created_by_python(widget)
            and widget.windowType()
            not in (QtCore.Qt.WindowType.Popup, QtCore.Qt.WindowType.ToolTip)
        ]
        windows.sort(key=lambda w: (type_str(w), w.objectName(), w.windowTitle()))
        return windows

    rehydrate_getters["~children"] = qt_children
    rehydrate_getters["~layout"] = qt_layout
    rehydrate_getters["~windows"] = qt_windows

    def init_parent(self):
        parent = self.parent()
        if parent is not None:
            return {"parent": parent}
        return ()

    if API.startswith("PyQt"):
        remove_types = None

        def serializejson_reducableQt(self):
            tuple_reduce = self.__reduce__()
            initargs = tuple_reduce[1][2]
            return type_str(self), initargs, None

    else:
        remove_types = [QtCore.SignalInstance]

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
            "qtpy.QtCore.Qt.AlignmentFlag",
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
            "QtGui.QGuiApplication",
            "QtCore.QCoreApplication",
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
            "QtCore.QTimer",
            "const",
            "QtGui.QAction",
            "QtWidgets.QAction",
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

    def QOBject_gestate(self):
        return getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=["parent"],
            filter_=True,
            properties=False,
            getters=False,
            sort_keys=True,
            remove_default_values=False,
            remove_types=remove_types,
        )

    QtCore.QObject.__getstate__ = QOBject_gestate

    def serializejson_QOBject(self):
        return (type_str(self), init_parent(self), state_with_connections(self))

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
                properties=False,
                getters=False,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    QtWidgets.QCommonStyle.__serializejson__ = serializejson_no_parent
    QtCore.QLocale.__serializejson__ = serializejson_no_parent
    QtGui.QRegion.__serializejson__ = serializejson_no_parent
    QtWidgets.QSizePolicy.__serializejson__ = serializejson_no_parent
    QtCore.Qt.AlignmentFlag.__serializejson__ = serializejson_no_parent

    if API != "PyQt6":
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
                properties=False,
                getters=False,
                sort_keys=True,
                remove_default_values=False,
            ),
        )

    def serializejson_QLayout(self):
        # "widgets" : les elements dans l'ordre, widget ou sous-layout ; en
        # grille [element, row, col, rowSpan, colSpan(, alignment)]
        grid = isinstance(self, QtWidgets.QGridLayout)
        widgets = []
        for i in range(self.count()):
            item = self.itemAt(i)
            element = item.widget()
            if element is None:
                element = item.layout()
                if element is None:  # espaceur
                    continue
            if grid:
                element = [element, *self.getItemPosition(i)]
                alignment = int(item.alignment())
                if alignment:
                    element.append(alignment)
            widgets.append(element)
        state = getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=["parent"],
            filter_=True,
            properties=False,
            getters=False,
            sort_keys=True,
            remove_default_values=False,
            remove_types=remove_types,
        )
        state["widgets"] = widgets
        parent = self.parent()
        if isinstance(parent, QtWidgets.QWidget):
            init = {"parent": parent}
        else:
            init = ()  # sous-layout : c'est addLayout qui le parente
        return type_str(self), init, state

    def QLayout_setWidgets(self, widgets):
        for element in widgets:
            position = []
            if isinstance(element, list):
                element, *position = element
                if len(position) == 5:
                    position[4] = QtCore.Qt.AlignmentFlag(position[4])
            if isinstance(element, QtWidgets.QLayout):
                if element.parent() is not self:  # rehydratation : deja en place
                    self.addLayout(element, *position)
            elif self.indexOf(element) == -1:
                self.addWidget(element, *position)

    QtWidgets.QLayout.setWidgets = QLayout_setWidgets
    QtWidgets.QLayout.__serializejson__ = serializejson_QLayout

    def serializejson_QCoreApplication(self):
        remove = ["parent", "eventDispatcher"]
        if self.overrideCursor() is None:
            remove.append("overrideCursor")
        state = getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=remove,
            filter_=True,
            properties=False,
            getters=False,
            sort_keys=True,
            remove_default_values=False,
            remove_types=remove_types,
        )
        if serialize_parameters.qt_tree:
            windows = qt_windows(self)
            if windows:
                state = {"~windows": windows, **state}
            connections_ = connections(self)
            if connections_:
                state["~connections"] = connections_
        return type_str(self), (sys.argv,), state

    def QCoreApplication_setstate(self, state):
        # une fenetre recreee sans parent n'a d'autre reference python que
        # celle-ci : sans elle, Python (proprietaire) la detruirait aussitot
        if "~windows" in state:
            self._serializejson_windows = state["~windows"]
        setstate(self, state, setters=True, properties=True)

    QtCore.QCoreApplication.__serializejson__ = serializejson_QCoreApplication
    QtCore.QCoreApplication.__setstate__ = QCoreApplication_setstate

    def application(argv=None, *args):
        # rend l'application existante (un singleton ne se recree pas) ;
        # l'argv du json est celui de la machine qui a ecrit, ignore
        return QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    for class_str in (
        "QtWidgets.QApplication",
        "QtGui.QGuiApplication",
        "QtCore.QCoreApplication",
    ):
        constructors[class_str] = application

    def load_application(file, obj=None, **kwargs):
        """Recree l'application decrite par un json ecrit avec qt_tree=True
        (fenetres, enfants anonymes, layouts, connexions), ou la rehydrate
        si obj est l'application vivante (defaut : celle qui existe).
        Rend l'application ; app.exec() reste a l'appelant."""
        import serializejson

        if obj is None:
            obj = QtWidgets.QApplication.instance()
        return serializejson.load(file, obj=obj, **kwargs)

    def serializejson_QMargins(self):
        return type_str(self), (self.left(), self.top(), self.right(), self.bottom())

    QtCore.QMargins.__serializejson__ = serializejson_QMargins

    def serializejson_InputMethodHints(self):
        return type_str(self), (int(self),)

    if API != "PyQt6":
        QtCore.Qt.InputMethodHints.__serializejson__ = serializejson_InputMethodHints

    # ---  QT GUI ------------------------------------------------------------

    QtGui.QPalette.__serializejson__ = serializejson_no_parent
    QtGui.QIcon.__serializejson__ = serializejson_no_parent

    def serializejson_QPen(self):
        # ne sauvegarde pas le brush si n'apporte rien de plus que la couleure
        brush = self.brush()
        if (
            brush.style() == 1
            and not brush.texture().size().width()
            and brush.transform() == QtGui.QTransform()
        ):
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
            remove_default_values=True,
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
                properties=False,
                getters=False,
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
        if not availableSizes:
            return True
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
                properties=False,
                getters=False,
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
                properties=False,
                getters=False,
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
        return (
            f"QtGui.QBitmap.fromData",
            (data,),
        )  # rien à partir de la fonction fromData ne permet de savoir qu'elle est une methode de QImage , ni à quel module ell

    QtGui.QBitmap.__serializejson__ = serializejson_QBitmap
    setters[QtGui.QBitmap] = {"data": "loadFromData"}

    def serializejson_QImage(self):
        # importé ici : il exige qtpy et numpy, que le reste du greffon n'exige pas
        from serializejson._smartframework.image.image_conversion import QImage_to_bytes_width_height_format

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

    if API.startswith("PyQt"):
        QtGui.QColor.__serializejson__ = serializejson_reducableQt
    else:  # pour PySide

        def serializejson_QColor(self):
            return (
                type_str(self),
                (self.red(), self.green(), self.blue(), self.alpha()),
                None,
            )

        QtGui.QColor.__serializejson__ = serializejson_QColor

    # def serializejson_QWidget(self):
    #    return type_str(self), {"parent": self.parent()}, getstate(self,split_dict_slots = False, keep=None, add= None, remove = ["parent","minimumSize"], filter_= True, properties=True, getters=True, sort_keys = True, remove_default_values = False)
    # QtWidgets.QWidget.__serializejson__ = serializejson_QWidget

    last_classes = (QtWidgets.QLayout,)

    def QWidget_getstate(self):
        remove = ["parent", "cursor"]
        if self.layout() is None:
            remove.append("layout")
        state = getstate(
            self,
            split_dict_slots=False,
            keep=None,
            add=None,
            remove=remove,
            filter_=True,
            properties=False,
            getters=False,
            sort_keys=True,
            remove_default_values=False,
            last_classes=last_classes,
            remove_types=remove_types,
        )
        if serialize_parameters.qt_tree:
            state = qt_tree_state(self, state)
        return state

    def qt_tree_state(self, state):
        # les proprietes Qt minimales pour qu'un widget anonyme recree ne
        # soit pas vide ; setters=True du decodeur les pose (setText...)
        if self.isWindow():
            state["windowTitle"] = self.windowTitle()
            state["geometry"] = self.geometry()
        if isinstance(self, (QtWidgets.QLabel, QtWidgets.QAbstractButton)):
            state["text"] = self.text()
            if isinstance(self, QtWidgets.QAbstractButton) and self.isCheckable():
                state["checked"] = self.isChecked()
        if isinstance(self, QtWidgets.QMainWindow) and self.centralWidget() is not None:
            state["centralWidget"] = self.centralWidget()
        children = qt_children(self)
        if children:
            state = {"~children": children, **state}
        layout = qt_layout(self)
        if layout is not None:
            state["~layout"] = layout
        return state

    QtWidgets.QWidget.__getstate__ = QWidget_getstate

    def serializejson_QWidget(self):
        return (type_str(self), init_parent(self), state_with_connections(self))

    QtWidgets.QWidget.__serializejson__ = serializejson_QWidget

    def QSpinBox_getstate(self):
        return {"value": self.value()}

    QtWidgets.QDoubleSpinBox.__getstate__ = QSpinBox_getstate
    QtWidgets.QSpinBox.__getstate__ = QSpinBox_getstate

    def serializejson_QSpinBox(self):
        return type_str(self), init_parent(self), self.__getstate__()

    QtWidgets.QSpinBox.__serializejson__ = serializejson_QSpinBox
    QtWidgets.QDoubleSpinBox.__serializejson__ = serializejson_QSpinBox
    # get_properties(QtWidgets.QSpinBox) {'value' : 'setValue'}
    setters[QtWidgets.QSpinBox] = True
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
                properties=False,
                getters=False,
                sort_keys=True,
                remove_default_values=False,
                remove_types=remove_types,
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
        return type_str(self), init_parent(self), {"text": self.text()}

    QtWidgets.QLineEdit.__serializejson__ = serializejson_QLineEdit
    setters[QtWidgets.QLineEdit] = {"text": "setText"}

    def serializejson_QPlainTextEdit(self):
        return type_str(self), init_parent(self), {"plainText": self.toPlainText()}

    QtWidgets.QPlainTextEdit.__serializejson__ = serializejson_QPlainTextEdit
    setters[QtWidgets.QPlainTextEdit] = {"plainText": "setPlainText"}

    # QObject non-widgets : leur etat Qt (lu par getter) rejoint les
    # attributs python ; __setstate__ le repose par les setters, dans
    # l'ordre du tableau ("active" en dernier : start() apres reglage).
    # Adopte en rehydrate, l'objet vivant recoit l'etat sans etre recree.
    QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
    qt_state = {
        QtCore.QTimer: {
            "interval": ("interval", "setInterval"),
            "singleShot": ("isSingleShot", "setSingleShot"),
            "timerType": ("timerType", "setTimerType"),
            "active": ("isActive", lambda self, v: self.start() if v else self.stop()),
        },
        QAction: {
            "text": ("text", "setText"),
            "shortcut": (lambda self: self.shortcut().toString(), "setShortcut"),
            "checkable": ("isCheckable", "setCheckable"),
            "checked": ("isChecked", "setChecked"),
            "enabled": ("isEnabled", "setEnabled"),
            "visible": ("isVisible", "setVisible"),
        },
    }

    def qt_state_table(self):
        return next(t for c, t in qt_state.items() if isinstance(self, c))

    def qt_state_getstate(self):
        state = QOBject_gestate(self)
        for key, (getter, _) in qt_state_table(self).items():
            state[key] = getter(self) if callable(getter) else getattr(self, getter)()
        return state

    def qt_state_setstate(self, state):
        for key, (_, setter) in qt_state_table(self).items():
            if key in state:
                value = state.pop(key)
                if callable(setter):
                    setter(self, value)
                else:
                    getattr(self, setter)(value)
        setstate(self, state)

    for cls in qt_state:
        cls.__getstate__ = qt_state_getstate
        cls.__setstate__ = qt_state_setstate

    # vire le prefixe PyQt5. et PySide2.
    def type_str(self):
        s = class_str_from_class(type(self))
        if s.startswith(API):
            return s[len(API) + 1 :]
        return s

    # ENUMS -----------------

    def serializejson_Enum(self):
        return "const", (qt_const_name[(type(self), self)],)

    qt_const_name = dict()
    qt_const_type = type(QtCore.Qt.CheckState)

    def register_consts(prefix, namespace):
        for key, value in namespace.__dict__.items():
            type_value = type(value)
            if type_value is qt_const_type:
                value.__serializejson__ = serializejson_Enum
                # enums python (PySide6) : les membres ne sont PAS dans le
                # dict du parent, seulement dans leur classe d'enum
                if isinstance(value, type) and issubclass(value, enum.Enum):
                    for member in value:
                        str_ = f"{prefix}.{key}.{member.name}"
                        qt_const_name.setdefault((value, member), str_)
                        consts[str_] = member
            if type(type_value) is qt_const_type:
                try:
                    str_ = f"{prefix}.{key}"
                    qt_const_name[(type(value), value)] = str_
                    consts[str_] = value
                except TypeError:
                    pass

    register_consts("QtCore.Qt", QtCore.Qt)
    for module, module_name in (
        (QtCore, "QtCore"), (QtGui, "QtGui"), (QtWidgets, "QtWidgets")
    ):
        for class_name, class_ in module.__dict__.items():
            if hasattr(class_, "__dict__") and class_name != "Qt":
                register_consts(f"{module_name}.{class_name}", class_)
    constructors["const"] = const

    # SERIALISATION DES CONNEXIONS ------------------------------------------------
    #
    # Sous PySide6, une methode python connectee a un signal est enregistree
    # comme slot dynamique du meta-objet : QObject.dumpObjectInfo() la liste
    # (« --> Classe::objectName slot(signature) »), sans surcharger connect.
    # Lambdas et fonctions libres y figurent en « <functor or function
    # pointer> » : non retrouvables, donc non serialisees. Sous PyQt, toute
    # connexion python passe par un PyQtSlotProxy opaque : aucune
    # introspection possible sans surcharger connect (ancien hack new_connect,
    # retire — voir l'historique git).
    #
    # Une connexion est stockee sous la cle "~connections" (triee en dernier)
    # de l'objet qui est le plus proche ancetre Qt commun de l'emetteur et du
    # recepteur : les deux sont alors deja serialises quand la reference est
    # ecrite, et chaque connexion ne l'est qu'une fois.

    class Connection:
        def __init__(
            self, signal_object, signal_name, signature, slot_object, slot_name
        ):
            self.signal_object = signal_object
            self.signal_name = signal_name
            self.signature = signature
            self.slot_object = slot_object
            self.slot_name = slot_name

        def __serializejson__(self):
            signal = "." + self.signal_name
            if self.signature:  # signal surcharge : PySide accepte sa signature C++ en index
                signal += "['" + self.signature + "']"
            return (
                "Connection",
                None,
                {
                    "signal": Reference(self.signal_object, signal),
                    "slot": Reference(self.slot_object, "." + self.slot_name),
                },
            )

        def __setstate__(self, state):
            self.signal = state["signal"]
            self.slot = state["slot"]
            # UniqueConnection : une connexion deja refaite par le __init__ de
            # l'objet recharge n'est pas doublee
            self.signal.connect(self.slot, QtCore.Qt.ConnectionType.UniqueConnection)

    constructors["Connection"] = Connection

    if API == "PySide6":
        import re

        _RE_SIGNAL = re.compile(r"^\s*signal: (\w+)\((.*)\)$")
        _RE_RECEIVER = re.compile(r"^\s*--> \S+::~sj(\d+) (\w+)\(.*\)$")

        def connections(root):
            """Connexions de l'arbre de root dont root est le plus proche
            ancetre commun de l'emetteur et du recepteur."""
            objects = [root] + root.findChildren(QtCore.QObject)
            if isinstance(root, QtCore.QCoreApplication):
                # les fenetres ne sont pas des enfants de l'application ;
                # sans qt_tree elles ne sont pas dans le document
                if not getattr(serialize_parameters, "qt_tree", False):
                    return []
                for window in qt_windows(root):
                    objects.append(window)
                    objects.extend(window.findChildren(QtCore.QObject))
            qt_tree = getattr(serialize_parameters, "qt_tree", False)

            def in_document(obj):
                # un objet ne peut etre reference que s'il est ecrit : tenu
                # par un attribut python de son parent (directement ou dans
                # une liste, un tuple, un dict), ou, avec qt_tree, widget ou
                # layout de l'arbre ; les enfants internes a Qt
                # (qt_spinbox_lineedit...) n'y sont jamais
                if obj is root:
                    return True
                if not created_by_python(obj):
                    return False
                parent = obj.parent()
                if parent is None:
                    return True  # fenetre listee par qt_windows
                if not (qt_tree and isinstance(obj, (QtWidgets.QWidget, QtWidgets.QLayout))):
                    # memes regles que QOBject_gestate/QWidget_getstate :
                    # un attribut `_xxx` ou d'un type de remove_types n'est
                    # jamais ecrit (un `_sync` de ControlUI, par exemple)
                    for key, value in getattr(parent, "__dict__", {}).items():
                        if key.startswith("_") or (
                            remove_types and type(value) in remove_types
                        ):
                            continue
                        if isinstance(value, dict):
                            value = value.values()
                        elif not isinstance(value, (list, tuple)):
                            value = (value,)
                        if any(element is obj for element in value):
                            break
                    else:
                        return False
                return in_document(parent)

            visible = [in_document(o) for o in objects]
            # dumpObjectInfo designe le recepteur par (classe, objectName) :
            # ambigu des que deux enfants sont anonymes -> noms temporaires
            # uniques, portant l'index dans objects (emet objectNameChanged)
            names = [o.objectName() for o in objects]
            lines = []
            previous = QtCore.qInstallMessageHandler(
                lambda mode, context, message: lines.append(message)
            )
            try:
                for i, o in enumerate(objects):
                    o.setObjectName("~sj%d" % i)
                for i, o in enumerate(objects):
                    if visible[i]:
                        lines.append(i)
                        o.dumpObjectInfo()
            finally:
                QtCore.qInstallMessageHandler(previous)
                for o, name in zip(objects, names):
                    o.setObjectName(name)

            def branch(obj):
                # enfant direct de root (fenetre, pour une application) sous
                # lequel obj se trouve ; None = root lui-meme
                while obj is not root:
                    parent = obj.parent()
                    if parent is root or parent is None:
                        break
                    obj = parent
                return None if obj is root else obj

            # seule la section SIGNALS OUT porte des lignes « signal: » et
            # « --> » ; SIGNALS IN ecrit « <-- », que les motifs ignorent
            result = []
            for line in lines:
                if isinstance(line, int):
                    emitter = objects[line]
                    emitter_branch = branch(emitter)
                    continue
                match = _RE_SIGNAL.match(line)
                if match:
                    signal_name, signature = match.groups()
                    continue
                match = _RE_RECEIVER.match(line)
                if match is None or signal_name == "destroyed":
                    continue
                if match.group(2).startswith("_q_"):
                    continue  # slot prive de Qt (QGuiApplication : ecrans)
                if not visible[int(match.group(1))]:
                    continue
                receiver = objects[int(match.group(1))]
                # emetteur et recepteur sous le meme enfant direct de root :
                # c'est cet enfant qui la stocke, pas root
                if emitter_branch is None or emitter_branch is not branch(receiver):
                    result.append(
                        Connection(
                            emitter, signal_name, signature, receiver, match.group(2)
                        )
                    )
            return result

    else:

        def connections(root):
            return []

    def state_with_connections(self):
        state = self.__getstate__()
        connections_ = connections(self)
        if connections_:
            state["~connections"] = connections_
        return state

    # -----------------------------------------------------------------------------
