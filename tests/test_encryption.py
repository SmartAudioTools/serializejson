"""Chiffrement authentifié des documents : format age v1, mot de passe (scrypt).

Deux familles de preuves :
- les vecteurs de test OFFICIELS d'age (C2SP/CCTV, age/testdata), copiés dans
  tests/age_testdata et vérifiés ici à l'octet par leur sha git : c'est la
  preuve d'interopérabilité avec les autres implémentations (age, rage...) ;
- les tests d'API : aller-retour par toutes les voies, altération de CHAQUE
  octet refusée, mauvais mot de passe, document chiffré lu sans clé, bornes
  des segments de 64 Kio, cache de scrypt.
"""

import hashlib
import io
import os
import re

import pytest

import serializejson
from serializejson import _encryption

pytest.importorskip("cryptography")

DOSSIER_VECTEURS = os.path.join(os.path.dirname(__file__), "age_testdata")

# sha git (blob) des vecteurs tels que publiés dans C2SP/CCTV : un vecteur qui
# ne correspond plus n'est plus le vecteur officiel, il ne prouve rien
SHA_OFFICIELS = {
    "scrypt": "57dd08f0e7b2312db772e8f24d786de3bb3da187",
    "armor_scrypt": "51e4092289f51de9efe2561be2b26885e50540ed",
    "scrypt_bad_tag": "b47512f0d17028b2b684b53248d07d3f5ce27d14",
    "scrypt_extra_argument": "3fa92ee932400a1646428ead4d88330775c1b4e2",
    "scrypt_long_file_key": "669c22257c94386469dff68ab80cb1152adf8856",
    "scrypt_no_match": "3d090e184d3eb69325430b9eebd2a5cc51ab1bd9",
    "scrypt_not_canonical_body": "65298afdcce6cf93b65003d1594c35a8e1076e79",
    "scrypt_salt_short": "a95f4608584930ff0805b2ba268f2b61c258e0e2",
    "scrypt_work_factor_23": "4d286beb1633f84968cc49dca4cfcaf714f75e93",
    "scrypt_work_factor_hex": "a1feca9aa4e54755b879c89c1e2041e7f1f24e74",
    "scrypt_work_factor_leading_zero_decimal":
        "303e2f97cfee62a79df29e2975a023729f6601b3",
}


def _lit_vecteur(nom):
    brut = open(os.path.join(DOSSIER_VECTEURS, nom), "rb").read()
    entete, corps = brut.split(b"\n\n", 1)
    champs = {}
    for ligne in entete.decode().split("\n"):
        cle, valeur = ligne.split(": ", 1)
        champs.setdefault(cle, valeur)
    return brut, champs, corps


@pytest.fixture(autouse=True)
def _scrypt_rapide(monkeypatch):
    # logN 18 (défaut d'écriture, celui de l'outil age) coûte ~1 s par
    # dérivation : les tests écrivent en logN 10 et repartent d'un cache vide
    monkeypatch.setattr(_encryption, "LOGN_ECRITURE", 10)
    _encryption._vide_caches()
    yield
    _encryption._vide_caches()


@pytest.fixture(autouse=True, params=["c", "python"])
def voie(request, monkeypatch):
    # chaque test passe par les DEUX voies de la charge utile : C (libcrypto
    # chargée à l'exécution) et python (cryptography), mêmes octets attendus
    if request.param == "python":
        monkeypatch.setattr(_encryption, "_voie_c", False)
    elif not _encryption._payload_c():
        pytest.skip("libcrypto introuvable : voie C indisponible")
    return request.param


# --- vecteurs officiels --------------------------------------------------------


def test_vecteurs_officiels_intacts():
    assert sorted(os.listdir(DOSSIER_VECTEURS)) == sorted(SHA_OFFICIELS)
    for nom, attendu in SHA_OFFICIELS.items():
        brut = open(os.path.join(DOSSIER_VECTEURS, nom), "rb").read()
        sha = hashlib.sha1(b"blob %d\0" % len(brut) + brut).hexdigest()
        assert sha == attendu, nom


