"""Greffon pickle Qt (pickle_PyQt5_PySide2) : aller-retour des reducteurs.

Jamais exerce jusqu'ici : qtpy partait sur PyQt5 quand QT_API n'etait pas pose,
et les enumerations y sont des entiers. Sous PySide6 (defaut de qtpy6) ce sont
des enum.Enum, que int() refuse et que les constructeurs Qt n'acceptent qu'en
enum : reduce_QPen et reduce_QBrush levaient TypeError. reduce_QPen perdait en
outre les largeurs fractionnaires (width() arrondit : 2.5 relu 3).

Les widgets demandent une QApplication : sous-processus offscreen.
"""

import os
import pickle
import subprocess
import sys

import pytest

pytest.importorskip("PySide6")

from serializejson.plugins import pickle_PyQt5_PySide2 as greffon  # noqa: E402

pytestmark = pytest.mark.skipif(greffon.API is None, reason="aucune API Qt")

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QtGui = greffon.QtGui


def _Qt():
    return sys.modules["QtCore"].Qt  # binding publie par le greffon serializejson


def _aller_retour(objet):
    return pickle.loads(pickle.dumps(objet))


@pytest.mark.parametrize("largeur, style", [(1.0, "SolidLine"), (2.5, "SolidLine"), (2.5, "DashLine"), (1.0, "DotLine")])
def test_pickle_qpen(largeur, style):
    stylo = QtGui.QPen(QtGui.QColor(1, 2, 3), largeur, getattr(_Qt(), style))

    relu = _aller_retour(stylo)

    assert relu.color() == stylo.color()
    assert relu.widthF() == largeur
    assert relu.style() == stylo.style()


@pytest.mark.parametrize("style", ["SolidPattern", "Dense3Pattern", "NoBrush"])
def test_pickle_qbrush(style):
    brosse = QtGui.QBrush(QtGui.QColor(4, 5, 6), getattr(_Qt(), style))

    relue = _aller_retour(brosse)

    assert relue.style() == brosse.style()
    if brosse.style() != _Qt().NoBrush:
        assert relue.color() == brosse.color()


@pytest.mark.parametrize("classe, point", [("QPolygon", "QPoint"), ("QPolygonF", "QPointF")])
def test_pickle_qpolygon(classe, point):
    QtCore = sys.modules["QtCore"]
    sommets = [getattr(QtCore, point)(1, 2), getattr(QtCore, point)(3, 4)]
    polygone = getattr(QtGui, classe)(sommets)

    relu = _aller_retour(polygone)

    assert list(relu) == sommets


def test_pickle_widgets():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["XDG_CONFIG_HOME"] = os.path.join(env.get("TMPDIR", "/tmp"), "qtcfg")
    resultat = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        cwd=RACINE, env=env, capture_output=True, text=True,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr


if __name__ == "__main__":
    sys.path.insert(0, RACINE)
    import conftest  # noqa: F401 — rend rapidjson importable (voir conftest)

    from serializejson.plugins import pickle_PyQt5_PySide2 as greffon_pickle

    QtWidgets = greffon_pickle.QtWidgets
    app = QtWidgets.QApplication([])

    spin = QtWidgets.QSpinBox()
    spin.setValue(7)
    case = QtWidgets.QCheckBox()
    case.setChecked(True)
    ligne = QtWidgets.QLineEdit("abc")
    texte = QtWidgets.QPlainTextEdit("def")
    widget = QtWidgets.QWidget()

    assert pickle.loads(pickle.dumps(spin)).value() == 7
    assert pickle.loads(pickle.dumps(case)).isChecked() is True
    assert pickle.loads(pickle.dumps(ligne)).text() == "abc"
    assert pickle.loads(pickle.dumps(texte)).toPlainText() == "def"
    assert isinstance(pickle.loads(pickle.dumps(widget)), QtWidgets.QWidget)
