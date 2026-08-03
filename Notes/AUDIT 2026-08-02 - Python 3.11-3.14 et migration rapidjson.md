# Audit serializejson — Python 3.11 → 3.14 et migration vers rapidjson C++

Nuit du 2 au 3 août 2026. Contrainte respectée : **aucun changement d'API** — les idées
qui la changeraient sont regroupées en fin de rapport, section « Idées écartées ».

Niveaux de preuve utilisés : *[testé]* = vérifié en exécutant du code cette nuit ;
*[lu]* = vérifié par lecture de code ; *[doc]* = affirmé par une documentation externe.

---

## 1. Résumé

- **La bibliothèque fonctionne maintenant sur 3.10, 3.11, 3.12, 3.13 et 3.14, avec
  numpy 2, et produit des sorties identiques octet pour octet sur les cinq versions**
  *[testé]* — quatre commits, détaillés en §2.
- **Seconde partie de nuit, sur ton feu vert** : étapes A, B, C du plan de migration
  exécutées (cycles et doublons de dicts/listes gérés en `$ref`, plus de remontée
  `gc`, garde anti-segfault 3.12/3.13) et base64 encodé directement dans la sortie
  (mémoire divisée par deux sur les gros bytes). Huit commits de plus, batterie et
  goldens intacts à chaque pas — détails en §6, §7 et §7 bis.
- La seule vraie cassure venait de Python 3.11 : `object.__getstate__` existe désormais
  par défaut, ce qui trompait la détection « la classe a-t-elle un `__getstate__`
  utilisateur ? ». Deux autres cassures venaient de numpy 2, pas de Python.
- Le tableau des cas de figure est remis à jour en §4, avec la réponse à ta note
  « passer tous les `__initargs__` en `__reduce__` ? » : **oui, sans risque** — ni
  pickle 3 ni serializejson n'appellent `__getinitargs__`, c'est du code mort depuis
  Python 2.
- L'audit des astuces (§5) confirme ton diagnostic : tout ce qui contourne rapidjson
  (références circulaires, `$ref`, listes sur une ligne, clés non-chaînes) tient sur
  UN manque : le C++ n'appelle `default()` que pour les objets inconnus, jamais pour
  les `dict`/`list` qu'il traverse nativement. Le plan de migration (§6) commence donc
  par là.

---

## 2. Travail de la nuit : quatre commits, tous validés par la batterie de tests

Les tests se lancent désormais sous Linux depuis la racine :
`<venv>/bin/python3 -m pytest tests/ -q` (ajouter `-p no:typeguard` sur 3.14, voir §8).
Vérification systématique : batterie verte sur les cinq versions **et** diff vide des
fichiers `tests/serialized/*.txt` entre 3.10 (référence) et chaque autre version,
variante numpy comprise *[testé]*.

1. **`tests/conftest.py`** (`7b2e473`) — le dossier `rapidjson/` du dépôt masquait le
   module compilé dès que la racine était sur `sys.path` (namespace package sans
   `Encoder`). Le conftest importe le `.so` du dossier et l'enregistre sous le nom
   `rapidjson`.
2. **`serializejson/tools.py`** (`10c700b`) — le correctif Python 3.11+ :
   `class_has_user_getstate()` ne compte un `__getstate__` que s'il n'est pas
   l'implémentation par défaut d'`object` (comparaison d'identité, marche aussi
   en 3.10 où elle vaut `None`). Sans lui, depuis 3.11 : slots sérialisés en
   `__state__` opaque au lieu d'attributs à plat, ordre d'insertion au lieu du tri
   alphabétique, et surtout **filtre d'attributs, properties et getters silencieusement
   ignorés**.
3. **`serializejson/plugins/serializejson_numpy.py`** (`2ce9460`) — numpy 2 : ajout de
   `numpy._core.multiarray._reconstruct`, `numpy._core.multiarray.scalar` (renommage
   de `numpy.core`) et `numpy.bool` (nouveau nom canonique) aux classes autorisées.
   Les anciens noms restent pour relire les fichiers numpy 1.
4. **`rapidjson/rapidjson.cpp` + les cinq `.so`** (`5e03851`) — les flottants étaient
   écrits avec `PyObject_Repr` : `repr(np.float64(0.0))` donne `np.float64(0.0)` avec
   numpy 2 → JSON invalide dans tous les modes. Passage à `PyFloat_Type.tp_repr`,
   exactement comme le cas entier trois lignes plus haut (`PyLong_Type.tp_repr`,
   IntEnum). Binaires recompilés pour 3.10 à 3.14 (`setup.py build_ext --inplace`).

En plus : `tests/test_serialize_vs_pickle.py` (`e29aa3f`) importait `numpy` nulle part —
`NameError` dès que `use_numpy = True`.

**Identité git** : `~/.gitconfig` est illisible depuis le bac à sable, les commits
portent `smartaudiotools <smartaudiotools@NUC12WSKi7.lan>` (même motif que tes commits
`DELL3551.lan`). `git commit --amend --reset-author` possible si tu configures autre
chose. Rien n'a été pushé.

---

## 3. Ce qui a changé dans Python entre 3.10 et 3.14 (pour la sérialisation)

| Version | Changement | Impact serializejson |
|---|---|---|
| 3.11 | `object.__getstate__` par défaut sur tous les objets ([doc pickle](https://docs.python.org/3/library/pickle.html#object.__getstate__), [jsonpickle #396](https://github.com/jsonpickle/jsonpickle/pull/396), [scikit-learn #25188](https://github.com/scikit-learn/scikit-learn/pull/25188) ont eu le même problème) | Corrigé (commit 2). C'est la SEULE cassure Python constatée *[testé]* |
| 3.11 | le `state` par défaut des classes à `__slots__` devient le tuple `(dict, slots_dict)` produit par `object.__getstate__` — la capacité que tu avais dû émuler à la main pour les versions antérieures (voir §4, note slots) | serializejson faisait déjà cette fusion dans `tuple_from_reduce` ; le commit 2 la réactive |
| 3.12 | rien touchant reduce/getstate ; `distutils` retiré (le `setup.py` du fork passe par setuptools, compile OK *[testé]*) | aucun |
| 3.13 | `array` : typecode `'u'` déprécié, **retrait prévu en 3.16** (warning vu dans la batterie *[testé]*) | voir §8 dettes |
| 3.14 | `pickle.DEFAULT_PROTOCOL` passe de 4 à 5 *[testé]* | aucun : serializejson fixe son protocole (4 par défaut), seule la sortie de pickle lui-même change dans les goldens |
| 3.14 | annotations paresseuses (PEP 649) | aucun constaté : batterie identique *[testé]* |

Preuve globale : après le commit 2, `tests/serialized/serializejson*.txt` sont
identiques octet pour octet entre les cinq versions, drapeaux par défaut ET variante
numpy *[testé]*.

---

## 4. Tableau des cas de figure remis à jour

Colonnes : ce que la classe implémente → ce que fait la sérialisation.
« reduce hérité » = `__reduce_ex__` d'`object` non réimplémenté (chemin
`copyreg.__newobj__`). Valable pickle ET serializejson, 3.10 → 3.14, après commit 2.

| Cas (classes de tests) | dump : état obtenu | JSON produit | load : restauration |
|---|---|---|---|
| rien (`C_New_SaveDict_RestoreNothing`) | reduce hérité → `__dict__` | attributs à plat, triés | `__new__` puis `__dict__.update` (ou setattr) |
| `__slots__` seuls (`no_init_slots`) | reduce hérité → `(None, {slots})` — fourni par `object.__getstate__` depuis 3.11, émulé avant | **fusionnés à plat** (astuce serializejson, réactivée par commit 2) | setattr slot par slot |
| `__dict__` + `__slots__` (`no_init_slots_and_dict`) | reduce hérité → `(dict, slots)` | fusionnés à plat, triés | setattr |
| `__getstate__` utilisateur → dict | reduce hérité → ton dict | attributs à plat (pas de re-tri : ton ordre) | `__dict__.update`/setattr |
| `__getstate__` + `__setstate__` utilisateur | idem | `__state__` si pas dict de str, sinon à plat | `__setstate__(state)` |
| `__getnewargs__`/`__getnewargs_ex__` (`new_getnewargs`) | reduce hérité | `__new__: [args]` | `cls.__new__(cls, *args)` |
| `__reduce__` = `(cls, initargs)` (`init_args`) | ton tuple | `__init__: [args]` | `cls(*args)` — **le** cas nominal |
| `__reduce__` = `(apply, (cls, None, kwargs))` (`init_kwargs`) | ton tuple | `__init__: {kwargs}` | `cls(**kwargs)` |
| `__reduce__` = `(cls, args, state)` | ton tuple | `__init__` + attributs/`__state__` | `cls(*args)` puis état |
| `__getinitargs__` (`*_ghost_getinitargs`) | **IGNORÉ** par pickle 3 et par serializejson *[testé, classes "ghost"]* | comme si absent | comme si absent |
| `__serializejson__` / plugin | ton tuple 3-6 éléments | selon tuple | selon tuple |

### Réponse à la note « passer tout les __initargs__ en __reduce__ ? »

**Oui, et c'est même la seule voie.** `__getinitargs__` est un protocole de pickle
**Python 2** (protocole 0/1) : pickle 3 ne l'appelle jamais, serializejson non plus —
les classes de test `*_ghost_getinitargs` existent précisément pour vérifier qu'il
reste fantôme *[testé]*. La convention `saveInitArgsDict`/`generateInitArgs` de
`SmartFramework/tools/objects.py:277-300` repose dessus : partout où elle est
utilisée, l'`__init__` n'est en réalité PAS rappelé à la désérialisation.

Migration mécanique, classe par classe, en relançant la batterie à chaque fois :

```python
# avant (mort depuis Python 3) :
def __getinitargs__(self):
    return (self._par1, self._par2)

# après (honoré par pickle ET serializejson, 3.10 → 3.14) :
def __reduce__(self):
    return (self.__class__, (self._par1, self._par2))
    # + un 3e élément state si des attributs doivent survivre en plus de l'__init__
```

Pour des arguments nommés : `return (apply, (self.__class__, None, kwargs))` — c'est
le format que le tableau ODS documentait déjà, il reste exact. Piège à connaître :
`__reduce__` réimplémenté fait que `__getstate__` n'est PLUS appelé (comme documenté
dans ta note « Sérialisation & Copy ») — si la classe avait les deux, rapatrier l'état
dans le tuple.

