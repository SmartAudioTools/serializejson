"""Authenticated encryption of serialized documents, in the age v1 format.

age (https://age-encryption.org/v1, specification C2SP) was chosen for its
long-term resilience: a public, frozen specification, several independent
implementations (age in Go, rage in Rust, typage in TypeScript...) and
official test vectors. A document written here can be decrypted without
serializejson (``age -d``) and read with any json parser.

Only the passphrase recipient (scrypt stanza) is implemented: the key is a
password, the same one encrypts and decrypts. The payload is ChaCha20-Poly1305
in 64 KiB segments: any modified, removed, swapped or appended byte makes
decryption fail, never returning partial data.

The primitives come from the ``cryptography`` package, imported lazily: it is
needed only when a key is given (``pip install serializejson[crypto]``).
When OpenSSL's libcrypto is found at run time (dlopen, no build dependency),
the payload segments are processed by the C extension instead, spread over
several threads with the GIL released; the output is identical byte for byte.
"""

import base64
import hmac
import os
import re
import threading

__all__ = ["DecryptionError", "encrypt", "decrypt", "is_encrypted"]

ENTETE = b"age-encryption.org/v1\n"
DEBUT_ARMURE = "-----BEGIN AGE ENCRYPTED FILE-----"
FIN_ARMURE = "-----END AGE ENCRYPTED FILE-----"
SEGMENT = 64 * 1024
ETIQUETTE = 16

# facteur de travail scrypt écrit : 18, celui de l'outil age (~1 s, 256 Mio).
# Relu : jusqu'à 22 comme age ; au-delà le fichier est refusé AVANT tout
# calcul — un fichier piégé ne doit pas pouvoir réclamer des minutes et des Go
LOGN_ECRITURE = 18
LOGN_MAX = 22

_ETIQUETTE_SCRYPT = b"age-encryption.org/v1/scrypt"
_B64_CANONIQUE = re.compile(rb"[A-Za-z0-9+/]*")
_ENTIER = re.compile(rb"[1-9][0-9]*")

MESSAGE_AUTHENTIFICATION = ("decryption failed: the data was modified or the"
                            " password is wrong")


class DecryptionError(ValueError):
    """The encrypted data is malformed, modified, or the password is wrong."""


def _crypto():
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import (
            ChaCha20Poly1305)
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as e:
        raise ImportError(
            "encryption_key needs the 'cryptography' package:"
            " pip install serializejson[crypto]") from e
    return InvalidTag, ChaCha20Poly1305, Scrypt


# Charge utile en C (rapidjson._age_payload) : libcrypto chargée à l'exécution,
# segments répartis sur plusieurs fils, ×6 mesuré sur 64 Mo. Sans libcrypto,
# voie python (cryptography), mêmes octets. None : pas encore tenté.
_voie_c = None


def _payload_c():
    global _voie_c
    if _voie_c is None:
        _voie_c = False
        from . import rapidjson
        for nom in ("libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so"):
            try:
                rapidjson.load_crypto_library(nom)
            except (OSError, AttributeError):
                continue
            _voie_c = rapidjson._age_payload
            break
    return _voie_c


def check_key(key):
    """Validate an ``encryption_key`` argument (None allowed: no encryption)."""
    if key is None:
        return
    if not isinstance(key, str):
        raise TypeError("encryption_key must be a str password, not %s"
                        % type(key).__name__)
    if not key:
        raise ValueError("encryption_key must not be empty")
    _crypto()


# --- dérivations ---------------------------------------------------------------


def _scrypt(mot_de_passe, sel, logn):
    Scrypt = _crypto()[2]
    return Scrypt(salt=_ETIQUETTE_SCRYPT + sel, length=32, n=1 << logn,
                  r=8, p=1).derive(mot_de_passe)


def _hkdf(cle, sel, info):
    # HKDF-SHA256 (RFC 5869) à 32 octets = extraction + UN bloc d'expansion,
    # par hmac.digest (hashlib, en C) : ~0,5 µs contre 3,4 par les objets de
    # cryptography. Sel vide = clé HMAC nulle, que HMAC complète de zéros
    # comme le sel de 32 zéros de la RFC ; les vecteurs officiels le prouvent.
    prk = hmac.digest(sel, cle, "sha256")
    return hmac.digest(prk, info + b"\x01", "sha256")