@pytest.mark.parametrize("nom", sorted(SHA_OFFICIELS))
def test_vecteur_officiel(nom):
    _, champs, corps = _lit_vecteur(nom)
    if champs.get("armored") == "yes":
        corps = corps.decode("ascii")
    if champs["expect"] == "success":
        clair = _encryption.decrypt(corps, champs["passphrase"])
        assert hashlib.sha256(clair).hexdigest() == champs["payload"]
    else:
        with pytest.raises(_encryption.DecryptionError):
            _encryption.decrypt(corps, champs["passphrase"])


def test_facteur_de_travail_excessif_refuse_sans_calcul(monkeypatch):
    # un fichier piégé à logN 23+ ne doit pas faire calculer scrypt
    appels = []
    monkeypatch.setattr(_encryption, "_scrypt",
                        lambda *a: appels.append(a) or b"\0" * 32)
    _, champs, corps = _lit_vecteur("scrypt_work_factor_23")
    with pytest.raises(_encryption.DecryptionError):
        _encryption.decrypt(corps, champs["passphrase"])
    assert appels == []


# --- format écrit ---------------------------------------------------------------


def test_ecriture_conforme_au_format_age(monkeypatch):
    monkeypatch.setattr(_encryption, "LOGN_ECRITURE", 18)
    _encryption._vide_caches()
    chiffre = serializejson.dumpb({"a": 1}, encryption_key="secret")
    lignes = chiffre.split(b"\n")
    assert lignes[0] == b"age-encryption.org/v1"
    assert re.fullmatch(rb"-> scrypt [A-Za-z0-9+/]{22} 18", lignes[1])
    assert re.fullmatch(rb"[A-Za-z0-9+/]{43}", lignes[2])
    assert re.fullmatch(rb"--- [A-Za-z0-9+/]{43}", lignes[3])


def test_armure_conforme():
    armure = serializejson.dumps({"a": 1}, encryption_key="secret")
    assert isinstance(armure, str)
    lignes = armure.split("\n")
    assert lignes[0] == "-----BEGIN AGE ENCRYPTED FILE-----"
    assert lignes[-2] == "-----END AGE ENCRYPTED FILE-----"
    assert lignes[-1] == ""
    assert all(len(l) == 64 for l in lignes[1:-3])
    assert 0 < len(lignes[-3]) <= 64