Note slots : ta remarque du 2/08 au soir — « prendre en compte ce qui a été ajouté à
Python pour la sérialisation des slots, que j'ai dû patcher avant 3.11 » — est
couverte : l'émulation maison (fusion `(dict, slots)` dans `tuple_from_reduce`,
`generic__reduce_ex__` dans tools.py) donne aujourd'hui exactement le même résultat
que le `object.__getstate__` natif de 3.11+ *[testé, diff octet pour octet]*.
`generic__reduce_ex__` (tools.py:938) n'est plus appelé par personne *[lu]* — il
pourra tomber quand 3.10 sera abandonné, `object.__getstate__` le remplace.

---

## 5. Audit des astuces Python qui contournent rapidjson

Le fil conducteur : **le C++ n'appelle `default()` que pour les objets qu'il ne
connaît pas.** `dict` et `list` sont traversés nativement, sans hook. Toutes les
astuces découlent de ce manque.

### 5.1 Références circulaires et objets partagés (`$ref`)

- Mécanisme *[lu, __init__.py:800-809 et 1100-1183]* : `default()` mémorise `id(inst)`
  dans `_already_serialized`. Si un id revient, reconstruction du CHEMIN du premier
  exemplaire par **remontée `gc.get_referrers` récursive** jusqu'à `root`, en
  re-sérialisant au passage les parents objets (`_dict_from_instance`) pour retrouver
  l'ordre des clés, puis émission de `{"$ref": "root.x[2].y"}`.
- Ça marche pour les objets : cycle d'objets vérifié cette nuit *[testé]*.
- **Trou connu et confirmé** *[testé cette nuit]* : `dict`/`list` **circulaires** →
  `RecursionError` (`A["link"]=B; B["link"]=A`, `L.append(L)`) ; `dict`/`list`
  **dupliqués** → écrits en double silencieusement, le partage est perdu à la
  relecture (`[d, d]` recharge deux dicts indépendants). Exactement ta note
  « Adding default_dict et default_list methods ».
  → **COMBLÉ en seconde partie de nuit** par les étapes B et C du plan (§6).
- Fragilités du mécanisme actuel :
  - `_already_serialized` ne garde que des **ids sans référence forte** : un objet
    temporaire créé pendant le dump (tuple sorti d'un reduce, par exemple) peut mourir
    et son id être réutilisé → fausse alerte « déjà vu », rattrapée parce que
    `_get_path` qui échoue laisse la sérialisation normale se faire, mais au prix d'une
    exploration `gc.get_referrers` complète *[lu ; ton commentaire __init__.py:921-924
    montre que tu l'avais repéré]*.
  - `gc.get_referrers` est O(tout le tas) À CHAQUE référence répétée, et la remontée
    re-sérialise les parents (allocations) juste pour retrouver un chemin.
  - `_searchSerializedParent` doit reproduire la logique de tri (`sort_keys`) pour que
    le chemin corresponde au JSON déjà écrit : duplication d'une règle à deux endroits.
- Verdict : à remplacer par une mémo-map C++ (voir plan §6, étape C).

### 5.2 Tableaux 2D « jolis » et listes de nombres sur une ligne

- `single_line_list_numbers` / `single_line_init` / `single_line_new` *[lu,
  __init__.py:861-920]* : chaque valeur candidate est **re-sérialisée dans un
  sous-appel `rapidjson.dumpb` complet** (avec `_default_one_line`), le résultat étant
  réinjecté comme `RawBytes`. Un tableau numpy 2D = un `dumpb` par LIGNE
  (`__init__.py:832-843`).
- Coût : un encodeur C++ complet instancié par liste ; `_onlyOneDimSameTypeNumbers`
  re-parcourt chaque liste en Python ; tes commentaires notent déjà « 91.2 % du temps »
  sur ce chemin.
- Limites fonctionnelles notées dans ton TODO et confirmées à la lecture : ne marche
  pas pour les valeurs d'un dict pur, ni les listes de listes hors numpy *[lu]*.
- Verdict : c'est un simple choix de FORMATAGE — sa place est dans le writer C++
  (étape D du plan), où « liste homogène de nombres → une ligne » se décide au moment
  d'écrire, sans double sérialisation ni RawBytes.
  → **FAIT en fin de nuit** (`rapidjson.SingleLine`, voir §6.D et §7 bis).

### 5.3 Dictionnaires à clés non-chaînes

- `_dict_from_instance` *[lu, __init__.py:952-997]* : dict encapsulé en
  `dict_non_str_keys`, chaque clé encodée en str (int → str, str ambiguë → quotes,
  bytes → `b'..'`/`b64'..'`, tuple → json). Fonctionne partout, racine et niché
  *[testé]*, parce que ton fork route DÉJÀ ces dicts vers `default()` : le chemin
  natif C++ est conditionné à `all_keys_are_string` (rapidjson.cpp:2380). C'est
  d'ailleurs le modèle à suivre pour l'étape B du plan : la même déviation vers un
  hook, mais pour TOUS les dicts/listes, pas seulement ceux à clés non-str.
- Verdict : disparaît aussi avec le hook dict C++ (étape C/E).

### 5.4 Paramètres globaux partagés

- `_update_serialize_parameters` *[lu, __init__.py:1083-1086]* recopie les paramètres
  de l'Encoder dans le MODULE `serialize_parameters`, que les plugins lisent en
  global. Deux encodeurs configurés différemment ne peuvent pas s'entrelacer
  (ni threads, ni réentrance dump-dans-dump). Pas un bug aujourd'hui (usage
  séquentiel), mais dette à connaître avant de multithreader la compression (§7).

### 5.5 Ce qui est DÉJÀ dans ton fork C++ (inventaire)

*[lu, rapidjson.cpp]* : `RawBytes` (2475), `RawBytesToPutInQuotes` (2478), `dumpb`
(2652), `Extend` memcpy dans le writer (tes notes RapidJson-Optimisations documentent
le x2 sur `WriteRawValue`), `MemoryBuffer` quand `ensure_ascii=False`,
`PyUnicode_FromStringAndSize`. Le fork est à jour de ces optimisations et compile
proprement de 3.10 à 3.14 *[testé]*.

---

## 6. Plan de migration progressive vers le C++ (une étape = un commit = batterie verte)

Ordonné pour que chaque étape soit petite, testable, et REMPLACE une astuce Python
sans changer ni l'API ni le format JSON. La batterie + le diff des
`tests/serialized/*.txt` entre avant/après servent de non-régression à chaque pas
(même méthode que cette nuit).

- **A. Filet de sécurité d'abord** — ✅ **FAIT cette nuit** (`tests/test_references.py`,
  commit `a608f29`) : cycles/duplicatas d'objets, de dicts et de listes, gros bytes
  compressés ou non, tableaux numpy 1D/2D/bool.
