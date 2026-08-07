"""Position index: load one object of a json file without parsing the rest.

L'index associe à chaque conteneur assez gros du document (`threshold` octets
au moins) ses positions de début et de fin dans le fichier, sous la grammaire
de chemins des `$ref` de serializejson (``root['clé'].attribut[0]``). Il se
range au choix, par le paramètre `index` de l'encodeur :

- ``"sidecar"`` : un fichier caché du même nom précédé d'un point, posé à
  côté du json — le json reste un json valide pour tout le monde ;
- ``"comment"`` : deux lignes de commentaire ajoutées à la fin du json — un
  seul fichier à déplacer, mais le fichier n'est plus du json standard.

L'index est CONSTRUIT PAR BALAYAGE du json produit, pas par instrumentation
de l'écrivain : la même fonction indexe donc un fichier déjà écrit, et
l'écriture ne paie rien quand l'index n'est pas demandé.
"""

import json
import os
import re

# lignes ajoutées en fin de json par la forme "comment". Le pied est de
# LARGEUR FIXE : une seule lecture de sa longueur, en fin de fichier, donne la
# position de l'index — sans quoi il faudrait remonter le fichier à l'aveugle
MARQUEUR = b"//serializejson_index "
PIED = b"//serializejson_index_start:"
LARGEUR_POSITION = 20
LONGUEUR_PIED = len(PIED) + LARGEUR_POSITION + 1

FORMES = ("sidecar", "comment")
SEUIL_DEFAUT = 1024

# index déjà lus, par chemin : {chemin: ((taille, mtime_ns), index)}
_memoire = {}

# jetons de STRUCTURE du json : chaînes complètes (pour sauter d'un coup ce
# qu'elles contiennent) et ponctuation. Les nombres, true, false et null ne
# contiennent aucun de ces caractères : les ignorer est sans risque
_JETONS = re.compile(rb'"(?:[^"\\]|\\.)*"|[][{}:,]')

# {"$ref": "..."} tel que l'écrivain l'émet, sur une seule ligne : une chaîne
# de DONNÉES qui contiendrait ce texte serait échappée (\") et ne peut donc
# pas être confondue avec un vrai marqueur
_REF = re.compile(rb'\{"\$ref": "((?:[^"\\]|\\.)*)"\}')

# segments de la grammaire des chemins, dans l'ordre où ils s'écrivent
_SEGMENT = re.compile(r"\['(?:(?!'\]).)*'\]|\[\d+\]|\.[^.\[]+")

# marqueur des références qui pointent HORS de la tranche chargée : le chemin
# ne commence plus par "root", donc ni le résolveur C ni from_name n'y
# touchent — elles arrivent intactes dans duplicates_to_replace
HORS = "hors:"


def chemin_sidecar(chemin):
    """Path of the hidden sidecar index of `chemin`."""
    dossier, nom = os.path.split(chemin)
    return os.path.join(dossier, "." + nom)


def _decode_cle(jeton):
    # le jeton est la clé telle qu'ÉCRITE, guillemets compris : les chemins,
    # eux, portent la clé réelle (l'échappement du $ref est défait par le
    # parseur quand le chemin est relu)
    if b"\\" in jeton:
        return json.loads(jeton)
    return jeton[1:-1].decode("utf-8")


class _Conteneur:
    __slots__ = ("chemin", "debut", "liste", "attrs", "n", "cle", "attend_cle",
                 "premiere")

    def __init__(self, chemin, debut, liste):
        self.chemin = chemin
        self.debut = debut
        self.liste = liste
        self.attrs = False
        self.n = 0
        self.cle = ""
        self.attend_cle = not liste
        self.premiere = True

    def chemin_enfant(self):
        if self.liste:
            return "%s[%d]" % (self.chemin, self.n)
        if self.attrs:
            return "%s.%s" % (self.chemin, self.cle)
        return "%s['%s']" % (self.chemin, self.cle)