def _mac(file_key, entete):
    return hmac.digest(_hkdf(file_key, b"", b"header"), entete, "sha256")


def _b64(octets):
    return base64.b64encode(octets).rstrip(b"=")


def _de_b64(texte):
    # base64 standard SANS remplissage et CANONIQUE (bits de queue nuls) :
    # deux graphies d'un même octet feraient deux fichiers qui s'ouvrent
    if not _B64_CANONIQUE.fullmatch(texte) or len(texte) % 4 == 1:
        raise DecryptionError("invalid age header: bad base64")
    octets = base64.b64decode(texte + b"=" * (-len(texte) % 4))
    if _b64(octets) != texte:
        raise DecryptionError("invalid age header: non canonical base64")
    return octets


# --- caches ----------------------------------------------------------------------
#
# scrypt coûte ~1 s par dérivation (c'est son rôle : freiner la force brute).
# Sans cache, chaque dump et chaque load paieraient cette seconde.
# - Lecture : (mot de passe, sel, logN) -> clé d'emballage.
# - Écriture : (mot de passe, logN) -> EN-TÊTE COMPLET (stanza + MAC) et sa
#   file key, réutilisés tels quels par les écritures suivantes. On NE PEUT PAS
#   réutiliser seulement le sel avec une file key neuve : la stanza emballe la
#   file key sous un nonce NUL imposé par la spec, deux file keys sous la même
#   clé d'emballage réutiliseraient le couple (clé, nonce) de ChaCha20-Poly1305
#   (fuite du XOR des file keys, clé Poly1305 à usage unique réutilisée). Un
#   en-tête réutilisé à l'identique n'emballe, lui, qu'UNE file key. La charge
#   reste propre à chaque document : sa clé de flux est dérivée de la file key
#   ET d'un nonce aléatoire de 128 bits tiré à chaque écriture — c'est lui qui
#   garantit qu'aucun flux ChaCha20 ne se répète. Ce que cela révèle : deux
#   documents chiffrés par le même mot de passe dans le même processus ont le
#   même en-tête, donc se reconnaissent comme tels ; qui connaît la file key
#   de l'un connaît le mot de passe de tous, rien de plus.
# Un document LU au mot de passe et au logN d'écriture fournit aussi son
# en-tête à l'écriture : relire puis réécrire ne coûte qu'un seul scrypt.

_verrou = threading.Lock()
_cles_lecture = {}
_entetes_ecriture = {}
_TAILLE_CACHE = 32


def _range(cache, cle, valeur):
    with _verrou:
        if len(cache) >= _TAILLE_CACHE:
            del cache[next(iter(cache))]
        cache[cle] = valeur


def _vide_caches():
    with _verrou:
        _cles_lecture.clear()
        _entetes_ecriture.clear()


def _entete_ecriture(mot_de_passe):
    logn = LOGN_ECRITURE
    trouve = _entetes_ecriture.get((mot_de_passe, logn))
    if trouve is not None:
        return trouve
    ChaCha20Poly1305 = _crypto()[1]
    sel = os.urandom(16)
    emballage = _scrypt(mot_de_passe.encode("utf-8"), sel, logn)
    file_key = os.urandom(16)
    corps = ChaCha20Poly1305(emballage).encrypt(bytes(12), file_key, None)
    entete = (ENTETE + b"-> scrypt " + _b64(sel) + b" " + b"%d" % logn
              + b"\n" + _b64(corps) + b"\n---")
    trouve = (entete + b" " + _b64(_mac(file_key, entete)) + b"\n", file_key)
    _range(_cles_lecture, (mot_de_passe, sel, logn), emballage)
    _range(_entetes_ecriture, (mot_de_passe, logn), trouve)
    return trouve


# --- chiffrement -----------------------------------------------------------------