- **B. Hooks `default_dict` / `default_list`** — ✅ **FAIT cette nuit** (commits
  `4a3a35e` C++ et `12fe53e` Python) : l'Encoder C++ consulte ces méthodes comme
  `default`, avant la traversée native d'un dict à clés chaînes ou d'une liste ;
  retour de l'objet lui-même = chemin natif, retour d'un remplaçant = sérialisé à la
  place. **Les dicts et listes circulaires ou dupliqués sont maintenant gérés en
  `$ref`**, rechargés avec cycles et partages restaurés. Découverte au passage :
  sur 3.12/3.13, la marge de pile C était si étroite qu'un JSON cyclique ou trop
  profond segfaultait AVANT la RecursionError (constaté avec l'ancien binaire aussi,
  déclenché par un simple accroissement de la taille des frames) — corrigé par une
  garde de récursion consommée à chaque niveau de `dumps_internal` (~750 niveaux
  d'imbrication restent acceptés). Et `append()` n'initialisait jamais le mémo :
  appender un objet plantait en AttributeError depuis toujours — corrigé.
- **C. Mémo id → chemin rempli au fil de l'écriture** — ✅ **FAIT cette nuit**
  (commits `4fdbb41` C++ et `b543be9` Python), sous une forme hybride : le C++
  maintient la pile des segments du chemin courant (traqueur exposé par
  `Encoder.json_path()`), le Python mémorise `id → chemin` à la première écriture
  et émet les `$ref` par simple lookup. Plus AUCUNE remontée `gc.get_referrers` à
  l'encodage (elle reste en secours et pour les `Reference`). Chemins produits
  identiques aux anciens (goldens octet pour octet).
- **D. Formatage « une ligne » dans le writer** — ✅ **FAIT en fin de nuit** (voir
  §7 bis) : `rapidjson.SingleLine`, sous-arbre compact écrit par le PrettyWriter
  lui-même, un seul encodeur pour tout le document. L'extension aux cas non
  couverts (valeurs de dict pur, listes de listes) reste possible et changerait la
  sortie — à activer plus tard derrière les paramètres existants si tu la veux.
- **E. Clés non-chaînes dans le hook dict** (fusion avec B) : l'encodage des clés
  reste en Python (logique fine), seul le POINT D'ENTRÉE migre.
- **F. (plus tard) chemin bytes zéro-copie** : voir §7 — dépend de B-D mais surtout
  du choix blosc2.

Jalon suggéré après C : figer une version, elle corrige déjà les deux limites les plus
douloureuses (cycles dict/list, coût des `$ref`).

---

## 7. Étude copies mémoire : données brutes → (blosc) → base64 → JSON

### Chaîne actuelle au dump d'un `bytes`/`ndarray` *[lu, plugins builtins et numpy]*

| # | Étape | Copie |
|---|---|---|
| 1 | `numpy.ascontiguousarray(data)` si non contigu | 0-1 |
| 2 | `blosc.compress(...)` → bytes compressé | 1 |
| 3 | `b64encode_as_string(...)` → str ascii | 1 |
| 4 | la str traverse le writer C++ (copie dans le buffer, chemin ascii sans re-scan) | 1 |
| 5 | `PyBytes_FromStringAndSize`/`PyUnicode_...` du buffer final (dumps) ou write fichier | 1 |

Soit 4 à 5 copies du même contenu. Au load, symétrique : str JSON →
`b64decode_as_bytearray` → `blosc.decompress` → `frombuffer` (celui-ci sans copie),
plus le « A REVOIR : 2 COPIES !!! » de `bytesB64` (builtins:38-41).

### Où gagner, par ordre de rentabilité

1. **Étape 3+4 fusionnées côté C++** — ✅ **FAIT cette nuit** (commits `da34c6a` C++
   et `e208a85` greffons) : nouvel objet `RawBytesToBase64` (tout buffer contigu :
   bytes, bytearray, tableau numpy), base64 encodé directement dans le buffer de
   sortie, par morceaux dans les chunks pour les fichiers. Les greffons bytes,
   bytearray et numpy l'utilisent. **Mesuré sur 50 Mo incompressibles : 84 → 64 ms
   et pic mémoire au-delà de l'entrée divisé par deux (134 → 67 Mo)**, sortie
   identique octet pour octet. (L'encodeur C++ est un 3-octets→4-chars simple ;
   passer à libbase64/SIMD comme pybase64 reste possible si besoin.)
2. **Étape 2 pilotée sans copie finale** : `blosc2.compress` accepte `dst` /
   travaille par chunks — on peut compresser VERS un buffer pré-réservé, voire
   directement vers la zone réservée du writer si 1 est fait (b64 ensuite in-place
   n'est pas possible, il faut deux zones — mais une seule allocation temporaire
   réutilisable entre bytes successifs suffit, ta « stratégie 4 » des notes Binaire).
3. **dumps vers fichier** : ton idée du TODO (queue de morceaux + pool de threads qui
   compressent/encodent pendant que le writer continue) est la bonne suite, mais elle
   dépend de la dette §5.4 (paramètres globaux) et n'a de sens qu'après 1-2.

### blosc2 : câblé en fin de nuit, sur ton idée « compresser côté C++ »

Faits vérifiés *[testé]* :

- La roue python-blosc2 (4.9.1, **Python ≥ 3.11**) embarque une vraie
  `libblosc2.so` + ses en-têtes → chargée par `dlopen` à l'exécution, AUCUNE
  dépendance de compilation. Installée cette nuit dans les venvs 3.11 → 3.14.
- ⚠ **La compatibilité est à sens unique** (contrairement à ce que j'ai d'abord
  affirmé) : blosc2 relit les trames v1 (octet de version 2), mais python-blosc
  v1 NE relit PAS les trames blosc2 (octet 5) — même via l'API « compatibilité
  blosc1 » de c-blosc2, qui n'est compatible qu'en SIGNATURES, pas en format.
- D'où le montage retenu : compressions `blosc2*` en OPT-IN
  (`bytes_compression=("blosc2_zstd", 9)`, étiquettes `"b64_blosc2"`/`"blosc2"`),
  compression faite en C sans le GIL (`rapidjson.BloscToBase64`), décodage qui
  dispatch sur l'octet de version et relit donc LES DEUX formats. Les défauts
  d'écriture ne bougent pas.
- **Mesuré sur un tableau de 200 Mo** : 110 → 43 ms, pic mémoire au-delà de
  l'entrée 200 Mo → 1 Mo (le bytes compressé intermédiaire disparaît), sortie
  deux fois plus petite (zstd plus récent).

**La décision restante** : basculer (ou non) les DÉFAUTS vers `blosc2_*`. Les
nouveaux fichiers seraient alors illisibles pour python-blosc v1, les
environnements 3.10 (pas de roue blosc2) et les anciennes versions de
serializejson — le décodage 3.11+ à jour, lui, lit tout.

---

## 7 bis. Seconde partie de nuit : coûts mesurés et questions ouvertes

Après ton feu vert « avance un maximum sur tout ce que tu as proposé », les étapes
A, B, C et le point 1 de l'étude mémoire ont été exécutés (voir les ✅ ci-dessus,
8 commits supplémentaires). Ce qui mérite ton regard au réveil :

### Ta question de la nuit : « le mémo qui garde les objets ne va pas faire exploser la mémoire ? »

Tu avais raison sur le passé : avant cette nuit, un id recyclé ne pouvait produire
qu'une recherche `gc` inutile et invisible (chemin introuvable → re-sérialisation
normale), d'où ton absence de problème. Mais maintenant que le mémo stocke
`id → chemin` pour émettre les `$ref` sans `gc`, un id recyclé émettrait un `$ref`
FAUX : la référence forte est devenue une condition de justesse — c'est exactement
le memo de pickle, qui garde lui aussi les objets vivants jusqu'à la fin du dump.

Mesuré *[testé]* sur 100 000 petits objets (json de 5,5 Mo) : pic 42 Mo sans
rétention → 56 Mo avec (+ un tiers, ~140 octets par objet : les dicts
`{"__class__": ...}` temporaires retenus le temps du dump, tout est libéré par
`_clean()`). Les VRAIS objets dupliqués, eux, étaient de toute façon vivants
pendant tout le dump (ton intuition). Piste si ce tiers gêne : ne pas mémoïser les
dicts d'état produits par `default()` (le C++ sait les distinguer via le marqueur
attributs) — mais un `obj.__dict__` partagé ne serait alors plus déduppliqué ;
à arbitrer.

