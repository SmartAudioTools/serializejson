"""Une application Qt recréée de toutes pièces, ou réhydratée, depuis un json
écrit avec qt_tree=True (PySide6) : fenêtres de premier niveau, enfants
anonymes, layouts, connexions, au fil du parse (rehydrate=True).

Le greffon se lie à UNE API Qt au premier import de serializejson : chaque
étape tourne dans un sous-processus sous QT_API=pyside6. Étapes :
  --ecrit      construit l'application, écrit le json (et vérifie l'opt-in)
  --recree     processus VIERGE : load_application recrée tout
  --rehydrate  application vivante modifiée : load_application la remet à jour
               deux fois (identités conservées, connexions non doublées)
Avec --sans-rehydrate (rehydrate=False), la recréation passe par la voie
classique : les enfants créés par __init__ ET ceux du json coexistent
(rouge attendu).
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
def test_application_pyside6(tmp_path):
    chemin = str(tmp_path / "application.json")
    for etape in ("--ecrit", "--recree", "--rehydrate"):
        resultat = _lance(etape, chemin)
        assert resultat.returncode == 0, (etape, resultat.stderr)
    resultat = _lance("--recree", chemin, "--sans-rehydrate")
    assert resultat.returncode != 0, "la voie classique doit doubler les enfants"
    assert "AssertionError" in resultat.stderr


if __name__ == "__main__":
    sys.path.insert(0, RACINE)
    etape, chemin = sys.argv[1], sys.argv[2]
    sans_rehydrate = "--sans-rehydrate" in sys.argv
    import conftest  # noqa: F401 — rend rapidjson importable (voir conftest)

    import serializejson
    from serializejson.plugins import serializejson_PyQt5_PySide2 as greffon
    from qtpy import QtCore, QtWidgets

    assert greffon.API == "PySide6"
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class Panel(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.spin = QtWidgets.QSpinBox(self)
            self.plus = QtWidgets.QPushButton("+", self)
            self.plus.pressed.connect(self.spin.stepUp)

    class Principale(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Principale")
            self.label = QtWidgets.QLabel("label", self)
            self.spin = QtWidgets.QSpinBox(self)
            self.panel = Panel(self)
            grille = QtWidgets.QGridLayout(self)
            grille.addWidget(self.label, 0, 0)
            grille.addWidget(self.spin, 0, 1)
            grille.addWidget(self.panel, 1, 0, 1, 2)
            self.spin.valueChanged.connect(self.label.setNum)
            self.recus = []

        def on_value(self, valeur):
            self.recus.append(valeur)

    class Secondaire(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Secondaire")
            self.spin = QtWidgets.QSpinBox(self)

    classes = [Principale, Panel, Secondaire]

    def construit():
        principale = Principale()
        # bouton ANONYME ajouté hors __init__ : une recréation doit le créer
        bouton = QtWidgets.QPushButton("anon", principale)
        principale.layout().addWidget(bouton, 2, 0)
        bouton.pressed.connect(principale.spin.stepUp)
        secondaire = Secondaire()  # tenue par aucun attribut python
        principale.spin.valueChanged.connect(secondaire.spin.setValue)
        principale.spin.valueChanged.connect(principale.on_value)
        app.principale = principale
        return principale, secondaire

    def verifie(principale, secondaire):
        fenetres = greffon.qt_windows(app)
        assert [f.windowTitle() for f in fenetres] == ["Principale", "Secondaire"]
        assert fenetres[0] is principale and fenetres[1] is secondaire
        # aucun doublon : les enfants du __init__ sont ADOPTÉS, pas recréés
        assert len(principale.findChildren(QtWidgets.QLabel)) == 1
        assert len(principale.findChildren(QtWidgets.QSpinBox)) == 2
        assert principale.panel.spin.parent() is principale.panel
        boutons = [b for b in principale.findChildren(QtWidgets.QPushButton)
                   if b.parent() is principale]
        assert [b.text() for b in boutons] == ["anon"]
        grille = principale.layout()
        assert isinstance(grille, QtWidgets.QGridLayout)
        assert grille.count() == 4
        assert grille.getItemPosition(grille.indexOf(principale.panel)) == (1, 0, 1, 2)
        assert grille.getItemPosition(grille.indexOf(boutons[0])) == (2, 0, 1, 1)
        assert (principale.spin.value(), secondaire.spin.value()) == (7, 7)
        # connexions actives, chacune UNE fois (bouton anonyme, inter-fenêtres,
        # enfant -> méthode de la racine, __init__ du panel)
        boutons[0].pressed.emit()
        assert principale.spin.value() == 8
        assert secondaire.spin.value() == 8
        assert principale.label.text() == "8"
        assert principale.recus.count(8) == 1, principale.recus
        principale.panel.plus.pressed.emit()
        assert principale.panel.spin.value() == 1

    if etape == "--ecrit":
        principale, secondaire = construit()
        principale.spin.setValue(7)
        # opt-in : sans qt_tree, rien de l'arbre ni des propriétés Qt
        json_defaut = serializejson.dumps(app)
        assert "~windows" not in json_defaut and "~children" not in json_defaut
        assert '"text"' not in json_defaut
        serializejson.dump(app, chemin, qt_tree=True)
        serializejson.wait_writes()
        with open(chemin, encoding="utf-8") as fichier:
            json = fichier.read()
        assert json.count('"windowTitle"') == 2
        assert '"text": "anon"' in json
        assert '"principale": {"$ref": "root.~windows[0]"}' in json
        assert '"__class__": "QtWidgets.QGridLayout"' in json
    elif etape == "--recree":
        assert not hasattr(app, "principale")
        if sans_rehydrate:
            serializejson.load(chemin, rehydrate=False, authorized_classes=classes)
        else:
            assert greffon.load_application(chemin, authorized_classes=classes) is app
        principale = app.principale
        assert isinstance(principale, Principale)
        (secondaire,) = [f for f in greffon.qt_windows(app) if f is not principale]
        verifie(principale, secondaire)
        QtCore.QTimer.singleShot(0, app.quit)
        assert app.exec() == 0
    elif etape == "--rehydrate":
        principale, secondaire = construit()
        principale.spin.setValue(3)
        bouton = principale.layout().itemAt(3).widget()
        ids = [id(o) for o in (principale, principale.label, principale.spin,
                               principale.panel, principale.panel.spin, bouton,
                               secondaire, principale.layout())]
        enfants = [len(principale.children()), len(secondaire.children())]
        for _ in range(2):
            assert greffon.load_application(chemin, authorized_classes=classes) is app
        assert app.principale is principale
        assert [id(o) for o in (principale, principale.label, principale.spin,
                                principale.panel, principale.panel.spin, bouton,
                                secondaire, principale.layout())] == ids
        assert [len(principale.children()), len(secondaire.children())] == enfants
        verifie(principale, secondaire)
    else:
        raise SystemExit("étape inconnue : " + etape)
