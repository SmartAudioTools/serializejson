import gc
import os
import time

import pytest

import serializejson


def _ecrit_liste(path, elements):
    encoder = serializejson.Encoder(str(path), indent=None)
    for element in elements:
        encoder.append(element)
    encoder.close()


def test_iterator():
    path = "my_list.json"
    if os.path.exists(path):
        os.remove(path)
    encoder = serializejson.Encoder(path, indent=None)
    elements = [False, True, 1, 2, "coucou", [1, 2]]
    for element in elements:
        encoder.append(element)
    # le fichier n'est un json complet qu'ici : le tampon de l'encodeur garde
    # le dernier maillon et le crochet fermant jusqu'à la fermeture. Avant, la
    # relecture anticipée voyait un document TRONQUÉ et zip() sautait
    # silencieusement le dernier élément — les six sont maintenant comparés
    encoder.close()
    print(open("my_list.json").read())
    for element, loaded_element in zip(elements, serializejson.Decoder(path)):
        assert element == loaded_element
        print(loaded_element)


def test_iterator_via_load(tmp_path):
    # load(path, iterator=True) doit rendre un itérateur qui lit CE fichier
    # (le paramètre file passait à la trappe : défaut préexistant)
    path = tmp_path / "liste.json"
    _ecrit_liste(path, [1, 2, 3])
    assert list(serializejson.load(str(path), iterator=True)) == [1, 2, 3]


def test_iterator_petits_maillons_sans_fil(tmp_path):
    # sous le seuil, l'itération reste sur la voie directe : aucun fil
    # n'est créé (le va-et-vient de fils coûterait plus que le décodage)
    path = tmp_path / "liste.json"
    _ecrit_liste(path, list(range(50)))
    decodeur = serializejson.Decoder(str(path))
    assert list(iter(decodeur)) == list(range(50))
    assert decodeur._avance is None


def test_iterator_avance_anticipe(tmp_path, monkeypatch):
    # la lecture d'avance doit décoder le maillon SUIVANT sans qu'on le
    # demande : après avoir pris le premier, le deuxième apparaît de
    # lui-même dans la file des résultats (seuil à zéro : fil engagé dès
    # le premier maillon)
    monkeypatch.setattr(serializejson, "_SEUIL_LECTURE_AVANCE", 0.0)
    path = tmp_path / "liste.json"
    _ecrit_liste(path, [1, 2, 3])
    decodeur = serializejson.Decoder(str(path))
    iterateur = iter(decodeur)
    assert next(iterateur) == 1  # chauffe des caches, pas encore de fil
    assert decodeur._avance is None
    assert next(iterateur) == 2  # la moyenne passe le seuil : fil engagé
    avance = decodeur._avance
    limite = time.monotonic() + 5.0
    while avance.resultats.qsize() == 0 and time.monotonic() < limite:
        time.sleep(0.001)
    assert avance.resultats.qsize() == 1  # le 3, décodé d'avance
    assert next(iterateur) == 3
    with pytest.raises(StopIteration):
        next(iterateur)
    # le protocole tient au-delà de la fin, et tout est refermé
    with pytest.raises(StopIteration):
        next(iterateur)
    avance.fil.join(5.0)
    assert not avance.fil.is_alive()
    assert avance.file_iter.closed


def test_iterator_abandon_ne_fuit_pas(tmp_path, monkeypatch):
    # itération abandonnée en cours de route : le décodeur meurt, son
    # finaliseur réveille le fil qui se termine et ferme le fichier
    monkeypatch.setattr(serializejson, "_SEUIL_LECTURE_AVANCE", 0.0)
    path = tmp_path / "liste.json"
    _ecrit_liste(path, list(range(6)))
    decodeur = serializejson.Decoder(str(path))
    iterateur = iter(decodeur)
    assert next(iterateur) == 0  # chauffe
    assert next(iterateur) == 1  # fil engagé
    avance = decodeur._avance
    fichier = avance.file_iter
    del iterateur, decodeur
    gc.collect()
    avance.fil.join(5.0)
    assert not avance.fil.is_alive()
    assert fichier.closed


