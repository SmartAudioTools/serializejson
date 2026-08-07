"""Position index: load one object of a json file without parsing the rest.

L'index associe à chaque conteneur assez gros du document (`threshold` octets
au moins) ses positions de début et de fin dans le fichier, sous la grammaire
de chemins des `$ref` de serializejson (``root['clé'].attribut[0]``). Il se
range au choix, par le paramètre `index` de l'encodeur :

- ``"sidecar"`` : un fichier caché du même nom précédé d'un point, posé à
  côté du json — le json reste un json valide pour tout le monde ;
- ``"comment"`` : une ligne de commentaire ajoutée à la fin du json — un seul
  fichier à déplacer, mais le fichier n'est plus du json standard.

L'index rangé est dégonflé en zstd dès qu'il y gagne, et rien n'est écrit du
tout quand aucun conteneur n'atteint le seuil : un petit json ne s'alourdit
pas d'un index qui ne dirait rien que sa taille ne dise déjà.

L'index se construit de deux façons, qui doivent rendre le MÊME index :

- PENDANT l'écriture, quand le json part droit dans un descripteur de fichier
  (`pose`) : l'écrivain relève les bornes des conteneurs qu'il ouvre et
  ferme, et compose leurs chemins des mêmes segments que les `$ref` ;
- par BALAYAGE du json écrit (`construit`), sinon — et c'est aussi ce qui
  indexe un fichier déjà là (`serializejson.index`).

Balayage, composition du bloc, dégonflage, base 64, queue de commentaire et
relecture se font tous en C++ (rapidjson/indexscan.h) : ce module n'en garde
que le mémo, la grammaire des chemins et le chargement par tranches. Le
balayage ne regarde que la structure et tourne à plus d'un gigaoctet par
seconde, cinq fois plus vite que la désérialisation complète du document.
"""

import json
import os
import re

import rapidjson

FORMES = ("sidecar", "comment")

# `index` non précisé : la forme que `dump` pose d'office. Un index n'a de
# place que là où les octets du json tombent tels quels, dans un fichier
# NOMMÉ ; demandé explicitement sur une cible qui n'en est pas une (une
# chaîne, un flux anonyme, un fichier compressé), il crie — posé d'office, il
# se tait, sans quoi `dumps` et les flux cesseraient de marcher.
#
# C'est le FICHIER VOISIN qui est posé d'office, pas le commentaire : mesuré
# le 07/08/2026, le commentaire de queue fait échouer les lecteurs json
# ordinaires (`json` de la bibliothèque standard : « Extra data » ; JSON.parse
# de Node ; jq, code 5), la RFC 8259 n'en prévoyant aucun. Le fichier voisin,
# lui, laisse le document valide partout.
FORME_DEFAUT = "sidecar"
NON_PRECISE = object()
SEUIL_DEFAUT = 1024

# index déjà lus : {chemin: (état du document et de ses deux index, index)}
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
    __slots__ = ("chemin", "debut", "liste", "attrs", "renvoi", "attend_classe",
                 "n", "cle", "attend_cle", "premiere")

    def __init__(self, chemin, debut, liste):
        self.chemin = chemin
        self.debut = debut
        self.liste = liste
        self.attrs = False
        self.renvoi = False
        self.attend_classe = False
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
    return rapidjson._scan_index(donnees, seuil,
                                 len(donnees) if fin is None else fin)


