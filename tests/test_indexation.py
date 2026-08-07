"""Index de position : charger un objet d'un json sans lire le reste.

Deux formes de rangement (`index="sidecar"` / `index="comment"`), la même
grammaire de chemins que les `$ref`, et l'exigence qui commande tout le
reste : le chemin doit rendre EXACTEMENT ce que rend le chargement complet,
références partagées comprises.
"""

import datetime
import decimal
import json
import os
import time

import pytest
import rapidjson
import serializejson
from serializejson import indexation

# l'alphabet de la queue de commentaire, réécrit ici EXPRÈS : le test doit
# constater la forme du fichier, pas la relire de la constante qui l'a produite
B64 = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

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
    # dump rend la main avant le disque (disk_write_mode vaut "fast_release"),
    # et l'index se range dans le thread d'écriture avec le reste : les tests
    # qui ouvrent le fichier EUX-MÊMES doivent attendre, comme n'importe quel
    # appelant qui le confie à autre chose. load, paths et index le font seuls
    serializejson.wait_writes()
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


def test_la_forme_comment_ajoute_sa_queue_au_fichier(tmp_path):
    chemin = ecrit(tmp_path, corpus(), "comment")
    assert not os.path.exists(indexation.chemin_sidecar(chemin))
    with open(chemin, "rb") as f:
        contenu = f.read()
    fin = rapidjson._index_fin(contenu)
    # la queue est de la base 64 derrière « // » : le fichier reste du TEXTE,
    # donc un vrai commentaire, et le document seul reste du json standard
    queue = contenu[fin:]
    assert queue.startswith(b"//") and queue[2:].strip(B64) == b""
    json.loads(contenu[:fin])
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


@pytest.mark.parametrize("forme", FORMES)
def test_index_reduit_a_root_n_est_pas_ecrit(tmp_path, forme):
    # rien n'atteint le seuil : l'index se réduirait à `root`, qui ne dit rien
    # que la taille du fichier ne dise déjà. L'écrire alourdissait un petit
    # json de plus que son propre poids ; le chemin reste chargeable, par
    # l'analyse complète, exactement comme sans index
    chemin = ecrit(tmp_path, corpus(), forme, seuil=1 << 20)
    assert serializejson.paths(chemin) is None
    assert not os.path.exists(indexation.chemin_sidecar(chemin))
    with open(chemin, "rb") as f:
        json.loads(f.read())            # rien n'a été collé derrière
    charge = serializejson.load(chemin, path="root['clients'][2].nom",
                                authorized_classes=[Client])
    assert charge == "c2"


def test_dump_indexe_d_office(tmp_path):
    # `dump` vers un fichier NOMMÉ pose l'index de lui-même : c'est ce qui fait
    # qu'un chemin se charge sans que personne ait eu à demander l'index à
    # l'écriture. La forme par défaut est le fichier VOISIN, qui laisse le
    # document lisible par n'importe quel lecteur json
    chemin = str(tmp_path / "defaut.json")
    serializejson.dump(corpus(), chemin, index_threshold=64)
    serializejson.wait_writes()
    assert os.path.exists(indexation.chemin_sidecar(chemin))
    with open(chemin, "rb") as f:
        json.loads(f.read())           # rien n'a été collé derrière
    assert "root['clients']" in serializejson.paths(chemin)
    charge = serializejson.load(chemin, path="root['clients'][2].nom",
                                authorized_classes=[Client])
    assert charge == "c2"


def test_index_none_laisse_le_json_nu(tmp_path):
    # `index=None` refuse l'index que `dump` pose d'office : le fichier reste
    # du json standard, et le chemin se charge quand même — par l'analyse
    # complète du document, exactement comme avant que l'index existe
    chemin = str(tmp_path / "sans_index.json")
    serializejson.dump(corpus(), chemin, index=None, index_threshold=64)
    assert not os.path.exists(indexation.chemin_sidecar(chemin))
    # sans index, personne n'a attendu l'écriture pour nous (disk_write_mode
    # vaut "fast_release") : lire le fichier soi-même l'exige
    serializejson.wait_writes()
    with open(chemin, "rb") as f:
        json.loads(f.read())           # rien n'a été collé derrière
    assert serializejson.paths(chemin) is None
    charge = serializejson.load(chemin, path="root['clients'][2].nom",
                                authorized_classes=[Client])
    assert charge == "c2"