def encrypt(data, password, armor=False):
    """Encrypt ``data`` (bytes) with ``password`` (str) into an age file.

    Returns the binary age file as bytes, or its ASCII armor as str if
    ``armor`` is true.
    """
    check_key(password)
    entete, file_key = _entete_ecriture(password)
    nonce = os.urandom(16)
    cle_flux = _hkdf(file_key, nonce, b"payload")
    c = _payload_c()
    if c:
        sortie = c(cle_flux, data, True, entete + nonce)
        return _en_armure(sortie) if armor else sortie
    aead = _crypto()[1](cle_flux)
    vue = memoryview(data)
    n = len(vue)
    derniers = max(1, -(-n // SEGMENT))
    # encrypt_into ne gagne ici RIEN : le tampon bytearray devrait être recopié
    # en bytes, type public de dumpb (mesuré : la copie mange le gain)
    morceaux = [entete, nonce]
    for k in range(derniers):
        morceaux.append(aead.encrypt(
            k.to_bytes(11, "big") + (b"\x01" if k == derniers - 1 else b"\x00"),
            vue[k * SEGMENT:(k + 1) * SEGMENT], None))
    sortie = b"".join(morceaux)
    return _en_armure(sortie) if armor else sortie


def _en_armure(octets):
    texte = base64.b64encode(octets).decode("ascii")
    lignes = [texte[i:i + 64] for i in range(0, len(texte), 64)]
    return "\n".join([DEBUT_ARMURE, *lignes, FIN_ARMURE, ""])


def _de_armure(texte):
    # la spec tolère des blancs autour de l'armure, rien d'autre : lignes de
    # 64 colonnes exactement sauf la dernière, base64 canonique
    texte = texte.strip(" \t\r\n")
    lignes = texte.split("\n")
    if (len(lignes) < 3 or lignes[0] != DEBUT_ARMURE
            or lignes[-1] != FIN_ARMURE):
        raise DecryptionError("invalid age armor")
    corps = lignes[1:-1]
    if (any(len(l) != 64 for l in corps[:-1])
            or not 0 < len(corps[-1]) <= 64):
        raise DecryptionError("invalid age armor: bad line length")
    b64 = "".join(corps).encode("ascii", "replace")
    if not re.fullmatch(rb"[A-Za-z0-9+/]*={0,2}", b64) or len(b64) % 4:
        raise DecryptionError("invalid age armor: bad base64")
    octets = base64.b64decode(b64)
    if base64.b64encode(octets) != b64:
        raise DecryptionError("invalid age armor: non canonical base64")
    return octets


def is_encrypted(data):
    """True if ``data`` (str or bytes-like) starts like an age file."""
    if isinstance(data, str):
        return data.lstrip(" \t\r\n").startswith(DEBUT_ARMURE)
    try:
        debut = bytes(memoryview(data)[:64])
    except TypeError:
        return False
    return (debut.startswith(ENTETE)
            or debut.lstrip(b" \t\r\n").startswith(DEBUT_ARMURE.encode()))


def decrypt(data, password):
    """Decrypt an age file (bytes, or armored str/bytes) with ``password``.

    Raises DecryptionError if the data is not an age file, is malformed or
    modified, or if the password is wrong.
    """
    check_key(password)
    if isinstance(data, str):
        if not is_encrypted(data):
            raise DecryptionError("data is not encrypted (not an age file)")
        data = _de_armure(data)
    else:
        data = bytes(data)
        if not data.startswith(ENTETE):
            if not is_encrypted(data):
                raise DecryptionError(
                    "data is not encrypted (not an age file)")
            try:
                data = _de_armure(data.decode("ascii"))
            except UnicodeDecodeError:
                raise DecryptionError("invalid age armor") from None
    file_key, fin_entete = _ouvre_entete(data, password)
    return _dechiffre_charge(data, fin_entete, file_key)


def _ouvre_entete(data, mot_de_passe):
    InvalidTag, ChaCha20Poly1305, _ = _crypto()
    fin_mac = data.find(b"\n--- ")
    if fin_mac < 0:
        raise DecryptionError("invalid age header")
    fin_ligne = data.find(b"\n", fin_mac + 1)
    if fin_ligne < 0:
        raise DecryptionError("invalid age header")
    entete = data[:fin_mac + 4]
    lignes = entete[len(ENTETE):].split(b"\n")
    # une seule stanza, scrypt, à deux arguments, corps d'une ligne : la spec
    # interdit toute autre stanza à côté d'une stanza scrypt
    if len(lignes) != 3 or not lignes[0].startswith(b"-> "):
        raise DecryptionError("invalid age header: expected one scrypt"
                              " stanza")
    args = lignes[0][3:].split(b" ")
    if args[0] != b"scrypt":
        raise DecryptionError("no scrypt stanza: not a password-encrypted"
                              " age file")
    if len(args) != 3:
        raise DecryptionError("invalid age header: bad scrypt stanza")
    sel = _de_b64(args[1])
    if len(sel) != 16:
        raise DecryptionError("invalid age header: bad scrypt salt")
    if not _ENTIER.fullmatch(args[2]) or int(args[2]) > LOGN_MAX:
        raise DecryptionError("invalid age header: bad or excessive scrypt"
                              " work factor")
    logn = int(args[2])
    corps = _de_b64(lignes[1])
    if len(corps) != 32 or len(lignes[1]) >= 64:
        raise DecryptionError("invalid age header: bad scrypt stanza body")
    cle_cache = (mot_de_passe, sel, logn)
    emballage = _cles_lecture.get(cle_cache)
    if emballage is None:
        emballage = _scrypt(mot_de_passe.encode("utf-8"), sel, logn)
    try:
        file_key = ChaCha20Poly1305(emballage).decrypt(bytes(12), corps, None)
    except InvalidTag:
        raise DecryptionError(MESSAGE_AUTHENTIFICATION) from None
    _range(_cles_lecture, cle_cache, emballage)
    mac = _de_b64(data[fin_mac + 5:fin_ligne])
    if len(mac) != 32 or not hmac.compare_digest(mac, _mac(file_key, entete)):
        raise DecryptionError(MESSAGE_AUTHENTIFICATION)
    if logn == LOGN_ECRITURE and (mot_de_passe, logn) not in _entetes_ecriture:
        _range(_entetes_ecriture, (mot_de_passe, logn),
               (data[:fin_ligne + 1], file_key))
    return file_key, fin_ligne + 1


def _dechiffre_charge(data, debut, file_key):
    InvalidTag, ChaCha20Poly1305, _ = _crypto()
    nonce = data[debut:debut + 16]
    if len(nonce) != 16:
        raise DecryptionError(MESSAGE_AUTHENTIFICATION)
    cle_flux = _hkdf(file_key, nonce, b"payload")
    vue = memoryview(data)[debut + 16:]
    n = len(vue)
    plein = SEGMENT + ETIQUETTE
    # au moins un segment ; le dernier porte le drapeau, et n'est vide que
    # s'il est le seul (sinon le précédent aurait dû être le dernier)
    derniers = max(1, -(-n // plein))
    taille = n - ETIQUETTE * derniers
    if taille < 0 or (derniers > 1 and taille == SEGMENT * (derniers - 1)):
        raise DecryptionError(MESSAGE_AUTHENTIFICATION)
    c = _payload_c()
    if c:
        sortie = c(cle_flux, vue, False)
        if sortie is None:
            raise DecryptionError(MESSAGE_AUTHENTIFICATION)
        return sortie
    # déchiffré EN PLACE dans un tampon unique, remis tel quel au parseur
    # (qui lit un bytearray) : ni morceaux ni copie finale, −10 à −19 %
    aead = ChaCha20Poly1305(cle_flux)
    sortie = bytearray(taille)
    cible = memoryview(sortie)
    try:
        for k in range(derniers):
            segment = vue[k * plein:(k + 1) * plein]
            aead.decrypt_into(
                k.to_bytes(11, "big")
                + (b"\x01" if k == derniers - 1 else b"\x00"),
                segment, None,
                cible[k * SEGMENT:k * SEGMENT + len(segment) - ETIQUETTE])
    except InvalidTag:
        raise DecryptionError(MESSAGE_AUTHENTIFICATION) from None
    return sortie