def _balaye_python(donnees, seuil=SEUIL_DEFAUT, fin=None):
    """Version python de `balaye`, gardée comme RÉFÉRENCE du portage C.

    Elle ne sert plus qu'au test, qui compare les deux sur tout le catalogue :
    c'est ce qui rend le portage vérifiable. Le balayage lui-même se fait en C
    (18 Mo/s ici, 1,4 Go/s là-bas — indexer coûtait vingt fois désérialiser).
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
        elif not pile:
            # hors de tout conteneur : un document réduit à un scalaire, et
            # rien d'autre — une chaîne seule est un json valide
            continue
        elif tete == 0x7D or tete == 0x5D:          # } ou ]
            conteneur = pile.pop()
            if not conteneur.renvoi and m.end() - conteneur.debut >= seuil:
                entrees[conteneur.chemin] = [conteneur.debut, m.end()]
        elif tete == 0x22:                          # une chaîne
            conteneur = pile[-1]
            if conteneur.attend_cle:
                conteneur.cle = _decode_cle(jeton)
                if conteneur.premiere:
                    # une enveloppe d'objet commence par "__class__" : ses
                    # autres clés sont des ATTRIBUTS (chemins en « .nom »),
                    # exactement la règle attrsDict de l'écrivain — sauf
                    # l'enveloppe de dict à clés non-str, dont la classe est
                    # lue juste après
                    conteneur.attend_classe = conteneur.cle == "__class__"
                    conteneur.attrs = conteneur.attend_classe
                    # un marqueur {"$ref": "chemin"} RENVOIE à un objet, il n'en
                    # porte pas les octets : l'indexer donnerait une tranche
                    # qu'il faudrait résoudre à nouveau. L'écrivain, qui l'écrit
                    # d'un bloc, ne l'indexe pas davantage
                    conteneur.renvoi = conteneur.cle == "$ref"
                    conteneur.premiere = False
            elif conteneur.attend_classe:
                # {"__class__": "dict", "2": …} : les clés d'un dict à clés
                # non-str s'écrivent ['2'], jamais .2 — le texte encodé d'une
                # clé tuple ou frozenset ne serait pas relisible en segment
                # d'attribut (voir test_references)
                conteneur.attrs = _decode_cle(jeton) != "dict"
                conteneur.attend_classe = False
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


def construit(chemin, forme=FORME_DEFAUT, seuil=SEUIL_DEFAUT):
    """Build the index of an already written json file.

    Args:
        chemin: path of the json file.
        forme: `"comment"` (end of the json) or `"sidecar"` (hidden file).
        seuil: containers smaller than that many bytes are not indexed.

    Return:
        the index. It holds only `root` when no container reaches `seuil`, and
        nothing is then written on disk.
    """
    return json.loads(
        rapidjson._index_construit(chemin, *_ou_ranger(chemin, forme), seuil))


def pose(chemin, forme, seuil, chemins):
    """Range l'index construit PENDANT l'écriture (voir rapidjson/indexscan.h).

    `chemins` est déjà du json — « "chemin":[début,fin],… » — et n'a donc pas
    à repasser par un dict python : seule l'entrée `root`, que l'écrivain
    laisse au rangement puisqu'elle vaut le document entier, s'y ajoute.
    """
    rapidjson._index_range(chemin, *_ou_ranger(chemin, forme), seuil, chemins)


def _ou_ranger(chemin, forme):
    # le chemin du sidecar et la forme retenue : le premier est donné dans les
    # deux cas, puisque la forme écrite retire l'autre. Passage obligé des deux
    # constructions, donc seul endroit où valider la forme
    if forme not in FORMES:
        raise ValueError("index must be one of %s"
                         % ", ".join(repr(f) for f in FORMES))
    return chemin_sidecar(chemin), forme == "sidecar"


def lit(chemin):
    """Return the index of a json file, or None if it has none or a stale one.

    Les deux formes se cherchent, et c'est la DATE qui tranche : celle que la
    queue de commentaire porte à côté de sa longueur, celle que le sidecar tire
    de son mtime — l'une comme l'autre se lisent sans rien dégonfler, la
    première en seize octets pris en fin de json. Le plus récent des deux
    l'emporte, l'autre ne servant que s'il se révèle périmé : c'est ce qui fait
    qu'un index refait à côté d'un document qui porte encore l'ancien en
    commentaire est bien celui qu'on suit.

    Le contrôle de fraîcheur, lui, est la TAILLE du document : un fichier
    réécrit sans son index laisse un index périmé, qu'il vaut mieux ignorer que
    suivre vers de mauvaises positions.

    L'index est mémorisé d'un appel à l'autre : aller chercher plusieurs
    objets dans le même fichier est l'usage même de l'index, et le relire
    chaque fois coûtait plus que le gain sur un fichier de taille modeste.
    """
    try:
        etat = os.stat(chemin)
    except OSError:
        return None
    queue = rapidjson._index_queue(chemin)
    try:
        cote_stat = os.stat(chemin_sidecar(chemin))
    except OSError:
        cote_stat = None
    # les deux dates se comparent en MILLISECONDES, l'échelle de celle que la
    # queue transporte ; le mémo, lui, garde la nanoseconde, sans quoi deux
    # écritures dans la même milliseconde se confondraient
    cote = cote_stat is not None and (
        queue is None or cote_stat.st_mtime_ns // 1000000 >= queue[1])
    cle = (etat.st_size, etat.st_mtime_ns, queue,
           None if cote_stat is None else (cote_stat.st_size,
                                           cote_stat.st_mtime_ns))
    memoire = _memoire.get(chemin)
    if memoire is not None and memoire[0] == cle:
        return memoire[1]
    index = _lit_du_disque(chemin, cote)
    if index is None and cote_stat is not None and queue is not None:
        # le plus récent des deux est périmé : l'autre peut être encore bon
        index = _lit_du_disque(chemin, not cote)
    if len(_memoire) > 8:
        _memoire.clear()
    _memoire[chemin] = (cle, index)
    return index


def _lit_du_disque(chemin, cote):
    lu = rapidjson._index_lit(chemin,
                              chemin_sidecar(chemin) if cote else None)
    if lu is None:
        return None
    fin, texte = lu
    try:
        index = json.loads(texte)
        # la fraîcheur se lit sur `root`, qui porte DÉJÀ l'étendue du document :
        # une taille redite à côté aurait coûté ses octets pour rien
        if index["paths"]["root"] != [0, fin]:
            return None
    except (ValueError, KeyError, TypeError):
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


class IndexDecale(Exception):
    """Une entrée de l'index ne tombe pas sur un conteneur : le fichier a été
    modifié sous l'index, ou l'index est faux — dans les deux cas, ce qu'on
    lirait là n'est pas l'objet demandé."""


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
            # Deux octets suffisent à faire CRIER un index décalé : une entrée
            # borne toujours un conteneur, donc ouvre et referme. Sans ce test,
            # un décalage d'un octet rendrait un objet plausible et faux — et
            # l'index construit à l'écriture n'a, lui, jamais relu le fichier.
            # « root » est hors du test : il vaut tout le document, que la
            # taille donne, et un document peut se réduire à un scalaire.
            if prefixe != "root" and (
                    tranche[:1] not in (b"{", b"[")
                    or tranche[-1:] != (b"}" if tranche[:1] == b"{" else b"]")):
                raise IndexDecale("%s: the index of %s does not fall on a "
                                  "container" % (prefixe, fichier))
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
