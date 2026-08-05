# Passation — soirée du 05/08/2026 (depuis 20 h)

Écrit à 21 h 30 à la demande de Baptiste (session sur le départ, accès
d'écriture de la conversation compromis par une fausse manipulation).
Le récit détaillé vit dans `Notes/AUDIT 2026-08-02 ... .md`, sections
« 17 decies » et suivantes ; ce fichier est le résumé opérationnel.

## Contexte et objectif validé

Programme validé à 20 h 26 : sur la table « par catégorie de types » du
rapport de benchmarks (`tests/lance_benchmarks.py`, section catalogue
d'objets), descendre dumps ET loads sous ×2 du temps de pickle pour
chaque catégorie, en commitant à chaque gain avec batterie verte
(`tests/lance_batterie.py`), et en consignant les exceptions.
La mesure se fait par LOTS de 32 répliques (clones pickle côté objets,
lecture sur le dump réel du lot) ; itération rapide via un script de
session `types_seuls.py` (scratchpad — VOLATIL, voir pièges).

## Fait depuis 20 h (tout commité, batterie verte à chaque pas)

- Mesure par lots honnête (coût fixe d'appel dilué ; singletons
  dédupliqués admis : les deux camps les mémoïsent).
- Lecture petits bytes ×172→~17, bytearray ×106→~10 : le vidage de la
  file base64 différée (déclenché à CHAQUE rappel python de fin
  d'objet) ne lance plus ni threads ni contexte multi-thread sous 1 Mo
  de charges ; forme chaîne ascii des bytes ajoutée à la table C de
  lecture.
- Dicts à clés non-str : loads ×66→~12 (un Décodeur PAR THREAD
  réutilisé pour les clés + chemins scalaires directs — `_decode_cle`) ;
  dumps ×25→~15 (la sonde `rapidjson.loads` par clé remplacée par un
  préfiltre exact : regex nombre json, mots-clés, sonde réservée aux
  clés commençant par `[`, `{`, `"`).
- Écriture des builtins par la recette C : bytes/bytearray passent par
  `class_plan` (leur forme plugin est déjà celle de la recette C) ;
  set/frozenset via recettes privées « éléments à plat » + règle C
  « liste exacte = valeur telle quelle » (un set d'un élément reste
  `[x]`). Set dumps ×29→~5, frozenset ×23→~4.
- Plans « constructeur seul » `(classe, 2)` : les classes C (Decimal,
  datetime, deque…) et celles à `__setstate__`/setters/properties
  s'appellent directement en C pour l'enveloppe stricte
  `{__class__, __init__}` (liste OU scalaire) ; garde explicite sur la
  classe `type` (piège : `type(x)` à un argument rend la classe de x).
  decimales ~×2,2, datetime loads ~×3,5.
- Valeurs de type : cache dédié `tools._type_values_cache` (⚠ PAS le
  registre `constructors`, où "bytes" vaut bytesB64 — piège attrapé par
  la batterie), partagé avec le C qui n'en sert que les HITS
  (`NoneType` compris). Lot types 1750→295 µs mesuré au calme.
- Résolution C des `$ref` : `sj_resolve_ref_path` (grammaire de
  l'encodeur : `root`, `.attr`, `[int]`, `['clé']`) branchée pendant le
  parse (racine dict) ET exposée `rapidjson._resolve_ref_path` pour la
  post-passe des documents à racine liste. Réfs en avant et cas
  exotiques restent python. types loads ×30→~12. Piège : format « s# »
  sans PY_SSIZE_T_CLEAN → SystemError (passer par l'objet unicode).
- Outillage versionné : `rapidjson/build_pgo_tous.sh` (PGO ×5) et
  `rapidjson/consolide_nuit.sh` (PGO ×5 + batterie) — un script posé
  dans /tmp a été MOISSONNÉ par le nettoyeur en pleine nuit, la PGO ×5
  n'avait jamais tourné.

## État au moment de la passation

- Une consolidation (`rapidjson/consolide_nuit.sh` : PGO ×5 puis
  batterie) a ÉTÉ MENÉE À BIEN à 21 h 31 : PGO x5 TERMINÉE et batterie
  TOUT VERT (103 tests x 5 versions, goldens identiques) — les
  cinq binaires sont à jour et commités. (Ce paragraphe remplace
  l ancienne consigne de relance : plus rien à relancer, passer
  directement au « reste à faire » ci-dessous.)
- ⚠ Si une PGO a été interrompue EN PLEIN build d'une version, son .so
  peut rester instrumenté (mode generate) : la consolidation le
  réécrit proprement.
- Batterie attendue : 103 tests × 5 versions, goldens identiques
  (times/pickle exclus, listes NaN triées).

## Fait aussi après la reprise de 21 h 34 (session suivante, tout commité)

- Écriture native C des petits bytes/bytearray (BytesEnvelope en UN
  passage, seuil `_bytes_natif_seuil`, jamais de court-circuit d'un
  greffon remplacé) : bytes dumps ×19,5→~×12 (le reste = entrées ≥
  seuil qui partent en COMPRESSION python : coût du poids, assumé).
- Reconnaissance des ENVELOPPES au parse : {__class__, __new__/__init__
  [, __items__]} capturé au vol sans remplir le dict, EnvFlush au
  moindre écart (dont versement de TOUTE la pile à la première clé
  `$ref` — une réf peut viser l'intérieur d'une enveloppe ouverte,
  attrapé par test_doublon_dans_init_compact) ; table EnvelopeConstruct
  partagée avec la chaîne de fin d'objet ; ReplaceInParent factorisé.
  Surcoût d'enveloppe 227→107 ns.
- Résolution C des `$ref` sur la racine du HANDLER : les racines LISTE
  résolvaient tout en post-passe python (~6 µs/réf) — tuple loads
  ×7,7→×3,3, types ×13→×3,9.
- CollectionsConstruct (deque/Counter/OrderedDict/defaultdict,
  sémantique instance() calquée) + DictNonStrConstruct : clés non-str
  décodées en C (miroir _decode_cle ; repli python PAR CLÉ restreint
  aux formes parseables [/{/" — le repli par clé ordinaire était LE
  coût) — dict loads ×11→×5,5, collections loads ×11→×5,6.

## Reste à faire (par priorité)

1. dict à clés non-str, ÉCRITURE (~×17) : porter _dict_from_instance
   (branche dict) en C — préfiltre de re-quotage exact (regex nombre
   json en C), int/bool/None/float/bytes en direct, pré-scan des clés
   et repli python du DICT ENTIER si une clé exotique (tuple/nested).
2. collections dumps ~×8,5 (2,7 ms le lot !) : recettes __items__ à
   l'écriture en C (deque/Counter/OrderedDict/defaultdict).
3. bytes ≥ seuil : compression blosc2 depuis le C de l'écrivain
   (cname/level via attrs comme le seuil) — fermerait bytes/bytesarray
   des deux côtés.
4. bytesarray loads ~×11 : ~7 µs par élément COMPRESSÉ restant —
   profiler le vidage différé (la garde <1 Mo existe pourtant).
5. types dumps ×5,8 ; sets dumps ×4-6 : écriture des valeurs de type
   (cache inverse) et recettes set C par éléments.
6. Scalaires dumps ×2-2,6, iterators/queue/range/slice loads ×2,4-3 :
   proches du plancher d'appel — consigner en exceptions si résiduels.
7. Table finale au calme + PGO ×5 + batterie + section « chaque type
   sous ×2 » dans l'audit (résultats et exceptions consignées).

## Pièges de la nuit (à ne pas repayer)

- pytest depuis la RACINE du dépôt (depuis rapidjson/ : « no tests
  ran ») ; le cwd du Bash persiste entre appels.
- Les scripts d'outillage ne vivent PAS dans /tmp (nettoyeur).
- La mémoire persistante (`~/.claude/projects/.../memory/`) est morte
  depuis ~20 h 40 : bind-monts de /DATA retombés (dossier réapparu vide
  en nobody) — un REDÉMARRAGE la rétablira ; d'ici là, l'état vit dans
  l'audit et ce fichier.
- Mesures de ratios du soir polluées (charge 2-6 : Baptiste
  travaillait) : choisir les cibles au PROFIL (compte d'appels python),
  et ne publier que des chiffres pris au calme.
- Le commit du soir dans le dépôt SmartOS (filtre --match du veilleur
  de fuseau horaire) est fait et déployé — sans rapport avec ce dépôt,
  mais c'est lui qui mangeait 15 % de CPU en continu.
