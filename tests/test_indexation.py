"""Index de position : charger un objet d'un json sans lire le reste.

Deux formes de rangement (`index="sidecar"` / `index="comment"`), la même
grammaire de chemins que les `$ref`, et l'exigence qui commande tout le
reste : le chemin doit rendre EXACTEMENT ce que rend le chargement complet,
références partagées comprises.
"""

import json
import os

import pytest
import serializejson
from serializejson import indexation

try:
    import numpy

    use_numpy = True
except ModuleNotFoundError:
    use_numpy = False

FORMES = ("sidecar", "comment")


class Client:
    def __init__(self, nom=None, notes=None):
        self.nom = nom
        self.notes = notes


def ecrit(tmp_path, obj, forme="sidecar", seuil=64):
    chemin = str(tmp_path / "base.json")
    serializejson.dump(obj, chemin, index=forme, index_threshold=seuil)
    return chemin


def corpus():
    # assez gros pour que chaque branche dépasse le seuil des tests
    return {"clients": [Client("c%d" % i, list(range(50))) for i in range(10)],
            "meta": {"n": 10, "titre": "corpus"}}


@pytest.mark.parametrize("forme", FORMES)
def test_chemin_rend_la_meme_chose_que_le_chargement_complet(tmp_path, forme):
    chemin = ecrit(tmp_path, corpus(), forme)
    complet = serializejson.load(chemin, authorized_classes=[Client])
    for chemin_objet, attendu in (
        ("root", complet),
        ("root['meta']", complet["meta"]),
        ("root['clients']", complet["clients"]),
        ("root['clients'][3]", complet["clients"][3]),
        ("root['clients'][3].nom", "c3"),
        ("root['meta']['titre']", "corpus"),
    ):
        obtenu = serializejson.load(chemin, path=chemin_objet,
                                    authorized_classes=[Client])
        if isinstance(attendu, Client):
            assert obtenu.nom == attendu.nom and obtenu.notes == attendu.notes
        else:
            assert serializejson.dumps(obtenu) == serializejson.dumps(attendu)


@pytest.mark.parametrize("forme", FORMES)
def test_le_document_reste_chargeable_en_entier(tmp_path, forme):
    chemin = ecrit(tmp_path, corpus(), forme)
    complet = serializejson.load(chemin, authorized_classes=[Client])
    assert [c.nom for c in complet["clients"]] == ["c%d" % i for i in range(10)]


def test_la_forme_sidecar_laisse_un_json_standard(tmp_path):
    chemin = ecrit(tmp_path, corpus(), "sidecar")
    with open(chemin, "rb") as f:
        json.loads(f.read())   # lisible par n'importe quel parseur json
    assert os.path.exists(indexation.chemin_sidecar(chemin))


def test_la_forme_comment_ajoute_ses_lignes_au_fichier(tmp_path):
    chemin = ecrit(tmp_path, corpus(), "comment")
    assert not os.path.exists(indexation.chemin_sidecar(chemin))
    with open(chemin, "rb") as f:
        contenu = f.read()
    assert contenu.rstrip().endswith(b"\n" + indexation.PIED
                                     + b"%0*d" % (indexation.LARGEUR_POSITION,
                                                  contenu.index(b"\n//") + 1))
    with pytest.raises(ValueError):
        json.loads(contenu)    # ce n'est plus du json standard


@pytest.mark.parametrize("forme", FORMES)
def test_reference_partagee_dans_la_tranche(tmp_path, forme):
    # PIÈGE : le chemin d'un $ref est ABSOLU. Chargé tel quel, {"$ref":
    # "root['a']['b']"} se résoudrait dans la tranche et tomberait sur son
    # propre ['a']['b'] — un autre objet, sans la moindre erreur
    partage = ["X"] * 30
    obj = {"a": {"a": {"b": ["PIEGE"] * 30}, "b": partage, "c": partage},
           "bourre": list(range(100))}
    chemin = ecrit(tmp_path, obj, forme)
    tranche = serializejson.load(chemin, path="root['a']")
    assert tranche["c"] == ["X"] * 30
    assert tranche["b"] is tranche["c"]


@pytest.mark.parametrize("forme", FORMES)
def test_reference_hors_de_la_tranche(tmp_path, forme):
    partage = {"gros": list(range(100))}
    obj = {"a": {"p": partage, "bourre": list(range(100))},
           "b": {"p": partage, "bourre": list(range(100))}}
    chemin = ecrit(tmp_path, obj, forme)
    tranche = serializejson.load(chemin, path="root['b']")
    assert tranche["p"] == partage


def test_references_circulaires_repassent_par_le_document_entier(tmp_path):
    x = Client("x", list(range(100)))
    y = Client("y", list(range(100)))
    x.notes, y.notes = y, x
    chemin = ecrit(tmp_path, {"x": x, "y": y})
    charge = serializejson.load(chemin, path="root['x']",
                                authorized_classes=[Client])
    assert charge.notes.nom == "y"
    assert charge.notes.notes is charge


