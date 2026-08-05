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

### Le mur des blobs, tombé (13 h – 14 h 30, sur ton feu vert)

Le mur « constructeurs copieurs » était contournable en trois étages :
1. **Instanciation C++ de bytes/bytearray** : leur charge pré-décodée EST
   l'objet final (le plugin acceptait déjà les charges telles quelles) — plus
   aucun aller-retour Python par blob.
2. **Décodage base64 différé-parallèle** : validation SIMD immédiate (repli
   et erreurs inchangés), objet destination inséré dans l'arbre tout de
   suite, tampons remplis en parallèle au premier rappel Python ou en fin de
   parse. Insitu seulement.
3. **Parse EN PLACE, zéro copie d'entrée** : nouveau drapeau de fork qui
   supprime les terminateurs nuls (les longueurs suffisent partout chez
   nous) ; dès lors un gros document sans AUCUN antislash (un memchr) n'a
   plus besoin de la copie insitu — or elle dominait le décodage des gros
   blobs (61 % du temps en memcpy au profil).

**30 blobs de 1 Mo : loads 25 → 9,5 ms.** numpy 64 Mo incompressible :
46 → 40 ms. Reste pour le plein effet numpy : instancier les tableaux en C++
via l'API C de numpy (dépendance de compilation optionnelle, non faite).

### La marche numpy (14 h 30 – 15 h) — sans l'API C de numpy

L'analyse a montré que l'API C n'était pas nécessaire : numpyB64 sans
compression ne LIT jamais sa charge (frombuffer = vue), il suffisait de ne pas
vider les différés pour ces dicts-là. Et pour les charges compressées en trame
blosc2 UNIQUE, l'entête (24 octets décodés depuis les 32 premiers caractères
base64) donne la taille décompressée : le job devient « base64 puis
décompression », l'objet destination remplace la charge dans les arguments, et
l'étiquette neutralisée fait même retomber bytes/bytearray dans le chemin C++
sans aucun Python. Trames multiples, blosc v1, _diff, dtype bool : voie
normale inchangée. Une régression du blob unique (dctx à 1 thread : 57 ms) a
été attrapée et corrigée avant commit (MT interne quand jobs < coeurs).

**Résultats loads : 30 tableaux non compressés 10,1 ms (devant pickle 10,7) ;
64 Mo compressibles 6,5 ms (pickle 19,5 — 3× plus vite) ; 30 tableaux
compressés ~8-11 ms ; 64 Mo incompressible stable à 40 ms.**

## BILAN DE LA CAMPAGNE (2-3 août 2026, ~24 h, 61 commits)

### Tableau définitif (3.14, PGO, min de 15-20, 13 h 35)

| Cas | dumps vs pickle | loads vs pickle |
|---|---|---|
| 20 000 objets | **×0,54** | ×1,19 |
| 50 000 chaînes | **×0,22** | ×1,17 |
| dict 100 000 clés | **×0,57** | **×0,89** |
| conteneurs mixtes | ×1,27 | **×1,01** |
| 1 000 000 d'entiers | **×0,91** | ×1,26 |
| 100 000 flottants | **×0,93** | ×1,45 |
| numpy 64 Mo compressible | **×0,19** | **×0,28** |
| numpy 64 Mo incompressible | ×1,39 | ×1,87 |
| 30 tableaux compressés 1 Mo | ×4,8 | ×2,7 |
| 30 blobs bruts 1 Mo | ×8,8 (zstd+b64 vs memcpy) | ×3,2 |

Au départ de la nuit : objets ×9,2/×8,3, chaînes ×4,5/×10,2, entiers
×10,5/×8,8 (×42 avant le correctif quadratique), conteneurs ×6,8/×6,6.
À l'arrivée : l'écriture BAT pickle sur toutes les familles usuelles, la
lecture est entre ×0,3 et ×1,5 (devant pickle sur dicts, conteneurs mixtes et
numpy compressé, devant json standard partout). Seul le binaire brut
incompressible reste structurellement derrière (compression+base64 contre un
memcpy).

### Les cinq découvertes qui ont fait la campagne

1. **Le module se compilait en -O0 depuis toujours** (distutils perdait les
   CFLAGS) — trouvé au profil gprofng, corrigé par -O3 imposé, puis PGO.
2. **L'encodage était QUADRATIQUE** (Flush par valeur qui rétrécissait le
   tampon) : 1M d'entiers 3 s → 72 ms avant même le reste.
3. **Les listes numériques racines contournaient tout le C++** par un
   raccourci Python historique.
4. **La compression tournait sur 1 thread** : les symboles documentés
   n'étaient pas résolus — le fork déterministe permettait le MT sans changer
   un octet.
5. **La copie d'entrée au décodage dominait les gros blobs** (61 % en
   memcpy) : parse en place sans terminateurs quand aucun échappement.

### Les mécanismes construits

Fork rapidjson : mémo  en C (cycles, doublons, __dict__ physiquement
partagés au-delà de pickle), chemins rapides par classe dans les deux sens,
plans de forme des dicts, Grisu3 à graphie repr() garantie, base64 SSE
parallèle bilatéral, conversion multithreadée des listes de nombres (octets
identiques), blobs différés (validation SIMD immédiate, remplissage
parallèle, décompression comprise), parse en place. Fork libblosc2 : le MT
interne rendu déterministe. Discipline : batterie 27 tests × 5 versions et
goldens octet à octet à CHAQUE étape, A/B contre-vérifiés, chaque rejet
chiffré et consigné.

### Benchmarks officiels pyperformance (14 h – 16 h)

La suite officielle (bm_pickle : 60 dumps/loads de micro-objets par itération)
révélait le régime opposé à nos gros volumes : le coût fixe PAR APPEL et les
allers-retours Python par objet. Trois vagues, avec le banc répliqué versionné
dans tests/bench_pyperformance_pickle.py :

1. **Coût fixe amorti** : la poussée des paramètres globaux (2,2 µs sur les
   3,3 d'un dump minuscule !) n'est refaite que si un autre Encoder/Decoder a
   poussé ou si un attribut a changé (__setattr__ côté encodeur ; garde par
   comparaison côté décodeur — un __setattr__ y taxait les écritures internes,
   régression mesurée et corrigée). Dump minuscule : 3,3 → 1,5 µs.
2. **Dicts à clés entières en C++** (MICRO_DICT était ×12) : forme
   dict_non_str_keys écrite en C, clés i64toa, prouvée à l'octet sur 22 cas.
3. **Chemins rapides tuple/date/complex/range/slice**, encode et décode, avec
   les drapeaux single_line_init/new transmis au C++. Un bogue de lecture
   d'un tampon encore différé (dates) attrapé par les tests avant commit.

Résultats officiels 3.14 (PGO) : pickle ×3,5 → ×2,20, unpickle ×2,6 → ×2,16,
pickle_list ×2,3 → ×1,38, unpickle_list ×1,8 → ×1,75, pickle_dict ×12,3 →
×2,10. Écarté sur mesure : le GC en pause à l'ENCODAGE (≤2 %, l'encodage
n'alloue presque plus d'objets Python) ; la branche set/frozenset à l'encodage
— et ce chantier a mis au jour un INDÉTERMINISME PRÉ-EXISTANT : l'ordre
d'itération d'un set à collision de hachage (ex. {(1,2), 3}) varie entre
processus même à PYTHONHASHSEED fixe, donc les sets ne sont pas garantis
octet-stables aujourd'hui — à trancher un jour (tri canonique ?). Symptôme
reconnaissable dans les diffs de goldens : une divergence INTERMITTENTE dont
toutes les lignes sont des set/frozenset (vu le 3/08 avec {1, NaN} : le hash
de NaN dépend de l'adresse mémoire, l'ordre change d'un processus à l'autre).

### La question « tout en C++ ? » et le découpage retenu (15 h – 16 h)

Réponse chiffrée : une bascule totale ne gagnerait presque rien sur les gros
volumes (déjà dominés par le C++) et ~×1,5 sur les micro-objets, avec un
plancher structurel (le texte écrit "birthday" en toutes lettres là où pickle
émet des jetons binaires mémoïsés). Le bon découpage : des RECETTES PAR CLASSE
déclarées en Python, exécutées en C. Première tranche livrée :
datetime.datetime et datetime.time (encode + décode), avec deux dettes
pré-existantes mises au jour — les datetime PERDENT fold et tzinfo à la
sérialisation, et datetime.timezone n'est pas dans les classes autorisées par
défaut — et une leçon de méthode : les goldens ont attrapé au premier jet que
strict_pickle garde la forme octets, le drapeau est désormais transmis au C++.

Benchmarks officiels après cette tranche (3.14, PGO) : pickle ×2,17,
unpickle ×1,76, pickle_list ×1,33, unpickle_list ×1,73, pickle_dict ×2,30.

CHANTIER SUIVANT SPÉCIFIÉ : (1) le __call__ des
Encoder/Decoder porté en C (le dernier ~µs par appel : garde amortie, reset,
curly-check, queue des doublons rare via helper Python) — FAIT le 3 août,
voir ci-dessous ; (2) la
généralisation des recettes — class_plan/decode_class_plan étendus pour que
le Python déclare une fois par classe (constructeur, disposition des
arguments, politique setters/properties) ce que le C exécute, couvrant les
classes utilisateur et l'habillage numpy — PREMIÈRE MOITIÉ FAITE le 3 août
au soir (gating par classe des getters/properties, classes à __slots__),
voir ci-dessous.

### Recettes par classe, première moitié (3 août, soir)

Deux extensions du class_plan, chacune vérifiée par A/B contrôlé (sorties de
HEAD régénérées par stash, aucune divergence d'octets sur toutes les
combinaisons) :

1. **Gating par classe des getters/properties.** Avant, `properties=True` ou
   `getters=True` sur l'encodeur coupait le chemin C pour TOUTES les classes.
   Le class_plan refait maintenant exactement les résolutions de tools.reduce
   (registres, dict par classe, introspection) et ne rend None que si CETTE
   classe a des getters/properties effectifs. 1 000 objets ordinaires avec
   `properties=True` : 2 713 → 429 µs (×6,3).

2. **Classes à __slots__ purs** (dictoffset == 0, donc sans __dict__ à
   fusionner ; sinon voie Python). La recette d'encodage gagne un 3e élément :
   les noms de slots de `copyreg._slotnames` (héritage et name mangling
   compris), triés une fois par classe ; le C lit chaque slot par getattr, un
   slot jamais assigné est simplement absent (même forme que le __getstate__
   par défaut). Au décodage, le plan `(classe, True)` restaure par setattr
   dans l'ordre du JSON (celui du setstate Python). Mémo/$ref et cycles
   couverts. 1 000 objets à slots : dump 2 633 → 528 µs (pickle : 849 —
   BATTU), load 1 853 → 599 µs (pickle : 315).