def test_la_date_departage_les_deux_index(tmp_path):
    # les deux formes cohabitent, et toutes deux bornent bien CE document :
    # rien dans leur contenu ne dit laquelle suivre, c'est la DATE qui tranche
    # — celle que la queue transporte à côté de sa longueur, celle que le
    # sidecar tire de son mtime. Les dates se posent ici à la main : la
    # comparaison se fait à la milliseconde, et deux écritures d'affilée y
    # tombent ensemble
    chemin = ecrit(tmp_path, {"a": list(range(200)), "b": list(range(200))},
                   "comment", seuil=16)
    date = rapidjson._index_queue(chemin)[1]
    index = json.loads(rapidjson._index_lit(chemin, None)[1])
    index["paths"]["root['temoin']"] = index["paths"]["root['a']"]
    sidecar = indexation.chemin_sidecar(chemin)
    with open(sidecar, "wb") as f:
        # en CLAIR : un bloc qui commence par « { » se relit tel quel
        f.write(json.dumps(index).encode("utf-8"))
    os.utime(sidecar, ns=(0, (date + 1000) * 1000000))
    assert "root['temoin']" in serializejson.paths(chemin)
    os.utime(sidecar, ns=(0, (date - 1000) * 1000000))
    assert "root['temoin']" not in serializejson.paths(chemin)


@pytest.mark.parametrize("forme", FORMES)
def test_index_perime_ignore(tmp_path, forme):
    chemin = ecrit(tmp_path, corpus(), forme)
    # réécrit petit : l'index d'office ne trouve plus rien à dire de ce
    # document, et celui d'avant ne le borne plus
    serializejson.dump({"autre": 1}, chemin)
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
    # `dump` a posé le sien dans la forme par défaut : réindexer dans l'autre
    # forme retire celui-là, sans quoi deux index restent en place et c'est
    # leur date, à la milliseconde, qui dirait au hasard lequel suivre
    assert os.path.exists(indexation.chemin_sidecar(chemin)) \
        == (forme == "sidecar")
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


def test_balayage_C_identique_au_python():
    # le balayage est porté en C (indexscan.h) ; la version python reste la
    # RÉFÉRENCE, et ce test est ce qui rend le portage vérifiable — clés
    # échappées, accents, enveloppes d'objets, conteneurs vides, document
    # réduit à un scalaire, seuils extrêmes, document borné avant sa fin
    cas = [
        corpus(),
        {"m": [[i * 1.5 + j for j in range(60)] for i in range(60)]},
        {'a"b': list(range(200)), "c\\d": list(range(200)), "éé": [1, 2, 3],
         "ligne\nsuite": list(range(200)), "tab\tici": list(range(200)),
         "é中": list(range(200))},
        {"a": {"b": {"c": {"d": list(range(200))}}}},
        {"a": [], "b": {}, "c": [[], [{}]], "d": list(range(200))},
        list(range(5000)),
        # une chaîne de DONNÉES pleine de ponctuation de structure : elle est
        # sautée d'un bloc, sinon elle ouvrirait des conteneurs fantômes
        {"a": "{[,:}]" * 400, "b": list(range(200))},
        "x" * 2000,
        42,
    ]
    # un json ÉCRIT PAR UN AUTRE OUTIL s'indexe aussi : ses clés portent
    # alors des \uXXXX, paires de substitution comprises, que serializejson
    # n'écrit jamais lui-même (il pose l'utf-8 tel quel)
    ailleurs = [json.dumps({"é中": list(range(60)), "\U0001F600": list(range(60)),
                            "a\tb": list(range(60))},
                           ensure_ascii=True).encode()]
    documents = list(ailleurs)
    for indent in (None, 2):
        encodeur = serializejson.Encoder(indent=indent)
        documents += [encodeur.dumpb(obj) for obj in cas]
    for donnees in documents:
        for seuil in (1, 16, 256, 10 ** 9):
            assert (indexation.balaye(donnees, seuil)
                    == indexation._balaye_python(donnees, seuil))
        # forme "comment" : le document s'arrête avant l'index
        suivi = donnees + b"//eyJ0Ijox" + b"K" + b"B"
        assert (indexation.balaye(suivi, 16, len(donnees))
                == indexation._balaye_python(suivi, 16, len(donnees)))