def test_iterator_erreur_maillon(tmp_path, monkeypatch):
    # un maillon en erreur (classe non autorisée) lève chez l'appelant à SA
    # place dans la séquence — même sémantique que la voie directe d'avant
    # la lecture d'avance, y compris sa limite : le parse avorté laisse le
    # lecteur borné sur une frontière vide, l'itération s'arrête ensuite
    # (vérifié identique sans le fil)
    monkeypatch.setattr(serializejson, "_SEUIL_LECTURE_AVANCE", 0.0)
    path = tmp_path / "liste.json"
    path.write_bytes(
        b'[1,\n2,\n{"__class__": "collections.Counter", "__init__": [[1, 2]]},'
        b'\n3]'
    )
    decodeur = serializejson.Decoder(str(path))
    iterateur = iter(decodeur)
    assert next(iterateur) == 1  # chauffe
    assert next(iterateur) == 2  # fil engagé : l'erreur arrive par le fil
    with pytest.raises(TypeError):
        next(iterateur)
    with pytest.raises(StopIteration):
        next(iterateur)
    avance = decodeur._avance
    assert avance is None or not avance.fil.is_alive()


def test_iterator_reiteration(tmp_path, monkeypatch):
    # re-itérer le même décodeur relance une lecture propre : l'ancien fil
    # est arrêté, la séquence repart du début
    monkeypatch.setattr(serializejson, "_SEUIL_LECTURE_AVANCE", 0.0)
    path = tmp_path / "liste.json"
    _ecrit_liste(path, ["a", "b", "c"])
    decodeur = serializejson.Decoder(str(path))
    premier = iter(decodeur)
    assert next(premier) == "a"  # chauffe
    assert next(premier) == "b"  # fil engagé
    ancien = decodeur._avance
    assert list(iter(decodeur)) == ["a", "b", "c"]
    ancien.fil.join(5.0)
    assert not ancien.fil.is_alive()


def test_iterator_index_arme(tmp_path):
    # un dump vers un chemin pose un index par défaut : l'itération doit s'en
    # servir — chaque maillon indexé part au parseur en UNE lecture contiguë,
    # sans scan. Preuve de voie : les plages sont armées et toutes consommées
    objets = [{"img": os.urandom(9000)}, 5, {"img": os.urandom(9000)},
              "petit", None, {"queue": list(range(2000))}]
    for indent in ("\t", None):
        path = tmp_path / f"indexe_{indent is None}.json"
        serializejson.dump(objets, str(path), indent=indent)
        serializejson.wait_writes()
        decodeur = serializejson.Decoder(str(path))
        assert list(decodeur) == objets
        assert decodeur.file_iter.ranges is not None
        assert len(decodeur.file_iter.ranges) == 0


def test_iterator_index_refuse_apres_append_nu(tmp_path):
    # un append sans index périme l'index du dump initial (sa racine ne
    # couvre plus le document) : lit() le refuse, l'itération retombe sur le
    # scan intégral et rend quand même tout
    objets = [{"img": os.urandom(9000)}, 5, {"img": os.urandom(8000)}, None]
    path = tmp_path / "mixte.json"
    serializejson.dump(objets[:2], str(path))
    serializejson.wait_writes()
    encoder = serializejson.Encoder(file=str(path))
    for objet in objets[2:]:
        encoder.append(objet)
    encoder.close()
    decodeur = serializejson.Decoder(str(path))
    assert list(decodeur) == objets
    assert decodeur.file_iter.ranges is None


def test_iterator_chunk_minuscule(tmp_path):
    # un chunk plus petit que les séparateurs entre maillons produisait des
    # tranches vides que le parseur prenait pour la fin du fichier : un dump
    # indenté relu au chunk 7 rendait 1 maillon sur 6, en silence. La relecture
    # sur tranche vide corrige — SAUF quand le vide est le terminateur d'une
    # valeur simple continuée (« null » coupé pile avant sa virgule), qui doit
    # rester une fin de maillon. Les deux cas sont dans ce corpus
    objets = [5, "petit", None, True, {"a": 1}, [1, 2], "fin"]
    for indent in ("\t", None):
        path = tmp_path / f"minuscule_{indent is None}.json"
        serializejson.dump(objets, str(path), indent=indent, index=None)
        serializejson.wait_writes()
        assert list(serializejson.Decoder(str(path), chunk_size=7)) == objets


def test_iterator_chunk_minuscule_echappements(tmp_path):
    # variante du même défaut avec guillemets échappés denses (perdait des
    # maillons sur le binaire d'avant le correctif)
    objets = [('q"' * 30000) + "\\", 5, ('a"' * 100) + "\\", None]
    path = tmp_path / "echappements.json"
    _ecrit_liste(path, objets)
    assert list(serializejson.Decoder(str(path), chunk_size=7)) == objets


if __name__ == "__main__":
    test_iterator()