def test_chemin_non_indexe_passe_par_son_ancetre(tmp_path):
    chemin = ecrit(tmp_path, corpus(), seuil=1 << 20)   # rien n'est indexé
    assert serializejson.paths(chemin) == ["root"]
    charge = serializejson.load(chemin, path="root['clients'][2].nom",
                                authorized_classes=[Client])
    assert charge == "c2"


def test_sans_index_le_chemin_marche_quand_meme(tmp_path):
    chemin = str(tmp_path / "sans_index.json")
    serializejson.dump(corpus(), chemin)
    assert serializejson.paths(chemin) is None
    charge = serializejson.load(chemin, path="root['clients'][2].nom",
                                authorized_classes=[Client])
    assert charge == "c2"


@pytest.mark.parametrize("forme", FORMES)
def test_index_perime_ignore(tmp_path, forme):
    chemin = ecrit(tmp_path, corpus(), forme)
    serializejson.dump({"autre": 1}, chemin)   # réécrit sans index
    assert serializejson.paths(chemin) is None
    assert serializejson.load(chemin) == {"autre": 1}


@pytest.mark.parametrize("forme", FORMES)
def test_index_remplace_pas_celui_memorise(tmp_path, forme):
    # l'index lu est gardé en mémoire d'un appel à l'autre : un fichier
    # réécrit ne doit pas continuer d'être lu avec les positions de l'ancien
    # même TAILLE de part et d'autre, mais des positions DIFFÉRENTES : suivre
    # l'index gardé en mémoire découperait le nouveau document au mauvais
    # endroit, et la taille seule ne le verrait pas
    chemin = ecrit(tmp_path, {"a": ["X"] * 100, "b": ["Z"] * 50}, forme)
    assert serializejson.load(chemin, path="root['a']") == ["X"] * 100
    ecrit(tmp_path, {"a": ["X"] * 50, "b": ["Z"] * 100}, forme)
    assert serializejson.load(chemin, path="root['a']") == ["X"] * 50


@pytest.mark.parametrize("forme", FORMES)
def test_index_d_un_fichier_deja_ecrit(tmp_path, forme):
    chemin = str(tmp_path / "base.json")
    serializejson.dump(corpus(), chemin)
    serializejson.index(chemin, forme, threshold=64)
    chemins = serializejson.paths(chemin)
    assert "root['clients'][3]" in chemins
    # ré-indexer un fichier déjà indexé ne l'empile pas sur lui-même
    serializejson.index(chemin, forme, threshold=64)
    assert serializejson.paths(chemin) == chemins


@pytest.mark.parametrize("forme", FORMES)
def test_index_sur_un_fichier_ouvert_par_l_appelant(tmp_path, forme):
    chemin = str(tmp_path / "ouvert.json")
    with open(chemin, "wb") as f:
        serializejson.dump(corpus(), f, index=forme, index_threshold=64)
    assert "root['clients'][3]" in serializejson.paths(chemin)
    charge = serializejson.load(chemin, path="root['clients'][3].nom",
                                authorized_classes=[Client])
    assert charge == "c3"


def test_index_sans_chemin_de_fichier_refuse():
    with pytest.raises(Exception):
        serializejson.dumps(corpus(), index="sidecar")


def test_forme_inconnue_refusee():
    with pytest.raises(Exception):
        serializejson.Encoder(index="peut-etre")


def test_chemin_absent_leve(tmp_path):
    chemin = ecrit(tmp_path, corpus())
    with pytest.raises(KeyError):
        serializejson.load(chemin, path="root['clients'][999]",
                           authorized_classes=[Client])


def test_cles_non_str_et_collections(tmp_path):
    obj = {"dico": {2: list(range(50)), (1, 2): "tuple en cle"},
           "ensemble": set(range(50)),
           "tuple": tuple(range(50))}
    chemin = ecrit(tmp_path, obj)
    complet = serializejson.load(chemin)
    for cle in ("dico", "ensemble", "tuple"):
        obtenu = serializejson.load(chemin, path="root['%s']" % cle)
        assert obtenu == complet[cle]


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_charge_un_seul_tableau_numpy(tmp_path):
    obj = {"a": numpy.arange(1000, dtype="int32"),
           "b": numpy.arange(1000, dtype="float64")}
    chemin = ecrit(tmp_path, obj, seuil=256)
    charge = serializejson.load(chemin, path="root['b']")
    assert charge.dtype == numpy.float64 and charge[-1] == 999


def test_balaye_donne_des_tranches_json_valides(tmp_path):
    chemin = ecrit(tmp_path, corpus())
    with open(chemin, "rb") as f:
        donnees = f.read()
    for debut, fin in indexation.lit(chemin)["paths"].values():
        json.loads(donnees[debut:fin])
