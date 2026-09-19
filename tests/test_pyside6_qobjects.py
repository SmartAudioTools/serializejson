"""QObject non-widgets (QTimer, QAction) et enfants sans état d'un objet
construit pendant le parse (PySide6, sous-processus : le greffon se lie à UNE
API Qt au premier import).

- recréation : l'état Qt des QTimer/QAction (intervalle, actif, texte,
  raccourci, coché) est rendu, et les enfants créés par le __init__ de la
  racine ne sont pas doublés — y compris un QWidget/QLabel écrit SANS état,
  adopté parce que son seul argument (le parent) est égal ;
- un enfant dont l'argument a changé sans être applicable par son nom
  (Echelle : argument transformé) est RECONSTRUIT, et l'ancien détaché de son
  parent (rehydrate_discarders) — pas de doublon ;
- un enfant adopté reste visible (setParent jamais rejoué à parent égal) ;
- réhydratation (obj=) : identités conservées, état appliqué.
Avec --rouge, la voie classique (rehydrate=False) doit doubler.
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
def test_qobjects_pyside6():
    resultat = _lance()
    assert resultat.returncode == 0, resultat.stderr
    resultat = _lance("--rouge")
    assert resultat.returncode != 0, "la voie classique doit doubler"
    assert "AssertionError" in resultat.stderr


if __name__ == "__main__":
    sys.path.insert(0, RACINE)
    import rapidjson.rapidjson as rj

    sys.modules["rapidjson"] = rj
    import serializejson
    from qtpy import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication([])

    class Echelle(QtWidgets.QWidget):
        def __init__(self, parent, n):
            super().__init__(parent)
            self._double = 2 * n

        def __serializejson__(self):
            return serializejson.tools.class_str_from_class(Echelle), (self.parent(), self._double // 2), None

    class W(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.echelle = Echelle(self, 1)
            self.label = QtWidgets.QLabel(self)
            self.sub = QtWidgets.QWidget(self)
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(250)
            self.action = QtGui.QAction("Ouvrir", self)

    w = W()
    w.timer.setInterval(999)
    w.timer.start()
    w.action.setText("Modifié")
    w.action.setCheckable(True)
    w.action.setChecked(True)
    w.action.setShortcut("Ctrl+O")
    w.echelle.setParent(None)
    w.echelle = Echelle(w, 5)
    texte = serializejson.dumps(w)
    options = {"authorized_classes": [W, Echelle]}
    if "--rouge" in sys.argv:
        options["rehydrate"] = False

    def verifie(v):
        assert v.timer.interval() == 999 and v.timer.isActive()
        assert v.action.text() == "Modifié" and v.action.isChecked()
        assert v.action.shortcut().toString() == "Ctrl+O"
        assert len(v.findChildren(QtCore.QTimer)) == 1
        assert len(v.findChildren(QtGui.QAction)) == 1
        assert len(v.findChildren(QtWidgets.QLabel)) == 1
        assert v.echelle._double == 10 and v.echelle.parent() is v
        assert v.findChildren(Echelle) == [v.echelle]
        assert len(v.findChildren(QtWidgets.QWidget)) == 3
        v.show()
        assert v.label.isVisible()

    verifie(serializejson.loads(texte, **options))
    if "--rouge" not in sys.argv:
        vivant = W()
        identites = (id(vivant.timer), id(vivant.action), id(vivant.label))
        ancienne = vivant.echelle
        assert serializejson.loads(texte, obj=vivant, **options) is vivant
        assert identites == (id(vivant.timer), id(vivant.action), id(vivant.label))
        assert vivant.echelle is not ancienne and ancienne.parent() is None
        verifie(vivant)