def cas_ecriture():
    # ce que l'écrivain sait écrire SANS repasser par python, donc sans que le
    # suivi de chemin pousse un segment : enveloppes de bytes (charge en
    # [base64,"b64"]), collections, dates, objets
    return [
        corpus(),
        {"petit": b"\x00\x01\x02" * 40, "gros": bytes(range(256)) * 40,
         "tableau": bytearray(range(256)) * 40, "bourre": list(range(200))},
        {"texte": b"lisible " * 200, "bourre": list(range(200))},
        {"ens": set(range(200)), "tup": tuple(range(200)),
         "dico": {2: list(range(200)), (1, 2): "tuple en cle"}},
        {"a": {"b": {"c": {"d": list(range(200))}}}, "vide": [], "rien": {}},
        [Client("c%d" % i, b"\x80\x81" * 100) for i in range(20)],
        # toutes les enveloppes que l'écrivain compose d'un bloc : leur charge
        # n'a pas de segment de chemin, c'est la clé de la tête qui la nomme
        {"dt": datetime.datetime(2026, 8, 7, 1, 2, 3, 4),
         "d": datetime.date(2026, 8, 7), "t": datetime.time(1, 2, 3),
         "td": datetime.timedelta(days=1, seconds=2),
         "st": time.struct_time((2026, 8, 7, 1, 2, 3, 4, 219, 0)),
         "dec": decimal.Decimal("1.25"), "cx": complex(1, 2),
         "rg": range(0, 10, 2), "sl": slice(1, 9, 3),
         "cl": Client, "fs": frozenset(range(200)),
         "bourre": list(range(200))},
    ]


@pytest.mark.parametrize("indent", (None, 2))
def test_index_ecrit_identique_au_balayage(tmp_path, indent):
    # l'index construit PENDANT l'écriture doit rendre EXACTEMENT le même
    # index que le balayage du fichier écrit : c'est cette égalité stricte,
    # et elle seule, qui interdit à un décalage de position de passer inaperçu
    chemin = str(tmp_path / "ecrit.json")
    for objet in cas_ecriture():
        for seuil in (1, 16, 256):
            encodeur = serializejson.Encoder(index="sidecar", indent=indent,
                                             index_threshold=seuil)
            encodeur.dump(objet, chemin)
            serializejson.wait_writes()
            with open(chemin, "rb") as f:
                donnees = f.read()
            assert (indexation.lit(chemin)["paths"]
                    == indexation.balaye(donnees, seuil))


def test_index_decale_crie(tmp_path):
    # un index faux d'UN octet rend un objet plausible et faux : la tranche
    # doit ouvrir et refermer un conteneur, faute de quoi le chargement crie
    chemin = str(tmp_path / "decale.json")
    objet = {"a": list(range(200)), "b": list(range(200))}
    serializejson.dump(objet, chemin, index="sidecar", index_threshold=16)
    serializejson.wait_writes()
    sidecar = indexation.chemin_sidecar(chemin)
    index = json.loads(rapidjson._index_lit(chemin, sidecar)[1])
    assert serializejson.load(chemin, path="root['a']") == objet["a"]
    index["paths"]["root['a']"][0] += 1
    # réécrit en CLAIR : un bloc qui commence par « { » se relit tel quel,
    # c'est ce premier octet qui dit s'il a été dégonflé
    with open(sidecar, "wb") as f:
        f.write(json.dumps(index).encode("utf-8"))
    with pytest.raises(indexation.IndexDecale):
        serializejson.load(chemin, path="root['a']")