### Coût des hooks sur les données JSON pures *[testé]*

Sur 21 000 dicts/listes purs (aucun objet) : 31,6 ms avant hooks → 57,3 ms avec
mémo complet (+81 %). Détail : ~1 ms d'appels de hooks à vide, le reste est le
travail Python par conteneur (id, insertion mémo, `json_path()`). C'est le prix de
la déduplication des dicts/listes ; les dumps riches en OBJETS, eux, payaient déjà
un `default()` par objet et bougent peu (batterie inchangée). Optimisation prévue
si besoin : descendre tout le mémo en C++ (plus d'appel Python par conteneur) —
c'est la suite naturelle de l'étape C.

### Fin de nuit (après ton « continue tant que tu peux »)

- **Étape D FAITE, sur ta consigne explicite** (commits `c92ee32` C++ et `2add915`
  Python) : tu as refusé le statu quo — « je ne veux pas appeler de deuxième
  encodeur compact, cette solution était un pansement, ce deuxième encodeur est
  incapable de détecter des références déjà sérialisées » — et c'était le bon
  argument. Nouvel objet `rapidjson.SingleLine(value, number_mode=None)` : le
  PrettyWriter écrit lui-même le sous-arbre en compact (bascule
  PushCompact/PopCompact effective après le préfixe du premier jeton, qui
  appartient encore à la mise en page du parent). `single_line_init`,
  `single_line_new`, `single_line_list_numbers` et les lignes de tableaux numpy
  passent par lui : **un seul encodeur pour tout le document, mémo/hooks/chemins
  actifs dans les sous-arbres** — un doublon dans les args `__init__` est
  désormais `{"$ref": "root.__init__[0]"}` et recharge partagé (nouveau test).
  Sorties de la batterie inchangées octet pour octet ; mesure alternée sous
  charge contrôlée : **105 ms contre 163 pour l'ancien double encodeur** sur
  5 000 objets mixtes (et 145 sans une-ligne : le compact unifié est même plus
  rapide que le tout-indenté). ⚠ méthode : mes premières mesures de la soirée
  (163/152, puis un faux « 362 ») étaient polluées par la charge des autres
  instances — refaites en alternant les variantes dans la même boucle.
- **Décodeur : `$ref` différés sans gc** (commit `f2b5015`) : les marqueurs non
  résolus pendant le parse étaient remplacés par `gc.collect()` + un
  `gc.get_referrers()` PAR marqueur ; remplacé par la résolution des chaînes de
  `$ref` puis UN parcours itératif de l'arbre chargé (dicts, listes, tuples,
  attributs, slots, protégé des cycles). Mesuré : ~23 s extrapolées → 36 ms pour
  18 000 marqueurs différés *[testé]*. Nouveau test : `$ref` différé réinstallé
  dans un slot.
- **Chemins paresseux** (commit `a7974ad`) : le profil montrait que 21 des 25 ms
  de surcoût des hooks venaient de la construction de la chaîne de chemin à
  chaque première écriture ; `json_path_id()` matérialise maintenant un noeud
  O(1) dans un arbre de segments partagé et la chaîne n'est construite que pour
  les vrais `$ref`. 57,3 → 51,4 ms sur le banc de 21 000 conteneurs purs
  (rapidjson brut : 31,6 ms).
- **Doc remise en accord** (commit `bcd4bd5`) : l'avertissement « pas encore pour
  les listes et dictionnaires » du README/docstring est retiré, la TODO de la doc
  mise à jour. Et les docstrings passent en chaînes brutes (commit `d971bab`) :
  plus de SyntaxWarning à l'import depuis 3.12.

