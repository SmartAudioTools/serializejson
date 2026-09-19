"""Connexions Qt retrouvées par introspection (PySide6, sans surcharge de
connect) : listées par QObject.dumpObjectInfo, stockées sous "~connections"
chez le plus proche ancêtre commun, rejouées au rechargement.

Le greffon se lie à UNE API Qt au premier import de serializejson (qtpy prend
PyQt5 par défaut) : le scénario tourne donc dans un sous-processus sous
QT_API=pyside6. Lancé avec --sans-lister, il neutralise l'introspection pour
prouver que les assertions dépendent bien d'elle (rouge attendu).
"""

import os
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lance(*args):
    env = dict(os.environ, QT_API="pyside6", QT_QPA_PLATFORM="offscreen")
    env["XDG_CONFIG_HOME"] = os.path.join(env.get("TMPDIR", "/tmp"), "qtcfg")
    return subprocess.run(
        [sys.executable, os.path.abspath(__file__), *args],
        cwd=RACINE, env=env, capture_output=True, text=True,
    )


@pytest.mark.skipif(
    subprocess.run([sys.executable, "-c", "import PySide6, qtpy"],
                   capture_output=True).returncode != 0,
    reason="PySide6 ou qtpy absent",
)
def test_connexions_pyside6():
    resultat = _lance()
    assert resultat.returncode == 0, resultat.stderr
    resultat = _lance("--sans-lister")
    assert resultat.returncode != 0, "le scénario doit échouer sans le lister"
    assert "AssertionError" in resultat.stderr


if __name__ == "__main__":
    sys.path.insert(0, RACINE)
    avec_lister = "--sans-lister" not in sys.argv
    import conftest  # noqa: F401 — rend rapidjson importable (voir conftest)

    import serializejson
    from serializejson.plugins import serializejson_PyQt5_PySide2 as greffon
    from qtpy import QtCore, QtWidgets

    assert greffon.API == "PySide6"
    if not avec_lister:
        greffon.connections = lambda root: []
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class Panel(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.plus = QtWidgets.QPushButton(self)  # deux boutons ANONYMES
            self.moins = QtWidgets.QPushButton(self)  # de même classe
            self.spin = QtWidgets.QSpinBox(self)

    class Fenetre(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.spin = QtWidgets.QSpinBox(self)
            self.label = QtWidgets.QLabel(self)
            self.panel = Panel(self)
            self.valeurs = []
            self.menus = 0
            # connexion faite dans __init__ : refaite par le __init__ du
            # rechargement ET rejouée par "~connections" -> une seule fois
            self.customContextMenuRequested.connect(self.on_menu)

        def on_value(self, valeur):
            self.valeurs.append(valeur)

        def on_menu(self, point):
            self.menus += 1

    f = Fenetre()
    f.spin.valueChanged.connect(f.on_value)  # enfant -> méthode de la racine
    f.spin.valueChanged.connect(f.label.setNum)  # enfant -> enfant
    f.panel.spin.valueChanged.connect(f.spin.setValue)  # petit-enfant -> enfant
    f.panel.plus.pressed.connect(f.panel.spin.stepUp)  # internes au panel :
    f.panel.moins.pressed.connect(f.panel.spin.stepDown)  # récepteurs anonymes
    f.spin.valueChanged.connect(lambda v: None)  # lambda : non retrouvable
    noms_avant = [o.objectName() for o in [f] + f.findChildren(QtCore.QObject)]

    json = serializejson.dumps(f)
    assert noms_avant == [
        o.objectName() for o in [f] + f.findChildren(QtCore.QObject)
    ], "les noms temporaires du lister doivent être restaurés"
    # chaque connexion une fois, chez le plus proche ancêtre commun
    assert json.count('"__class__": "Connection"') == 6
    assert '"signal": {"$ref": "root.spin.valueChanged[\'int\']"}' in json
    assert '"slot": {"$ref": "root.on_value"}' in json
    assert '"slot": {"$ref": "root.panel.spin.stepDown"}' in json
    assert "lambda" not in json
    # l'enfant interne à Qt du QSpinBox (qt_spinbox_lineedit) n'y est pas
    assert "qt_spinbox" not in json

    f2 = serializejson.loads(json, authorized_classes=[Fenetre, Panel])
    f2.panel.plus.pressed.emit()  # panel.spin 0 -> 1 -> f2.spin -> on_value, label
    f2.panel.plus.pressed.emit()
    f2.panel.moins.pressed.emit()
    assert [f2.panel.spin.value(), f2.spin.value()] == [1, 1]
    assert f2.valeurs == [1, 2, 1]
    assert f2.label.text() == "1"
    f2.customContextMenuRequested.emit(QtCore.QPoint())
    assert f2.menus == 1, "UniqueConnection : la connexion du __init__ n'est pas doublée"
