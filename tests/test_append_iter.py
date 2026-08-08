# Itération sur un fichier d'objets appendés (append + for obj in Decoder).
# Ce chemin n'avait AUCUN test : il a cassé silencieusement pendant la
# migration des __call__ en C (état volatil jamais posé), et son scanner
# avalait le guillemet fermant après un échappement (\n en fin de chaîne).
# Les deux sont corrigés le 04/08/2026 — et le scanner est porté en C.
import io
import os

import pytest

import serializejson
from serializejson import _json_object_file_iterator


@pytest.fixture
def chemin(tmp_path):
    return str(tmp_path / "appended.json")


def test_iteration_formes_variees(chemin):
    partage = {"x": 1}
    objets = [
        {"num": 1, "nom": "objet"},
        [1, "deux", None],
        5,
        "texte",
        "",
        {"a": partage, "b": partage},
    ]
    for objet in objets:
        serializejson.append(objet, chemin)
    relus = list(serializejson.Decoder(chemin))
    assert relus == objets
    # le partage interne est restauré ($ref résolu après le parse)
    assert relus[5]["a"] is relus[5]["b"]


def test_iteration_echappements(chemin):
    # le scanner d'origine avalait le guillemet fermant après \n ou \\ :
    # toutes les bornes d'objets suivantes étaient fausses
    objets = [
        "fin\n",
        "anti\\",
        'gu"illemets',
        {"k": "a\nb", "vide": ""},
        ["avec ]crochet", "avec }accolade"],
        "suivant",
    ]
    for objet in objets:
        serializejson.append(objet, chemin)
    assert list(serializejson.Decoder(chemin)) == objets


def test_scanner_c_identique_boucle_python(chemin):
    # le scanner C et la boucle Python de repli rendent les mêmes tranches
    # et les mêmes états, y compris sur des tailles de lecture hostiles
    for objet in ({"k%d" % i: "v\n" % () for i in range(4)}, [1, [2, "]"]],
                  7, "fin\\", ""):
        serializejson.append(objet, chemin)

    class ScannerPython(_json_object_file_iterator):
        def read(self, size=-1):
            if self.shedule_break:
                self.shedule_break = False
                return ""
            if self.in_chunk_start == 0:
                self.s = io.FileIO.read(self, size)
            return self._read_python(self.s)

    def etat(x):
        return (x.in_chunk_start, bool(x.in_quotes), int(x.in_curlys),
                int(x.in_squares), bool(x.in_simple), bool(x.in_object),
                bool(x.backslash_escape), bool(x.shedule_break))

    for taille in (1, 7, 4096):
        a = _json_object_file_iterator(chemin, mode="rb")
        b = ScannerPython(chemin, mode="rb")
        vides = 0
        while vides < 50:
            ca = a.read(taille)
            cb = b.read(taille)
            assert ca == cb
            assert etat(a) == etat(b)
            vides = vides + 1 if ca in ("", b"") else 0
        a.close()
        b.close()


def test_fichier_absent(chemin):
    # fichier absent : un seul élément, la valeur par défaut du décodeur
    assert not os.path.exists(chemin)
    assert list(serializejson.Decoder(chemin, default_value=None)) == [None]


def test_append_octets_identiques_a_la_serialisation_directe(chemin):
    # depuis le 04/08/2026, les éléments appendés sont indentés d'un
    # niveau : le fichier est octet pour octet ce que donnerait la
    # sérialisation directe de la liste complète
    objets = [{"a": 1}, [1, 2], "texte", {"imbrique": {"n": [1, {"p": "q"}]}}]
    for objet in objets:
        serializejson.append(objet, chemin)
    with open(chemin, encoding="utf-8") as f:
        assert f.read() == serializejson.dumps(objets)
    assert list(serializejson.Decoder(chemin)) == objets


def test_append_compact_inchange(chemin):
    encoder = serializejson.Encoder(chemin, indent=None)
    for objet in [1, "a", [2, 3]]:
        encoder.append(objet)
    encoder.close()
    with open(chemin, encoding="utf-8") as f:
        contenu = f.read()
    assert "\n" not in contenu and "\t" not in contenu
    assert list(serializejson.Decoder(chemin)) == [1, "a", [2, 3]]


def test_poussee_amortie_pas_rejouee_a_chaque_maillon(chemin):
    """La comptabilité d'append ne doit pas invalider la poussée amortie.

    `_update_serialize_parameters` pousse les paramètres globaux et résout
    le nombre de threads blosc — un `os.cpu_count()`, appel système à ~2 µs.
    Elle est gardée par un témoin `_owner` que le `__setattr__` de la classe
    remet à zéro dès qu'un attribut change. Or `append` tient un rang, un
    descripteur et deux témoins : écrits par `self.x = ...`, ils
    invalidaient la garde à CHAQUE maillon, et la poussée se rejouait en
    entier. Mesuré le 08/08/2026 : 7,6 µs par append au lieu de 2,9 sur
    20 000 maillons. Ils s'écrivent depuis dans le `__dict__`.
    """
    encoder = serializejson.Encoder(chemin, indent=None)
    encoder.append({"n": 0})  # ouverture du fichier : une poussée légitime
    appels = []
    vraie = type(encoder)._update_serialize_parameters

    def espion(self):
        appels.append(1)
        return vraie(self)

    type(encoder)._update_serialize_parameters = espion
    try:
        for i in range(1, 20):
            encoder.append({"n": i})
    finally:
        type(encoder)._update_serialize_parameters = vraie
    encoder.close()

    # le C ne rappelle python que sur DÉFAUT de garde : zéro appel est la
    # preuve que la garde tient d'un maillon à l'autre. Avant le correctif,
    # elle défaillait à chaque fois — un appel par maillon.
    assert appels == []