Reste de ce chantier : les recettes déclaratives complètes (constructeur et
disposition des arguments __init__/__new__ décrits par le Python, exécutés
par le C — couvrirait __getinitargs__, les setters, et l'habillage numpy).

### Nuit du 3 au 4 août : allocation et recette constructeur

1. **Allocation de sortie** (règle décidée en planification du soir) :
   préallocation = 2 × haute-eau décroissante (max(taille, niveau/2)),
   croissance ×4 en dépassement, grosse réservation sautant directement à la
   puissance de deux couvrante. A/B ENTRELACÉ (rondes alternées ancien/
   nouveau, minimums — la charge machine à 8 rendait les mesures absolues
   inutilisables, premier jet des chiffres jeté pour cette raison) : aucun
   écart significatif dans les deux sens sur Linux — la glibc agrandit par
   mremap sans recopie, la croissance était déjà presque gratuite. La règle
   vaut par sa marge sous Windows (mémoire réservée pour de vrai) et par sa
   robustesse ; à re-mesurer machine calme si besoin.

2. **Recette constructeur au décodage** : {"__class__": X, "__init__":
   [args], attrs...} instancié en C — cls(*args) comme instance(), fusion
   des attributs restants dans inst.__dict__ (jamais de remplacement : le
   __init__ a pu le remplir), setattr pour les slots, repli Python si
   __init__ n'est pas une liste exacte. Utilisateurs réels de cette forme :
   les classes Qt (QPoint, QWidget...) et les plugins — non testables ici
   (pas de Qt dans les venvs), validés par classes-miroir forgées.
   1 000 objets à __init__ : 963 → 432 µs (×2,2). Le vrai __init__ est bien
   appelé (side effects préservés), vérifié par A/B de traces contre HEAD.

Leçon de mesure consignée : sous charge (load 8, autres instances), seules
les mesures ENTRELACÉES minimum-de-rondes sont interprétables ; un premier
verdict « tout s'est dégradé » venait entièrement de la charge.

3. **Recette __serializejson__ à l'encodage** (suite de la même nuit) :
   pour les classes à méthode __serializejson__ (Qt, classes utilisateur),
   la méthode est appelée par objet — seul Python restant — et l'emballage
   complet s'écrit en C : mémo $ref, règles exactes de déballage des
   arguments, SingleLine (single_line_init/new — c'était la divergence
   attrapée par l'A/B indenté au premier jet), __items__, état à plat,
   rigueur du __dict__ partagé, dumped_classes. Formes inattendues et
   registre plugins serializejson_ (array, dtype, function... — il PRIME
   sur la méthode) : voie Python. 1 000 objets : 1 236 → 264 µs (×4,7),
   baseline mesurée sur le MÊME build en neutralisant la recette par une
   sous-classe de class_plan (l'ancien .so était incompatible avec le
   nouveau class_plan : premier essai de mesure faux, jeté).

   Étendu dans la foulée au REGISTRE plugins : array.array en recette (les
   plugins retournent la CLASSE en tuple[0], le nom émis est précalculé par
   class_plan) — 3 305 → 2 184 µs le millier (×1,5), les 13 formes
   array.array des goldens passent par la recette. Les autres entrées du
   registre restent volontairement en voie Python : datetime.datetime a sa
   branche C dédiée, ndarray et les scalaires numpy sont traités par
   default() AVANT _dict_from_instance (la recette les court-circuiterait),
   et les instances numpy 2 de dtype ont pour type exact une sous-classe
   (dtype[int32]) qui ne matche pas le registre de toute façon.

4. **Recette __getstate__** (même nuit, sur directive) : pour une classe au
   __getstate__ UTILISATEUR et au reduce hérité d'object, la méthode est
   appelée par objet et l'enveloppe s'écrit en C — état à plat dans l'ordre
   du dict (ni getters/properties ni tri/filtre : la voie Python les
   réserve aux classes SANS __getstate__), rigueur du __dict__ partagé,
   __state__ pour les états non-dict. Délégué à la voie Python : état
   2-tuple, clés non-str sans __setstate__. 1 000 objets : 1 802 → 326 µs
   (×5,5) — PICKLE BATTU (483 µs). Les familles *getstate* des goldens
   passent par la recette.

5. **Recette __reduce__ réimplémenté** (fin de nuit) : un adaptateur Python
   minuscule appelle obj.__reduce_ex__(protocole) et reforme (classe, args,
   état) pour la branche recette C existante — zéro nouveau code C. Repli
   voie Python : callable ≠ classe, listitems/dictitems. Deux exclusions
   apprises DE LA BATTERIE (leçon : les recettes doivent reproduire l'ordre
   de priorité complet de tuple_from_instance) : serializejson_builtins
   (bytearray a un __reduce_ex__ mais son plugin prime) et
   remove_add_braces (Counter). 1 000 objets : 1 919 → 529 µs (×3,6 ;
   pickle 259 — devant ici, listes d'arguments texte).

   RESTE au chantier des recettes : __getnewargs__/__getnewargs_ex__
   (forme __new__), et côté décodage la généralisation aux __state__/
   __items__.

### Pistes consignées sur les conversions nombre ↔ texte (questions du soir)

- **Écriture des flottants** : remplacer Grisu3 par **Dragonbox** (Junekey
  Jeon, 2020) — même repr le plus court (unique mathématiquement, donc
  octets identiques après nos règles de format), 2 à 3 × plus rapide, sans
  repli. État de l'art adopté par {fmt}/MSVC.
- **Lecture des flottants** : **Eisel-Lemire** (fast_float, dans GCC 12 et
  Rust) — 4 à 10 × plus rapide que la voie classique, exact.
- **Entiers** : déjà proches du plancher (i64toa, tables 2 chiffres en L1 ;
  borné par le calcul, pas la mémoire). SIMD utile en LOTS : itoa vectorisé
  dans chaque tranche de la conversion multi-thread existante ; au parsing,
  validation/découpe SWAR-SIMD par paquets de 8-16 octets (simdjson,
  fast_float).
- Le multi-thread des conversions par lots est DÉJÀ en place (campagne du
  2-3/08) ; un nombre isolé (~40 ns) n'est pas parallélisable.

### Nombres, ce qui a été FAIT dans la nuit du 3 au 4 (directive « battre
### pickle partout, sans questions, le plus sûr d'abord »)

- **Eisel-Lemire au parse des flottants** : COMMITÉ. Produit 128 bits avec
  table générée exactement, correctement-arrondi-ou-renonce (~0,1 % de
  renoncements vers le chemin exact existant). Validation : 9 M de cas C
  contre strtod (dont VRAIS mi-chemins à 54 bits impairs — un premier
  générateur à 53 bits ne testait rien), 13,2 M de bout en bout contre
  float() au bit près. Gain net : 14,1 → 12,7 ms sur 200 k repr longs. Le
  DiyFp de rapidjson était déjà bon : l'essentiel de l'écart long/court
  vient du VOLUME de caractères, pas de la conversion.
- **Cache des clés par octets bruts au décodage** : COMMITÉ. −8 % sur les
  dicts aux clés répétées, −2,5 % sur le trio unpickle.

Écarté « le plus sûr d'abord », à faire proprement plus tard :

- **SWAR/SIMD sur les chiffres au parse** : FAIT dans la foulée (flux
  insitu borné SjBoundedInsituStream, 8 chiffres par multiplication SWAR,
  plafond 17 chiffres) — −18 % sur les entiers de 15-16 chiffres, neutre
  sur les petits. Piège consigné : le parse relit le début d'un nombre via
  le flux ORIGINAL non avancé (copyOptimization) — le trait doit être
  déclaré pour la sous-classe, sinon tous les nombres du chemin
  nombres-en-chaînes lisent du vide (attrapé par la batterie).
- **Dragonbox à l'écriture des flottants** : remplaçant exact de Grisu3
  (repr le plus court unique → octets identiques), ~×2-3 sur la conversion
  seule. Implémentation substantielle (intervalles de Schubfach, table
  128 bits) : à faire de jour, avec le même protocole de validation
  massive que Grisu3/Eisel-Lemire.
- **itoa vectorisé par lots** dans les tranches multi-thread existantes.

### Score pyperformance en fin de nuit (3.14, PGO, charge ~4-5)

pickle ×1,63 ; unpickle ×1,84 → **×1,70** ; pickle_list ×1,11 ;
unpickle_list ×1,79 ; pickle_dict ×2,24. Et hors benchmarks officiels,
pickle est BATTU sur : chaînes, gros numpy compressibles, objets ordinaires
en écriture, objets à __slots__ en écriture, objets à __getstate__ en
écriture.

### Tableau par type après SWAR (3.14, PGO, ~23 h, ratios sj/pickle)

| charge             | dump      | load  |
|--------------------|-----------|-------|
| floats (200 k)     | ×2,9      | ×2,8  |
| gros ints (200 k)  | **×0,44** | ×1,18 |
| chaînes (20 k)     | **×0,33** | ×2,1  |
| objets slots (5 k) | **×0,63** | ×1,47 |

(Le load des chaînes à ×2,1 : pickle rend des objets str mémoïsés ; nous
recréons chaque str depuis l'UTF-8 — voir piste ci-dessous.)

### Balayage par lots : FAIT dans la même nuit (23 h)

Les motifs « nombre, » des tableaux sont consommés par une boucle serrée
sur le tampon borné, sans repasser par ParseValue/ParseNumber : entiers
(SWAR 8 chiffres, plafond 17) PUIS flottants (mantisse.fraction/exposant,
conversion Eisel-Lemire directe). Au moindre doute la voie normale reprend
le jeton entier — erreurs JSON comprises ([01,2], [1,,2] toujours rejetés).
Gains A/B entrelacés : −26 % gros entiers, −19 % petits, −23 % flottants,
−18 % charge unpickle_list. Validation : 2 M de mélanges au bit et au TYPE
près, bords (-0.0, 5e-324, 1E3, 1e+5, 1., e vide).

### Tableau de position après la nuit complète (3.14, PGO, ~23 h 15)

Officiels : pickle ×1,62 · unpickle ×1,88 · pickle_list ×1,17 ·
unpickle_list **×1,39** (était ×1,86) · pickle_dict ×2,23.

| charge             | dump      | load      |
|--------------------|-----------|-----------|
| floats (200 k)     | ×2,4      | ×2,4 (était ×2,8) |
| gros ints (200 k)  | **×0,36** | **×0,84** |
| petits ints (200 k)| **×0,41** | **×0,97** |
| chaînes (20 k)     | **×0,33** | ×2,0      |
| objets slots (5 k) | **×0,61** | ×1,54     |

LES ENTIERS BATTENT PICKLE DANS LES DEUX SENS. Restent derrière : les
flottants (structurel : texte contre memcpy binaire — Dragonbox réduirait
le dump, le load restant est dominé par PyFloat_FromDouble + le scan), les
chaînes au load (création str depuis UTF-8 contre opcode+alloc), les
enveloppes des micro-dicts (verbosité du format).

### Chantiers restants, spécifiés (arrêt « le plus sûr » à 23 h 15)

- **Dragonbox à l'écriture des flottants** : ~×2-3 sur la conversion,
  protocole de validation massive identique à Grisu3/EL. Ne suffira PAS à
  battre le memcpy binaire de pickle sur les floats.
- **Cache adaptatif des VALEURS chaînes au décodage** : FAIT — et deux
  leçons au passage. (1) Par parse, il RÉGRESSAIT de +10 % sur les petits
  documents (amorçage payé, jamais récolté) : il est PERSISTANT sur le
  DecoderObject (32 Ko), comme le memo de pickle mais entre appels. (2) Le
  crédit adaptatif doit persister AUSSI (plancher 64/parse, purge de la
  table à l'épuisement), sinon chaque parse de données distinctes repayait
  l'amorçage (+25 %). Final : −40 % répétitives, NEUTRE distinctes.
  Sémantique : les chaînes identiques relues par le même Decoder sont le
  MÊME objet str (immutable, sans danger — pickle fait pareil via son memo).
- **Chaînes ASCII au décodage** : la remarque utilisateur du soir (détecter
  non-ASCII + échappement puis copier tel quel) est DÉJÀ en place aux deux
  étages : RAPIDJSON_SSE42 balaie les chaînes sans échappement par 16
  octets, et sj_unicode_from_utf8 fait la copie brute quand tout est ASCII
  (scan 8 octets). Le ×2 restant est le coût de l'objet str lui-même.
  Micro-redondance identifiée en y regardant de plus près (2e question du
  soir) : les octets sont balayés DEUX fois — une par le SSE du reader
  (guillemet/échappement/contrôles), une par le scan ASCII à la création.
  FUSION possible : faire accumuler le bit de poids fort par le balayage
  SSE du reader et transmettre « pur ASCII » au handler (drapeau sur le
  flux borné) → économise le second scan, estimé ~5 % du load des chaînes
  (2-3 ns sur ~45 ns : l'essentiel est l'allocation de l'objet str, que
  pickle paie aussi — son avance vient de l'opcode+longueur en tête contre
  notre recherche SSE du guillemet fermant). À faire avec le cache adaptatif
  des valeurs répétées, qui lui évite l'objet TOUT ENTIER.

### Cycle de vie du tampon de sortie : fuite str et OOM (3 août, soir)

Deux défauts trouvés en répondant aux questions sur l'allocation de sortie :

1. **FUITE : chaque dumps vers str fuyait tout son tampon.** PyBytesBuffer
   n'avait ni destructeur ni décrément ; seule la sortie bytes (objet donné à
   Python) ne fuyait pas. Mesuré : +205 Mo et +202 blocs en 200 dumps de
   1 Mo. Piège de mesure au passage : le premier test était passé au vert
   parce que `return_bytes=True` est le DÉFAUT de l'Encoder serializejson —
   les deux branches mesuraient le chemin bytes. Correctif : destructeur
   (Py_XDECREF), la sortie bytes TRANSFÈRE la référence (stealPyBytes), les
   chemins str et d'erreur libèrent au destructeur. Après : +2 blocs sur 200
   dumps, test de non-régression par getallocatedblocks.

2. **OOM : plantage au lieu de MemoryError.** Sur échec d'allocation,
   _PyBytes_Resize libère l'objet et met le pointeur à NULL ; le code
   déréférençait ce NULL (PyBytes_AS_STRING) et continuait d'écrire.
   Correctif : Resize lève std::bad_alloc (MemoryError déjà posée par
   l'allocateur CPython), rattrapé dans do_encode. Vérifié sous
   RLIMIT_AS 400 Mo : MemoryError propre, et l'encodeur reste réutilisable
   après trois OOM successifs (octets identiques ensuite).

### Le __call__ porté en C (3 août, tranche 1 du chantier)

Les Encoder/Decoder Python ne définissent plus de `__call__` : le tp_call C
de rapidjson exécute tout le protocole d'appel — poussée amortie des
paramètres globaux (garde par identité de pointeurs, jamais d'égalité par
valeur : un défaut à tort ne coûte qu'une repoussée), équivalents C de
_reset/_clean posés par PyObject_GenericSetAttr (contourne le __setattr__,
comme le voulaient déjà les attributs volatils), json_startswith_curly,
drapeaux _fast_start_object/_fast_plain_end_object, queue des doublons. Le
Python n'est rappelé que sur les chemins rares : `_update_serialize_parameters`
(défaut de garde encodeur), `_push_decode_parameters` (défaut de garde
décodeur), `_call_update` (mise à jour d'objet), `_resolve_duplicates`
($ref en avant). L'enregistrement se fait à l'import :
`rapidjson.register_serializejson(Encoder, Decoder, serialize_parameters)` ;
une instance de rapidjson.Encoder/Decoder « nue » garde le comportement brut,
et `rapidjson.Decoder._decode` expose le décodage brut (itérateur de fichier,
mise à jour).

Mesures (3.14, PGO) : dump minuscule 2 313 → 1 299 ns (pickle : 513),
load minuscule 1 433 → 1 220 ns (pickle : 314). Benchmarks officiels
pyperformance : pickle ×1,97 → ×1,64, unpickle ×1,84 → ×1,75,
pickle_list ×1,56 → ×1,09, unpickle_list ×1,79 → ×1,64,
pickle_dict ×2,21 → ×2,07.

Le portage a mis au jour et RÉPARÉ deux régressions de la nuit de migration,
jamais couvertes par un test : `Encoder.dumps()`/`dumpb()` ignoraient le
return_bytes par appel (dumps rendait des bytes), et `Encoder.dump(obj,
fichier)` levait TypeError (chunk_size passé à un __call__ qui ne l'acceptait
plus). Trois tests de non-régression ajoutés (tests/test_encoder_methods.py).
Vérification : A/B contrôlé même machine même interpréteur (sorties de HEAD
régénérées par stash) — aucun octet ne change ; batteries 30/30 vertes et
octets identiques sur les 5 versions ; chemins rares exercés un à un
(update via updatables_classes, dotdict, $ref en avant, flux str/bytes,
liste racine, append+itérateur, invalidation par __setattr__, alternance de
deux encodeurs et d'un décodeur).

Dettes pré-existantes relevées au passage (comportement identique sur HEAD,
vérifié avant de conclure) : `append()` de doublons partagés écrit des $ref
relatifs à chaque append, illisibles au chargement du fichier entier
(TypeError dans from_name) ; la mise à jour `decoder(json, obj)` ne touche
que les updatables_classes (un dict ou un objet ordinaire ne sont PAS mis à
jour — c'était déjà le cas) ; la docstring de Decoder.__call__ (exemples
d'usage) disparaît de help() puisque le __call__ est un slot C ; changer
`sort_keys` (et les autres membres C) après construction a toujours été
impossible (membre en lecture seule). Passe de simplification : __call__ ×2,
_clean et le protocole manuel d'append supprimés côté Python ; regardé et
laissé tel quel — le couple _reset/_update dans clear() (pas un chemin
chaud, comportement historique conservé).

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


---

## 10. Nuit du 3 au 4/08 (suite) — clôture des points 1 à 9 de la liste d'améliorations

Directive : « finis les points 1, 2, 3, 4, 6, 7, 8, 9 sans t'arrêter » (le 5,
mode update, reste exclu à ta demande). Chaque point est clos : soit fusionné,
soit essayé-mesuré-écarté avec les chiffres. Sept commits (f8da97e → cb9b40a).

### Point 1 — fusion des balayages de chaînes (f8da97e) : FAIT
Découverte en chemin : le scan SSE des chaînes de rapidjson ne s'appliquait
qu'à `InsituStringStream` EXACT — notre flux borné (classe dérivée) se liait
au template générique qui NE FAIT RIEN, et chaque caractère repassait par le
transcodage unitaire. Surcharges dédiées : tête SWAR de 16 octets (les clés et
petites valeurs se règlent sans la mécanique d'alignement), SSE aligné pour les
longues, et le même scan accumule le bit non-ascii. Verdict écrit en UNE fois
chez le handler (`sjHintOut` du flux, un seul store par chaîne — la v1
reset+salissage coûtait ~3 ns/chaîne de trop) ; le handler fabrique alors le
str par copie brute sans re-scan. A/B : ascii long −40 %, ascii court −15 %,
unicode −16 %, objets neutres ; échappements +10 % (mécanique SSE par segment,
assumé). Piège consigné : la position SWAR d'un « premier octet spécial » est
exacte (les faux positifs des emprunts n'apparaissent qu'au-dessus du premier
vrai), c'est ce qui autorise le ctz.

### Point 3 — lot étendu (3d85f18) : FAIT
Le lot des tableaux consomme aussi `true/false/null` (memcmp borné, « nan »
échoue au memcmp et garde sa voie) et les chaînes courtes propres (≤ 24 octets,
SWAR quote/antislash/contrôle/non-ascii, repli voie normale au moindre doute).
Plafond à 24 octets et pas 48 : au-delà, un pré-scan raté coûte un double
balayage (mesuré +12 % sur des chaînes de 52). Dispatch chiffres d'abord :
l'ordre inverse coûtait 4-8 % aux nombres purs. A/B : littéraux −50 %, chaînes
courtes −18/−20 %, mixte −20 %, nombres neutres. Les chaînes du lot passent par
le même `handler.String` que la voie normale : datetime/uuid/base64 identiques.

### Point 4 — pré-dimensionnement des listes (3d85f18 puis retiré ed2ddd5) :
ESSAYÉ, MESURÉ, ÉCARTÉ. Tranche de 64 None épissée en une fois, les valeurs
volaient leur case (SET_ITEM) au lieu d'append. Mesure : neutre sur les grands
lots (l'append de CPython est déjà amorti — l'économie incref/decref de la
valeur est reprise par l'incref/decref des None), et +45 % sur unpickle_list
(épissure de 64 cases pour des tableaux de 10, rendu de 54). Tous les gains
du lot venaient du saut de dispatch. Leçon : le banc « 100 k éléments plats »
ne voit pas le régime « 20 tableaux de 10 » — c'est l'officiel unpickle_list
qui a crié.

### Point 6 — écriture des flottants (cb9b40a) : FAIT, avec Ryu plutôt que
Dragonbox (même objectif, algorithme que je maîtrise à l'implémentation près,
tables 128 bits GÉNÉRÉES en arithmétique exacte — gen_ryu_table.py au
scratchpad, comme la table Eisel-Lemire). Ryu est TOTAL (jamais d'échec) :
Grisu3 ET toute la machinerie de repli PyOS (vecteur fallbacks des chunks,
recollage, trois sites directs) sont retirés — plus aucun scénario ne les
déclenchait. Validation bit-exacte contre float.__repr__ : 25 M+ de valeurs
(tous les exposants × motifs de mantisse, subnormaux, puissances de 10,
décimaux « humains », entiers × 10^n et voisins ULP). A/B : 1 M flottants
24,1 → 17,0 ms (−30 %, écart vs pickle ×2,7 → ×1,9), 20 k −45 %.
Note d'implémentation : variante `multipleOfPowerOf2(mv, q-1)` (la borne du
d2s.c de référence) — validée par la masse, aucun écart.

### Point 7 — itoa vectorisé (essayé, mesuré, ÉCARTÉ)
SSE2 8-chiffres (schéma mulhi de l'itoa-benchmark) posé dans
sj_render_int_chunk, validé octet pour octet sur 7 jeux (2 M exhaustifs,
bornes 10^k, extrêmes, aléatoires par plages). Mesure : < 2 % sur le mur —
la conversion est déjà parallélisée sur 8 threads, le goulot du dump des gros
tableaux d'entiers est l'EXTRACTION sous GIL (PyLong_AsLongLong par élément)
et le recollage. Code retiré. Piste consignée : lecture directe des petits
PyLong compacts (ob_digit, 3.12+) pour accélérer l'extraction — API privée,
décision à prendre.

### Point 8 — recettes restantes (16b065a) : FAIT
- `__getnewargs__`/`__getnewargs_ex__` (reduce hérité d'object) : l'adaptateur
  rend le 6-uplet de `tuple_from_instance` TEL QUEL — la décomposition (forme
  __newobj__, état trié/filtré, getters/properties) reste la voie Python,
  seule l'émission passe par la branche recette C (qui portait déjà __new__,
  __items__ et l'état à plat). Identité d'octets vérifiée sur 9 familles,
  doublons et $ref compris. Mesures : getnewargs+état ×1,5, namedtuples ×1,9.
- builtins à forme chaîne : `type` et `function` passent leur fonction du
  tableau builtins en recette (tuple[0] déjà str, la branche C l'émet tel
  quel). Modules NON inclus : leur encodage n'a JAMAIS fonctionné (voir bug 2).
- registre plugins : array.array reste la seule entrée en recette — les autres
  (datetime, ndarray, scalaires/dtype numpy) ont une branche C dédiée ou un
  traitement default() en amont qu'une recette court-circuiterait.

### Deux défauts PRÉEXISTANTS découverts par les tests du point 8
1. **`__getnewargs_ex__` à arguments positionnels plantait depuis toujours**
   (`for index, new_arg in new_largs` sans enumerate, tools.py) — CORRIGÉ
   (16b065a) : le chemin ne pouvait qu'échouer, aucune compatibilité d'octets
   à préserver.
2. **L'encodage d'un MODULE n'a jamais fonctionné** :
   `serializejson_builtins[types.ModuleType] = serializejson_function` (au
   lieu de serializejson_module, mort juste au-dessus) → AttributeError sur
   `__module__`. NON corrigé : le « bon » comportement (sérialiser tout
   l'espace de noms du module ?) est une décision d'API/format qui te revient.

### Points 2 et 9 — déjà faits la veille (cache persistant des valeurs
chaînes ; SWAR sur la fraction du lot flottant). Point 5 (mode update) exclu.

### Où on en est (PGO 3.14, tour final de la nuit)
Officiels : pickle ×1,63 · unpickle ×1,65 (était ×1,92 la veille au soir) ·
pickle_list ×1,27 · unpickle_list ×1,33 · pickle_dict ×2,17.
Par type (dump/load vs pickle) : gros entiers ×0,49/×0,74 ·
petits entiers ×0,76/×1,23 · chaînes distinctes ×0,24/×1,56 ·
chaînes répétitives ×1,49/×3,74 · flottants ×3,9/×2,8 (magnitudes -8..8,
graphies longues — le memcpy de pickle est le plancher structurel) ·
littéraux ×3,9/×3,0 (opcodes d'un octet côté pickle, structurel) ·
objets slots ×0,65/×1,16.

### Prochaines pistes (par rendement estimé)
1. unpickle/pickle_dict : l'enveloppe des micro-dicts (décision de format, §9).
2. Extraction des PyLong compacts sans appel (3.12+, API privée) — dump des
   gros tableaux d'entiers.
3. Étendre le fast-path valeur d'objet aux chaînes courtes/littéraux
   (aujourd'hui nombres seulement).
4. Décodage multi-thread par sous-arbres (free-threaded 3.13+).


---

## 11. Nuit du 3 au 4/08, seconde partie — PyLong compacts, contre-vérifications, valeur d'objet

### Extraction rapide des petits entiers : ESSAYÉ, MESURÉ, ÉCARTÉ
Lecture directe des PyLong compacts (PyUnstable_Long_IsCompact/CompactValue
en 3.12+, Py_SIZE ∈ {-1,0,1} + ob_digit[0] en 3.10/3.11) posée aux quatre
sites du dump (entier isolé ×2, extraction MT, boucle séquentielle).
Octets identiques (4 jeux d'empreintes dont bornes 2^30/2^62/2^63).
Mesure, 6 tours entrelacés : NEUTRE sur les petits (7,5 → 7,3 ms/M, dans le
bruit) et ~+2 % sur les gros (test compact raté puis appel). Cause : le
convertisseur de CPython a déjà son raccourci interne pour les valeurs
moyennes, et le mur réel est la MARCHE MÉMOIRE (un pointeur à déréférencer
par élément sur un tas de dizaines de Mo), pas l'appel. Retiré.

### Contre-vérifications des rejets (demande explicite), 10 tours chacun
- **Tranche de None (pré-dimensionnement)** : unpickle_list ×2,13-2,56 AVEC
  contre ×1,76-1,95 SANS — 10/10 sans recouvrement, rejet CONFIRMÉ largement
  au-dessus du bruit. Les 10 tours ont aussi montré un vrai gain de la
  tranche sur les grands lots plats de littéraux (~−15 %).
- **itoa SSE2** : −2 à −3 % sur les seuls gros tableaux (7/10 tours dans ce
  sens), neutre ailleurs — rejet confirmé (90 lignes de SIMD pour un gain
  au niveau du bruit).

### ⚠ LEÇON DE MÉTHODE : le bruit de DISPOSITION BINAIRE entre deux builds
vaut ~5-10 % sur les micro-bancs. Prouvé en comparant deux variantes de la
tranche hybride aux chemins logiquement identiques pour les booléens :
10 % d'écart systématique. Conséquences : (1) seuls sont probants les
écarts >> 10 %, les A/B du MÊME build (copie de .so), ou les RATIOS contre
pickle mesurés dans le même processus ; (2) une ligne micro qui bouge de
5 % entre deux builds ne prouve RIEN. C'est ce bruit qui rendait la
tranche hybride « gagnante » puis « perdante » selon le build.

### Tranche HYBRIDE (activation paresseuse au 65e élément) : essayée sur la
foi du gain −15 % ci-dessus, puis ABANDONNÉE : ses gains apparents
(littéraux −20 %, mixte −10 %) ne se sont pas reproduits d'un build à
l'autre (voir leçon), unpickle_list neutre, chaînes plates ~+7 % sur
certains builds. Aucun effet net ne franchit le plancher de
reproductibilité → la simplicité l'emporte, code retiré.

### Raccourci « valeur d'objet » étendu (746ec36) : FAIT
SjObjectSimpleValue : true/false/null et chaînes courtes propres émis sans
ParseValue en position de valeur d'objet, mêmes règles que le lot des
tableaux, même handler.String (datetime/uuid/hooks). unpickle ×1,90 →
×1,83, 8 tours sur 8 dans le même sens (ratio interne au processus, donc
insensible au bruit de disposition), reste neutre.

### Réflexion : ce qui peut encore accélérer (par rendement estimé)
1. **Enveloppe des micro-dicts** (pickle_dict ×2,1) : le chemin C des clés
   entières existe déjà ; le reste est la VERBOSITÉ du format
   ("__class__":"dict_non_str_keys" par dict) + un pousser/dépiler de
   chemin par clé (memo). Toute forme plus compacte = décision de FORMAT
   (à toi). Sans changer le format : plafonner le suivi de chemin quand
   memo_refs ne peut plus rencontrer de conteneur (~5-10 % estimé).
2. **Chargement des chaînes répétitives** (×3,7) : pickle mémoïse DANS son
   format (BINGET). Nos caches (clés, valeurs persistantes) compensent en
   partie ; le reste est structurel sans étiquette $strref (format).
3. **Décodage multi-thread par sous-arbres** : free-threaded 3.13+/3.14t —
   le gros levier restant côté load (les builds ft ne sont pas dans la
   batterie aujourd'hui).
4. **Écriture des flottants** : Ryu fait ; l'écart restant (×2-4 au dump)
   est le texte contre le memcpy de 8 octets — structurel. Un mode
   « float hex » ou binaire = format.
5. **Extraction MT des gros tableaux d'entiers** : le mur est la marche
   mémoire des PyObject (~12 ns/élément incompressibles en pointeurs
   épars). Seule une source contiguë (numpy, array) l'évite — déjà
   couverte par les chemins numpy.
6. **Fusion clé+valeur au parse d'objets** : scanner « "clé": valeur, » en
   un seul passage SWAR (aujourd'hui clé et valeur ont chacun leur
   mécanique). Gain estimé 3-5 % sur unpickle, complexité moyenne.
7. **PGO élargi** : le profil actuel vient de la batterie + pgo_workload ;
   y ajouter les benchs officiels pourrait déplacer 2-3 % (à essayer une
   fois, mesure par ratios).


---

## 12. Matin du 4/08 — deux décisions de format tranchées et appliquées

### Enveloppe des dicts à clés non-str : nom court (a401e39)
Décision utilisateur (critère : « le format le plus consistant avec les
conventions de serializejson, et lisible ») après examen des variantes
($dict compact, __items__ en paires — la plus pure mais moins lisible,
__dict__ imbriqué — propre mais sans gain) : la forme à plat
`{"__class__": "dict", "0": null, ...}` — même chapeau que tous les
objets, clés codées inchangées, 13 octets gagnés par dict. L'ancien nom
`dict_non_str_keys` reste lu POUR TOUJOURS.

### Collision des clés réservées : échappement (b9115c7)
Question utilisateur « comment résoudre élégamment la collision d'un dict
légitime portant une clé __class__ ». Mesure préalable : TROIS corruptions
préexistantes (dict {"__class__": ...} relu comme objet ; clé utilisateur
écrasant silencieusement l'étiquette dans un dict mixte ; {"$ref": ...}
relu comme référence). La piste positionnelle (« __class__ toujours
premier ») a été écartée : sensible à sort_keys et aux outils tiers qui
réordonnent, et elle n'aurait de toute façon pas couvert le cas premier —
l'échappement est nécessaire, donc suffisant partout. Solution retenue :
ces dicts passent par l'enveloppe avec la clé RÉSERVÉE échappée entre
apostrophes (`"'__class__'"`), c'est-à-dire le mécanisme d'échappement de
clés DÉJÀ dans le format — zéro changement côté lecture, et les anciennes
versions relisent ces fichiers correctement.

Deux pièges d'implémentation, tous deux attrapés par les tests avant
commit :
- l'enveloppe produite par default() contient `__class__` par
  construction : sans garde, la détection la renvoyait à default() en
  boucle infinie. Garde = le marqueur « résultat de default() »
  (attrsDict) ;
- ce marqueur vivait sur le pathTracker, or les dumps SANS pathTracker
  (encodage des clés complexes par rapidjson.dumps brut) rebouclaient
  quand même (pile épuisée sur le golden des clés mélangées) → repli du
  marqueur en drapeau de module sous GIL.

Trou de l'attribut d'objet au nom porteur : TRAITÉ dans la foulée
(0769c28). Un attribut nommé comme un champ d'enveloppe (__class__,
__init__, __new__, __state__, __items__, __dict__, $ref) écrasait
l'étiquette à l'aplatissement. Détection hybride au niveau le moins
coûteux : par CLASSE pour les slots (class_plan, coût par objet nul),
pré-passe filtrée au premier octet pour les états dict — placée APRÈS le
filtre d'attributs, découverte en testant : avec le filtre par défaut les
attributs _xxx sont déjà écartés PAR CONCEPTION, seul $ref était donc
réellement exposé ; sans filtre, les 7 noms l'étaient. L'état fautif part
sous __state__, où l'échappement des dicts du même matin le couvre — les
deux mécanismes composent :
    {"__class__": "module.Classe",
     "__state__": {"__class__": "dict", "'__class__'": "piégé", "x": 1}}
Ratios officiels inchangés (contrôle en ratio, méthode fiable) ; 61 tests
× 5 versions, goldens intacts.

Couverture : tests/test_dict_court.py, tests/test_cles_reservees.py,
600 fuzz orientés collisions ; 58 tests × 5 versions, goldens du
changement de nom vérifiés ligne à ligne (seule l'étiquette), goldens de
l'échappement inchangés (aucune donnée saine n'était concernée).


---

## 13. Matin du 4/08, suite — les pistes restantes du §11, chacune tranchée

### Littéraux inline dans les boucles de dicts (3edb2a9) : ADOPTÉ, pickle_dict ×2,2 → ×1,7
Un scalaire n'est jamais cible de $ref ni parent d'un conteneur : le
segment de chemin poussé avant sa récursion (deux push_back + deux pop
par valeur) était du travail à vide. None/True/False s'écrivent
maintenant inline dans les trois boucles chaudes (dict à clés entières,
plan de forme, recette plate). Mesure en ratio : pickle_dict −18 % en
plain (6/6 sans recouvrement), ×1,68-1,73 en PGO contre ×2,17-2,19 le
matin même. Extension naturelle si besoin : ints/floats inline (portent
numberMode et débordements — non fait, gain résiduel faible).

### PGO élargi aux formes des benchmarks officiels : ESSAYÉ, ÉCARTÉ
Profil enrichi (enregistrements bm_pickle, micro-dicts, petites listes
imbriquées, lots de littéraux et chaînes courtes) : pickle −3 % mais
unpickle_list +7 % (5/6) — le profil déplace plus qu'il ne gagne.
Workload restauré.

### Fusion clé-valeur au parse d'objets : ESSAYÉ, ÉCARTÉ
Clé courte propre lue en un passage SWAR (guillemets, blancs, « : »
compris) sans la mécanique ParseString. Neutre en ratio sur unpickle et
les micros : depuis la réactivation SSE et la tête SWAR de la nuit, la
lecture d'une clé courte ne coûte presque plus rien à contourner.
800 fuzz de clés pathologiques verts avant retrait.

### État des pistes restantes du §11 après cette passe
1. micro-dicts : nom court FAIT (§12) + littéraux inline FAITS — l'écart
   restant (×1,7) est l'enveloppe elle-même et le par-clé résiduel ;
2. mémo de chaînes dans le format : décision de format, en attente ;
3. multi-thread free-threaded : gros chantier, builds ft hors batterie ;
4. flottants au dump : plancher structurel (texte vs memcpy), Ryu fait ;
5. extraction MT des entiers : mur mémoire, couvert par numpy ;
6. fusion clé-valeur : écartée (ci-dessus) ;
7. PGO élargi : écarté (ci-dessus).


---

## 14. Matin du 4/08, fin — la note Optimisation.rtf traitée (itération des fichiers appendés)

En travaillant l'item « _json_object_file_iterator → passer en cython ? »
de la note, TROIS défauts sont apparus, tous corrigés (7591c4d) :

1. **L'itération était cassée net** (`for obj in Decoder(fichier)` →
   AttributeError) depuis la migration des __call__ en C : `__next__`
   appelle `_decode` brut, et l'état volatil par décodage (root,
   converted_numpy..., duplicates_to_replace...) n'était jamais posé.
   AUCUN test ne couvrait ce chemin (la note Tests le réclamait).
   `__next__` pose désormais l'état et résout les $ref après le parse
   (chemin général, correct pour dict/liste/scalaire appendu).
2. **Le scanner avalait le guillemet fermant après un échappement** (bug
   d'origine) : après `\x`, le drapeau restait levé jusqu'au prochain
   caractère « intéressant » — une chaîne finissant par `\n` faussait
   TOUTES les bornes d'objets suivantes. Le caractère qui suit un
   antislash est maintenant consommé quel qu'il soit, et le drapeau est
   persisté aux bornes.
3. **`__iter__` sur fichier absent** retournait une liste nue → TypeError.

Puis l'item lui-même : la machine à états de read() portée en C
(`rapidjson._scan_appended`), boucle Python conservée comme repli du mode
texte. Équivalence STRICTE tranche à tranche ET état à état vérifiée
sur des chunks de 1, 7, 97 et 4096 octets (le harnais a d'ailleurs mis au
jour deux sous-écarts : drapeau non persisté aux bornes, états non sauvés
en fin de liste — alignés). Itération : 15 → 6,4 µs/objet (−57 %).
Tests : tests/test_append_iter.py (formes variées, échappements, $ref
partagés, équivalence C/Python, fichier absent). 65 tests × 5 versions.

Autres items de la note tranchés en même temps (déplacés au _DONE) :
array_from_list/__init__ (résolu de longue date par
converted_numpy_array_from_lists, constaté), load_iter (existait, portage
fait), serializeRepr/encodedB64 (obsolète par sa propre conclusion).
Restent dans la note : dump_iter sans fermeture de fichier, écriture
non-bloquante (piste), sous-items numpy tolist.


### Complément (6d666f6) : append aligné sur la sérialisation directe
Décision utilisateur : un fichier construit par `append` est désormais
octet pour octet ce que donnerait la sérialisation directe de la liste
complète (éléments indentés d'un niveau via un proxy d'écriture — sûr,
un saut de ligne réel n'existant que dans la mise en forme JSON). Compact
inchangé ; anciens fichiers lus et appendables (mixité valide). Repéré au
passage, non corrigé : appendre à une liste vide `[\n]` produit une
virgule de tête invalide (cas limite préexistant, `[]` compact est sain).


---

## 15. Question creusée : dismatch entre clés JSON et attributs de classe

Vieille question de References.rtf (« peut-il y avoir un problème si les
clés du JSON ne correspondent plus aux attributs ? »). Réponse mesurée :
OUI, deux familles de défauts.

| Cas | Comportement actuel |
|---|---|
| objet à __dict__, clé orpheline | posée SILENCIEUSEMENT (attribut fantôme) |
| attribut renommé | vieux nom posé, nouveau nom ABSENT (init non rappelé) — erreur différée à l'usage |
| clé non-identifiant | posée dans __dict__ (accessible par getattr seulement) |
| __slots__, clé inconnue | AttributeError BRUTE au chargement, sans chemin ni contexte |
| property sans setter | AttributeError brute idem |
| setters=True | la correspondance v→setV fonctionne |

Le danger réel est le cas RENOMMAGE : silencieux au chargement, l'objet
est incomplet et l'erreur éclate loin, à l'usage. Les cas slots/property
échouent bruyamment mais sans dire OÙ (ni chemin JSON ni classe).

⚠ Objection utilisateur (12:24), qui invalide la piste 1 dans le cas
général : pour une classe à __dict__, il n'existe AUCUNE référence de ce
qu'est un attribut « connu » — Python n'exige aucune déclaration, un
attribut peut être légitimement ajouté à chaud, hors __init__ (que le
chargement ne rappelle d'ailleurs pas). Une politique « clé inconnue »
n'a donc de sens que là où une déclaration EXISTE : les __slots__ (et
c'est justement là que ça échoue déjà bruyamment), ou une déclaration
explicite fournie par l'utilisateur (annotations de classe, liste par
classe). Le « poser silencieusement » actuel n'est pas un défaut mais le
SEUL comportement correct par défaut pour les classes à __dict__.

Pistes restantes (décisions d'API, non implémentées) :
1. enrichir les AttributeError slots/property du chemin JSON et de la
   classe (amélioration de message, sans changement d'API) ;
2. table de renommage par classe (migration de schéma) — API nouvelle,
   opt-in ;
3. politique « clé inconnue » SEULEMENT opt-in et seulement pour les
   classes offrant une référence déclarée (slots, annotations, liste
   explicite).


---

## 16. Après-midi du 4/08 — la dérivée de compression, du paramètre mort au filtre blosc2

Chantier déroulé en quatre temps sur bytes_compression_diff_dtypes,
chaque étape mesurée avant la suivante (commits 19f925e, 386d16d,
60a0686, 2b5fa58) :

1. **Réactivation** : le paramètre était documenté mais MORT (encode
   désactivé en dur, cumsum oublié au décodage — un fichier _diff se
   relisait avec les différences —, repli non-compressé corrupteur).
   Revue commune, entiers seulement, 7 tests.
2. **Portages C** : _diff_axis0 (une allocation, prepend fusionné, et la
   corruption latente int8 de numpy.diff(prepend=uint8) supprimée) ;
   _cumsum_axis0 en préfixe SIMD (décalages-additions + report, ×13 sur
   int16). Puis dérivée MULTITHREAD par plages (aucune dépendance).
   La décompression était déjà MT (vérifié avant d'y toucher).
3. **Exploration du delta natif blosc2** : écarté chiffres à l'appui
   (delta d'octets sans retenue AVANT shuffle : quasi nul), et un bug de
   la lib trouvé (pipeline shuffle→delta du filtre NATIF corrompt).
4. **Filtre utilisateur enregistré (id 242)** : la sonde de balayage a
   révélé le VRAI pipeline gagnant — « shuffle PUIS delta d'octets » :
   une fois shufflé, chaque flux d'octets (poids faibles, poids forts)
   est lisse et le delta les linéarise TOUS. Signal int16 : **28,2 % du
   brut** contre 36,2 % (dérivée globale) et 51,6 % (shuffle seul). Par
   bloc, dans les threads de blosc2 des deux côtés, trame
   auto-descriptive (plus d'étiquette sur ce chemin), bit-exact pour
   tout dtype → l'opt-in s'ouvre aux FLOTTANTS (−6 à −9 % mesurés).
   Bout en bout : dump 0,89 ms (2,24 avant), load 0,90 ms = le
   sans-dérivée. Pièges consignés : la trame unique passait par l'API
   blosc1 qui ignorait les cparams et lisait shuffle=2 comme BITSHUFFLE
   (démasqué par une sonde fprintf dans le filtre — trois hypothèses de
   corruption émulées avant de sonder, aucune ne collait) ; le nombre de
   threads des contextes reprend le réglage global retenu.

La voie python-blosc v1 (sans filtres) garde la dérivée globale C et
l'étiquette _diff, entiers seulement ; tous les fichiers _diff existants
se rechargent. Restent ouverts dans la note Compression : le choix d'axe
(sans objet pour le delta d'octets ?), l'audio stéréo, les images, le
zip global, la compression itérative.

## 17. Soirée du 4/08 — l'essai automatique, le codec Rice, et les leçons de mesure

Suite directe du §16, en trois commits de fond (01d58be, 5843c85,
5a03ea8) plus un de réglage (78d8cb6).

1. **Essai automatique** (`bytes_compression_diff_dtypes=True`,
   01d58be) : au lieu de dériver sur foi d'un dtype, chaque tableau est
   sondé sur un ÉCHANTILLON (1/8 du tableau borné [4 Ko, 256 Ko], en
   4 bandes de lignes entières réparties — une bande unique au milieu
   tombait en plein silence d'un wav et faisait perdre le bon candidat)
   et le gagnant en taille est appliqué au tout. Candidats : shuffle,
   filtre 242, dérivée arithmétique axe 0 (entiers, étiquette `_diff`)
   en version shuffle et filtre, et le codec Rice (entiers 2/4 octets).
   Égalité → le plus simple ; échantillon == tableau → trame réutilisée
   telle quelle. Déterministe (sondes nthreads=1, choix par taille).
2. **Codec Rice enregistré (id 243**, 5843c85, stéréo 5a03ea8) : le
   mode « fixed » de FLAC dans le pipeline blosc2 — par trame de 1024
   échantillons, meilleur prédicteur polynomial fixe d'ordre 0-3, puis
   résidus zigzag codés en Rice, calibre k réajusté par partition de
   256 (escape verbatim pour le bruit, partition « tout zéro » à 6 bits
   pour le silence — sans elle le silence coûtait 1 bit/éch là où zstd
   fait du RLE). Canaux entrelacés gérés par prédiction PAR CANAL (pas
   c dans le quartet haut du meta ; nibble 0 = mono, trames antérieures
   lisibles). Adaptation locale = exactement ce que zstd n'a pas : zstd
   atteint déjà l'entropie GLOBALE d'ordre 0 des résidus, FLAC descend
   dessous en réajustant par trame — c'est de là que Rice tire ses
   ~10 points sur l'audio réel.
3. **Bug C de fond trouvé par la stéréo** (5a03ea8) : `acc >>= (t+1)`
   avec t+1 == 64 est INDÉFINI — x86 masque le décalage modulo 64,
   l'accumulateur ne bouge pas, un bit fantôme décale tout le flux. Ne
   se déclenche que si un unaire finit PILE en haut de la fenêtre de
   64 bits : de la vraie voix stéréo l'a produit, le mono quasi jamais.
   Méthode qui a marché : bissection à 64 échantillons, simulation
   Python au niveau des jetons (spec OK), comparaison d'octets flux C
   contre flux simulé (encodeur OK), sondes fprintf (décodeur faux dès
   l'échantillon 1), relecture bit à bit du flux réel (flux OK) → le
   lecteur était le coupable. Correction : décalage conditionnel.
4. **Leçons de mesure du soir** (bancs refaits proprement) :
   - Mes tailles « audio » de l'après-midi comptaient l'inflation
     base64 (×4/3). Les ratios restaient justes, les valeurs non.
   - Le wav stéréo du banc était un FAUX stéréo (canaux identiques) :
     zstd exploite cette redondance inter-canaux, Rice par canal non —
     seul cas où il perd (+43 %). Sur de la vraie musique (corrélation
     0,73), égalité de poids ; c'est le trou que le mid/side comblera.
   - Le duel des vitesses dépend entièrement du NIVEAU zstd : niveau 1
     (le défaut réel) Rice écrit ~2× plus lent que dérivée+filtre ;
     niveau 5, il est 3-7× plus RAPIDE ; niveau 9, 30-80×. Monter le
     niveau zstd n'achète que ~2 points de poids sur l'audio. En
     lecture, égalité partout (le cumsum de reconstruction est le
     goulot du camp zstd ; Rice lit même +25-40 % sur le 24 bits).
   - Sur le rock chargé, FLAC 60 % contre 74 % pour nos deux meilleurs :
     son avance restante = LPC adaptatif + mid/side, pas un défaut de
     notre Rice (74,4 % mesuré = 76 % prédit par l'entropie d'ordre 2).
   - PIÈGE d'outil : libsndfile PCM_24 écrit les 3 octets HAUTS d'un
     int32 — sans `<<8` la troncature est silencieuse et donne des
     taux « impossibles » (attrapé par l'argument du plancher
     d'entropie).
5. **Réglage harmonisé** (78d8cb6) : le niveau par défaut n'est plus
   défini qu'à UN endroit (le repli, niveau 1) ; le défaut de l'Encoder
   est la chaîne nue `"blosc2_zstd"`, et le nom est validé aussi pour
   les chaînes nues (avant, seule la forme tuple l'était). Octets
   produits inchangés (vérifié run fraîche contre run fraîche).

Décisions restées ouvertes : faire de l'essai automatique le DÉFAUT de
`bytes_compression_diff_dtypes` (posée plusieurs fois, non tranchée —
effets : les octets des tableaux lisses changent, petits dumps ×1,5-3,9) ;
la grille à 8 pipelines (`_diff1`/`_diff01`, ne paie que sur les entiers
larges 2D) ; la transposition en pré-passe ; une option `"flac"`.

### 17 bis. Nuit du 4 au 5/08 — le mid/side dans Rice

Autorisé à 20 h 29, livré dans la nuit. Mesure préalable (numpy) : le
mid/side en pré-transformée GÉNÉRALE ne paie pas pour les pipelines
d'octets (en 16 bits il faut élargir en 32, tout perd ; en 24/96 ± 1
point) — il n'est rentable QUE dans Rice. Implémentation retenue, la
plus simple qui gagne : canaux == 2 seulement, UN bit par trame
(gauche/droite ou mid/side), décision par une passe bon marché sur les
résidus d'ordre 1, recherche complète du prédicteur sur le seul domaine
élu. Transformée exacte mid = (L+R)>>1, side = L−R (la parité de side
rend la paire), historique recalculé des deux côtés depuis les paires
déjà vues — aucun état, aucune trame de contexte. L'escape s'élargit
d'un bit côté M/S (le side occupe un bit de plus que la source).

Deux pièges rencontrés et réglés :
  - **Les partitions mélangeaient mid et side entrelacés** : un side
    quasi nul payait le calibre k des mids actifs, le gain fondait
    (8 % au lieu de 25 sur canaux identiques). Correctif : dans une
    trame M/S, TOUS les mids d'abord, puis les sides — partitions
    homogènes, comme FLAC sépare ses canaux. C'est ce réordonnancement
    qui a donné les vrais chiffres.
  - **Les appels « à la volée » coûtaient 2× en vitesse** (transformée
    recalculée par échantillon et par ordre) : valeurs matérialisées
    une fois par trame (+ 6 d'historique), vitesse remontée de 0,16 à
    0,21 Go/s (mono 0,30 : le surcoût stéréo net est ×1,4).

Résultats (trames binaires, zstd hors jeu) : vraie stéréo 16 bits
74,5 → **67,1 %** (FLAC 59,9 — écart ramené de 24 à 12 %) ; faux
stéréo (canaux identiques) 56,2 → **28,4 %**, le SEUL cas perdant de
Rice devient 11 points DEVANT le meilleur pipeline zstd (39,3) ; 24
bits/96 kHz 56,0 → **52,0 %**. Mono strictement inchangé (le bit de
mode n'existe que pour c == 2). ⚠ Compat : les trames c == 2 écrites
entre 5a03ea8 (après-midi) et ce commit ne se relisent plus (le bit de
mode s'insère avant les bits d'ordre) — aucune n'existe hors bancs
d'essai, rien n'a été livré.

### 17 ter. Matin du 5/08 — la matinée des représentations, et la 6e candidate

Exploration guidée par Baptiste (mid/side pour les pipelines d'octets,
« ±ε aux mêmes bits », offset moitié), close par l'intégration d'une
sixième candidate. ⚠ PIÈGE D'OUTIL découvert en route : la signature
est `_diff_axis0(buffer, ITEMSIZE, cols)` — mes bancs de la veille au
soir et du matin passaient (buffer, cols, itemsize), justes par
symétrie sur la stéréo int16 (2 = 2) mais faux sur le 24/96 (dérivée
par sous-champs int16 au lieu d'int32) et plantant en 2D large. Toute
mesure « dérivée » de ces bancs a été refaite après correction ;
référence corrigée : d0+filtre = 74,1 / 41,2 / **56,4** % (vraie
stéréo / faux stéréo / 24-96), rice M/S = 67,1 / 28,4 / 52,0 %.

Écarté, chiffres à l'appui — le mid/side pour les pipelines d'octets :
  - **mid/side élargi (int32 exact)** : le side prend un bit de plus,
    le conteneur double, le surcoût mange tout (89,1 % vraie stéréo) ;
  - **lifting 16 bits (S-transform modulaire** : side = L−R enroulé,
    mid = R + (side>>1) enroulé, inversible modulo 2^16) : au mieux
    −0,4 point sur UN profil, perd ailleurs — le M/S aide le shuffle
    nu mais ABÎME le filtre delta (ils captent en partie la même
    chose), et l'enroulement salit les octets hauts ;
  - **offset moitié (non-signé décalé)** : identique au complément à
    deux au bit de signe près — le saut ±ε déménage (0x7FFF↔0x8001),
    ne disparaît pas ;
  - **signe-amplitude** : équivalent au zigzag sous bitshuffle, moins
    propre (double zéro, comblé par -2^(n-1) dans la variante testée).

INTÉGRÉ — la **6e candidate : dérivée → zigzag → bitshuffle**, baptisée
**« smart »** par Baptiste le 5/08 (idée « ±ε partagent leurs bits »,
de lui aussi). Le zigzag replie les
négatifs entre les positifs (0,-1,+1 → 0,1,2) : sans lui le
bitshuffle est une catastrophe (87 % — chaque bascule de signe
traverse tous les plans de bits), avec lui les plans hauts se vident.
Implémentation : filtre utilisateur 244 (largeur d'élément dans
filters_meta, persistée par la trame — auto-descriptif comme le 242),
chaîné au bitshuffle NATIF de blosc2, blocs élargis à 1 Mo en
NEVER_SPLIT (le bitshuffle transpose par bloc : à 32-256 Ko il
rendait 2-4 points contre la transposition globale). Gagne : 24/96
**51,9 %** (bat rice 52,0), camera u8 54,2 (filtre : 56,7), image
lisse 2 axes 4,4, signal 2M 26,0 ; perd : timestamps (12,3 contre
10,5 au d0+shuffle), RVB, stéréo 16 bits où rice M/S reste roi.
~1,2 Go/s mono-thread. Sans repli silencieux : shuffle=3 sans
libblosc2 lève ValueError, que l'essai automatique saute.

### Tableau de performance globale (approches EN PLACE, 05/08 matin)

Convention demandée par Baptiste, désormais permanente : chaque case
donne « poids % · ×écriture / ×lecture » rapportés à la référence
zstd seul niveau 1 (100 % · ×1,00 par définition ; valeurs absolues
de la référence entre parenthèses). Mesures mono-thread ; ± ~20 % sur
les vitesses (machine partagée) — depuis ce chapitre : machine calme
et CPU réveillé par un burst avant chaque chronométrage.

| Chaîne | voix 16b (70 % · 1,3 Go/s · 0,7) | stéréo 16b (97 % · 1,4 · 7,0) | 24b/96k (86 % · 1,2 · 7,3) | timestamps i64 (23 % · 0,6 · 4,1) | signal 2M i16 (80 % · 0,7 · 5,0) | camera u8 (71 % · 0,5 · 1,2) | surface lisse i32 (34 % · 0,5 · 4,8) |
|---|---|---|---|---|---|---|---|
| octet_shuffle → zstd | 80 % · ×0,4/×0,9 | 93 % · ×0,9/×1,0 | 79 % · ×1,0/×1,1 | 69 % · ×4,5/×2,4 | 64 % · ×3,8/×2,2 | 100 % · ×0,6/×1,1 | 63 % · ×2,7/×1,9 |
| octet_shuffle → delta (242) → zstd | 73 % · ×0,7/×0,7 | 84 % · ×0,8/×0,6 | 73 % · ×0,9/×0,7 | 54 % · ×3,6/×1,2 | 33 % · ×2,7/×1,2 | 80 % · ×1,0/×0,8 | 17 % · ×2,6/×1,1 |
| dérivée axe 0 → octet_shuffle → zstd | 73 % · ×0,3/×0,8 | 80 % · ×0,7/×0,2 | 71 % · ×0,7/×0,4 | 45 % · ×4,5/×1,8 | 44 % · ×0,9/×0,6 | 80 % · ×1,0/×1,0 | 14 % · ×3,2/×1,3 |
| dérivée axe 0 → 242 → zstd | 71 % · ×0,6/×0,7 | 76 % · ×0,6/×0,2 | 66 % · ×0,6/×0,3 | 50 % · ×5,6/×1,3 | 51 % · ×0,9/×0,6 | 81 % · ×0,9/×0,8 | 15 % · ×3,0/×1,0 |
| dérivée axe 0 → zigzag (244) → bitshuffle → zstd | 63 % · ×0,8/×0,7 | 76 % · ×0,7/×0,2 | 61 % · ×0,8/×0,3 | 53 % · ×2,2/×0,8 | 33 % · ×1,2/×0,5 | 78 % · ×0,7/×0,5 | 10 % · ×4,3/×0,8 |
| rice M/S auto (243) | 58 % · ×0,3/×0,6 | 69 % · ×0,2/×0,2 | 61 % · ×0,4/×0,3 | — | 34 % · ×0,5/×0,3 | — | 22 % · ×1,6/×0,8 |

(La matrice EXHAUSTIVE — 19 approches × 15 profils, écartées comprises
— est archivée dans la conversation du 05/08 ; les lignes ci-dessus
sont les six en production.)

Même tableau rapporté à **cPickle protocole 5** (référence demandée le
05/08 — pickle d'un tableau numpy ≈ recopie mémoire brute : poids en %
du brut, vitesses en fraction d'un memcpy ; mono-thread, dérivée par
blocs et fusion cache comprises) :

| Chaîne | voix 16b (réf. d 18,6 · l 28,3 Go/s) | stéréo 16b (15,8 · 29,0) | 24b/96k (3,9 · 20,0) | timestamps i64 (24,6 · 24,9) | signal 2M i16 (25,1 · 26,7) | camera u8 (24,0 · 33,4) | surface lisse i32 (20,4 · 22,3) |
|---|---|---|---|---|---|---|---|
| pickle (réf.) | 100 % · ×1,00/×1,00 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |
| octet_shuffle → zstd | 56 % · ×0,05/×0,02 | 90 % · ×0,08/×0,22 | 68 % · ×0,29/×0,40 | 16 % · ×0,10/×0,37 | 51 % · ×0,10/×0,36 | 71 % · ×0,02/×0,02 | 3 % · ×0,12/×0,39 |
| octet_shuffle → 242 → zstd | 51 % · ×0,04/×0,01 | 82 % · ×0,07/×0,16 | 63 % · ×0,27/×0,27 | 12 % · ×0,09/×0,17 | 26 % · ×0,07/×0,21 | 57 % · ×0,02/×0,02 | 1 % · ×0,16/×0,33 |
| dérivée blocs → octet_shuffle → zstd | 51 % · ×0,03/×0,02 | 77 % · ×0,07/×0,20 | 61 % · ×0,18/×0,28 | 11 % · ×0,16/×0,28 | 35 % · ×0,02/×0,14 | 57 % · ×0,02/×0,03 | 0,3 % · ×0,35/×0,35 |
| dérivée blocs → 242 → zstd | 50 % · ×0,03/×0,01 | 75 % · ×0,06/×0,13 | 56 % · ×0,19/×0,21 | 12 % · ×0,15/×0,20 | 41 % · ×0,03/×0,12 | 57 % · ×0,02/×0,02 | 0,3 % · ×0,17/×0,25 |
| dérivée blocs → zigzag (244) → bitshuffle → zstd | 44 % · ×0,05/×0,02 | 74 % · ×0,06/×0,11 | 52 % · ×0,26/×0,18 | 12 % · ×0,10/×0,11 | 26 % · ×0,05/×0,10 | 55 % · ×0,02/×0,02 | 0,2 % · ×0,13/×0,18 |
| rice M/S auto | 41 % · ×0,02/×0,01 | 67 % · ×0,02/×0,05 | 52 % · ×0,11/×0,12 | — | 27 % · ×0,01/×0,06 | — | 8 % · ×0,04/×0,17 |

Lecture : face à pickle (une recopie), toute compression paie sa
vitesse — de ×0,4 à ×0,01 selon le profil — et achète du poids (jusqu'à
÷300 sur les surfaces lisses). Les rapports contre pickle sont durs sur
les PETITS tableaux (la référence tient en cache : 18-33 Go/s).

SYNTHÈSE finale (conventions arrêtées le 05/08 midi : référence zstd
niveau 1 sans filtre, rapports de TEMPS — ×2 = deux fois plus long —,
écriture = compression pure, base64 mesuré à part, MÉDIANE d'~50
essais, moyennes GÉOMÉTRIQUES sur les profils applicables ; les lignes
émulées numpy ne sont pas reprises ici, leurs lectures sont plombées
par l'inverse non porté en C) :

| Chaîne (en production) | profils | poids moyen | ×écriture | ×lecture |
|---|---|---|---|---|
| zstd niveau 1 sans filtre (réf.) | 15 | 100 % | ×1,00 | ×1,00 |
| octet_shuffle → zstd | 15 | 81 % | ×0,77 | ×0,84 |
| octet_shuffle → delta (242) → zstd | 15 | 63 % | ×0,95 | ×1,10 |
| dérivée blocs → octet_shuffle → zstd | 14 | 54 % | ×1,01 | ×1,17 |
| dérivée blocs → 242 → zstd | 14 | 53 % | ×1,17 | ×1,33 |
| dérivée blocs → zigzag (244) → bitshuffle → zstd | 14 | **46 %** | ×1,04 | ×1,72 |
| rice M/S auto | 9 | 77 %* | ×3,26 | ×1,78 |

*La moyenne de rice inclut bruit et rampes où il s'effondre — des cases
que l'essai automatique, qui choisit par la taille, ne lui donne
jamais ; sur son terrain (l'audio réel) il est 10-20 points devant.

⚠ MÉTHODE (leçon du 05/08, complète celle du §11 sur le bruit de
build) : une comparaison de vitesses n'a de sens qu'entre mesures
prises SOUS LA MÊME CHARGE — même passe, A/B immédiat, référence
mesurée une fois et réutilisée. Les chiffres pris à des moments
différents ont divergé du simple au quadruple sur cette machine
partagée ; le « deux fois plus rapide que pickle » de la nuit de
migration mesurait un pickle écrasé par la charge (0,48 Go/s pour une
recopie de 96 Mo ; 3,9 à vide). Les TAILLES, elles, sont
déterministes : toutes les décisions de candidates reposaient dessus
et tiennent. Discipline désormais appliquée : machine calme, burst de
réveil CPU avant chaque chronométrage. Et sur machine calme, pickle
sur un tableau tenant en L3 est une recopie en cache (19-25 Go/s) :
imbattable en vitesse pure — nos gains contre lui sont le POIDS
(÷4-7), et la vitesse seulement au-delà du cache (timestamps 32 Mo :
dumps ×1,12) ou dès qu'un disque/réseau entre en jeu.

### 17 quater. Matin du 5/08 — la dérivée par BLOCS : la lecture parallèle

Idée de Baptiste (« des dérivées et des cumsum sur des blocs
indépendants ») : la dérivée d'axe 0 globale imposait à la lecture une
somme cumulée en chaîne — série pure en 1D, à 2 chaînes striées en
stéréo (2,2 Go/s, le goulot des lectures _diff). Désormais chaque bloc
de ~512 Ko de lignes ENTIÈRES redémarre sa dérivée (première ligne
brute) : les sommes cumulées deviennent indépendantes, multithread par
blocs + SSE dans chaque bloc. L'étiquette `_diffb<lignes>` porte la
taille de bloc ; `_diff` historique = globale, toujours lue (compat
descendante) ; en dessous d'un bloc, rien ne change (mêmes octets,
même étiquette). Coût en poids : une ligne brute par 512 Ko,
négligeable. Mesuré (machine calme, burst de réveil avant chaque
chrono) : somme cumulée stéréo 2,22 → **6,77 Go/s** (×3,05), 1D int16
7,94 → 9,88 (×1,25 — le SSE série était déjà bon en 1D). Nota : sur
l'audio réel l'essai élit rice, l'étiquette blocs sert donc surtout
aux profils où la dérivée gagne (timestamps, signaux, 2D).

Complété dans la foulée (demandes de Baptiste, même matinée) :

  - **Préfixe SIMD à enjambée 2** (stéréo entrelacée) : la cascade
    décalages-additions de Hillis-Steele en sautant la première passe
    (les lanes paires ne reçoivent que des lanes paires — les canaux
    ne se mélangent jamais), report par dernier COUPLE. La somme
    cumulée stéréo passe de 2,2 à **10,1 Go/s en un seul thread**
    (int32 : 8,6) — le SIMD seul bat les huit threads d'avant, on est
    à la bande passante RAM. int16 et int32, enjambée 2 seulement (le
    cas au-delà reste au code générique vectorisé par colonne).
  - **FUSION CACHE de la lecture** (« se rapprocher du L1 de blosc2 ») :
    la somme cumulée n'est plus une seconde passe RAM — elle est un
    POSTFILTRE blosc2, exécuté par bloc dans les threads de la lib,
    pendant que le bloc décompressé est chaud. Pour cela l'écriture
    CALE les blocs blosc2 sur les blocs de dérivée
    (cparams.blocksize = block_rows × octets_par_ligne, paramètre
    `blocksize` de BloscToBase64 ; la trame unique passe par l'API
    contextes pour tous les gagnants à dérivée). Deux pièges résolus :
    le postfiltre reçoit un TAMPON temporaire et doit écrire la sortie
    — un memcpy + cumsum en place rendait le gain nul (×1,02) ; la
    somme de préfixe est devenue LA copie (toutes les passes refactorées
    en (destination, source), l'appel en place = deux fois le même
    pointeur) → ×1,20 au niveau de la trame. Le filtre 242 y gagne
    aussi (son inverse n'a plus de memcpy).
  - **Fusion base64 comprise** : la voie C++ différée du parseur (qui
    fusionnait déjà b64 → zstd pour les trames « blosc2 » nues) est
    étendue aux étiquettes `_diff`/`_diffb` — dtype, forme et taille
    de bloc analysés en C++, cumsum par postfiltre si les blocs sont
    calés, post-passe par blocs sinon, repli voie Python dans tous les
    autres cas. Un chargement `_diffb` fait donc : parse → b64 → zstd
    → cumsum en UNE traversée C++ multithread, zéro passage Python.
    Bout en bout : timestamps 6,6 → **7,3 Go/s**, signal 1D 3,4 → 3,5
    (zstd domine désormais ce profil).

### 17 quinquies. Midi du 5/08 — la fusion ÉCRITURE, et un bug de fond du fork

Symétrique de la lecture : la dérivée par blocs n'est plus une pré-passe
(qui coûtait ~40 % de l'écriture : la passe + la remise de son tampon à
cache froid) mais un PRÉFILTRE blosc2 — la lib la calcule au moment où
elle constitue chaque bloc, octets de sortie STRICTEMENT identiques
(vérifié trame contre trame). Paramètre `diff_cols` de BloscToBase64
(exige `blocksize`, trame unique — les morceaux ne sont pas alignés aux
lignes) ; le plugin l'utilise quand le fork est là, pré-passe sinon.
Mesuré : écriture de la chaîne 244 sur 32 Mo 1,22 → **1,80 Go/s**
(×1,47), dumps auto bout en bout 1,97 Go/s.

**BUG DE FOND DU FORK trouvé par ce chantier** (et couvert par test) :
dans `pipeline_forward`, après un préfiltre, `_cycle_buffers` faisait
entrer le pointeur SOURCE — le tampon const de l'APPELANT — dans la
rotation des brouillons : avec DEUX filtres ou plus derrière le
préfiltre (zigzag puis bitshuffle), le deuxième filtre écrivait ses
résultats DANS le tableau numpy de l'utilisateur. Symptômes vécus avant
le diagnostic : échecs NON REPRODUCTIBLES (les scripts qui copiaient
leurs références avant l'appel « passaient », la boucle de stress
échouait 60/60), trames de tailles différentes entre deux voies censées
être identiques. La leçon de méthode : quand un aller-retour échoue,
VÉRIFIER AUSSI QUE LA SOURCE N'A PAS BOUGÉ — un memcmp source/copie
aurait montré la corruption au premier essai. Correctif dans le fork
(`blosc2.c` : le brouillon de thread `tmp4`, inutilisé en compression,
remplace la source dans la ronde), patch `blosc2_determinisme.patch`
régénéré, aucune trame modifiée (goldens identiques à l'octet avec
l'ancien et le nouveau fork), test `test_prefiltre_derivee_source_intacte`
qui ÉCHOUE sur l'ancien fork (vérifié) et passe sur le corrigé.

Dans la foulée (accélération de la LECTURE 244 demandée) : le profil a
montré la lecture dominée par zstd lui-même (7,5 ms sur 10,2 pour
32 Mo) — les filtres zigzag+bitshuffle ne coûtent que 0,4 ms, rien à
vectoriser de plus. Les vrais leviers mesurés : la taille de bloc —
**512 Ko partout** (L2-résident : lecture de trame 10,3 → 6,6 ms
×1,56, écriture ×1,1, poids conservé à 0,1 pt près sauf +0,9 pt sur le
24/96 où rice gagne l'essai de toute façon ; le « 1 Mo pour le
bitshuffle » venait d'une mesure du blocksize AUTO de blosc2, pas d'un
512 Ko explicite) — et le nombre de threads, dont l'optimum suit la
taille de bloc (8 threads avec 512 Ko, 4 avec 1 Mo : les tampons par
thread doivent tenir dans les L2 cumulés ; le plafond de 8 est bon).
Écartés : plafond 16 threads (les cœurs E dégradent), SIMD
supplémentaire du zigzag (déjà auto-vectorisé à -O3, part négligeable).
Bilan bout en bout du jour sur 32 Mo : dumps auto 1,36 → **2,59 Go/s**
(préfiltre + blocs), loads limité par base64+parse à ~3,3.

### 17 sexies. Après-midi du 5/08 — « smart » DEVIENT LE DÉFAUT, les sondes disparaissent

Décision de Baptiste (« je préfère partir toujours sur smart, plutôt que
de tester un échantillon », puis « n'avoir pas de dispositif de sonde du
tout ») : le défaut de `bytes_compression_diff_dtypes` devient
**`"smart"`** — les tableaux d'ENTIERS passent directement par la chaîne
smart (dérivée par blocs en préfiltre → zigzag 244 → bitshuffle → codec
au niveau choisi par l'utilisateur), les autres dtypes (flottants
compris) par le filtre 242, bit-exact pour tous. AUCUNE sonde : tout le
dispositif d'essai automatique est RETIRÉ du plugin (échantillonneur
stratifié compris) ; `True` est rabattu sur « smart » ; le tuple de
dtypes et `None` gardent leurs sens. Le codec rice reste enregistré
(toutes les trames écrites — rice, _diff, _diffb — se relisent, et il
demeure invocable par la couche C), mais plus aucun chemin de l'Encoder
ne l'élit : ses 10-20 points sur l'audio sont volontairement laissés au
profit de la simplicité et d'une écriture sans détour. Le niveau de
compression (`bytes_compression=("blosc2_zstd", N)`) pilote le zstd de
la chaîne, comme partout. Conséquence assumée : les octets par défaut
changent (compat ascendante levée le matin même) — goldens régénérés,
IDENTIQUES entre les cinq Pythons (vérifié octet à octet), anciens
fichiers toujours lus. Blocs unifiés à 512 Ko dans la foulée (§ ci-
dessus). Sur le bruit pur, smart paie ~×2 à l'écriture pour un poids
égal — coût accepté en connaissance de cause.

### 17 septies. Fin d'après-midi du 5/08 — fusion base64 : faite, mesurée, retirée ; cumsum dans le filtre 244 : gagné

**Fusion base64 par blocs** (demande « aller jusqu'au bout ») : le schéma
conçu avec Baptiste — relais d'offsets le long du commit ordonné du fork,
fusion des bits aux joints entre blocs, décodage par tranches à la volée
dans blosc_d (le base64 est une bijection sans état : l'octet d vit dans
le quadruplet d/3) — a été IMPLÉMENTÉ côté lecture (fork + enveloppe,
décodeur SSSE3 porté), validé exact (108 tests + 35 aller-retours), puis
MESURÉ en A/B alterné : perdant de 0 à 3 % en régime cache ET en régime
RAM (244 Mo, trame de 180 Mo). Cause structurelle : plafond d'Amdahl —
par octet compressé, le base64 SSE coûte 10-20 fois moins que zstd, le
gain maximal (~5-10 %) est du même ordre que les frais de la fusion
(lectures dispersées contre flux séquentiel que les préchargeurs
servent). RETIRÉ intégralement, fork revenu au patch commité. ⚠ Au
passage, piège du fork : ses modifications sont un diff NON COMMITÉ dans
c-blosc2/ — un git checkout là-bas les efface (il faut réappliquer
blosc2_determinisme.patch), une lib vanille a été déployée par erreur
puis rattrapée.

**Chantier gagnant né de l'autopsie : le cumsum DANS le filtre 244.**
À la lecture, le postfiltre imposait un saut de tampon par bloc
(décompression vers un temporaire, recopie-cumul vers la sortie). Le
dézigzag et le cumsum étant adjacents et composables, l'ARRIÈRE du
filtre 244 les fait désormais en UNE passe quand son octet meta le
demande : quartet bas = largeur d'élément, quartet haut = code de
colonnes (1, 2, 4, 8 — le 1D, la stéréo, le quadri ; au-delà, repli
postfiltre). L'écrivain grave le code en mode préfiltre ; les deux
lecteurs C détectent l'octet 28 de l'en-tête et sautent alors tout
post-traitement. PIÈGE INSTRUCTIF : la première version scalaire
PERDAIT (×0,85-0,95 — une boucle à dépendance séquentielle contre le
préfixe SSE du postfiltre) ; la version gagnante fusionne dézigzag ET
cascade de Hillis-Steele dans la même passe vectorielle
(sj_unzig_prefix_u16/u32, enjambées 1 et 2). Verdict A/B (9 paires,
même processus) : **×1,08 à ×1,50, médiane ~×1,25** sur la lecture des
trames smart 1D/stéréo, int16 et int32.

Piste examinée et NOTÉE SANS SUITE — entrelacer le base64 bloc par bloc
avec zstd : aujourd'hui le base64 est un étage séparé (une passe SIMD
sur la trame COMPRESSÉE, vers/depuis un tampon de travail), pas fondu
dans la boucle de blocs. Mais il porte sur des octets 2-10× plus petits
que les données, et pour les tailles courantes ce tampon tient en L3 :
la passe zstd le relit depuis le cache — « au plus proche » par
accident de taille. Un vrai entrelacement exigerait un lecteur base64
à accès aléatoire (blosc2 lit sa trame par offsets) pour un enjeu
mesuré de +0 % (trame minuscule) à +38 % (bruit incompressible) du
temps d'écriture ; le seul cas gagnant serait des trames plus grosses
que le L3, donc des données énormes ET incompressibles — celles qu'on
ferait mieux de ne pas compresser. Coût/bénéfice défavorable.

### 17 octies. Soirée du 5/08 — chantier 2 : le préfixe de longueur, le scan de chaîne sauté

Deuxième des trois chantiers du soir. À la lecture, le parseur devait
SCANNER chaque charge base64 caractère par caractère (SSE, mais une
passe entière quand même) juste pour trouver le guillemet fermant —
alors que l'écrivain connaît la longueur au moment où il l'écrit.

**Format.** Le sérialiseur écrit désormais `"<n>:<base64>"`, où n est
le nombre de caractères base64 (`339296:BQGVAs...`). Le ':' n'appartient
pas à l'alphabet base64 : la détection est sans ambiguïté, et un fichier
ANCIEN (sans préfixe) retombe sur le scan normal — une charge qui
commence par des chiffres sans ':' à suivre échoue en quelques octets.
Point d'émission UNIQUE : `RawDataToBase64` (pybytesbuffer.h), par
lequel passent toutes les charges (BloscToBase64 ET RawBytesToBase64).

**Lecture, trois étages.**
1. *Le saut de scan* (reader.h, branche insitu de ParseString) : si le
   handler attend une charge — prédicat `SjExpectB64Payload()`, pile =
   liste `__init__`/`__new__` encore vide d'une classe binaire
   enregistrée, mêmes conditions que la branche charge de `String()`,
   évaluées AVANT le parse — et que la chaîne commence par
   chiffres+':', on saute n caractères et on vérifie le guillemet.
   BORNÉ par la fin du tampon (`SjBoundedInsituStream.sj_end_`) : un n
   menteur ne lit jamais hors du tampon, il retombe sur le scan. Le
   saut pose aussi l'indice « ascii propre » gratuitement. Restreint
   aux positions charge : une chaîne UTILISATEUR « 2:a\" » contenant
   un échappement ne peut pas détourner le saut, il ne s'applique
   jamais à elle.
2. *La branche charge de String()* (rapidjson.cpp) retire le préfixe
   avant `sj_b64_layout`/décodage : le différé (pendingB64) et le
   décodage immédiat reçoivent le span base64 nu.
3. *Les replis python* (`numpyB64`, `bytesB64`, `bytearrayB64`,
   `blosc_chunks_decompress`) : `sans_prefixe_longueur()` — chemins
   froids seulement (dtype bool, flux, petites charges).

**Verdict A/B** (même processus, paires alternées, médiane de 50,
burst CPU, machine calme ; le « sans » est le même JSON, préfixes
retirés par regex — seule variable) :

| cas | avec préfixe | sans (scan) | gain lecture |
|---|---|---|---|
| int16 lisse 8 Mo (json 4,5 Mo) | `3,26 ms` | 3,68 ms | **×1,13** |
| stéréo int16 16 Mo (json 9,3 Mo) | `6,86 ms` | 7,78 ms | **×1,13** |
| int32 lisse 32 Mo (json 16 Mo) | `10,81 ms` | 12,83 ms | **×1,19** |

Mieux que les ~5 % espérés du seul scan : le saut économise aussi la
pose de l'indice ascii et les branchements du flux. Surcoût d'écriture :
6-8 caractères par charge, négligeable. Les goldens ont suivi le
nouveau format ; les tests qui décodaient le dump à la main passent par
`_trame()` (retrait guillemets + préfixe) ; le seuil de `test_2d_axe_0`
passe de /2 à ×0,55 (préfixe constant des deux côtés d'une inégalité
serrée à 1 octet près).

### 17 nonies. Soirée du 5/08 — chantier 3 : la grande coupe (écriture v1, blosc2p, _diff global, rice)

Troisième chantier du soir : tout ce qui n'était plus écrit que par
compatibilité disparaît de l'ÉCRITURE — la LECTURE de chaque format
jamais produit demeure, intégralement.

**Vérification préalable, qui a élargi la coupe** : le fork libblosc2
relit les trames v1 python-blosc — testé sur les 5 codecs × 3 shuffles
× 2 typesizes, 30/30 exacts. Et l'octet de version des trames écrites
par le repli blosc1 du C++ est 5 (format blosc2), pas un format v1 :
rien de ce que nous écrivons ne dépendait déjà plus de python-blosc.
Conséquence : **python-blosc n'est plus une dépendance** (retiré de
setup.py, plus aucun import en dur ; il ne reste qu'un repli paresseux
si aucune libblosc2 n'est chargeable). Prouvé par un test qui rend
`import blosc` impossible puis importe serializejson, relit du v1
(bytes + `_diff` global) et fait un aller-retour d'écriture.

**Supprimé (écriture et code mort)** :
- le codec Rice 243 en entier (~420 lignes : SjBitWriter/Reader,
  encodeur/décodeur, mid/side, enregistrement) et le paramètre
  `channels` de BloscToBase64 (signature recalée, `nthreads` accepté
  et ignoré — le multithread interne suit le réglage global) ;
- l'écriture par morceaux concaténés blosc2p (sj_compress_chunks,
  worker, étiquettes `blosc2p`/`b64_blosc2p` à l'écriture) ;
- le repli d'écriture blosc1 du C++ : TOUT passe par l'API contextes
  (bonus mesuré au passage : sur des octets périodiques, la voie
  contextes compresse 13× mieux que le repli blosc1, blocs plus
  larges) ; les symboles blosc1_compress/set_compressor ne sont plus
  résolus ;
- les branches d'écriture v1 des greffons (blosc.compress bytes,
  bytearray, numpy) ; un nom v1 dans `bytes_compression` produit un
  message explicite « v1 write removed, v1 files remain readable » ;
- l'étiquette `_diff` GLOBALE à l'écriture : un tableau plus petit
  qu'un bloc est UN bloc `_diffb<lignes>` ;
- l'échafaudage restant des sondes (cname_gagnant/payload=None) et
  `blosc.set_nthreads` côté python.

**Conservé en lecture, avec tests à trames FIGÉES** (produites par
python-blosc avant la coupe, incorporées en littéraux dans les tests —
elles prouvent la lecture v1 sans python-blosc) : bytes `b64_blosc`,
numpy `blosc_diff` (v1 + dérivée globale), `blosc2_diff` (blosc2 +
dérivée globale, écrit un temps le matin du 5/08), la boucle
multi-trames de blosc_decompress_chunks (fichiers blosc2p existants),
les noms numpy1. Les tests « rice » qui n'étaient que des
allers-retours smart sous un autre nom sont renommés et conservés
(bords de trame, stéréo, int32 mêlé, déterminisme, canaux disparates) ;
seuls ceux qui forçaient le codec disparaissent avec lui.

### 17 decies. Nuit du 5 au 6/08 — chaque type sous ×2 de pickle : état du chantier

Objectif VALIDÉ par Baptiste (20 h 26) : sur la table par types du rapport
de benchmarks (mesure par LOTS de 32 répliques ; itération rapide par le
script de session types_seuls.py), descendre dumps ET loads sous ×2 de
pickle pour chaque catégorie ; batterie verte et commit à chaque gain,
exceptions consignées ici. (Soirée déclarée exceptionnelle : pas de
bascule d'autonomie à 21 h dans la session en cours.)

FAIT et commité :
- mesure par lots honnête (clones pickle ; singletons dédupliqués admis,
  les deux camps les mémoïsent) ;
- vidage de la file base64 différée — il survient à CHAQUE end_object
  python — sans threads ni contexte multi-thread sous 1 Mo, et forme
  chaîne ascii des bytes dans la table C de lecture :
  bytes loads ×172→17, bytearray ×106→10 ;
- clés non-str : Décodeur par thread réutilisé + chemins scalaires
  (_decode_cle) : dict loads ×66→12,5, collections ×56→13.

RESTE, par priorité mesurée : bytes dumps ×36 ; types loads ×30 ;
set/frozenset dumps ×29/×23 ; dict dumps ×25 ; collections ×13 ;
bytesarray ×11 ; tuple loads ×9 ; binary ×6,5 ; decimales/datetime
loads ×4-4,6 ; range/slice/queue/iterators loads ×2,5-3,5 ; scalaires
dumps ×2,4-3,6.

VOIE RETENUE pour l'écriture des builtins (set/frozenset/bytes/bytearray) :
étendre class_plan (serializejson/__init__.py:986) d'un plan « natif »
(code PyLong 1..4) pour les classes EXACTES, gardé par l'absence d'entrée
registre utilisateur ; côté C (rapidjson.cpp, branche des plans ~5420)
ajouter `else if PyLong_CheckExact(plan[0])` → enveloppe écrite en C
(RECURSE éléments, mémo CONTAINER_MEMO_OR_REF, PySet_Add dumpedClasses,
PATH pour $ref). ⚠ IDENTITÉ OCTETS : enveloppe set MONO-ligne
(SingleLine/PushCompact), enveloppe bytes MULTI-lignes — répliquer
exactement (_dict_from_instance dit qui enveloppe quoi). Pour bytes :
le plan est mis en cache PAR DUMP → y embarquer seuil/compression du
moment ; le C ne traite que len<seuil (ascii imprimable → forme chaîne,
sinon b64 via RawDataToBase64 qui pose déjà le préfixe « n: ») ; ≥seuil
→ None, voie python blosc. Reproduire EXACTEMENT l'ensemble accepté du
codec ascii_printables (SmartFramework/string/encodings) avant d'écrire
le test C d'imprimabilité.

Fin de nuit : PGO ×5, batterie complète, benchmarks sur machine calme,
rapport final ici. ⚠ Mémoire persistante indisponible depuis ~20 h 40
(bind-monts de /DATA retombés, dossier projet réapparu vide en nobody —
redémarrage requis) : CE document est le porteur d'état de la nuit.

Avancement ~21 h 15 (tout commité, batterie verte à chaque pas) :
bytes loads ×172→17 puis file différée sans threads <1 Mo ; bytearray
×106→10 ; dict loads ×66→12,5 (Décodeur par thread + clés scalaires) et
dumps ×25→15 (préfiltre regex au lieu de la sonde loads par clé) ;
collections ×56→13 par ricochet ; set/frozenset dumps ×29/23→5,4/4,1
(recette C via class_plan + règle « liste exacte = telle quelle ») ;
types loads ×30→6 (cache dédié des valeurs de type — PAS le registre
constructors, piège attrapé par la batterie — partagé avec le C qui n'en
sert que les hits, NoneType compris ; lot 1750→295 µs). ⚠ Les mesures de
ratios de ce soir sont polluées (Baptiste travaille, charge 5-6) : se fier
aux PROFILS (compte d'appels python) pour choisir les cibles, et refaire
la table finale sur machine calme. RESTE : bytes dumps ~×19 (plancher =
appel plugin par objet ; viser une branche C native avec seuil/params via
pathTracker), collections ~×12, bytesarray dumps, tuple loads ×8 (le
chemin C PyList_AsTuple existe — chercher pourquoi il ne prend pas sur la
catégorie), decimales/datetime/binary, iterators/queue, scalaires dumps.

Avancement ~21 h 50 : plans « constructeur seul » (classe, 2) EN PLACE —
les classes C (Decimal ×2,2, datetime ×3,3, deque...) et celles à
__setstate__/setters/properties s'appellent en C pour l'enveloppe stricte
{__class__, __init__} (liste ou scalaire) ; DEUX pièges attrapés par la
batterie : type(x) à un argument (garde « type » explicite) et le registre
constructors utilisé comme cache. Harnais : la lecture se mesure sur le
dump réel du lot ($ref internes respectés) — ce qui expose une NOUVELLE
cible : la résolution python des références (~2 µs par $ref via
_resolve_duplicates/from_name ; les lots de types dédupliqués la rendent
dominante). RESTE par priorité : résolution $ref en C ; bytes dumps ~×20
(plancher appel plugin par objet → branche C native avec seuil/params via
pathTracker) ; collections ~×13 (formes __items__) ; bytesarray dumps ;
tuple loads ~×8 (plancher enveloppe C — candidat exception ou
reconnaissance au parse) ; scalaires dumps ×2-3 (coût de l'enveloppe
générique par appel) ; iterators/queue ≈ plancher d'appel. Mesures de
ratios TOUJOURS polluées ce soir (charge 4-6) : table finale sur machine
calme en fin de nuit + PGO ×5 + batterie avant le rapport.

Avancement ~22 h 30 : résolution C des $ref EN PLACE (sj_resolve_ref_path,
grammaire de l'encodeur root/.attr/[int]/['clé'] ; branchée pendant le
parse pour les racines dict, exposée en module rapidjson._resolve_ref_path
pour la post-passe des racines liste ; réfs en avant et cas exotiques
restent python) — types loads ×30→12 ; piège : les formats s# exigent
PY_SSIZE_T_CLEAN (SystemError sur 15 tests), passer par l'objet unicode.
Table indicative du moment (charge machine 2-6, valeurs à refaire au
calme) : dict ~×15 dumps / ×12 loads ; bytes dumps ~×20 (plancher plugin
python par objet) ; collections ~×12 ; bytesarray ~×11 loads ;
tuple ~×9 loads (plancher enveloppe) ; set/frozenset ~×4-5 ;
binary ~×4 ; datetime ~×3,5 loads ; scalaires ×2-3,5 dumps ;
range/slice/queue/iterators ×2,5-3,5 loads. PROCHAINES marches :
_replace_ref_placeholders (le PARCOURS python de l'arbre en post-passe)
en C ; écriture C native des bytes (seuil/params via pathTracker) ;
formes __items__ des collections en C ; enveloppes {__class__} en
reconnaissance au parse pour abaisser le plancher tuple/scalaires ;
puis PGO ×5 + batterie + table finale sur machine calme + rapport.

### 17 undecies. Nuit du 5 au 6/08, seconde partie — la reconnaissance d'enveloppe au parse

Reprise après passation (conversation perdue, état relu dans le
CLAUDE.md du dépôt). Quatre marches, batterie verte et commit à
chacune :

**Écriture native C des petits bytes/bytearray.** L'enveloppe est
composée en UN passage par l'écrivain (`BytesEnvelope`, formes
compacte et indentée conformes aux goldens) sous un seuil posé par
l'Encoder (`_bytes_natif_seuil` — zéro dès qu'un greffon bytes a été
remplacé : on ne court-circuite jamais un greffon utilisateur).
Leçon de mesure : ni le mémo (~0) ni les sept appels d'écrivain
(~0,08 µs) n'étaient le gros du coût — l'aller-retour python de la
recette pesait l'essentiel. 0,33 µs par petit bytes ; le reste de la
catégorie, ce sont les entrées ≥ seuil qui partent en compression :
le prix du POIDS, assumé et consigné.

**La reconnaissance des enveloppes AU PARSE** (la pièce centrale).
`{"__class__": nom, "__new__"/"__init__" [, "__items__"]}` est capturé
au vol dans le contexte du handler — le dict d'enveloppe reste VIDE —
et la fin d'objet instancie directement par une table
(`EnvelopeConstruct`, partagée avec la chaîne historique de fin
d'objet, dédupliquée à cette occasion). Au moindre écart de forme,
`EnvFlush` verse la capture dans le dict et la voie classique reprend
à l'identique. Deux pièges réels attrapés :
  - une référence `$ref` peut viser l'INTÉRIEUR d'une enveloppe encore
    ouverte (doublon mémoïsé dans les args `__init__`) — à la première
    clé `$ref` du document, TOUTES les captures de la pile sont
    versées (attrapé par test_doublon_dans_init_compact) ;
  - un conteneur capturé peut être REMPLACÉ par la suite (enveloppe
    imbriquée) : `ReplaceInParent`, factorisé, sait viser la capture
    du parent plutôt que son dict.
Surcoût d'enveloppe : 227 → 107 ns.

**Les racines LISTE résolvaient leurs `$ref` en post-passe python.**
Le résolveur C n'avait de racine que pour les documents à racine dict
(attribut `.root` du décodeur) ; il utilise désormais la racine du
HANDLER, qui existe pour les deux formes — chaque référence coûtait
~6 µs de python. tuple loads ×7,7→×3,3, types ×13→×3,9.

**Collections et clés non-str en lecture.** Capture du troisième slot
`__items__` + `CollectionsConstruct` (deque, Counter, OrderedDict,
defaultdict — sémantique d'instance() calquée : init liste →
`cls(*init)`, dict à clés str → `cls(**init)`, scalaire → `cls(init)`,
puis `update` sinon `extend`) ; et `DictNonStrConstruct` : les clés
des dicts `{"__class__": "dict"}` décodées en C (miroir exact de
`_decode_cle` : 'quotée', b'ascii', b64', booléens, null, entiers
python arbitraires, flottants), avec repli python PAR CLÉ restreint
aux seules formes encore parseables (`[`, `{`, `"`, marqueurs cassés)
— le repli par clé ORDINAIRE était précisément le coût historique.
dict loads ×11→×5,5 ; collections loads ×11→×5,6 (dont le gros était
en réalité le dict non-str INCORPORÉ dans Counter_no_string_keys).

État de la table à la passe de 00 h 15 (32 répliques par lot, machine
calme) : plus aucune catégorie au-dessus de ×17 ; en LECTURE, tout est
sous ×6 sauf bytesarray (~×11, ~7 µs par élément compressé restant à
profiler) ; en ÉCRITURE restent dict (×17), bytes (×12, compression),
collections (×8,5), sets/types (×4-6). Le reste à faire priorisé vit
dans le CLAUDE.md du dépôt.