def balaye(donnees, seuil=SEUIL_DEFAUT, fin=None):
    """Scan json bytes, return {path: [start, stop]} for big enough containers.

    Args:
        donnees: the json bytes.
        seuil: containers smaller than that many bytes are not indexed.
        fin: end of the json document in `donnees` (its length by default).
    """
    if fin is None:
        fin = len(donnees)
    entrees = {}
    pile = []
    for m in _JETONS.finditer(donnees, 0, fin):
        jeton = m.group()
        tete = jeton[0]
        if tete == 0x7B or tete == 0x5B:            # { ou [
            chemin = pile[-1].chemin_enfant() if pile else "root"
            pile.append(_Conteneur(chemin, m.start(), tete == 0x5B))
        elif tete == 0x7D or tete == 0x5D:          # } ou ]
            conteneur = pile.pop()
            if m.end() - conteneur.debut >= seuil:
                entrees[conteneur.chemin] = [conteneur.debut, m.end()]
        elif tete == 0x22:                          # une chaîne
            conteneur = pile[-1]
            if conteneur.attend_cle:
                conteneur.cle = _decode_cle(jeton)
                if conteneur.premiere:
                    # une enveloppe d'objet commence par "__class__" : ses
                    # autres clés sont des ATTRIBUTS (chemins en « .nom »),
                    # exactement la règle attrsDict de l'écrivain
                    conteneur.attrs = conteneur.cle == "__class__"
                    conteneur.premiere = False
        elif tete == 0x3A:                          # :
            pile[-1].attend_cle = False
        else:                                       # ,
            conteneur = pile[-1]
            if conteneur.liste:
                conteneur.n += 1
            else:
                conteneur.attend_cle = True
    # la racine est indexée quelle que soit sa taille : c'est elle qui donne
    # l'étendue du document, et le point de départ de toute recherche
    entrees["root"] = [0, fin]
    return entrees


def etendue(f):
    """Return (end of the json document, start of the index line) of a binary
    file that may carry an index in comment form — (its size, None) if not.

    Le fichier est laissé au début, prêt à être lu. Le pied de largeur fixe
    évite de remonter le fichier : une seule lecture, à la fin.
    """
    taille = os.fstat(f.fileno()).st_size
    debut = None
    if taille > LONGUEUR_PIED:
        f.seek(taille - LONGUEUR_PIED)
        pied = f.read(LONGUEUR_PIED)
        if pied.startswith(PIED):
            debut = int(pied[len(PIED):])
    f.seek(0)
    return (taille, None) if debut is None else (debut - 1, debut)


def construit(chemin, forme="sidecar", seuil=SEUIL_DEFAUT):
    """Build the index of an already written json file.

    Args:
        chemin: path of the json file.
        forme: `"sidecar"` (hidden file) or `"comment"` (end of the json).
        seuil: containers smaller than that many bytes are not indexed.

    Return:
        the index, as the dict written on disk.
    """
    if forme not in FORMES:
        raise ValueError("index must be one of %s"
                         % ", ".join(repr(f) for f in FORMES))
    with open(chemin, "rb") as f:
        # un index déjà en place ne fait pas partie du document à indexer
        fin, _ = etendue(f)
        donnees = f.read(fin)
    index = {"serializejson_index": 1, "size": fin, "threshold": seuil,
             "paths": balaye(donnees, seuil, fin)}
    texte = json.dumps(index, ensure_ascii=False).encode("utf-8")
    if forme == "sidecar":
        with open(chemin_sidecar(chemin), "wb") as f:
            f.write(texte)
    else:
        with open(chemin, "r+b") as f:
            f.truncate(fin)
            f.seek(fin)
            f.write(b"\n" + MARQUEUR + texte + b"\n")
            f.write(PIED + b"%0*d\n" % (LARGEUR_POSITION, fin + 1))
    return index


def lit(chemin):
    """Return the index of a json file, or None if it has none or a stale one.

    Le contrôle de fraîcheur est la TAILLE du document : un fichier réécrit
    sans son index laisse un index périmé, qu'il vaut mieux ignorer que
    suivre vers de mauvaises positions.

    L'index est mémorisé d'un appel à l'autre : aller chercher plusieurs
    objets dans le même fichier est l'usage même de l'index, et le relire
    chaque fois coûtait plus que le gain sur un fichier de taille modeste.
    """
    try:
        etat = os.stat(chemin)
        taille = etat.st_size
    except OSError:
        return None
    memoire = _memoire.get(chemin)
    if memoire is not None and memoire[0] == (taille, etat.st_mtime_ns):
        return memoire[1]
    index = _lit_du_disque(chemin, taille)
    if len(_memoire) > 8:
        _memoire.clear()
    _memoire[chemin] = ((taille, etat.st_mtime_ns), index)
    return index


