# Passation — nuit du 05 au 06/08/2026, close le 06 à 10 h

## Addendum 09/08/2026 — campagne $ref/enveloppes (commit 7669ef7)

Trois retouches C++ commitées (raccourci $ref SAX −32 %, recyclage
des dicts d'enveloppe ~10-15 ns, anneau dumped_classes), PGO des 5
versions, 204 tests verts partout. Essayé et rejeté : itération
directe des sets (_PySet_NextEntry interne depuis 3.13), cache dédié
aux noms de classes (valCache couvre déjà).

Pistes identifiées, NON tentées, à reprendre le cas échéant :

1. **Création différée du dict d'enveloppe en lecture.** Aujourd'hui
   chaque StartObject alloue (ou recycle) un dict inséré aussitôt
   chez le parent via Handle(mapping) ; pour une enveloppe il est
   jeté à EndObject. Différer la création jusqu'à la première clé
   non-enveloppe supprimerait alloc + insertion + remplacement,
   plusieurs dizaines de ns par enveloppe. INVASIF : revoir
   l'insertion hâtive chez le parent et tous les points touchant
   current.object. À ne faire que sur binaire de chantier avec A/B
   min-de-N.
2. **Plancher $ref restant** (121-133 ns contre ~18 ns le memo
   pickle) : ce qui reste = poussée de contexte + dict vide (créé
   puis jeté, résorbable par la piste 1) + sonde du cache. Au-delà,
   c'est une décision de FORMAT (cf. « Le mur restant »).

Piège nouveau : le greffon pytest typeguard est trop vieux pour
3.14 (ImportError ast.Str) — lancer avec `-p no:typeguard`.

## Addendum 09/08/2026 fin de journée — campagne 3, tête d'enveloppe
## fusionnée + dict différé (lecture)

La piste 1 de l'addendum précédent est FAITE, combinée à une
reconnaissance LEXICALE de la tête d'enveloppe par le reader :

- **SjTryEnvelopeHead (reader.h)** : devant `{`, pure lecture en
  avant du motif `{"__class__": "nom", "__new__"|"__init__":` —
  rien n'est consommé tant que le handler n'a pas accepté ; remis au
  PyHandler en UN événement SjEnvelopeHead (StartObject + 2 parses
  de clé + 1 parse de chaîne économisés). Décliné à la racine, si
  string/start_object hooks actifs, ou pour numpyB64.
- **Dict d'enveloppe DIFFÉRÉ** : le contexte est empilé avec
  object=nullptr ; le cas nominal (EnvelopeConstruct à la fermeture)
  ne crée ni ne détruit plus aucun dict. Au moindre écart de forme,
  EnvFlush → EnvDeferMaterialize recrée le dict et l'insère chez le
  parent à l'identique de la voie classique (cas $ref vidage :
  insertion dans la tranche d'attente du parent + décalage des
  attenteBase plus profonds). Invariant : object==nullptr ⟺
  envState∈{3..6} et envClass≠nullptr.
- **EndArray dédoublonné** : son bloc de remplacement (end_array)
  dupliquait la fin de ReplaceInParent SANS les états d'enveloppe →
  remplacé par ReplaceInParent (−44 lignes). Au passage, la
  liste-valeur d'un slot d'enveloppe n'est PLUS soumise à end_array
  (la voie python la reconvertissait en liste par tolist() de toute
  façon ; l'ancien code C++ ne « marchait » que par une incohérence :
  il insérait le tableau dans le dict jeté et construisait sur la
  capture restée liste). Les listes imbriquées dans les args restent
  converties — vérifié identique au binaire de référence.

Gains lecture PGO contre PGO commité (min de 5 tours interlacés,
3.13) : datetime −17,8 % (3,36 → 2,77× pickle), tuples −16 %
(4,16 → 3,50), sets −15,6 % (2,42 → 2,04), bytes −8,9 %
(8,76 → 7,97) ; dicts/listes/écriture neutres (±1 %). 204 tests
verts sur les 4 versions, empreinte d'écriture identique, sonde des
écarts de forme (9 cas : clé en plus, $ref dans args, classe
inconnue, __class__ non-chaîne, end_array numpy) verte.

## Addendum 09/08/2026 soir — campagne « paquets de caractères »

Écriture uniquement, sortie inchangée à l'octet près (sha256 sur 11
cas × 3 configs), lecture neutre (±3 %). Trois leviers :

- **Écritures fusionnées** : séparateurs `,\n`+indentation et `": "`
  en UNE réservation (SepEtIndent), têtes d'enveloppe au memcpy,
  charge bytes imprimable en une réservation au pire cas. Gains PGO
  contre PGO commité (min de 5 tours interlacés) : datetime −57 %
  (0,36× pickle), tuples −34 % (2,24), decimal −32 % (0,39),
  bytes −22 %, sets −21 % (2,49).
- **Corpus PGO enrichi** (pgo_workload.py) : flottants à graphie
  LONGUE (sans eux le chemin complet de dtoa compile froid : ×1,7
  mesuré sur flottants quelconques) + les six familles à enveloppe.
  list_float −46 % (5,4 → 2,76× pickle).
- **Essayé et REJETÉ : élagage des options rapidjson** (modes figés
  en dur dans dumps_internal) : −9 à +4 % selon le placement du code,
  aucun signal — les 257 branches de mode sont parfaitement prédites,
  gratuites. Ne pas y revenir.

⚠ **L'environnement 3.10 a DISPARU de la machine** au redémarrage du
09/08 après-midi (versions/3.10.20 et SmartPython-3.10.20_2026-07-26
absents). Le .so 310 du dépôt reste celui du commit 7669ef7 : il
fonctionne mais ne correspond plus aux sources — à reconsolider si
l'environnement revient.