- **Mémo tout-C++ : FAIT aussi** (commits `c2265de` et `f88a835`) : nouveau
  paramètre `memo_refs=True` de l'Encoder du fork — l'encodeur mémorise lui-même
  les dicts/listes écrits (carte conteneur → noeud de chemin, références fortes
  relâchées en fin d'encodage) et émet les `$ref` sans repasser par Python ;
  serializejson a retiré ses hooks `default_dict`/`default_list`. Gain plus
  modeste qu'espéré : 51,4 → 48,6 ms sur le banc de 21 000 conteneurs purs
  (rapidjson brut : 33,1) — le surcoût restant est maintenant réparti entre la
  garde de récursion, le push/pop de segments par valeur et la mécanique de mémo
  par conteneur, tous côté C ; plus grand-chose à gratter sans changer de
  structure. Les `Reference` interrogent ce mémo via `json_path_id_of()`.

- **blosc2 côté C : FAIT aussi, en opt-in** (commits `083d445` et `111c9c9`,
  détails §7) — sur ta question « tu ne peux pas utiliser la version C++ pour ne
  pas repasser par du python ? ». Compression en C sans le GIL via la libblosc2
  de la roue python-blosc2 chargée par dlopen, 110 → 43 ms et pic 200 → 1 Mo sur
  200 Mo. Défauts inchangés : trames illisibles par v1/3.10 (compat à sens
  unique, vérifiée), la bascule des défauts te revient.

### Ce qui reste volontairement en plan (arbitrages à toi)

- ~~Basculer les défauts vers blosc2~~ **fait sur ta décision** (`dab3f9a`),
  et le problème 3.10 est DISSOUS depuis le fork embarqué (§7 quinquies) :
  les cinq versions écrivent et lisent blosc2 à l'identique. Reste vrai :
  les fichiers compressés par défaut ne sont plus lisibles par les ANCIENNES
  versions de serializejson (python-blosc v1 seul).
- ~~Dédup des dicts d'état, extension du une-ligne~~ **tranchés et faits sur
  tes consignes de 23 h 35** (rigueur totale + extension partout).
- **Pousser le fork c-blosc2 sur GitHub** (le clone patché est local,
  `rapidjson/blosc2_determinisme.patch` contient tout) et, à terme, statifier
  la lib dans le module rapidjson (« fusion » complète).

## 7 ter. Troisième vague (nuit du 2 au 3, sur tes six consignes de 23 h 35)

1. **Défauts de compression basculés vers blosc2** (`dab3f9a`) : `blosc2_zstd`
   dès que la roue est là, repli v1 sur 3.10. Conséquence actée : 3.10 et 3.11+
   n'écrivent plus les mêmes octets pour les gros bytes.
2. **Rigueur des `__dict__` partagés** (`59177a1`) : plus jamais aplatis deux
   fois — `$ref` vers le nœud `.__dict__` du premier exemplaire, clé `__dict__`
   ASSIGNÉE au chargement : les partages physiques sont restaurés, ce que
   pickle lui-même perd (mesuré en référence). Trois tests couvrent les deux
   ordres d'apparition et le partage entre objets. Et ton idée d'optimisation
   est en place : les dicts d'état construits par serializejson, uniques par
   construction, ne passent plus par le mémo (le marqueur « attributs »
   existant suffit, pas besoin d'un nouveau type).
3. **Une-ligne généralisé, décidé en C++** (`9850fc9`) : les listes homogènes
   de nombres passent sur une ligne PARTOUT (valeurs de dicts purs, listes de
   listes rendues en 2D lisible) — mise en forme des fichiers changée, comme
   accepté. Au passage, bug d'imbrication de bascules compactes corrigé
   (garde `InCompact()`).
4. **Tableaux numpy écrits depuis leur buffer** (`d5e9a8a`) :
   `rapidjson.ArrayRows`, 1D/2D, sans `tolist()` ni aller-retour Python —
   414 → 96 ms le million de float64 en 1000×1000. Graphie des flottants par
   le dtoa de rapidjson (valeurs identiques, forme parfois différente de
   `repr`).
5. **Déterminisme multi-thread : NON, mesuré** — ni blosc v1 ni blosc2 ne sont
   déterministes au-delà d'un thread (deux exécutions à 8 threads diffèrent,
   même blocksize et splitmode figés ; un thread est parfaitement stable —
   d'où la stabilité de ton défaut à 1 thread). Le déterminisme parallèle
   devra se construire au-dessus : morceaux d'entrée de taille fixe compressés
   indépendamment puis concaténés dans l'ordre (chaque trame blosc connaît sa
   taille : flux re-découpable sans index) — design consigné, non implémenté.
6. **Course à pickle** — trois chantiers :
   - **chemin rapide d'encodage par classe** (`1ea6f8e`) : `class_plan()`
     décide UNE fois par classe ; les objets ordinaires sont écrits tout en
     C++ (attributs filtrés/triés, mémo, rigueur `__dict__`), identique à
     l'octet près au chemin Python. 83 → 39 ms les 20 000 objets.
   - **chemin rapide de décodage** (`14477ad`) : `decode_class_plan()`,
     instanciation directe `cls.__new__` + assignation du dict parsé, zéro
     appel Python par objet ; `start_object` court-circuité, racine posée par
     le C++. 70 → 39 ms.
   - **SIMD SSE 4.2 du parseur activé** (`041b9c0`) : un define ;
     50 000 chaînes chargées en 6,0 ms au lieu de 15,4.

   **Où on en est face à pickle** (mesure finale, min de 5, 3.14) :

   | Cas | dumps | loads |
   |---|---|---|
   | 20 000 objets à 3 attributs | 38,6 ms vs 8,7 (×4,4 — était ×9,2) | 29,8 vs 7,0 (×4,3 — était ×8,3) |
   | conteneurs purs | ×7,0 (inchangé — déjà tout C++) | ×6,0 (était ×6,6) |
   | numpy 8 Mo | ×0,6 — PLUS RAPIDE que pickle | ×2,7 (était ×3,2) |
   | 50 000 chaînes | ×4,3 | ×3,1 (était ×10,2) |

   L'écart restant est structurel pour l'essentiel : JSON lisible + tri +
   mémo universel contre un format binaire à longueurs préfixées. Prochaines
   marches identifiées si tu veux continuer : conteneurs purs (séparateurs et
   préfixes du writer appelés valeur par valeur), et le base64/blosc au
   DÉCODAGE (b64 vers buffer sans copie).

## 7 quater. Quatrième vague (fin de nuit, sur ta liste de 4 h 40)

1. **Écriture directe des fichiers depuis le C++** : NON fait, documenté — le
   flux passe par `stream.write(bytes)` Python par tranche de 64 Ko (quelques
   appels par fichier : coût réel faible). La voie propre est un wrapper
   d'écriture sur le descripteur (`fileno()`) court-circuitant Python ; gain
   attendu modeste, à faire à tête reposée.
2. **Options de compilation** : déjà agressives — l'interpréteur SmartPython
   impose `-O3 -march=native -ftree-vectorize -fno-semantic-interposition`
   à ses extensions ; ce qui manquait était le SIMD interne de rapidjson,
   activé cette nuit (`041b9c0`).
3. **Marches 1 et 2** : la marche 2 est faite (`29b4468`) — le base64 des
   charges binaires est décodé DIRECTEMENT depuis le tampon de parse (table C,
   repli automatique si pas du base64 propre), plus de chaîne intermédiaire.
   Verdict mesuré : gain réel sur tailles moyennes, mais sur les très gros
   tampons le plancher est le SCAN du parseur lui-même (9 ms sur 13 pour
   10,5 Mo) — c'est LE prochain gisement côté chargement. La marche 1
   (conteneurs purs) est structurelle : l'écart restant est entre rapidjson et
   pickle (~90 ns par valeur de JSON contre une recopie binaire), nos couches
   n'y ajoutent plus que quelques ms.
4. **Modifier blosc2 pour un multi-thread déterministe** : pas besoin de le
   forker — l'API par CONTEXTES de c-blosc2 est mono-thread donc pure et
   déterministe ; le parallélisme est construit au-dessus (`53467e3`) :
   morceaux d'entrée de taille FIXE (1 Mo) compressés indépendamment par nos
   threads C++, trames concaténées dans l'ordre, décompression parallèle
   symétrique vers des positions précalculées. **Octets identiques quel que
   soit le nombre de threads et d'une exécution à l'autre (testé), 441 →
   179 ms sur 96 Mo à 8 threads.** Étiquettes `b64_blosc2p`/`blosc2p`,
   activation par `bytes_compression_threads > 1` avec un nom `blosc2_*`.
   En-têtes blosc2 vendorés (types seulement, dlsym pour tout appel, garde de
   version majeure).
5. **Niveaux de cache** : la leçon de blosc est le BLOCAGE — travailler par
   blocs tenant en L1/L2 et enchaîner toutes les passes sur un bloc avant de
   passer au suivant. Nos morceaux de 1 Mo (~L2) vont dans ce sens pour la
   compression ; l'étape suivante serait de fusionner compression ET base64
   par morceau (compresser le morceau, l'encoder en base64 pendant qu'il est
   chaud, plutôt que deux passes complètes) — design noté, non fait.
6. **Accélérer encore** : fait ce qui était sûr cette nuit (voir 7 ter/quater) ;
   les deux gisements suivants sont le scan du parseur (chargement) et la
   fusion par morceaux ci-dessus (écriture).
7. **Multi-threader serializejson** : réalisé là où c'est parallélisable sans
   casser le GIL ni le déterminisme — compression et décompression par
   morceaux (point 4). Le reste (encodage JSON lui-même) est séquentiel par
   nature de l'arbre d'objets ; des pistes existent (pré-compression des gros
   bytes en tâche de fond pendant l'encodage du reste, ta note « stratégie
   4 ») mais exigent l'architecture en file de ta note Binaire.

**Ta clarification « peut-être faut-il passer intégralement la partie Python
dans le C++ »** : c'est la trajectoire déjà engagée — `class_plan`/
`decode_class_plan` migrent le cas général objet, les charges binaires et le
formatage sont descendus ; ce qui reste en Python est la LOGIQUE rare
(reduce personnalisés, plugins, propriétés/setters, mode update). La suite
naturelle : élargir les plans de classe (slots, `__reduce__` simples) puis
descendre `instance()`/`setstate()`. À ce stade le Python ne serait plus que
la configuration et les cas exotiques.

## 7 quinquies. Dernière ligne droite (5 h – 8 h) : le fork blosc2

- **Base64 parallèle et déterministe à l'écriture** (`c5aec5a`) : au-delà de
  3 Mo, l'encodage vers le buffer de sortie est découpé en segments FIXES
  alignés sur des multiples de 3 octets, chaque segment encodé vers son offset
  exact — octets identiques au séquentiel (parité vérifiée), GIL relâché.
  96 Mo compressés+encodés : 179 → 119 ms.
- **LE FORK blosc2, comme demandé à 4 h 55** (`9ede457`) : cause du
  non-déterminisme localisée dans `c-blosc2/blosc/blosc2.c` — les threads
  compressent en parallèle mais COLLENT les blocs dans l'ordre de terminaison
  (l'index `bstarts` rend le désordre décodable, pas les octets stables).
  Patch d'une quarantaine de lignes (« commit des blocs dans l'ordre » par
  condition) : compression toujours parallèle, écriture ordonnée — **sortie
  strictement identique au mono-thread, run-to-run stable, format standard
  relu par la libblosc2 officielle, 22 → 8 ms sur 80 Mo à 8 threads
  internes** *[tout testé]*. La bibliothèque patchée est EMBARQUÉE dans le
  dépôt (`rapidjson/libblosc2_serializejson.so`, patch à côté, clone hors
  dépôt à pousser comme fork GitHub), chargée en priorité ; les greffons
  préfèrent alors le multi-thread interne (trame unique standard) au format
  par morceaux, conservé en repli pour la roue officielle.
- **Conséquence majeure : l'arbitrage « blosc2 impose de sortir 3.10 » est
  DISSOUS** — le décodage des trames blosc2 passe par notre C (dlsym), donc
  Python 3.10, sans roue python-blosc2, encode ET décode blosc2 : les cinq
  versions produisent à nouveau des octets identiques, défauts compris
  *[testé]*.
- **Écriture directe des fichiers par descripteur** : tranchée par la mesure —
  une écriture Python par tranche de 64 Ko, gain de l'ordre de la milliseconde
  aux 100 Mo, contre un vrai risque de corruption avec les fichiers
  bufferisés ; design consigné, non réalisé.

### Bilan final face à pickle (min de 5, 3.14, fin de nuit)

| Cas | dumps | loads |
|---|---|---|
| 20 000 objets à 3 attributs | ×4,6 (était ×9,2) | ×4,4 (était ×8,3) |
| conteneurs purs | ×6,8 | ×6,1 |
| numpy 8 Mo compressible | **×0,5 — deux fois plus rapide que pickle** | ×2,0 (était ×3,2) |
| 50 000 chaînes | ×4,8 | ×4,7 (était ×10,2) |
| 96 Mo peu compressibles (fork, 8 threads) | 120 ms — sortie plus PETITE que pickle (82 vs 96 Mo) | 201 ms |

## 7 sexies. Sprint final (5 h – 7 h) : le quadratique et les nombres

- **BUG MAJEUR ancien débusqué et corrigé** (`afcbec9`) : `dumps_internal`
  faisait un `Flush()` — qui RÉTRÉCIT le buffer de sortie — à CHAQUE valeur,
  et chaque valeur suivante le ré-agrandissait (realloc + copie entière) :
  encodage QUADRATIQUE sur les longues listes de scalaires. **Un million
  d'entiers : 3 033 → 72 ms.** Le vice bridait tous les gros encodages depuis
  l'origine du fork ; le Flush est désormais unique, en sortie de racine.
- **Entiers** (`afcbec9`, `7855315`) : écriture directe des int exacts 64 bits
  (chiffres identiques à `repr()`, qui ne reste que pour sous-classes et
  entiers plus larges) ; boucles serrées sans aiguillage par élément pour les
  listes homogènes de scalaires ; au décodage, parse C direct jusqu'à 18
  chiffres au lieu de la machinerie des grands entiers (225 → 180 ms le
  million, limites et grands entiers testés).
- **Flottants** (`7855315`) : écriture par le moteur INTERNE de `repr()`
  (`PyOS_double_to_string 'r'`) sans chaîne Python — et les lignes
  `ArrayRows` adoptent la même graphie : la divergence documentée la veille
  (1e16) disparaît, tout est redevenu strictement `repr()` (cas pièges
  vérifiés : `-0.0`, `5e-324`, `1e308`...).
- **Essai écarté, mesures à l'appui** (`93b0058`) : parser SANS copier
  l'entrée (StringStream au lieu d'insitu-sur-copie) — régression partout
  (295 ms le million d'entiers, chaînes aussi) : hors insitu les nombres se
  recopient caractère par caractère. Le choix historique du fork était bon ;
  consigné en commentaire dans le code pour ne pas retenter.
- **Prochains gisemets identifiés** (non faits) : le chemin
  nombres-comme-chaînes du LECTEUR (encore ~130 ns/entier de mécanique
  au-dessus du parse pur — la stdlib fait 50 ns), et l'inlining des scalaires
  dans le chemin rapide des objets.

### Tableau final définitif (min de 5, 3.14, 7 h du matin)

| Cas | dumps | loads |
|---|---|---|
| 20 000 objets | ×3,4 (début de nuit : ×9,2) | ×4,4 (×8,3) |
| conteneurs purs | ×4,3 (×6,8) | ×5,1 (×6,6) |
| numpy 8 Mo | **×0,5 — 2× plus rapide que pickle** | ×2,0 (×3,2) |
| 50 000 chaînes | ×2,5 (×4,5) | ×4,8 (×10,2) |
| 1 000 000 d'entiers | ×10,5 (42× avant le correctif quadratique !) | ×8,8 |

## 7 septies. Matinée du 3 : la découverte du -O0, et le grand bond

### La trouvaille qui domine tout le reste

En profilant le décodage (gprofng, seul profileur disponible dans le bac à sable),
les fonctions les plus chaudes étaient Peek(), Take(), Consume() du lecteur —
des accesseurs d'un caractère qui auraient dû être inlinés. Cause : **distutils
perdait les CFLAGS du python et compilait le module SANS AUCUN -O, donc en -O0,
depuis toujours**. Tous les chiffres de la nuit (et d'avant) mesuraient un module
non optimisé. Correctif : '-O3 -fno-semantic-interposition' imposés dans
extra_compile_args de setup.py.

### Ce qui a aussi été fait ce matin

1. **Chaînes : raccourcis en ligne** dans les quatre boucles de conteneurs
   (liste, dict trié/non, attributs du chemin rapide) — les str exacts s'écrivent
   sans repasser par le dispatch.
2. **Drapeau maybe_non_ascii** (ton idée historique des notes RapidJson) : posé en
   O(1) par le writer à chaque chaîne non-ascii ; si rien de non-ascii n'a été
   écrit, la conversion finale bytes→str est une copie brute (PyUnicode_New+memcpy)
   au lieu du décodeur utf-8 — la sortie str coûte le prix de la sortie bytes.
3. **Parse natif des nombres au décodage** : nouveau drapeau de fork
   kParseBigIntsAsStringsFlag dans reader.h — ints et floats créés directement en
   C++ (pleine précision, bit-à-bit identique à float(), vérifié sur 200 000
   doubles aléatoires), repli chaîne uniquement pour les entiers au-delà de
   64 bits (exactitude conservée, vérifiée jusqu'à 10^100 et en négatif).
4. **Encodage indenté : WriteIndent** passait par le PutN générique de stream.h
   (une boucle de Put par caractère) → PutN membre du flux (un memset).
5. **Mémo des conteneurs** : unordered_map remplacée par une table à adressage
   ouvert dédiée pointeur→long (PtrMemo).
6. **Pré-réservations inter-appels** : l'encodeur retient les tailles atteintes
   (noeuds de chemin, mémo) au dump précédent et pré-réserve d'autant.

### Tableau après le matin (min de 15, 3.14, OpenBLAS à 1 thread)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×1,28** (hier soir ×9,2) | ×1,57 (×8,3) |
| conteneurs mixtes | ×2,15 | ×2,11 |
| 50 000 chaînes | **×0,44 — 2,3× plus rapide que pickle** | ×1,56 |
| dict 100 000 clés | **×0,93 — plus rapide que pickle** | ×1,52 |
| 1 000 000 d'entiers | ×5,3 | ×2,29 |
| 100 000 flottants | ×13,5 | ×2,25 |
| numpy 8 Mo | ~×1 à ×2 selon l'état mémoire (les deux <1 ms) | ×2,6 |

Le décodage bat désormais le module json de la bibliothèque standard sur tous les
cas mesurés (chaînes, entiers, flottants, dicts).

### 7 h 50 – 8 h 15 : Grisu3 pour les flottants (sur ton feu vert)

Nouveau `dtoa_repr.h` : le DigitGen de rapidjson (Grisu2) complété par la
détection d'incertitude de double-conversion. Quand Grisu3 réussit (>99 % des
valeurs), la sortie est la représentation la plus courte correctement arrondie
— exactement `float.__repr__` — écrite sans malloc ; sinon repli sur
PyOS_double_to_string. Validation : **41 millions de doubles aléatoires** (motifs
de bits uniformes) et 48 600 voisins des frontières décimales 10^k comparés
octet à octet à repr(), zéro écart ; batterie 5 versions ; goldens intacts.

### Tableau final (3.14, min de 15, OpenBLAS 1 thread, 8 h 15)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×0,94 — plus rapide que pickle** (nuit d'avant : ×9,2) | ×1,58 |
| 50 000 chaînes | **×0,42 — 2,4× plus rapide** | ×1,47 |
| dict 100 000 clés | **×0,96 — plus rapide que pickle** | ×1,57 |
| conteneurs mixtes | ×1,87 | ×1,99 |
| 100 000 flottants | ×5,7 (était ×13,5 le matin, ×12+ la veille) | ×2,28 |
| 1 000 000 d'entiers | ×5,0 | ×2,33 |

### Matinée, suite (9 h 45 – 11 h) : lecture puis conteneurs, sur ton « les deux »

Côté lecture (profil gprofng) :
- **GC en pause pendant le parse** : le GC générationnel se déclenchait au fil
  des millions d'allocations alors que l'arbre construit est acyclique et
  entièrement accessible — les collections ne libéraient RIEN (~13 % du temps).
  Pause RAII, rétablie même sur erreur.
- **Internement des clés plafonné** à 4096 clés distinctes : rentable quand les
  mêmes clés reviennent (objets, listes d'enregistrements), pur surcoût quand
  elles sont toutes différentes (gros dicts).
- **Création des str par copie brute quand ascii** (scan par mots de 8 octets),
  longueurs 0-1 laissées au chemin standard qui renvoie les singletons du
  cache CPython (la copie brute les manquait — régression attrapée et corrigée
  avant commit).

Côté conteneurs en écriture :
- **Une seule sonde de hachage par conteneur** (find_or_reserve au lieu de
  find puis emplace, ~15 % au profil).
- **Matérialisation incrémentale des chemins** : invariant « préfixe rempli /
  suffixe -1 » du tableau registered, materialize repart du premier niveau
  non enregistré — O(1) amorti par conteneur.

### Tableau définitif (3.14, min de 25, 11 h)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×0,97** | ×1,48 |
| 50 000 chaînes | **×0,50** | ×1,53 |
| dict 100 000 clés | **×0,92** | **×1,17** |
| conteneurs mixtes | ×1,86 | ×1,86 |
| 100 000 flottants | ×5,5 | ×2,26 |
| 1 000 000 d'entiers | ×5,3 | ×2,34 |

### Fin de matinée (10 h 15 – 12 h) : la salve « out-of-box »

1. **PGO** (compilation guidée par profil) : setup.py accepte
   SERIALIZEJSON_PGO=generate/use, build_pgo.sh fait les deux passes avec la
   batterie + pgo_workload.py comme charge. Gains majeurs partout (jusqu'à
   -35 % : objets dumps ×0,97 → ×0,65, chaînes ×0,50 → ×0,23).
2. **Plans de forme** : un dict dont la séquence de pointeurs de clés est
   identique au précédent à la même profondeur écrit ses clés en RawValue
   pré-échappé — l'équivalent du class_plan pour les enregistrements. Cache de
   4 plans indexé par profondeur, références fortes sur les clés.
3. **Conversion multithreadée des listes de nombres** : au-delà de 32 768
   éléments, extraction sous GIL en tableau C puis conversion par tranches
   d'index fixes sur 8 threads max (GIL relâché), recollage dans l'ordre —
   octets prouvés identiques au séquentiel (référence recousue, nan/inf/-0.0/
   5e-324 compris). Les échecs Grisu3 sont rendus au recollage sous GIL.
4. **Découverte en passant** : les listes numériques RACINES prenaient un
   raccourci Python historique (_onlyOneDimSameTypeNumbers + rapidjson.dumps)
   qui scannait toute la liste en Python et contournait boucles serrées et
   parallélisme. Retiré : mêmes octets par le chemin C++, et les listes
   racines retrouvent la sémantique $ref des listes imbriquées pour un même
   objet répété (seul écart de format, relevé sur [numpy.bool_(True)]*10).

Écarté sur mesure (« j'ai essayé/mesuré, non, et voici pourquoi ») :
- **Scanner par blocs des tableaux de nombres au décodage** : sous PGO le
  lecteur bat déjà json-std ×1,5–2 ; l'écart restant vs pickle est l'allocation
  des PyLong (~21 ns/élément) que pickle paie aussi ; le scan ne pèse plus que
  ~6 ns/élément. ~15 % au mieux, dans la fonction la plus délicate du lecteur.
- **Fusion blosc2→base64 par blocs L2** (ta question cache) : 64 Mo
  compressibles → ×0,37 de pickle, déjà gagnant ; 64 Mo incompressibles →
  ×2,97, dominés par zstd + l'inflation base64 (72 Mo écrits contre un memcpy
  de 64). La fusion ne toucherait que la passe b64 (~10-15 % du cas
  incompressible) et exige un recollage de phase base64 à cheval sur des blocs
  de tailles imprévisibles.
- **Dicts pré-dimensionnés au décodage** : dict 100k déjà à ×1,09, dictresize
  ~0,8 ms ; différer la construction casserait l'interception base64 qui
  consulte le dict parent en cours de parse.

### TABLEAU FINAL (3.14, PGO, min de 25, 12 h)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×0,63** | ×1,20 |
| 50 000 chaînes | **×0,22** | ×1,28 |
| dict 100 000 clés | **×0,57** | ×1,09 |
| conteneurs mixtes | **×1,26** | ×1,62 |
| 1 000 000 d'entiers | **×1,18** | ×1,52 |
| 100 000 flottants | **×1,05** | ×1,68 |
| numpy 64 Mo (rampe) | **×0,34** | **×0,97** |

Au départ de la nuit : objets ×9,2/×8,3, entiers ×10,5 (×42 avant le correctif
quadratique)/×8,8, chaînes ×4,5/×10,2. À l'arrivée : l'écriture bat pickle sur
objets, chaînes, dicts, numpy, flottants — et s'en approche à 20 % près
partout ailleurs ; la lecture est entre ×1,1 et ×1,7 et bat le module json
standard sur tous les cas mesurés.

### Copies et redimensionnements (question FIFO, début d'après-midi)

Mesure qui invalide deux intuitions : pré-allouer le tampon de sortie à
128 Mo est PLUS LENT que les doublements actuels (57,3 vs 52,2 ms sur 64 Mo ;
12,3 vs 8,5 ms sur 1M d'ints). Sur Linux, le realloc des gros blocs est un
mremap (remappage de pages, zéro copie) et la chaîne de doublements réutilise
ses pages déjà touchées, alors qu'une grosse allocation fraîche re-paie tous
les défauts de page. Un FIFO de chunks (l'idée posée) ajouterait une copie
pleine de recollage puisque le bytes retourné doit être contigu — c'est déjà
le modèle du flux fichier (PyWriteStreamWrapper), où le recollage n'existe pas.
Ce qui marchait dans l'autre sens a été fait : les brouillons du multithread
numérique (8 Mo re-mmappés à chaque dump) sont désormais possédés par
l'Encoder et réutilisés (SjMtScratch, tp_dealloc ajouté).

Pistes restantes non réalisées : re-mesurer le décodage sans copie d'entrée
sous PGO (l'essai perdant datait du -O0) et sa variante memchr-SIMD « pas
d'échappement -> zéro copie » ; décodage différé-parallèle des blobs
b64/blosc2 (gros gain attendu sur les fichiers à nombreux tableaux) ; écriture
fichier par fwrite direct ; free-threading 3.13t/3.14t pour les sous-arbres.

### Après-midi : blobs, copies, et la charge PGO complétée

- **Décodage base64 parallèle** (ta remarque « 3 octets deviennent 4 » — le
  symétrique de l'encodage de la nuit) : segments à frontières de groupes de
  4 caractères, chaque thread écrit à 3/4 de son offset d'entrée. Vérifié
  identique au module base64 sur toutes les tailles limites.
- **MT interne blosc2 à la décompression** : blosc_decompress_chunks ne
  parallélisait qu'entre trames — une seule grosse trame ne profitait de
  rien ; le parallélisme passe au dctx interne quand trames < coeurs.
- **Entrée bytes directe** : bytes/bytearray étaient décodés-recodés via un
  unicode intermédiaire (DEUX copies pleines, +25 ms sur 72 Mo) → parse
  direct du tampon.
- **Essai sans copie d'entrée re-mesuré en -O3** : toujours perdant (objets
  +19 %) — le dés-échappement des chaînes vers la pile coûte plus que
  l'unique memcpy. Verdict daté en commentaire dans le code.
- **FIFO / pré-allocation du tampon de sortie** (ta question) : mesuré
  contre-productif — le realloc Linux des gros blocs est un mremap sans
  copie qui garde ses pages, une grosse allocation fraîche re-paie tous les
  défauts de page (57 vs 52 ms), et un FIFO ajouterait la copie de recollage.
  En revanche les brouillons du MT numérique (8 Mo re-mmappés par dump) sont
  maintenant possédés par l'Encoder et réutilisés.
- **Charge PGO complétée** : la sortie flux n'était pas profilée et sortait
  en code froid — 10,4 → 7,8 ms sur les conteneurs mixtes juste en
  l'ajoutant à pgo_workload.py (l'entrée bytes ajoutée de même).

### TABLEAU DE FIN DE SALVE (3.14, PGO, 13 h)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×0,64** | ×1,19 |
| conteneurs mixtes | **×0,98** | ×1,64 |
| 50 000 chaînes | **×0,22** | ×1,31 |
| dict 100 000 clés | **×0,54** | ×1,07 |
| 1 000 000 d'entiers | ×1,19 | ×1,68 |
| 100 000 flottants | **×0,93** | ×1,62 |
| numpy 64 Mo compressible | **×0,24** | **×0,36** |
| numpy 64 Mo incompressible | ×3,3 (structurel : b64+zstd vs memcpy) | ×2,25 (90 → 48 ms) |

L'écriture est désormais au niveau de pickle ou devant sur TOUTES les familles
sauf les entiers scalaires (×1,19) et le binaire incompressible (coût
structurel du texte). La lecture est entre ×1,1 et ×1,7, et 2 à 3× devant le
module json standard partout.

### Salve « au plus près du CPU » (12 h – 13 h, sur ta question caches L1/L2/L3)

- **Base64 vectorisé SSE (pshufb, algorithme Mula/aklomp)** dans les deux
  sens : 12 octets → 16 caractères et 16 caractères → 12 octets par
  itération, au lieu d'une table par octet. Queue scalaire par segment (aucun
  débordement d'écriture entre threads, aucune sur-lecture d'entrée) ; au
  décodage le scalaire reste l'arbitre de validité en cas de rejet SIMD.
  Validé contre le module base64 : 344 payloads en encode, toutes les
  tailles limites et les 256 octets à chaque position en décode, rejets de
  caractères invalides à chaque position d'un bloc.
- **Le vrai déblocage trouvé en chemin : bytes_compression_threads valait 1
  par défaut** — les symboles documentés ('cpus', 'determinist') n'étaient
  résolus nulle part. Nouveau défaut 'determinist' : multithread UNIQUEMENT
  par la voie à octets stables (le MT interne du fork livré, vérifié
  identique à 1 thread) ; sans fork 1 thread, blosc v1 toujours 1.

Résultat blobs 64 Mo : incompressibles dumps 52 → 24,8 ms (×1,45 de pickle,
était ×3), loads 90 → 48 ms ; compressibles dumps 6,9 → 2,9 ms (×0,18 —
5,5× plus rapide que pickle), loads 18 → 7 ms (×0,38).

### Contre-vérification des rejets (12 h 30, sur ta remarque « disponibilité CPU »)

Méthode durcie : A/B ALTERNÉ dans le même build (bascule par variable
d'environnement), 4 manches, charge consignée à chaque passe — plus un A/B
« placebo » accidentel qui a chiffré le bruit de mesure (~±6 %).

- **Décodage sans copie d'entrée** : rejet CONFIRMÉ à charge égale — la copie
  gagne sur les objets à chaque manche (+8 % pour le sans-copie), égalité sur
  les nombres.
- **Pré-allocation du tampon de sortie** : verdict RENVERSÉ — ma mesure du
  matin comparait un build -O3 frais à la référence PGO (erreur de méthode,
  ta méfiance était fondée). L'A/B propre donne ~10 % de gain. Implémenté en
  version adaptative : capacité initiale = taille du DERNIER dump de
  l'Encoder (un petit dump après un gros retombe aussitôt au niveau d'un
  encodeur frais, mesuré). **1M d'entiers : dumps 8,5 → 6,2-6,8 ms — ×0,93,
  les entiers passent sous pickle, dernière famille scalaire.**

### TABLEAU GÉNÉRAL (3.14, PGO, 13 h)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×0,59** | ×1,19 |
| 50 000 chaînes | **×0,22** | ×1,40 |
| dict 100 000 clés | **×0,50** | **×1,01** |
| 100 000 flottants | **×0,74** | ×1,61 |
| 1 000 000 d'entiers | **×0,93** | ×1,64 |
| conteneurs mixtes | ×1,30 | ×1,55 |
| numpy 64 Mo compressible | **×0,17** | **×0,34** |
| numpy 64 Mo incompressible | ×1,29 | ×2,26 |

### Les optimisations risquées (13 h – 14 h)

1. **Les dicts ordinaires ne repassent plus par end_object Python** (~11 % du
   décodage des conteneurs au profil) : le Decoder certifie par
   _fast_plain_end_object (dotdict et recognized_classes inactifs, jamais en
   update), le C++ marque les dicts où passe une clé __class__ ou $ref et
   rend les autres directement. Conteneurs mixtes : loads ×1,55 → ×1,35.
2. **Chirurgie du lecteur (chiffres paresseux)** : la partie entière des
   nombres n'est plus empilée chiffre à chiffre pendant le scan ; rempilage
   d'un bloc seulement si '.', 'e' ou grand entier. Validé par 2M de doubles
   bit-à-bit, les formes textuelles pièges et les grands entiers ; gain ~5 %
   (33,3 ms le million d'entiers), conservé car borné et prouvé.
3. **No-go ARCHITECTURAL consigné — construction différée des dicts** : la
   résolution des $ref en cours de parse navigue dans self.root, donc dans
   les dicts partiellement remplis ; les différer casserait la résolution.
   Ce n'est pas une question de mesure.
4. **No-go consigné — décodage différé-parallèle multi-blobs** : les
   constructeurs peuvent copier leur charge à l'instanciation (array.array
   le fait), qui arriverait avant le remplissage différé.

### Ce qui borne encore, et pourquoi

- **Flottants et entiers scalaires en dumps** : pickle copie 8 octets binaires
  (~9 ns), nous générons des chiffres décimaux exacts (repr le plus court,
  identique à float.__repr__). PyOS_double_to_string coûte ~110 ns ; l'engin
  interne _Py_dg_dtoa n'est pas exporté par libpython, et les dtoa rapides
  (Grisu2 de rapidjson) ne garantissent PAS le repr le plus court, donc
  casseraient l'identité octet à octet. FAIT à 8 h : Grisu3 avec repli (voir
  ci-dessus), ×2,3 de gain. Le reste est le coût irréductible de générer des
  chiffres décimaux exacts. En texte JSON, faire mieux que le pickle binaire
  sur des nombres scalaires restera hors de portée ; pour les tableaux de
  nombres, le chemin binaire (numpy/blosc2/base64) est déjà au niveau de pickle.
- **PrettyPrefix** (~18 % de l'encodage indenté) : logique de niveau par jeton,
  partiellement incompressible sans réécrire la tenue de pile du PrettyWriter.
- **path_tracker_materialize** (~10 % sur les graphes de conteneurs) : piste
  identifiée — remplacer la matérialisation immédiate par des fils de parenté
  (conteneur parent + clé, reconstruits seulement quand un $ref est émis).

## 8. Dettes et points d'attention relevés en passant

- **typecode `'u'` d'`array`** : déprécié, retrait Python 3.16 — la batterie et
  le plugin array le rencontrent (warning vu sur 3.13/3.14). Prévoir `'w'` (3.13+)
  avec relecture des anciens fichiers.
- **venv 3.14** : `typeguard` y est trop vieux pour 3.14 (`ast.Str`), d'où
  `-p no:typeguard`. À mettre à jour dans le venv, rien à faire dans le dépôt.
- **`tests/serialized/*.txt` commités** : les goldens du dépôt viennent d'un run
  Windows AVEC Qt (tailles `array('l')` 4 octets, lignes Qt). Chaque run les réécrit.
  Je les ai laissés au dernier état vert ; à re-commiter un jour depuis une machine de
  référence, ou à sortir du suivi git.
- **`rapidjson/python_rapidjson.egg-info/`** : régénéré par les builds, modifié dans
  l'arbre AVANT mon intervention — laissé tel quel, non commité.
- **Sécurité `$ref`/`__class__`** : ta note TODO le dit déjà — un JSON forgé peut
  contenir `__class__` non voulu ; le hook dict C++ (étape B) est aussi l'endroit
  propre pour distinguer « dict utilisateur contenant la clé __class__ » d'un objet
  sérialisé (ton point « trou de sécurité » des notes RapidJson-Améliorations).

---

## 9. Idées écartées cette nuit parce qu'elles changeraient l'API (à discuter)

1. **`sort_keys` par défaut** : ta note TODO hésite (« j'ai remis sort_keys=False pour
   que les tests passent ») — tout changement du défaut change les fichiers produits.
   Statu quo conservé.
2. **Supprimer `generic__reduce_ex__` et le paramètre `split_dict_slots` de
   `getstate()`** : simplification réelle (redondants depuis 3.11) mais `getstate` est
   exporté — attendre l'abandon de 3.10.
3. **`numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit`** : ta note demande
   « faut vraiment convertir ? » — le retirer change le comportement 32 bits ;
   à trancher toi (y a-t-il encore un Python 32 bits vivant ?).
4. **Étiquette de compression `"b64_blosc2"`** : nouveau format de fichier → décision
   d'API/format à prendre avec la migration blosc2 (§7).
5. **`already_serialized`/`$ref` pour les dicts RACINE à clés non-str** : couvert
   naturellement par l'étape B, pas de rustine Python ajoutée en attendant.

---

*Méthode de validation utilisée toute la nuit : batterie `pytest` sur les cinq
interpréteurs (venvs SmartPython du 26/07), plus diff octet pour octet des sorties
sérialisées entre versions et entre avant/après chaque commit. Variante numpy activée
par copie temporaire du test (`use_numpy = True`) — non commitée.*
