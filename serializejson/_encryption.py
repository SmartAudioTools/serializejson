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

The primitives (scrypt, ChaCha20-Poly1305) come from libsodium, linked into
the C extension, natively as in the WebAssembly build: no dependency at run
time, and one cryptographic chain on every platform. The payload segments are
spread over several threads with the GIL released.
"""

import base64
import hmac
import os
import re
import threading

from . import rapidjson

__all__ = ["DecryptionError", "encrypt", "decrypt", "is_encrypted",
           "salt", "prime"]

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


def check_key(key):
    """Validate an ``encryption_key`` argument (None allowed: no encryption)."""
    if key is None:
        return
    if not isinstance(key, str):
        raise TypeError("encryption_key must be a str password, not %s"
                        % type(key).__name__)
    if not key:
        raise ValueError("encryption_key must not be empty")


# --- dérivations ---------------------------------------------------------------


def _scrypt(mot_de_passe, sel, logn):
    return rapidjson._scrypt(mot_de_passe, _ETIQUETTE_SCRYPT + sel, 1 << logn,
                             8, 1, 32)


def _hkdf(cle, sel, info):
    # HKDF-SHA256 (RFC 5869) à 32 octets = extraction + UN bloc d'expansion,
    # par hmac.digest (hashlib, en C) : ~0,5 µs contre 3,4 par les objets du
    # paquet cryptography. Sel vide = clé HMAC nulle, que HMAC complète de zéros
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
# - Ouverture : (mot de passe, en-tête EXACT, MAC compris) -> file key. Un
#   en-tête déjà authentifié sous ce mot de passe l'est à nouveau à l'octet
#   près (unwrap et MAC sont des fonctions de ces seules entrées) : relire un
#   document de même en-tête — tous ceux qu'écrit un même processus — saute
#   analyse, unwrap et MAC (8,7 -> ~1 µs).

_verrou = threading.Lock()
_cles_lecture = {}
_entetes_ecriture = {}
_entetes_ouverts = {}
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
        _entetes_ouverts.clear()


def _entete_ecriture(mot_de_passe, sel=None):
    logn = LOGN_ECRITURE
    if sel is None:
        trouve = _entetes_ecriture.get((mot_de_passe, logn))
        if trouve is not None:
            return trouve
        sel = os.urandom(16)
    emballage = _scrypt(mot_de_passe.encode("utf-8"), sel, logn)
    file_key = os.urandom(16)
    corps = rapidjson._chacha20poly1305(emballage, bytes(12), file_key, True)
    entete = (ENTETE + b"-> scrypt " + _b64(sel) + b" " + b"%d" % logn
              + b"\n" + _b64(corps) + b"\n---")
    trouve = (entete + b" " + _b64(_mac(file_key, entete)) + b"\n", file_key)
    _range(_cles_lecture, (mot_de_passe, sel, logn), emballage)
    _range(_entetes_ecriture, (mot_de_passe, logn), trouve)
    _range(_entetes_ouverts, (mot_de_passe, trouve[0]), file_key)
    return trouve


def prime(password, salt):
    """Make the next encryptions with ``password``, in this process, write
    ``salt`` (16 bytes) in their scrypt stanza instead of a random one.

    For a password derived from the salt (a master secret and the salt
    through HMAC, say): whoever holds the master secret reads the salt of
    such a file (``salt``) and derives its password. Draw the salt at random
    (``os.urandom(16)``), derive the password, then prime.
    """
    check_key(password)
    if not isinstance(salt, bytes) or len(salt) != 16:
        raise ValueError("salt must be 16 bytes")
    _entete_ecriture(password, salt)


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
    sortie = rapidjson._age_payload(cle_flux, data, True, entete + nonce)
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
    data = _binaire(data)
    file_key, fin_entete = _ouvre_entete(data, password)
    return _dechiffre_charge(data, fin_entete, file_key)


def salt(data):
    """The scrypt salt (16 bytes) of an age file (bytes, or armored str/bytes).

    It is written in clear in the header, readable without the password: see
    ``prime``. Raises DecryptionError if ``data`` is not a password-encrypted
    age file.
    """
    data = _binaire(data)
    fin_mac, _ = _fin_entete(data)
    return _stanza(data[:fin_mac + 4])[0]


def _binaire(data):
    # le fichier age binaire, désarmuré s'il le faut
    if isinstance(data, str):
        if not is_encrypted(data):
            raise DecryptionError("data is not encrypted (not an age file)")
        return _de_armure(data)
    data = bytes(data)
    if data.startswith(ENTETE):
        return data
    if not is_encrypted(data):
        raise DecryptionError("data is not encrypted (not an age file)")
    try:
        return _de_armure(data.decode("ascii"))
    except UnicodeDecodeError:
        raise DecryptionError("invalid age armor") from None


def _fin_entete(data):
    # position du « \n--- » qui précède le MAC, et de la fin de sa ligne
    fin_mac = data.find(b"\n--- ")
    if fin_mac < 0:
        raise DecryptionError("invalid age header")
    fin_ligne = data.find(b"\n", fin_mac + 1)
    if fin_ligne < 0:
        raise DecryptionError("invalid age header")
    return fin_mac, fin_ligne


def _stanza(entete):
    # (sel, logn, corps) de l'unique stanza scrypt de l'en-tête
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
    corps = _de_b64(lignes[1])
    if len(corps) != 32 or len(lignes[1]) >= 64:
        raise DecryptionError("invalid age header: bad scrypt stanza body")
    return sel, int(args[2]), corps


def _ouvre_entete(data, mot_de_passe):
    fin_mac, fin_ligne = _fin_entete(data)
    ouvert = (mot_de_passe, data[:fin_ligne + 1])
    file_key = _entetes_ouverts.get(ouvert)
    if file_key is not None:
        return file_key, fin_ligne + 1
    entete = data[:fin_mac + 4]
    sel, logn, corps = _stanza(entete)
    cle_cache = (mot_de_passe, sel, logn)
    emballage = _cles_lecture.get(cle_cache)
    if emballage is None:
        emballage = _scrypt(mot_de_passe.encode("utf-8"), sel, logn)
    file_key = rapidjson._chacha20poly1305(emballage, bytes(12), corps, False)
    if file_key is None:
        raise DecryptionError(MESSAGE_AUTHENTIFICATION)
    _range(_cles_lecture, cle_cache, emballage)
    mac = _de_b64(data[fin_mac + 5:fin_ligne])
    if len(mac) != 32 or not hmac.compare_digest(mac, _mac(file_key, entete)):
        raise DecryptionError(MESSAGE_AUTHENTIFICATION)
    if logn == LOGN_ECRITURE and (mot_de_passe, logn) not in _entetes_ecriture:
        _range(_entetes_ecriture, (mot_de_passe, logn),
               (data[:fin_ligne + 1], file_key))
    _range(_entetes_ouverts, ouvert, file_key)
    return file_key, fin_ligne + 1


def _dechiffre_charge(data, debut, file_key):
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
    # déchiffré dans un tampon unique, remis tel quel au parseur (qui lit un
    # bytearray) : ni morceaux ni copie finale
    sortie = rapidjson._age_payload(cle_flux, vue, False)
    if sortie is None:
        raise DecryptionError(MESSAGE_AUTHENTIFICATION)
    return sortie
