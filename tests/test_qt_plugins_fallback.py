"""Cascade d'import des deux greffons Qt : qtpy6, puis PySide6, PyQt5, PySide2.

qtpy6 met PySide6 en tete la ou qtpy partait sur PyQt5 quand QT_API n'etait pas
pose ; les replis existent pour qui n'a pas la couche. Chaque branche est
exercee dans un SOUS-PROCESSUS (le greffon se lie a UNE API au premier import)
en masquant les modules par un chercheur place en tete de sys.meta_path.

Ce qui est verifie par branche : l'API retenue, les alias que la branche PyQt5
pose elle-meme (Signal, SignalInstance, Slot, Property — la couche les
garantit, PyQt5 nu ne les a pas), les modules QtCore/QtGui/QtWidgets publies
dans sys.modules (image_conversion y prend le binding du greffon, plutot que
d'en choisir un second), et le fait que serializejson reste utilisable sans
aucune API Qt.
"""

import importlib.util
import os
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _installe(module):
    return importlib.util.find_spec(module) is not None


def _lance(api_attendue, *masques):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["XDG_CONFIG_HOME"] = os.path.join(env.get("TMPDIR", "/tmp"), "qtcfg")
    resultat = subprocess.run(
        [sys.executable, os.path.abspath(__file__), api_attendue, *masques],
        cwd=RACINE, env=env, capture_output=True, text=True,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr


@pytest.mark.skipif(not _installe("qtpy6"), reason="qtpy6 absent")
def test_cascade_qtpy6():
    _lance("PySide6")


@pytest.mark.skipif(not _installe("PySide6"), reason="PySide6 absent")
def test_cascade_pyside6_direct():
    _lance("PySide6", "qtpy6")


@pytest.mark.skipif(not _installe("PyQt5"), reason="PyQt5 absent")
def test_cascade_pyqt5():
    _lance("PyQt5", "qtpy6", "PySide6")


def test_cascade_sans_api_qt():
    _lance("None", "qtpy6", "PySide6", "PyQt5", "PySide2")


if __name__ == "__main__":
    attendue, masques = sys.argv[1], set(sys.argv[2:])

    class Absent:
        """Rend introuvables les modules masques, comme s'ils n'etaient pas installes."""

        def find_spec(self, nom, chemin=None, cible=None):
            if nom.split(".")[0] in masques:
                raise ImportError("%s masque par le test" % nom)
            return None

    sys.meta_path.insert(0, Absent())
    for nom in [n for n in sys.modules if n.split(".")[0] in masques]:
        del sys.modules[nom]

    sys.path.insert(0, RACINE)
    import conftest  # noqa: F401 — rend rapidjson importable (voir conftest)

    import serializejson
    from serializejson.plugins import serializejson_PyQt5_PySide2 as greffon
    from serializejson.plugins import pickle_PyQt5_PySide2 as greffon_pickle

    assert str(greffon.API) == attendue, "%s au lieu de %s" % (greffon.API, attendue)
    assert str(greffon_pickle.API) == attendue, greffon_pickle.API

    if attendue == "None":
        assert serializejson.loads(serializejson.dumps([1, "a"])) == [1, "a"]
    else:
        assert ("qtpy6" in sys.modules) is ("qtpy6" not in masques)
        for nom in ("QtCore", "QtGui", "QtWidgets"):
            assert sys.modules[nom] is getattr(greffon, nom), nom
        for alias in ("Signal", "SignalInstance", "Slot", "Property"):
            assert hasattr(greffon.QtCore, alias), alias
        image = greffon.QtGui.QImage(4, 3, greffon.QtGui.QImage.Format_ARGB32)
        image.fill(greffon.QtGui.QColor(10, 20, 30))
        relue = serializejson.loads(
            serializejson.dumps(image), authorized_classes=["QtGui.QImage"]
        )
        assert relue == image
