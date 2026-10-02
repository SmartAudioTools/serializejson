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

## Points ouverts / relecteur

- À regarder en premier : `sj_etat_sans_defauts` dans `rapidjson.cpp` (refcounts et ordre des
  exceptions), puis `tests/test_etat_sans_defauts.py::test_exceptions_propagees`.
- Fragilité préexistante de `test_reecriture_sans_nouveau_scrypt` (ci-dessus), non corrigée.
- Le `.so` 311 reste sans la fonction (interpréteur non exécutable par ce compte) : le repli
  python de `noyau.py` est ce qui couvre ce cas.
- Les environnements ont changé depuis les addenda (3.13.14/3.14.6/3.12.13 dans
  `versions/<v>/envs/SmartPython-<v>_2026-07-26/`) ; 3.13.15/3.14.7/3.11.x non exécutables
  par ce compte.
