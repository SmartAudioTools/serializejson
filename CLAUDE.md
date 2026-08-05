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

## Reste à faire (par priorité, chiffres indicatifs pollués par la
## charge du soir — refaire la table au calme)

1. Relancer la consolidation (ci-dessus), vérifier TOUT VERT.
2. Écriture native C des bytes (dumps ~×20 : plancher = appel plugin
   python par objet ; passer seuil/compression via pathTracker comme
   singleLineInit, ne traiter en C que len<seuil : ascii imprimable —
   codec = {tab, LF, CR} ∪ [0x20..0x7E] — sinon b64 via RawDataToBase64
   qui pose déjà le préfixe « n: » ; ≥seuil → voie python blosc).
3. Collections ~×12 : formes `__items__` (OrderedDict, deque, Counter,
   defaultdict) en C.
4. `_replace_ref_placeholders` (parcours python de l'arbre en
   post-passe des racines liste) → C.
5. dict à clés non-str : le reste (~×12-15) est l'enveloppe par clé —
   candidate voie C (écriture des clés + `dict_non_str_keys` C).
6. tuple loads ~×9 : plancher = construction de l'enveloppe dict en C
   puis conversion — candidat « exception consignée » ou reconnaissance
   des enveloppes au parse (éviter le dict intermédiaire).
7. Scalaires (None/bool/int/float) dumps ×2-3,5 et
   iterators/queue/range/slice loads ×2,5-3,5 : proches du plancher
   d'appel — mesurer au calme avant de trancher.
8. Table finale sur machine calme + PGO ×5 + batterie + section rapport
   dans l'audit (« chaque type sous ×2 : résultats et exceptions »).

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