@pytest.mark.parametrize("taille", [0, 1, 65535, 65536, 65537, 131072, 200000])
def test_segments_aux_bornes(taille):
    clair = os.urandom(taille)
    chiffre = _encryption.encrypt(clair, "secret")
    # 64 Kio pile = UN segment plein, le dernier ; 0 = un segment vide
    fin_entete = chiffre.index(b"\n--- ") + 49
    charge = len(chiffre) - fin_entete - 16
    segments = max(1, -(-taille // 65536))
    assert charge == taille + 16 * segments
    assert _encryption.decrypt(chiffre, "secret") == clair
    armure = _encryption.encrypt(clair, "secret", armor=True)
    assert _encryption.decrypt(armure, "secret") == clair


def test_segments_ne_peuvent_pas_etre_permutes_ni_retires():
    clair = os.urandom(3 * 65536 + 10)
    chiffre = bytearray(_encryption.encrypt(clair, "secret"))
    debut = chiffre.index(b"\n--- ") + 49 + 16
    s = 65536 + 16
    seg = [bytes(chiffre[debut + k * s:debut + (k + 1) * s]) for k in range(4)]
    tete = bytes(chiffre[:debut])
    for charge in (seg[1] + seg[0] + seg[2] + seg[3],  # permutés
                   seg[0] + seg[1] + seg[3],           # un retiré
                   seg[0] + seg[1] + seg[2],           # queue coupée
                   b"".join(seg) + seg[3]):            # queue rejouée
        with pytest.raises(_encryption.DecryptionError):
            _encryption.decrypt(tete + charge, "secret")


def test_dernier_segment_vide_refuse_apres_un_segment_plein():
    # la spec : le dernier segment n'est vide que s'il est le seul. Fabriqué
    # avec la VRAIE clé de flux (un écrivain fautif, pas un attaquant)
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    clair = os.urandom(65536)
    chiffre = _encryption.encrypt(clair, "secret")
    debut = chiffre.index(b"\n--- ") + 49
    entete, nonce = chiffre[:debut], bytes(chiffre[debut:debut + 16])
    _, file_key = _encryption._entete_ecriture("secret")
    aead = ChaCha20Poly1305(_encryption._hkdf(file_key, nonce, b"payload"))
    fautif = (entete + nonce
              + aead.encrypt(bytes(11) + b"\x00", clair, None)
              + aead.encrypt((1).to_bytes(11, "big") + b"\x01", b"", None))
    with pytest.raises(_encryption.DecryptionError):
        _encryption.decrypt(fautif, "secret")


# --- API ---------------------------------------------------------------------------

DOC = {"noms": ["alpha", "beta"], "valeurs": [1, 2.5, None],
       "octets": b"\x00\x01" * 100, "ensemble": {1, 2}}


def test_aller_retour_dumps_dumpb():
    armure = serializejson.dumps(DOC, encryption_key="secret")
    assert "valeurs" not in armure and "alpha" not in armure
    assert serializejson.loads(armure, encryption_key="secret") == DOC
    binaire = serializejson.dumpb(DOC, encryption_key="secret")
    assert binaire.startswith(b"age-encryption.org/v1\n")
    assert serializejson.loads(binaire, encryption_key="secret") == DOC


def test_aller_retour_fichier_sans_index(tmp_path):
    chemin = str(tmp_path / "doc.json")
    sidecar = str(tmp_path / ".doc.json")
    # un index laissé par un document EN CLAIR précédent décrirait sa
    # structure : il ne doit pas survivre à un dump chiffré
    serializejson.dump({"cle": list(range(5000))}, chemin, index="sidecar",
                       index_threshold=16)
    serializejson.wait_writes()
    assert os.path.exists(sidecar)
    serializejson.dump(DOC, chemin, encryption_key="secret")
    assert not os.path.exists(sidecar)
    serializejson.wait_writes()  # dump vers un chemin : asynchrone
    brut = open(chemin, "rb").read()
    assert brut.startswith(b"age-encryption.org/v1\n")
    assert b"alpha" not in brut
    assert serializejson.load(chemin, encryption_key="secret") == DOC
    assert os.listdir(tmp_path) == ["doc.json"]


def test_aller_retour_flux():
    flux = io.BytesIO()
    serializejson.dump(DOC, flux, encryption_key="secret")
    flux.seek(0)
    assert serializejson.load(flux, encryption_key="secret") == DOC
    texte = io.StringIO()
    serializejson.dump(DOC, texte, encryption_key="secret")
    assert texte.getvalue().startswith("-----BEGIN AGE ENCRYPTED FILE-----")
    texte.seek(0)
    assert serializejson.load(texte, encryption_key="secret") == DOC


def test_armure_relue_depuis_un_fichier(tmp_path):
    chemin = tmp_path / "doc.age"
    chemin.write_text(serializejson.dumps(DOC, encryption_key="secret"))
    assert serializejson.load(str(chemin), encryption_key="secret") == DOC


def test_api_par_classes(tmp_path):
    encoder = serializejson.Encoder(encryption_key="secret")
    decoder = serializejson.Decoder(encryption_key="secret")
    assert decoder.loads(encoder.dumps(DOC)) == DOC
    assert decoder.loads(encoder.dumpb(DOC)) == DOC
    chemin = str(tmp_path / "doc.json")
    encoder.dump(DOC, chemin)
    assert decoder.load(chemin) == DOC
    # l'appel direct de l'encodeur ne doit JAMAIS rendre du clair en silence
    assert decoder.loads(encoder(DOC)) == DOC
    assert encoder(DOC).startswith(b"age-encryption.org/v1\n")


def test_sous_classe_d_encodeur_chiffre_aussi():
    class MonEncodeur(serializejson.Encoder):
        pass

    encoder = MonEncodeur(encryption_key="secret")
    assert isinstance(encoder, MonEncodeur)
    assert encoder(DOC).startswith(b"age-encryption.org/v1\n")
    assert MonEncodeur()(DOC).startswith(b"{")


def test_alteration_de_chaque_octet_refusee():
    binaire = serializejson.dumpb({"note": 12}, encryption_key="secret")
    for i in range(len(binaire)):
        for masque in (0x01, 0x80):
            altere = bytearray(binaire)
            altere[i] ^= masque
            with pytest.raises(_encryption.DecryptionError):
                serializejson.loads(bytes(altere), encryption_key="secret")


def test_troncature_refusee():
    binaire = serializejson.dumpb(DOC, encryption_key="secret")
    for n in range(len(binaire)):
        with pytest.raises(_encryption.DecryptionError):
            serializejson.loads(binaire[:n], encryption_key="secret")
    with pytest.raises(_encryption.DecryptionError):
        serializejson.loads(binaire + b"\0", encryption_key="secret")


def test_alteration_de_l_armure_refusee():
    armure = serializejson.dumps({"note": 12}, encryption_key="secret")
    debut = armure.index("\n") + 1
    fin = armure.index("\n-----END")
    for i in range(debut, fin):
        if armure[i] == "\n":
            continue
        remplacant = "A" if armure[i] != "A" else "B"
        with pytest.raises(_encryption.DecryptionError):
            serializejson.loads(armure[:i] + remplacant + armure[i + 1:],
                                encryption_key="secret")


def test_mauvais_mot_de_passe():
    binaire = serializejson.dumpb(DOC, encryption_key="secret")
    with pytest.raises(_encryption.DecryptionError, match="password"):
        serializejson.loads(binaire, encryption_key="Secret")


def test_document_chiffre_lu_sans_cle(tmp_path):
    armure = serializejson.dumps(DOC, encryption_key="secret")
    with pytest.raises(ValueError, match="encryption_key"):
        serializejson.loads(armure)
    with pytest.raises(ValueError, match="encryption_key"):
        serializejson.loads(armure.encode())
    chemin = str(tmp_path / "doc.json")
    serializejson.dump(DOC, chemin, encryption_key="secret")
    with pytest.raises(ValueError, match="encryption_key"):
        serializejson.load(chemin)
    with pytest.raises(ValueError, match="encryption_key"):
        for _ in serializejson.load(chemin, iterator=True):
            pass


def test_cle_sur_document_en_clair():
    with pytest.raises(_encryption.DecryptionError, match="not encrypted"):
        serializejson.loads(serializejson.dumps(DOC), encryption_key="secret")


def test_voies_non_prises_en_charge(tmp_path):
    chemin = str(tmp_path / "liste.json")
    with pytest.raises(ValueError, match="encryption_key"):
        serializejson.append(1, chemin, encryption_key="secret")
    serializejson.dump([1, 2], chemin, encryption_key="secret")
    with pytest.raises(ValueError, match="encryption_key"):
        serializejson.load(chemin, iterator=True, encryption_key="secret")
    with pytest.raises(ValueError, match="encryption_key"):
        serializejson.load(chemin, path="root[0]", encryption_key="secret")
    with pytest.raises(ValueError, match="index"):
        serializejson.dump(DOC, chemin, index="sidecar",
                           encryption_key="secret")


def test_types_de_cle():
    with pytest.raises(TypeError):
        serializejson.dumpb(DOC, encryption_key=b"secret")
    with pytest.raises(ValueError):
        serializejson.dumpb(DOC, encryption_key="")


def test_reecriture_sans_nouveau_scrypt(monkeypatch):
    appels = []
    vrai = _encryption._scrypt

    def compte(*args):
        appels.append(args)
        return vrai(*args)

    monkeypatch.setattr(_encryption, "_scrypt", compte)
    a = serializejson.dumpb(DOC, encryption_key="secret")
    b = serializejson.dumpb(DOC, encryption_key="secret")
    assert serializejson.loads(a, encryption_key="secret") == DOC
    assert serializejson.loads(b, encryption_key="secret") == DOC
    assert len(appels) == 1
    # même en-tête, charges différentes (nonce de charge aléatoire)
    assert a != b
    serializejson.dumpb(DOC, encryption_key="autre")
    assert len(appels) == 2


def test_entete_deja_authentifie_non_rouvert(monkeypatch):
    binaire = serializejson.dumpb(DOC, encryption_key="secret")
    appels = []
    vrai = _encryption._mac
    monkeypatch.setattr(_encryption, "_mac",
                        lambda *a: appels.append(a) or vrai(*a))
    assert serializejson.loads(binaire, encryption_key="secret") == DOC
    assert appels == []
    # le cache ne vaut que pour cet en-tête exact et ce mot de passe
    fin = binaire.index(b"\n", binaire.index(b"\n--- ") + 1)
    altere = bytearray(binaire)
    altere[fin - 1] ^= 0x01
    for donnees, cle in ((bytes(altere), "secret"), (binaire, "Secret")):
        with pytest.raises(_encryption.DecryptionError):
            serializejson.loads(donnees, encryption_key=cle)


def test_sans_cle_rien_ne_change():
    assert serializejson.dumpb(DOC) == serializejson.dumpb(
        DOC, encryption_key=None)
    assert serializejson.loads(serializejson.dumps(DOC),
                               encryption_key=None) == DOC


def test_dump_chiffre_asynchrone_puis_load(tmp_path):
    # comme en clair, dump vers un chemin rend la main avant le disque :
    # load, wait_writes et la lecture brute après wait voient le document
    chemin = str(tmp_path / "doc.json")
    docs = [{"n": i, "charge": "x" * (70000 + i)} for i in range(4)]
    for doc in docs:
        serializejson.dump(doc, chemin, encryption_key="secret")
    assert serializejson.load(chemin, encryption_key="secret") == docs[-1]
    serializejson.dump(docs[0], chemin, encryption_key="secret")
    serializejson.wait_writes()
    brut = open(chemin, "rb").read()
    assert serializejson.loads(brut, encryption_key="secret") == docs[0]


@pytest.mark.parametrize("ordre", ["chiffre_puis_clair", "clair_puis_chiffre",
                                   "chiffre_puis_chiffre"])
def test_dumps_successifs_meme_chemin_le_dernier_gagne(tmp_path, ordre):
    chemin = str(tmp_path / "doc.json")
    gros = {"liste": list(range(200000))}
    petit = {"dernier": True}
    premier, second = {
        "chiffre_puis_clair": ("secret", None),
        "clair_puis_chiffre": (None, "secret"),
        "chiffre_puis_chiffre": ("secret", "secret"),
    }[ordre]
    serializejson.dump(gros, chemin, encryption_key=premier)
    serializejson.dump(petit, chemin, encryption_key=second)
    serializejson.wait_writes()
    assert serializejson.load(chemin, encryption_key=second) == petit


def test_dump_chiffre_bloquant_est_synchrone(tmp_path):
    chemin = str(tmp_path / "doc.json")
    encodeur = serializejson.Encoder(encryption_key="secret",
                                     disk_write_mode="blocking")
    encodeur.dump(DOC, chemin)
    # aucune attente : le fichier est complet au retour de dump
    brut = open(chemin, "rb").read()
    assert serializejson.loads(brut, encryption_key="secret") == DOC


def test_dump_chiffre_erreur_d_ouverture_levee_par_dump(tmp_path):
    with pytest.raises(OSError):
        serializejson.dump(DOC, str(tmp_path / "absent" / "doc.json"),
                           encryption_key="secret")
    serializejson.wait_writes()  # rien de différé en échec


def test_voies_c_et_python_memes_octets(monkeypatch, voie):
    # même en-tête (cache) et même nonce : la charge doit être identique
    # à l'octet, multi-segments et bornes de segment comprises
    if voie == "python":
        pytest.skip("comparaison faite une fois, sous la voie C")
    c_voie = _encryption._voie_c
    monkeypatch.setattr(_encryption.os, "urandom", lambda n: bytes(range(n)))
    for n in (0, 1, 65536, 65537, 20 * 65536 + 3):
        clair = bytes(i % 251 for i in range(n))
        c = _encryption.encrypt(clair, "secret")
        _encryption._voie_c = False
        try:
            p = _encryption.encrypt(clair, "secret")
            assert _encryption.decrypt(c, "secret") == clair
        finally:
            _encryption._voie_c = c_voie
        assert c == p, n
        assert _encryption.decrypt(p, "secret") == clair