def _lit_du_disque(chemin, taille):
    index = None
    sidecar = chemin_sidecar(chemin)
    if os.path.exists(sidecar):
        try:
            with open(sidecar, "rb") as f:
                index = json.loads(f.read())
        except (OSError, ValueError):
            return None
    else:
        with open(chemin, "rb") as f:
            fin, debut_index = etendue(f)
            if debut_index is None:
                return None
            f.seek(debut_index)
            ligne = f.read(taille - debut_index - LONGUEUR_PIED)
            if not ligne.startswith(MARQUEUR):
                return None
            try:
                index = json.loads(ligne[len(MARQUEUR):])
            except ValueError:
                return None
        taille = fin
    if not isinstance(index, dict) or index.get("size") != taille:
        return None
    return index


def prefixes(chemin_objet):
    """Yield the path and its ancestors, from the deepest to the root."""
    segments = _SEGMENT.findall(chemin_objet)
    reste = ""
    while segments:
        yield "root" + "".join(segments), reste
        reste = segments.pop() + reste
    yield "root", reste


def _sous_chemin(chemin, prefixe):
    # `chemin` désigne-t-il `prefixe` ou l'un de ses descendants ? La coupe
    # doit tomber sur une FRONTIÈRE de segment : root.ab n'est pas sous root.a
    if chemin == prefixe:
        return ""
    if chemin.startswith(prefixe) and chemin[len(prefixe)] in ".[":
        return chemin[len(prefixe):]
    return None


def rebase_refs(tranche, prefixe):
    """Rewrite the `$ref` paths of a slice extracted at `prefixe`.

    Les références INTERNES à la tranche sont ramenées sur sa propre racine ;
    les EXTERNES sont marquées, pour être chargées depuis le fichier.
    """
    def remplace(m):
        cible = json.loads(b'"' + m.group(1) + b'"')
        interne = _sous_chemin(cible, prefixe)
        nouveau = ("root" + interne if interne is not None
                   else HORS + cible)
        return b'{"$ref": ' + json.dumps(nouveau).encode("utf-8") + b"}"

    return _REF.sub(remplace, tranche)


class Circulaire(Exception):
    """Deux objets d'un même fichier se référencent : rien à gagner à les
    charger par tranches, l'appelant relit le document en entier."""


def _resolveur(decodeur, charge_externe):
    # les marqueurs HORS arrivent ici parce qu'aucun résolveur ne sait les
    # lire : on les remplace par les objets chargés depuis le fichier, puis
    # on laisse la post-passe habituelle traiter les références internes
    from . import _replace_ref_placeholders

    original = type(decodeur)._resolve_duplicates

    def resolve(loaded):
        externes = {}
        internes = []
        for marqueur in decodeur.duplicates_to_replace:
            cible = marqueur.get("$ref")
            if isinstance(cible, str) and cible.startswith(HORS):
                externes[id(marqueur)] = charge_externe(cible[len(HORS):])
            else:
                internes.append(marqueur)
        if externes:
            decodeur.duplicates_to_replace = internes
            _replace_ref_placeholders(loaded, externes)
        return original(decodeur, loaded) if internes else loaded

    return resolve


def charge(fichier, chemin_objet, fabrique_decodeur, index=None):
    """Load one object of a json file, using its index.

    Args:
        fichier: path of the json file.
        chemin_objet: path of the wanted object, in the `$ref` grammar.
        fabrique_decodeur: callable returning a fresh `Decoder`.
        index: the already read index, read from the file if not given.

    Return:
        the object, or `NotImplemented` if the file has no usable index —
        the caller then reads the whole document.
    """
    import rapidjson

    if index is None:
        index = lit(fichier)
    if index is None:
        return NotImplemented
    entrees = index["paths"]
    charges = {}
    en_cours = set()

    def charge_chemin(cible):
        if cible in charges:
            return charges[cible]
        if cible in en_cours:
            raise Circulaire(cible)
        for prefixe, reste in prefixes(cible):
            if prefixe in entrees:
                break
        else:
            raise KeyError("%s not found in the index of %s"
                           % (cible, fichier))
        debut, fin = entrees[prefixe]
        en_cours.add(cible)
        try:
            f.seek(debut)
            tranche = f.read(fin - debut)
            if b'"$ref"' in tranche:
                tranche = rebase_refs(tranche, prefixe)
                decodeur = fabrique_decodeur()
                decodeur._resolve_duplicates = _resolveur(decodeur,
                                                          charge_chemin)
            else:
                decodeur = fabrique_decodeur()
            objet = decodeur.loads(tranche)
        finally:
            en_cours.discard(cible)
        if reste:
            objet = rapidjson._resolve_ref_path("root" + reste, objet)
            if objet is None:
                raise KeyError("%s not found in %s" % (cible, fichier))
        charges[cible] = objet
        return objet

    with open(fichier, "rb") as f:
        return charge_chemin(chemin_objet)
