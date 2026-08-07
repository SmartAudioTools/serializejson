# Les commandes C0 (U+0000 à U+001F) DOIVENT être échappées : json ne les
# admet pas brutes dans une chaîne. L'écrivain n'échappait que la tabulation,
# le saut de ligne et le retour chariot ; les vingt-neuf autres sortaient
# telles quelles, produisant un document qu'aucun lecteur ne reprend — pas
# même le nôtre. Sans le correctif, le premier test échoue sur 0x00.
import json

import serializejson

COMMANDES = [chr(c) for c in range(0x20)]


def test_aller_retour_de_toutes_les_commandes():
    for c in COMMANDES:
        for objet in ([c], {c: 1}, [c * 40], [("a" * 7 + c) * 9]):
            dump = serializejson.dumpb(objet)
            assert serializejson.loads(dump) == objet, repr(c)


def test_document_valide_pour_un_lecteur_json_tiers():
    # le vrai enjeu : la sortie doit rester du json, lisible par autre chose
    # que nous. Les longueurs traversent le bloc de seize octets du balayage
    # vectoriel, et le débordement de tranche des très longues chaînes.
    for c in COMMANDES:
        for n in (1, 15, 16, 17, 40, 40000):
            dump = serializejson.dumpb([c * n])
            assert json.loads(dump.decode()) == [c * n], (repr(c), n)


def test_les_accentues_ne_sont_pas_pris_pour_des_commandes():
    # le test « <= 0x1F » se prend en non signé : pris en signé, tout octet
    # de continuation utf-8 tomberait dedans et serait échappé à tort.
    texte = "élève à l'école, où l'été fût très chaud — çà et là, naïf"
    for n in (1, 3, 100):
        dump = serializejson.dumpb([texte * n])
        assert json.loads(dump.decode()) == [texte * n]
        assert serializejson.loads(dump) == [texte * n]