def test_index_refait_sans_toucher_au_document(tmp_path):
    # PIÈGE : réindexer plus finement ne touche QUE le sidecar. Si le mémo de
    # fraîcheur ne regardait que le document, le second chargement suivrait
    # l'index grossier et ne trouverait pas le chemin que le nouveau apporte
    chemin = str(tmp_path / "refait.json")
    objet = {"a": {"b": list(range(200))}}
    serializejson.dump(objet, chemin, index="sidecar", index_threshold=10 ** 6)
    assert serializejson.load(chemin, path="root['a']") == objet["a"]  # mémorise
    serializejson.index(chemin, threshold=16)
    assert "root['a']['b']" in indexation.lit(chemin)["paths"]


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
@pytest.mark.parametrize("bloquant", ("blocking", "fast_release"))
def test_index_et_base64_encode_par_le_thread(tmp_path, bloquant):
    # PIÈGE : une grosse trame compressée est REMISE TELLE QUELLE au thread
    # d'écriture, qui en fait le base64 plus tard — les octets ne sont donc pas
    # encore écrits quand l'écrivain relève ses positions. Elles restent justes
    # parce que le compte des octets déposés compte la taille ENCODÉE (voir
    # WriterThread::depose) ; sans quoi tout ce qui suit serait décalé.
    # Données incompressibles : la trame doit dépasser la tranche du flux.
    alea = numpy.random.RandomState(0).bytes(400000)
    obj = {"gros": numpy.frombuffer(alea, dtype="uint8"),
           "apres": [{"x": i, "notes": list(range(20))} for i in range(200)]}
    chemin = str(tmp_path / "b64.json")
    encodeur = serializejson.Encoder(index="sidecar", index_threshold=64,
                                     disk_write_mode=bloquant)
    encodeur.dump(obj, chemin)
    serializejson.wait_writes()
    with open(chemin, "rb") as f:
        donnees = f.read()
    index = indexation.lit(chemin)["paths"]
    assert index == indexation.balaye(donnees, 64)
    assert "root['apres'][199]" in index


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0,
                    reason="un dossier en lecture seule n'arrête pas root")
@pytest.mark.parametrize("mode", ("blocking", "fast_release"))
def test_index_impossible_a_ranger_crie(tmp_path, mode):
    # PIÈGE : l'index se range dans le THREAD d'écriture, où plus personne
    # n'attend — un sidecar impossible à écrire n'y a plus d'appelant à qui le
    # dire. L'erreur doit sortir quand même : de dump en écriture bloquante,
    # de la prochaine attente en libération rapide. Sans quoi un index
    # silencieusement absent ferait relire tout le document, sans un mot.
    dossier = tmp_path / "ferme"
    dossier.mkdir()
    chemin = str(dossier / "x.json")
    encodeur = serializejson.Encoder(index="sidecar", index_threshold=16,
                                     disk_write_mode=mode)
    fichier = open(chemin, "wb")     # ouvert AVANT : le json, lui, s'écrit
    os.chmod(str(dossier), 0o500)    # plus rien de neuf dans le dossier
    try:
        with pytest.raises(OSError):
            encodeur.dump({"a": list(range(200))}, fichier)
            serializejson.wait_writes()
    finally:
        os.chmod(str(dossier), 0o700)
    assert not os.path.exists(indexation.chemin_sidecar(chemin))
    # l'erreur est CONSOMMÉE : elle ne doit pas revenir hanter le dump suivant
    serializejson.wait_writes()


def test_balaye_donne_des_tranches_json_valides(tmp_path):
    chemin = ecrit(tmp_path, corpus())
    with open(chemin, "rb") as f:
        donnees = f.read()
    for debut, fin in indexation.lit(chemin)["paths"].values():
        json.loads(donnees[debut:fin])
