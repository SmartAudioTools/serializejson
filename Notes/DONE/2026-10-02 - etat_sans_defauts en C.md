# 2026-10-02 — `etat_sans_defauts` en C (état plat sans valeurs par défaut)

## Demande (Baptiste, 02/10 13 h 04)

> « une fonction C++ dans le module rapidjson de serializejson qui calcule l'état "plat sans
> valeurs par défaut" d'un objet, pour remplacer le Python de SmartTeacher/QCM/noyau.py,
> méthode Objet.__serializejson__ […] sémantique de _defaut EXACTEMENT conservée (ordre des
> clés compris). Le cache par classe reste côté appelant. »
> Enjeu : 3 806 appels à l'ouverture d'un sujet (python_tp) dans le navigateur, ≈ 60 ms sur 1,7 s.
> Puis (13 h 06) : « vérifie que c'est la meilleure approche ? » et (13 h 09) : « s'il y a un
> gain, pourquoi ne devrais-je pas l'implémenter ? » → on livre.

## Livré

- `rapidjson/rapidjson.cpp` : `sj_est_defaut` (la sémantique `_defaut`, trois branches dans
  l'ordre du `or` python, exceptions propagées au même point) + `sj_etat_sans_defauts`,
  exposée `etat_sans_defauts(obj, defauts, proprietes) -> dict`. Itération de `vars(obj)` par
  `PyDict_Next` (même ordre d'insertion que la compréhension python), garde « dict modifié
  pendant l'itération », puis les properties par `PyObject_GetAttr` — getattr AVANT
  `defauts[nom]`, comme la référence (ordre des exceptions identique, KeyError si la property
  manque de `defauts`).
- `serializejson/__init__.py` : export `etat_sans_defauts` par
  `getattr(rapidjson, ..., None)` — **liaison TOLÉRANTE obligatoire**, voir le piège payé.
- `tests/test_etat_sans_defauts.py` (13 cas) : équivalence à une référence python recopiée
  (valeurs, ordre des clés, types), property déjà dans vars non relue, identité des objets
  rendus, ordre vars→properties, exceptions (comparaison qui lève, property qui lève, property
  absente de defauts → KeyError, objet sans `__dict__` → TypeError, `__dict__` non-dict —
  le mappingproxy d'une classe — → TypeError), comparaison non booléenne (numpy : ValueError
  comme le `or` python), non-fuite de références (refcounts stables sur 100 appels).
- `dist_wasm/serializejson-0.4.0-cp313-cp313-pyemscripten_2025_0_wasm32.whl` (881 041 octets),
  reconstruite par `scripts/construit_wasm.sh` — ignorée par git, non commitée.

## Choix, et alternatives écartées

- **`defauts`/`proprietes` en arguments, cache côté appelant** (demandé par Baptiste) plutôt
  qu'un cache par classe en C : l'amortissement existe déjà (`functools.cache`), un cache C
  dupliquerait l'état et coûterait l'invalidation.
- **Fonction générique à `defauts` explicite** plutôt qu'un branchement dans l'encodeur ou
  `getstate` : la sémantique `_defaut` (tuple == list, None-falsy-sauf-0) est propre à
  SmartTeacher. Vérifié que serializejson ne le fait pas déjà : un
  `getstate_factory(..., remove_default_values=False)` existe à `tools.py:473` — en
  commentaire, jamais implémenté ; `attributes_filter` filtre par préfixe `_`, pas par défauts.
- **Pas de raccourci d'identité `valeur is defaut`** dans `sj_est_defaut` : il changerait le
  résultat pour un défaut NaN (`nan == nan` est faux) — sémantique exacte exigée.

## Mesure (niveau de preuve : A/B interlacé, même processus, 3.13.14, natif)

Objet QCM représentatif (10 paramètres, 4 hors défaut, 1 property) : python 2,4 µs → C 1,5 µs
par appel, **−38 %** (9 → 6 ms pour 3 806 appels). Le gros du coût était déjà en C
(comparaisons riches, getattr) ; dit à Baptiste : les 60 ms du navigateur ne tomberont
probablement qu'à ~la moitié — confirmé ensuite en wasm (−39 %, section roue ci-dessous).

## Piège payé (13 h 06, signalé par la session smartteacher-48)

La première liaison `etat_sans_defauts = rapidjson.etat_sans_defauts` a **cassé l'import de
serializejson pour toute session dont le `.so` n'avait pas encore la fonction** (3.14 de
SmartTeacher, et le 311 qui ne sera JAMAIS rebâti — interpréteur non exécutable par ce
compte). Corrigé par `getattr(..., None)` : ce n'est pas un provisoire, c'est la forme
définitive ; l'appelant garde un repli python par `getattr(serializejson,
"etat_sans_defauts", None)`.

## Vérification côté SmartTeacher (02/10, 13 h 17)

- `noyau.py` : SEUL le corps de `__serializejson__` est touché (d'autres sessions ont des
  modifications non commitées dans ce fichier) — `getattr(serializejson, "etat_sans_defauts",
  None)` dans le corps, pas de ligne au niveau module, et le repli python d'origine conservé
  mot pour mot dans le `else`.
- **Copie sérialisée identique à l'octet** : `sha256` cumulé des `dumpb(copier(charger(f)),
  indent=2)` des 417 json de `banque/**` et `sujets/**`, sous `noyau.en_donnees()` —
  `5eeea4c90bd2c6587b9b486e1972192c27e3017c99cadde8f52ae850663adf10` par la voie python
  (fonction neutralisée) ET par la voie C. Niveau de preuve : exécuté, deux processus, même
  interpréteur (SmartPython 3.13.14).
  Piège payé : le script doit charger par `modele.charger` (il passe
  `authorized_classes=list(serializejson.constructors)`) — sinon `TypeError: Proposition is
  not in authorized_classes` ; et il lui faut `QT_QPA_PLATFORM=offscreen` (sans écran, Qt
  abandonne par core dump).
- `tests_modele.py` : 72 verts, exit 0, d'abord sur la voie **python** (la copie
  `serializejson/rapidjson.cpython-313*.so` qu'importe réellement SmartPython n'avait pas
  encore la fonction — c'est elle, et non `rapidjson/*.so`, qui est importée), **puis rejoués
  sur la voie C** une fois les PGO et leurs copies en place : 72 verts, exit 0.
- Empreinte rejouée sur les binaires définitifs (13 h 55) :
  `95b72f7f…` **identique voie C et voie python**, dans le même état du disque. Elle diffère
  du `5eeea4c9…` de 13 h 17 parce que **74 json de `QCM/banque`/`QCM/sujets` ont été modifiés
  entre-temps par d'autres sessions** (`hg status` → 74 lignes) : dérive de contenu, pas de
  code. La garantie porte sur la comparaison C ≡ python au même instant.

## PGO et copies (13 h 24 → 13 h 33)

- `rapidjson/build_pgo.sh` lancé **depuis `rapidjson/`**, un `.gcda` périmé supprimé avant
  chaque `generate` : .so 312/313/314 à 2 340 312 / 2 340 280 / 2 340 280 octets (un PGO
  avorté laisse un .so INSTRUMENTÉ de 5,4 Mo — c'est le repère). **Le .so 311 n'est pas
  rebâti** (interpréteur non exécutable par ce compte) : il n'aura pas la fonction, d'où le
  `getattr` tolérant.
- Copies `serializejson/rapidjson.cpython-31{2,3,4}-*.so` refaites par copie temporaire +
  `mv` (le `cp` direct dessus échoue : masque ACL) ; `sha256` identique à `rapidjson/*.so`
  version par version — la voie réellement importée porte bien la fonction.
- Suite serializejson : **394 verts × 3.12.13 / 3.13.14 / 3.14.6**, goldens restaurés
  (seuls des artefacts non suivis restent).
- Incident : la passe `generate` du 3.13 s'est d'abord arrêtée sur
  `tests/test_encryption.py::test_reecriture_sans_nouveau_scrypt` (`assert len(appels) == 1`,
  cache scrypt/en-tête). **Non reproductible** : la suite complète passe 394/394 sur la même
  version. C'est une fragilité PRÉEXISTANTE d'ordre/état de ce test, sans rapport avec ce
  chantier ; signalée ici pour le relecteur, non corrigée. Le `set -e` du script fait qu'un
  tel échec abandonne AVANT la passe `use` (d'où le .so instrumenté laissé en place).

## Roue WebAssembly (13 h 40) et mesure wasm (13 h 5x)

Roue reconstruite hors ligne par `scripts/construit_wasm.sh` (Pyodide 0.29.3, cp313,
`pyemscripten_2025_0`), 860 Kio. **Exercée réellement** sous node + le Pyodide **0.29.3** de
`SmartTeacher/QCM/web/pyqt6/pyodide-qt/` (script jetable du bac à sable) :
`etat_sans_defauts` présente, équivalence à la référence python sur les 7 cas (valeurs ET
ordre des clés), et **C 1,88 µs contre py 3,09 µs par appel, −39 %** — le gain natif (−38 %)
se retrouve donc tel quel en wasm. Niveau de preuve : exécuté.
Pièges payés : `loadPackage("emfs:…")` refusé en 0.29 (déjà au CLAUDE.md) et un chemin écrit
dans le FS Emscripten n'est pas vu non plus — en node, `loadPackage` prend le chemin HÔTE
absolu ; l'import de serializejson exige `apply`, fourni au lecteur par `lecteur.zip` (monté
en NODEFS pour l'essai) ; et le `node_modules/pyodide` de `web/` est passé à **314.0.7
(Python 3.14, emscripten 2026_0)** — avec celui-là la roue cp313 ne s'installe pas. C'est
`web/pyqt6/pyodide-qt/` (0.29.3) que charge le lecteur, et c'est le bon.
La roue déployée `web/pyqt6/serializejson-0-cp313-…whl` reste l'ancienne : `construire.py`
(ligne 122) la reprend par glob dans `serializejson/dist_wasm` — elle sera à jour à la
prochaine construction du lecteur, côté SmartTeacher.

## Gain de bout en bout (niveau de preuve : A/B interlacé, 3 tours, même processus)

`charger` + `copier` + `dumpb` des 417 documents : **0,72 s → 0,59 s, −18 %** (min de 3
tours ; le premier tour à froid donnait 1,11 s contre 0,81 s — mesure refusée, c'était le
chauffage des caches). Cohérent avec le −38 % sur la fonction seule : elle ne porte qu'une
part du travail.

## Passe de simplification (par fichier du commit)

- `rapidjson/rapidjson.cpp` : un `__dict__` non-dict (mappingproxy d'une classe, mapping
  exotique) rendait **silencieusement un résultat faux** — `PyDict_Next` n'était pas appelé,
  la fonction rendait `{}` ; remplacé par un `TypeError` franc (+ test). Rien d'autre à
  enlever : chaque branche de `sj_est_defaut` correspond à un terme du `or` python, la garde
  « dict modifié pendant l'itération » reproduit celle de CPython.
- `tests/test_etat_sans_defauts.py` : du code mort de mise au point retiré
  (`["saisie"] if False else []` → `[]`).
- `serializejson/__init__.py` : regardé, rien à enlever — 2 lignes + une entrée de `__all__`,
  le `getattr` tolérant est justifié par le piège ci-dessus (et porte son commentaire).
- `noyau.py` (dépôt SmartTeacher) : regardé, rien à enlever — le corps est le repli d'origine
  mot pour mot plus le branchement ; la résolution `getattr` reste DANS le corps (pas de
  ligne au niveau module), exigence de non-intrusion dans un fichier partagé.
- `Notes/DONE/…` (ce fichier) : regardé.
- Essayé et ÉCARTÉ : supprimer le `getattr` tolérant au profit d'un import direct — c'est ce
  qui a cassé l'import des autres sessions, le .so 311 ne sera jamais rebâti.

## Leçon générale, écrite ailleurs

Question de Baptiste : « pourquoi n'avais tu pas pensé et codé cette optimisation plus tôt,
lorsqu'on avait d'optimiser au maximum serializejson ». Cause réelle : toutes les campagnes
ont mesuré serializejson sur SON corpus de banc, où `__serializejson__` — code de l'appelant —
n'apparaît jamais ; elles chassaient les replis python que serializejson déclenche lui-même,
pas ceux que l'application lui tend. Sur son accord, la leçon est écrite comme règle de
méthode (déclencheur en geste : profiler la bibliothèque dans une application réelle qui la
consomme) dans le CLAUDE.md global — source versionnée
`/DATA/Python/SmartOS/Commun/config_files/Claude/CLAUDE.md` (hg r205, draft) ET copie active
`/home/claude/.claude/CLAUDE.md`, éditée à la main parce que le déploiement ne réécrit ce
fichier que s'il est ABSENT (`installation_Claude_commun.sh:1017`). Écarté : la mémoire
automatique, ni versionnée ni propagée à une machine neuve.

## Suite (02/10, 14 h) — le coût d'un crochet d'appelant entre au banc et au corpus PGO

Proposé en conclusion de la leçon ci-dessus, accepté par Baptiste (« Oui ») : *« ajouter au banc
(et au corpus PGO) une famille “objet à crochet python”, pour que ce coût ait désormais sa barre
dans le rapport »*. C'est la contrepartie OUTILLÉE de la leçon : une règle de méthode s'oublie, une
barre dans le rapport se voit.

### Livré

- `tests/objects/crochets_objects.py` (neuf) : **cinq catégories qui écrivent exactement le même
  état** — six champs hors défaut d'un objet qui en porte dix, à la forme de l'`Objet` de
  SmartTeacher (défauts de constructeur, une property, la règle `_defaut` recopiée) — par les cinq
  voies qu'une application peut prendre : `crochet_python` (filtrage en python),
  `crochet_C` (`etat_sans_defauts`), `crochet_getstate`, `crochet_reduce`, et `sans_crochet`
  (TÉMOIN, pas de crochet, `__dict__` lu en C). Module inerte pour le reste du dépôt : rien
  n'énumère `tests/objects/`, seul le banc l'importe.
- `tests/lance_benchmarks.py` : `mesure_types_objets` itère `dict(basic_objects.objects,
  **crochets_objects.objects)` ; titre de page, intro markdown et commentaire de `figure_types`
  étendus. Aucune liste de catégories n'est codée en dur : la figure et le tableau se déduisent
  des lignes.
- `rapidjson/pgo_workload.py` : classe `Objet` à `__serializejson__` appelant `etat_sans_defauts`,
  5 000 instances dans `cases`, nom enregistré dans `serializejson.constructors` pour la
  relecture. Sans ce cas, la fonction neuve était compilée comme **code froid** par la PGO.

### Mesures (niveau de preuve : exécuté, 3.13.14, machine chargée ; rapports à pickle)

`dumps` : `crochet_python` ×2,49 contre `crochet_C` ×1,60 — soit, en absolu sur un lot de 256
objets, 750 µs contre 437 µs (**−42 %**), le témoin étant à 205 µs. Le crochet python coûte donc
≈ 2,1 µs par objet au-dessus du témoin, sa version C ≈ 0,9 µs. `crochet_getstate` ×0,84 et
`crochet_reduce` ×1,13 : **pickle appelle ces deux crochets-là lui aussi**, le rapport sous-estime
leur prix — c'est écrit dans la page. `ECARTEES: []` : aucune des cinq n'est muette d'un côté ou de
l'autre. `loads` (×1,98 à ×2,43) ne doit rien à la voie : aucun crochet n'y est appelé.

### Choix, et alternatives écartées

- **Comparaison contrôlée, même état écrit par les cinq classes** plutôt que cinq objets
  « réalistes » différents : sans cela l'écart entre deux barres mêlerait le prix de la voie et
  celui du document. Vérifié : 1 537 à 1 689 octets écrits, l'écart tenant au seul nom de classe
  (et au `"__init__":[]` de `__reduce__`).
- **Un témoin sans crochet** plutôt que les seules quatre voies : sans lui, rien ne dit ce que
  coûte le fait même d'avoir un crochet, seulement ce que coûte l'un par rapport à l'autre.
- **Module de corpus séparé** (`tests/objects/crochets_objects.py`) plutôt qu'un ajout à
  `basic_objects.py` : ce dernier est le corpus de `test_serialize_vs_pickle` ; y ajouter cinq
  classes changerait ce que teste un test, pour un besoin de banc.
- **`Objet` recopié dans `pgo_workload.py`** plutôt qu'importé de `tests/objects/` : la roue est
  construite sans l'arbre de tests (`SERIALIZEJSON_PGO_LIB`), un import le casserait.
- **Écarté : mesurer le crochet seul, hors banc** (un `timeit` dans une note) — c'est ce qui a
  manqué pendant deux mois ; la mesure doit vivre dans le rapport que l'on relit.

### Pièges payés (deux, tous deux AVANT la mesure)

- **`$ref`** : le premier `_lot` donnait la même liste `choix` aux huit objets → une écriture et
  sept références, le banc aurait mesuré `$ref`. Chaque valeur liste est désormais copiée par
  objet (compte de `$ref` vérifié nul dans les cinq catégories).
- **Banc à vide** : le banc réplique ses lots **au pickle**, et un clone pickle d'une classe à
  `__getstate__`/`__reduce__` ne restaure que les six attributs d'état — le crochet n'aurait plus
  eu aucun défaut à écarter. Corrigé par `_Base.__setstate__`, qui repose les défauts avant
  l'état ; vérifié : 10 attributs sur l'objet direct, sur son clone pickle et sur l'objet relu,
  et json du clone identique à l'octet à celui de l'original.

### Passe de simplification (par fichier du commit)

- `tests/objects/crochets_objects.py` : les cinq classes partagent `_Base` (`__init__`,
  `__setstate__`, la property) et une seule fonction `etat_python` — trois recopies supprimées
  avant livraison. `_lot` est la seule fabrique. Rien d'autre à enlever : chaque élément porte un
  cas (la property exerce la branche `proprietes`, `reponse=0` contre défaut `None` et la liste
  contre un défaut tuple sont les deux cas limites de `_defaut`).
- `tests/lance_benchmarks.py` : **deux lignes de code** (l'import et le `dict(...)`), le reste est
  du texte de rapport ; `figure_types` et le tableau n'ont PAS été touchés — ils se déduisaient
  déjà des lignes. Essayé et écarté : une page distincte pour les cinq voies — elle dupliquerait
  tout le dispositif de figure pour cinq barres, et perdrait la comparaison avec les types.
- `rapidjson/pgo_workload.py` : regardé, rien à enlever — la classe est le minimum qui exerce
  `etat_sans_defauts` (défauts, une property, des valeurs hors défaut) et la ligne
  `constructors["Objet"]` est ce qui permet la relecture dans la même charge.
- `Notes/DONE/…` (ce fichier) : regardé.

### Vérification

394 verts × 3.12.13 / 3.13.14 / 3.14.6 (changement purement additif, aucun `.so` touché, goldens
restaurés après le run) ; `pgo_workload.py` exécuté en entier avec le cas neuf (1,2 s, « charge PGO
exécutée ») ; page de figure rendue et relue à l'image (28 catégories, libellés lisibles). **La PGO
n'est pas rebâtie** : le corpus enrichi ne vaudra qu'au prochain `build_pgo.sh` — à faire lors du
prochain chantier C, pas pour un changement sans source C++.

## Suite (02/10, 14 h 30 → 16 h) — les trois pistes de lecture croisées

### Demande (Baptiste, dictée)

« Vois-tu d'autres choses pour optimiser serializejson qui n'auraient pas été vues à l'époque et
qui pourraient être mises en évidence par ces nouveaux tests ou par d'autres tests auxquels on n'a
pas encore pensé ? », puis, sur les trois pistes proposées : « **On croise toutes les pistes en
autonomie.** »

Les trois pistes, telles qu'elles ont été énoncées : (1) seule la moitié ÉCRITURE a jamais été
optimisée du côté de l'appelant — la lecture repose l'état objet par objet en python, jamais
mesurée ; (2) le banc ne mesure que des lots HOMOGÈNES d'objets identiques, jamais un document
applicatif profond et hétérogène ; (3) la résolution des noms de classes à la lecture
(`authorized_classes` / `constructors`) n'a jamais été isolée.

### Le défaut trouvé (piste 3), et ce qu'il coûtait

`serializejson.constructors` porte DEUX rôles : registre des constructeurs personnalisés, et cache
de résolution des noms de classes — `class_from_class_str_dict` **est** `constructors`
(`tools.py:690`), et `instance()` y écrit la classe résolue (`tools.py:1250-1254`).
`Decoder.decode_class_plan` rendait `None` dès que le nom figurait dans ce registre, **sans regarder
ce qu'il désigne**. Or une application qui raccourcit les noms de ses classes y inscrit la CLASSE
elle-même sous son propre nom : SmartTeacher le fait pour toutes les siennes
(`constructors[cls.__name__] = cls`, `noyau.py:145`, dans `__init_subclass__`). Ces classes
perdaient donc le chemin rapide C alors que la voie python se contente de lire dans ce même
registre exactement la même classe.

Mesure sur le document applicatif réel (274 843 octets, 450 objets ; A/B interlacé dans le même
processus, 9 tours, min de 3 lectures par tour, empreinte de sortie vérifiée identique,
SmartPython 3.13.14) : **−22,9 %** de temps de lecture (4,14 → 3,19 ms, soit 9,19 → 7,09 µs par
objet) contre un témoin A/A à **+1,8 %**. Un premier passage du même protocole avait donné −21,9 %
contre −1,0 % : l'effet est reproduit. Les trois classes rencontrées (`Paquet`, `Question`,
`Choix`) passent du plan `None` au plan `(classe, 2)`.

Effet de bord, et c'est le plus grave des deux : `instance()` INSCRIT le nom qu'elle résout, donc
le plan d'une classe était perdu **définitivement, pour tout le processus**, dès qu'un seul de ses
objets était passé par la voie python (un objet écrit avec des arguments, un appel direct à
`tools.instance` depuis serializeRepr). Mesuré avant correctif, à sémantique identique :
**+409,8 %** de temps de lecture pour un nom seulement PRÉSENT, contre un témoin A/A à +4,9 %.
Après correctif, le même protocole donne **+2,6 % contre un témoin à +0,9 %** — l'empoisonnement
est éteint, puisqu'une inscription faite par `instance()` est par construction « ce nom désigne
cette classe-là », donc un raccourci de nom.

### Livré

- `serializejson/__init__.py`, `decode_class_plan` : le test d'appartenance au registre devient un
  test de NATURE — le plan est accordé si l'entrée est une **classe portant ce nom**
  (`class_str.rsplit(".", 1)[-1] == cible.__name__`), et la résolution réutilise cette entrée au
  lieu de refaire un import. Tout le reste de la cascade (garde `type`, HEAPTYPE, `__setstate__`,
  slots, setters, properties, `except Exception: return None`) est intact.
- `serializejson/_smartframework/tools/objects.py` : `notInstanceTypes` nommé une fois, et
  `isInstance` écrit par un seul `isinstance` au lieu de trois appels python
  (`inspect.isclass`/`isfunction`/`ismodule` SONT ces trois `isinstance`, cf. `inspect.py`).
- `serializejson/tools.py` : la nature du `__class__` reçu par `instance()` est tranchée en ligne
  (`isinstance(__class__, type)`, puis le test d'instance déjà construite) — un appel python de
  moins par objet applicatif, soit 450 par lecture du document réel, ~3,6 %.
- `tests/test_plan_registre.py` : 9 tests.
- `tests/test_encryption.py` : la fixture autouse attend les écritures chiffrées en vol avant de
  vider les caches (course diagnostiquée en fin de chantier, section plus bas).

### Choix, et alternatives écartées

- **Le critère retenu est « le registre RACCOURCIT le nom de cette classe-là »**, pas « le registre
  contient un type ». Alternative écartée, et c'est ce qui l'écarte : `constructors["bytes"]` est
  `bytesB64`, une **substitution** délibérée (une autre classe que celle que le nom désigne) sur le
  chemin le plus chaud de la bibliothèque — et `bytesB64` étant un type du tas sans `__setstate__`,
  elle aurait même gagné le plan COMPLET, pour un bénéfice nul (bytes est déjà servi nativement).
  Une fabrique qui n'est pas une classe (`application`, `const`, `numpyB64`, `datetime_depuis`…)
  garde `None` par le même test. Inventaire fait : 10 entrées à l'import, dont 2 types seulement.
- **Écarté : séparer le cache de résolution du registre de constructeurs** (garder
  `class_from_class_str_dict` en alias public consulté d'abord, et écrire les résolutions dans un
  dict distinct). C'était la réponse à l'empoisonnement, et elle n'est plus nécessaire : le test de
  nature l'éteint à lui seul (+2,6 % contre témoin +0,9 %, ci-dessus). Un dict de plus serait une
  deuxième source de vérité pour le même fait, et romprait le point de dérogation documenté dans
  `class_from_class_str` (« il ne faut pas mettre en caching sinon ne peut pas bidouiller
  class_from_class_str_dict »).
- **Équivalence sémantique établie par LECTURE, pas supposée** : `instance()` résout par ce même
  dict puis fait le même `class_.__new__(class_)` (état seul) ou `class_(*__init__)` (arguments) ;
  le commentaire de `class_from_class_str` dit que le registre EST le point de dérogation voulu —
  un plan bâti dessus est donc plus fidèle qu'un plan bâti par import. Empiriquement,
  `__setstate__` reste honoré sous le plan `(classe, 2)` (test `AvecSetstate` → 30) et l'empreinte
  du document réel, dont toutes les classes en ont un, est inchangée.
- **Non implémenté, mesuré : un code de plan « tp_new + collecte des clés d'état + UN seul appel à
  `__setstate__` »**. Après correctif, `instance()` est encore appelée **450 fois par lecture** du
  document réel (contre 900 avant) : une fois par objet, parce que `(classe, 2)` laisse la pose de
  l'état à python. Ce serait exactement ce que fait `instance()` pour une classe à `__setstate__`,
  et cela ramènerait ces classes de 2,35 µs vers les 0,68-0,80 µs du plan complet — un appel python
  par objet au lieu de sept. C'est un changement C++ : noté, pas fait.

### Pistes 1 et 2 : ce qu'elles ont donné

- **Piste 1 (plafonds)** : sur le document réel, la lecture coûte 3,2-4,2 ms contre 1,42 ms pour
  l'écrire — l'asymétrie annoncée est réelle. Dans ce temps, le défaut `rehydrate` pèse 26,4 % et
  la descente vers l'homologue vivant au plus 12,2 % (A/B interlacé, témoin ±2,2 %). Ces deux
  chiffres sont des PLAFONDS de gain, pas des gains : les deux mécanismes rendent un service
  (adoption, réconciliation) qu'on ne peut pas retirer.
  ⚠ Niveau de preuve : **les premiers chiffres de plafond ont été JETÉS** — ils avaient été mesurés
  en blocs séquentiels séparés, ce que le `CLAUDE.md` du dépôt interdit explicitement. Tous ceux
  écrits ici sont interlacés et portent leur témoin A/A.
- **Piste 2 (document hétérogène)** : vérifiée — aucune catégorie du banc n'exerçait un document
  applicatif. Sa forme CONTRÔLÉE est le corpus `tests/objects/crochets_objects.py` livré plus haut
  dans la journée ; un document applicatif réel ne peut pas entrer au banc (il dépend de
  SmartTeacher). C'est pourquoi la mesure de la piste 3 vit dans une sonde de session, et le TEST
  qui la garde dans `tests/test_plan_registre.py`.

### Passe de simplification (par fichier du commit)

- `serializejson/__init__.py` : regardé en entier. Le bloc neuf tient en un `get` + un test de
  nature ; essayé et écarté : factoriser le test dans `tools.py` auprès du registre — il n'a qu'un
  appelant, le déplacer éloignerait le critère de la cascade de plans qu'il sert. La résolution par
  `class_from_class_str` n'est plus appelée quand le registre a répondu : une ligne au lieu de
  deux chemins.
- `serializejson/tools.py` : l'import d'`isInstance` devenu INUTILE après l'inlinage a été retiré
  (seul `notInstanceTypes` est importé) ; sans cette passe il restait un import mort. `isInstance`
  reste défini dans le module vendu : c'est une API préexistante de `_smartframework`, pas du code
  que j'ai écrit, et sa forme neuve est la seule à ne pas redire ce que `notInstanceTypes` dit déjà.
- `serializejson/_smartframework/tools/objects.py` : regardé, rien à enlever — le fait (« quels
  types ne sont pas des instances ») est désormais écrit UNE fois et `isInstance` s'en déduit.
- `tests/test_plan_registre.py` : les quatre formes du registre (raccourci, raccourci à
  `__setstate__`, substitution, fabrique) sont posées par UNE fixture qui rend le registre tel
  qu'elle l'a trouvé ; deux tests de relecture au lieu de six (un paramétré pour l'état seul, un
  pour la fabrique). Essayé et écarté : un seul test paramétré pour les deux formes d'enveloppe —
  une fabrique ne peut PAS servir une enveloppe d'état seul (`function.__new__` lève), les deux
  formes ne se paramètrent pas ensemble.
- `tests/test_encryption.py` : une seule ligne ajoutée de chaque côté du `yield` de la fixture
  autouse ; regardé le reste du fichier, rien à enlever.
- `Notes/DONE/…` (ce fichier) : regardé.

### La fragilité de `test_reecriture_sans_nouveau_scrypt`, DIAGNOSTIQUÉE et fermée

Ce rouge intermittent sous charge (noté plus haut comme préexistant et non reproductible) a été
cerné en fin de chantier, parce qu'il brouillait la validation du correctif de plan. Ce n'est pas
le test qui est faux, c'est une COURSE réelle, et elle n'a rien à voir avec le plan de classe :

- **Mécanisme** : un `dump(..., chemin, encryption_key=…)` est ASYNCHRONE depuis l'addendum du
  19/09 ; le chiffrement tourne sur un exécuteur et c'est LUI qui range l'en-tête d'écriture dans
  `_entetes_ecriture`. Deux tests avant (lignes 322 et 339) écrivent ainsi sous le mot de passe
  « secret » sans attendre. Quand l'insertion du fil tombe APRÈS le `_vide_caches()` de la fixture,
  le test entre avec l'en-tête déjà en cache, son premier `dumpb` ne dérive plus rien et il compte
  **0 scrypt au lieu de 1** — exactement l'assertion observée en rouge. Sous charge (runs à 45-54 s)
  le fil finit tard, d'où l'intermittence ; machine calme (16-22 s) il a fini avant, d'où les runs
  verts et la non-reproductibilité initiale.
- **Niveau de preuve : mécanisme DÉMONTRÉ en direct**, pas déduit. Sonde hors dépôt (dump chiffré
  vers un chemin, puis `_vide_caches()`, puis le comptage du test) : **0 scrypt comptés** ; la même
  sonde avec l'attente intercalée : **1**. La course elle-même reste par nature non reproductible à
  volonté.
- **Correctif** : `serializejson._attend_ecritures()` avant chacun des deux `_vide_caches()` de la
  fixture autouse — on vide les caches quand plus aucun fil ne peut y écrire. Alternative écartée :
  changer le test en `assert len(appels) <= 1`, qui aurait rendu muet ce que ce test garde (un seul
  scrypt par mot de passe) ; autre alternative écartée : attendre dans les deux tests coupables —
  la fixture couvre tout le fichier, y compris les tests à venir.
- **Rien à corriger dans la bibliothèque** : un `dump` asynchrone non attendu puis un vidage de
  cache est un enchaînement que seul un test fait ; le piège « `dump` vers un chemin est asynchrone,
  `_attend_ecritures()` avant toute lecture » est déjà écrit dans le `CLAUDE.md` du dépôt.

### Vérification

- **403 verts × 3.12.13 / 3.13.14 / 3.14.6, DEUX fois chacun** (six runs, après le correctif de
  fixture ; venvs SmartPython, `-p no:typeguard`), goldens
  `tests/serialized` restaurés après chaque run ; aucun `.so` touché (changement purement python,
  la PGO n'a pas à être rebâtie).
- **Preuve par le rouge** : les 9 tests neufs rejoués sur le `__init__.py` COMMITÉ (`git show HEAD:`)
  → exactement les deux tests qui exigent le plan échouent (`assert None == (<class
  AvecSetstate>, 2)`), les 7 autres passent. Les quatre tests de REFUS passent dans les deux
  versions : le statu quo des substitutions et des fabriques est bien préservé, c'est ce qu'ils
  gardent.
- Empreinte de sortie du document réel (`dumps(..., sort_keys=True)`) vérifiée identique entre les
  deux versions avant toute mesure de temps.

- À regarder en premier : `sj_etat_sans_defauts` dans `rapidjson.cpp` (refcounts et ordre des
  exceptions), puis `tests/test_etat_sans_defauts.py::test_exceptions_propagees`.
- Fragilité de `test_reecriture_sans_nouveau_scrypt` : diagnostiquée et fermée (section ci-dessus) ;
  ce qui reste à surveiller est la famille, pas ce test — tout test qui vide un cache ou relit un
  fichier après un `dump` chiffré vers un chemin doit d'abord appeler `_attend_ecritures()`.
- Le `.so` 311 reste sans la fonction (interpréteur non exécutable par ce compte) : le repli
  python de `noyau.py` est ce qui couvre ce cas.
- Les environnements ont changé depuis les addenda (3.13.14/3.14.6/3.12.13 dans
  `versions/<v>/envs/SmartPython-<v>_2026-07-26/`) ; 3.13.15/3.14.7/3.11.x non exécutables
  par ce compte.

## Audit du 02/10 (fin de journée, Fable 5.1) — relecture des commits fba6665,
## 15554c7 et 5abea26 avec un œil neuf

Demande de Baptiste, dictée : « un petit audit sur ce qu'a fait Opus, voir si c'est toujours la
meilleure solution, la meilleure approche, et voir s'il y a d'autres optimisations qui seraient
faisables ou d'autres cas auxquels on n'aurait pas pensé dans la banque d'objets servant à
benchmarker ». Audit par LECTURE SEULE (aucun fichier de code touché, aucune mesure nouvelle) :
`decode_class_plan`, `instance()`, les trois voies C (SjConstruit / SjKeyConstruit /
SjAppliqueEtat / SjChaine, EndObject), `sj_etat_sans_defauts`, le plan d'écriture
`__serializejson__`, `tests/objects/crochets_objects.py`, `lance_benchmarks.mesure_types_objets`,
`test_serialize_vs_pickle.py`, et `noyau.py` de SmartTeacher (lecture seule).

### Verdict sur les deux commits

- **Critère registre (5abea26) : à GARDER.** Le plan n'est refusé que si la cible du registre
  n'est pas une classe portant le dernier segment du nom — c'est exactement la règle
  d'`instance()` (même dict, mêmes formes `__new__`/`__init__`), moins cher qu'une vérification
  d'identité par import, et il laisse passer les classes imbriquées et le nom raccourci de
  SmartTeacher tout en continuant d'exclure substitutions (`bytes` → `bytesB64`) et fabriques.
  Rien de plus simple qui garde les quatre tests de refus.
- **`etat_sans_defauts` en C (fba6665) : correct, mais c'est une DEMI-MESURE.** Le filtrage
  lui-même ne pèse plus que ~0,2 µs ; ce qui reste par objet (+0,9 µs contre le témoin, banc
  crochets 3.13 : 1,7 contre 0,8 µs) est l'appel python de `__serializejson__` + la construction
  du tuple + l'appel C — la primitive a déplacé le coût, pas supprimé la boucle python.
  L'alternative structurelle : un attribut de classe DÉCLARATIF (défauts + propriétés à
  écrire, l'ordre à part) que le plan d'écriture C lirait une fois par classe → zéro python
  par objet, ≈ témoin. C'est un AJOUT d'API (mémoire `api-fidelity-constraint`) : proposition
  pour Baptiste, pas de code. Mineur : `sj_est_defaut` alloue `list(defaut)` à chaque défaut
  tuple — comparaison élément par élément possible, négligeable, pas une priorité.

### Autres optimisations faisables, par ordre de rendement attendu

1. **Lecture : plan C « tp_new + collecte des clés d'état + UN appel `__setstate__` ».**
   Toute classe à `__setstate__` prend aujourd'hui le plan `(cls, 2)` : construction en C, mais
   l'état est posé par `instance()` en python, objet par objet (450 appels par chargement du
   document réel). Mesuré dans la section « trois pistes » : 2,35 → ~0,8 µs/objet, soit ≈ −20 %
   des 3,19 ms de lecture. TOUTES les classes SmartTeacher sont éligibles (`__setstate__` =
   `self.__init__(**etat)` dans `noyau.py`). Première piste à ouvrir.
2. **`SjChaine` parcourt la pile des ancêtres (SjEnveloppeTraversee / SjPlan par niveau) même
   quand `liveRoot == nullptr`** (lecture sans `obj=`, le cas de 100 % des `load` SmartTeacher) :
   `possible` est calculé mais il n'y a pas de sortie anticipée en tête. Court-circuit à tenter,
   borné par le plafond « réhydratation = 26,4 % de la lecture », à mesurer en A/B interlacé
   avec témoin A/A — peut être dans le bruit.
3. **Écriture : `__reduce__` n'a AUCUN plan C** (voie python par défaut, `Encoder.default`),
   alors que `__getstate__` et `__serializejson__` en ont un. La barre `crochet_reduce` du banc
   le mesure déjà ; à chiffrer avant de décider (rare chez SmartTeacher, courant ailleurs).

### Cas manquants dans la banque d'objets du banc

- **Le banc ne voit que `basic_objects` + `crochets_objects`**, alors que `test_serialize_vs_
  pickle.py` fusionne déjà TOUS les modules de `tests/objects/` (slots avec/sans init,
  properties, setters, init args/kwargs/défauts, sous-classes de dict/tuple, variantes
  getstate, init_and_new). Gain de couverture le moins cher : donner au banc le MÊME catalogue
  fusionné (une ligne dans `mesure_types_objets`), chaque module devenant une barre.
- **Pas de catégorie « nom raccourci »** (`constructors[cls.__name__] = cls`, le cas
  SmartTeacher) : l'empoisonnement ×5 corrigé le 02/10 n'aurait été visible QUE par une telle
  barre. À ajouter dans `crochets_objects` (même objet, inscrit sous son nom court).
- **Pas de document synthétique PROFOND et hétérogène** (paquets × questions × choix, références
  arrière denses en `$ref`) : le banc mesure des lots plats de 32 × 8 objets homogènes ; le
  document réel de 450 objets ne s'exerce que hors banc. Un substitut contrôlé, sans dépendance
  à SmartTeacher, donnerait une barre « document » reproductible.
- **Pas de banc d'adoption** (`obj=`, réconciliation par argument) ni d'A/B
  `rehydrate=True/False` : la voie SjChaine/SjVivant n'est mesurée nulle part.
- **Types absents** : namedtuple (commenté dans le test), dataclass, enum, `datetime` à
  ZoneInfo (greffon python PAR objet depuis le 24/09 — à chiffrer), objets numpy sur la page des
  types, `__reduce_ex__` / `__getnewargs__`.
- **Rapport** : afficher les µs/objet ABSOLUS à côté des ratios pickle — pickle paie aussi
  `__getstate__`/`__reduce__`, un ratio seul masque que la barre « crochet » coûte 2× le témoin
  dans les deux camps.

### Niveau de preuve et suite

Tout ce qui précède est vérifié par LECTURE ; seuls les chiffres cités viennent des mesures
déjà consignées plus haut dans cette note. Rien n'est codé : chaque piste (plan C
`__setstate__`, court-circuit SjChaine, extension de la banque) demande son feu vert, sa propre
entrée ici, sa passe de simplification et son autorisation de commit. La proposition d'API
déclarative pour l'écriture se décide avant tout code.

## Suites de l'audit (02/10 soir) — plan `polished-orbiting-swing`

Demande de Baptiste après l'audit : `/plan` « fais un plan ». Ses deux arbitrages : périmètre
« **Lecture + banque** » ; API déclarative d'écriture « **Non, plus tard** » (reste une
proposition, section précédente). Trois étapes : plan C `__setstate__`, court-circuit SjChaine
(mesurer d'abord), banque d'objets.

### Étape 1 — `__setstate__` remis en C : plan `(classe, 3)`

**Livré.**
- `serializejson/__init__.py`, `decode_class_plan` : une classe python (heap) à `__setstate__`
  rend `(classe, 3)` au lieu de `(classe, 2)`. Les classes C (non-HEAPTYPE), setters et
  properties gardent `(classe, 2)`.
- `rapidjson/rapidjson.cpp` : `SjMarquePlan` (second item entier du plan, sinon 0) et
  `SjAppliqueSetstate` (rien si l'état est vide, sinon `inst.__setstate__(mapping)` en un appel,
  `setstate_name` interné). Branchés dans les DEUX branches d'`EndObject` :
  - réhydratation (instance déjà construite par `SjConstruit`, le cas par défaut) : le plan 3
    n'est plus décliné vers python ; `__class__`/`__init__`/`__new__` retirés du mapping par la
    boucle existante, puis `__setstate__` au lieu de `__dict__ = mapping` / `SjAppliqueEtat` ;
  - classique (`rehydrate=False`) : instanciation inchangée (`tp_new`, ou `cls(*args)` pour un
    `__init__` liste), puis le même appel. Un `__init__` dict, un `__init__` scalaire avec
    état, reste en python comme avant ; l'enveloppe stricte `{__class__, __init__}` reste
    « constructeur seul » (le 3 est un entier, `ctor_only` le couvre déjà).
- `tests/test_plan_registre.py` : le plan attendu de `AvecSetstate` devient `(AvecSetstate, 3)` ;
  son test de relecture (`__setstate__` qui multiplie par 10) reste vert, preuve que l'appel a lieu.
- `tests/test_setstate_en_c.py` (neuf, 16 cas × rehydrate True/False) : état remis, état vide =
  `__setstate__` NON appelé, clés `~` transmises, `__init__` liste puis `__setstate__`,
  enveloppe stricte = constructeur seul, aller-retour, exception de `__setstate__` propagée
  avec son type, et **preuve de voie** : `serializejson.instance` remplacé par une fonction qui
  lève, la lecture passe quand même.

**Sémantique de référence** : celle d'`instance()` (`tools.py:1206-1338`) — instance déjà
construite → `__init__`/`__new__` ignorés, toutes les autres clés passées à `__setstate__`
(`~…` compris) seulement si non vide.

**Choix et alternatives écartées.**
- Passer le mapping du décodeur lui-même à `__setstate__` plutôt qu'une copie : personne d'autre
  ne le tient après remplacement chez le parent (même raisonnement que `__dict__ = mapping` du
  cas `envFresh`). Une copie coûterait une allocation par objet pour rien.
- Nouveau marqueur 3 plutôt qu'un plan distinct (classe nue + drapeau ailleurs) : le 3 reste un
  entier, donc tous les consommateurs existants du plan (SjChaine, SjVivant, `ctor_only`) le
  traitent sans retouche ; vérifié par lecture, aucun ne dépend de la valeur 2.
- Écart ACCEPTÉ : une vieille clé `__initArgs__` serait passée à `__setstate__` par la voie C,
  alors que la voie python la consomme. Format antérieur à 2021, jamais écrit depuis ; rare.

**Preuves.**
- Suite complète 3.13 sur binaire de chantier : 403 verts. Sur la PGO finale (gcda supprimés
  avant, .so ≈ 2,34 Mo comme le commité), suite complète APRÈS l'étape 3 : **419 verts ×
  3.12/3.13/3.14**, goldens restaurés. Roue wasm rebâtie (`construit_wasm.sh`, 861 Kio) :
  construite sans erreur, NON rejouée sous Pyodide.
- Rouge sur le binaire commité : les 2 cas de preuve de voie échouent, les 14 de sémantique
  passent à l'identique (le comportement observable ne change pas, seule la voie).
- Identité : `dumps(loads(doc), sort_keys=True)` de 120 json de la banque SmartTeacher, × 2
  voies, même sha256 sur les deux binaires.
- A/B lecture (3.13, hors PGO des deux côtés, sous-processus interlacés, 7 tours, min de 25,
  **charge 24-28**) : document réel (`07 - Structures de contrôle.json`) 3,51 → 2,67 ms
  (**−24 %**), synthétique 2000 objets à `__setstate__` 5,39 → 2,80 ms (**−48 %**) ; témoin
  A/A −3,6 / +2,3 %. Cible du plan (≈ −20 %) atteinte.

### Étape 2 — court-circuit de `SjChaine` sans `obj=` : NON fait, sur lecture et mesure

**Prémisse de l'audit fausse, vérifiée par lecture** (`rapidjson.cpp`, `SjChaine`) : sans racine
vivante, `possible` part faux mais est REMIS à vrai par le premier ancêtre construit non frais
(`possible = !ctx.envFresh`). C'est voulu : en recréation, un parent construit par son `__init__`
a déjà créé ses enfants, qu'il faut adopter au lieu de les doubler (addendum CLAUDE.md du 19/09,
« enfants sans état d'une racine construite par __init__ DOUBLÉS »). Une sortie anticipée sur
`liveRoot == nullptr` réintroduirait ce défaut. Le seul parcours évitable est celui qui remonte
jusqu'à la racine sans trouver d'ancêtre construit : quelques niveaux, sans allocation.

**Mesure du plafond** (3.13, binaire de chantier de l'étape 1, même processus, 9 tours
interlacés, min de 40, charge 24-28), document réel : `rehydrate=True` 2,81 ms, `False` 2,91 ms,
témoin `True'` 2,86 ms. Le crochet ENTIER (SjChaine compris) est sous le bruit depuis l'étape 1 :
le « 26,4 % » de l'audit venait surtout du déclin des plans `(classe, 2)` vers python, qu'a
résorbé l'étape 1. Rien à gagner ici ; ne pas y revenir sans nouveau profil.

### Étape 3 — banque d'objets du banc

**Demande** : étape 3 du plan (catalogue partagé, barre « nom raccourci », document profond,
colonne µs/objet).

**Livré.**
- `tests/objects/__init__.py` : `catalogue(pyqt5=False, numpy=False) -> (objects,
  authorized_classes)`, la fusion qui vivait dans `test_serialize_vs_pickle.py` seul (liste
  `MODULES`, catégories `object_<module>`). Le test l'appelle ; sa boucle de fusion disparaît.
- `tests/objects/crochets_objects.py` : `CrochetCourt`, inscrit sous son nom court dans
  `serializejson.constructors` (la forme de SmartTeacher), catégorie `crochet_C_nom_court` ;
  `nombre_objets` par catégorie.
- `tests/objects/document_objects.py` (neuf) : `Paquet → 50 Question → 8 Choix` + un `Bareme`
  partagé (452 objets), référence arrière choix → question encore ouverte, `__setstate__ =
  __init__(**etat)`, `etat_sans_defauts`, noms courts par `__init_subclass__`. Catégorie `document`.
- `tests/lance_benchmarks.py`, `mesure_types_objets` : catalogue + crochets + document ;
  `log.logs` vidée avant chaque catégorie (liste globale remplie par les `__init__` des
  modules) ; nombre d'objets mesuré par catégorie. Page markdown : deux colonnes « sj par objet
  (µs) » (dumps, loads), « — » pour les catégories de types. Figure SCINDÉE : `benchmark_types_
  objets` (types python) et `benchmark_classes_objets` (voies de construction, crochets,
  document), préfixe `object_objects.` retiré des étiquettes.

**Choix et alternatives écartées.**
- Une figure unique : 59 groupes illisibles sur une page A4 (constaté au rendu) → deux pages,
  séparées par `_categorie_applicative` (préfixe `object_` ou nombre d'objets connu).
- Raccourcir les noms de catégories dans `catalogue()` : ce sont les noms du test (messages
  d'échec, goldens éventuels) → raccourcis dans la figure seulement.
- Compter les objets par parcours de l'arbre : un compteur déclaré par module (`nombre_objets`)
  est exact par construction et ne coûte rien ; les catégories de types n'en ont pas, la
  colonne y vaut « — » (un « objet » n'y a pas de sens commun).

**Preuves.** `test_serialize_vs_pickle` vert sur le catalogue partagé. Document : aller-retour
identique (`dumps` des deux côtés), plans `(classe, 3)` vérifiés, `$ref` présents. Banc en
fumée (chronos et disque neutralisés) : 59 catégories mesurées, 25 types + 34 classes, une seule
écartée (`object_objects.no_init_slots_and_dict`, déjà écartée avant, nommée par le rapport).
Figure des classes rendue et relue à l'œil. Pas de banc complet chiffré : à rejouer machine
calme.

**Points ouverts.** `README.rst` ne référence que `benchmark_types_objets.svg` ; le nouveau
`benchmark_classes_objets.svg` n'y est pas lié (README tenu par une autre instance).