Trois missions successives, dictées par Baptiste : « chaque type sous
×2 de pickle » (20 h 26), puis « jusqu'aux performances de pickle »
(00 h 59, « mieux que pickle c'est bien aussi »), puis « lance une
campagne pour identifier les cas les plus problématiques » (03 h 32).
Récit détaillé dans `Notes/AUDIT 2026-08-02 ... .md`, sections 17
decies → quindecies, avec la TABLE FINALE chiffrée ; ce fichier est le
résumé opérationnel.

## État — chantier CLOS, tout commité

- Binaires PGO des 5 versions (3.10 → 3.14), batterie 117 tests verte
  partout (`tests/rapport_batterie_2026-08-06_1010.pdf`).
- **Zéro repli python, écriture ET lecture**, sur tout le catalogue —
  seules exceptions : les trois clés vraiment exotiques (tuple et
  frozenset EN CLÉ) des deux dicts non-str, et le remplissage des
  caches au premier passage.
- Table finale mesurée machine calme sur les binaires définitifs, deux
  passes concordantes : six catégories PLUS RAPIDES que pickle dans un
  sens (datetime ×0,73, decimales ×0,89 et slice ×0,95 en écriture ;
  str, list, composeds en lecture), quinze sous ×2 en lecture. Ce qui
  reste au-dessus de ×2 est chiffré et justifié dans l'audit.
- Écriture : têtes d'enveloppe fusionnées (EnvelopeHead), inliner
  scalaire dans huit boucles chaudes, cache des graphies de flottants
  par motif de bits, cache classe→nom des valeurs de type, branches
  natives directes pour sets/tuples/collections/datetime/date/time/
  timedelta/struct_time/Decimal.
- Lecture : décodage AU VOL des clés non-str, EnvelopeConstruct
  aiguillé par longueur de nom, caches par parse, interception b64 dès
  2 caractères, cache partagé des valeurs de type.
- dumps/dumpb/loads réutilisent une instance PAR DÉFAUT par thread
  (~11/7 µs de construction par appel économisés ; réentrance gérée).
- DÉCISION DE FORMAT : datetime.datetime s'écrit en forme reduce
  OCTETS (10 octets b64, comme date/time) — tzinfo désormais
  transporté (avant : PERDU), ancienne forme 7 entiers toujours lue.
  Greffon python datetime supprimé.
- Le hack SingleLine des __init__/__new__ est SUPPRIMÉ : la règle vit
  dans le writer ; SingleLine ne sert plus qu'au repli numpy qui porte
  un number_mode par sous-arbre.

## Le mur restant, à ne pas réattaquer sans nouveau profil

Deux causes, toutes deux chiffrées dans la table finale de l'audit :

1. **Le format.** Texte json lisible contre opcodes binaires. Sur
   micro-objets purs (tuple de 2 ints ≈ 40 octets de json contre ~10
   d'opcodes), plancher ×2,5-3,3 malgré zéro python et des enveloppes
   écrites au memcpy. Sur charges réelles, l'écart s'efface.
2. **La compression.** bytes ≥ seuil = prix de zstd (2,7 µs les 512
   octets après le cache de contexte, contre un memcpy chez pickle).
   Échange octets ↔ µs assumé ; porter la compression dans l'écrivain
   ne gagnerait que ~0,4 µs par entrée — abandonné sur mesure.

Si une reprise est demandée : ce n'est pas une chasse aux rappels
python (il n'y en a plus), c'est une décision de FORMAT.

## Pièges (à ne pas repayer)

- **Un espion qui surcharge `Encoder.default` MENT** : la garde de
  `_configure` désactive alors le chemin natif des dicts à clés
  non-str, et l'espion compte un rappel que sa propre présence a créé.
  Compter en enveloppant `_cle_json`, hors de la garde.
- **`nohup … &` dans un appel Bash ne survit pas à la fin de l'appel**
  (log resté vide 5 min, rien lancé). Utiliser le mécanisme
  d'arrière-plan de l'outil.
- Depuis la racine, `import serializejson` échoue seul : le dossier
  `rapidjson/` du dépôt masque le module. Faire comme
  `tests/conftest.py` — `import rapidjson.rapidjson as rj` puis
  `sys.modules["rapidjson"] = rj` AVANT tout import.
- pytest et les scripts de tests depuis la RACINE ; le cwd du Bash
  PERSISTE — un build lancé du mauvais dossier échoue en SILENCE
  (« grep -c » rend 0 pour zéro erreur COMME pour zéro build : vérifier
  la ligne « copying »). Payé plusieurs fois cette nuit.
- Ne PAS éditer les sources pendant qu'une consolidation/un build
  d'arrière-plan tourne : binaires mélangés, une PGO a écrasé un build
  de chantier en course.
- Sous charge : cibles au COMPTE D'OPÉRATIONS et A/B interlacés dans
  le MÊME processus ; jamais de ratios absolus.
- `std::thread::hardware_concurrency()` est un APPEL SYSTÈME coûteux
  dans le bac à sable (~1,7 µs) : jamais dans un chemin chaud, le
  passer en `static const`.
- PyLong_FromString exige un tampon TERMINÉ : depuis le tampon de
  parse, copie bornée d'abord (int relu en float sinon — attrapé par
  le test des types de clés).
- matplotlib : parse_math=False sur tout texte porteur de `$`.
- Les scripts d'outillage ne vivent PAS dans /tmp (nettoyeur).
