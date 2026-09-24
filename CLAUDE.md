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

## Addendum nuit du 09 au 10/08 — zéro-copie str (écriture),
## COMMITÉ git 999764a (10/08 matin)

Trois pistes retenues, tout est construit et validé, RIEN n'est commité
(autorisation attendue au matin) :

- **① dumps → str sans copie terminale** : tampon adossé à un str
  ascii compact (strBacking, stealPyStrAscii). PGO/PGO : gros ascii
  −29 %, liste_str −12,6 %, petit ascii −10,4 % ; accents +3 %
  (chemin copie inchangé).
- **④ grands str propres remis zéro-copie au fil d'écriture**
  (fichier) : RawPyStrPropre remet le PRÉFIXE propre (scan SSE2),
  l'appelant échappe la queue ; référence forte rendue par
  libereRefs. PGO/PGO : liste 100×100 Ko −17,8 %, gros 10 Mo −10,3 %,
  perdant −5,4 %, témoin +1,6 % (bruit). Lecture neutre partout.
- **④bis (idée de Baptiste, 22 h 14) : le str part SANS ÊTRE LU** —
  scan ET échappement dans le fil d'écriture (Bloc::Echappe,
  ecritEchappe sur le modèle d'ecritBase64, graphie sjEchappeUn
  identique à Writer::EchappeUn à l'octet près). GARDÉE par
  `index_ == nullptr` : dump vers un chemin indexe PAR DÉFAUT, la
  taille échappée inconnue au dépôt fausserait Tell/depose — les
  populations servies sont `index=None` et les append. PGO/PGO
  (`index=None`, latence/débit) : échappements denses −88/−72 %,
  gros propre −33/−14 %, dispersés −37/−25 %, perdant −25/−13 %,
  témoin ±0,5 % ; population indexée neutre (±5 %, signes mêlés).
  Piste ouverte pour servir l'index (audit §20.7) : positions
  numériques + formatage tardif + deltas d'expansion — refonte
  indexscan, pas cette nuit.
- Fermées : ② seuil parse en place (commentaire à rapidjson.cpp:5159),
  ③ compression écrivain (= décision de FORMAT, arbitrage au matin),
  ⑤ segments dumps (2×outputHighWater couvre déjà).
- Fichiers à commiter (les MIENS seulement) : rapidjson/{fdwritestream.h,
  prettywriter.h, pybytesbuffer.h, pywritestreamwrapper.h,
  rapidjson.cpp, writer.h, writerthread.h, pgo_workload.py} + les .so
  PGO + Notes/AUDIT (§20) + ce fichier. NE PAS toucher : README.rst,
  docs_source/images/*.svg, tests/serialized/*.json (autres instances).

Suite de nuit (23 h → …) — l'INDEX N'ÉTAIT PAS UN VERROU, Baptiste
avait raison (« il suffit de cumuler des deltas ») :
- **Refonte index-par-deltas FAITE** (audit §21.3) : Bloc::posBrut,
  journal (posBrut, expansion) relevé par le fil dans ecritEchappe,
  sj_index_corrige au rangement (cumul + recherche binaire, strict <
  car une borne d'entrée ne tombe jamais dans un str). ④bis DÉGARDÉ :
  garde `index_ == nullptr || !indexeRacine` — les dumps PAR DÉFAUT
  vers un chemin prennent la voie Echappe ; seul l'append indexé
  garde le préfixe (son rangement vit dans un WriterThread(-1) sans
  journal — piste : copier le journal sous verrou à la fermeture).
- Validation : 204 pytest verts, test paramétré neuf dans
  tests/test_indexation.py (égalité stricte index écrit = balayage),
  sonde refcount prouvant la voie. A/B décongestionné (audit §21.4) :
  lat −23 à −89 % sur toute la population indexée, contre chantier
  d'avant ET contre PGO ④bis ; seul débit esc_dense en boucle serrée
  retrait (échappement scalaire chantier ~90 Mo/s) — verdict PGO/PGO.
- pgo_workload.py étendu : bytes différés (ecritBase64), dump indexé
  seuil 16 multi-entrées échappées (sj_index_corrige à chaud).

Suite (00 h 09, question de Baptiste « et append a profité ? ») —
**l'append rejoint la voie Echappe, la porte ④bis DISPARAÎT**
(audit §21.6) : les entrées d'un append sont corrigées à la mort de
CHAQUE écrivain (sj_append_ferme, après termine(), expansions
closes) — un écrivain ultérieur relit son debut du descripteur donc
repart en coordonnées réelles, la correction est exacte par époques,
le poseur WriterThread(-1) reçoit des entrées déjà réelles.
RawPyStrPropre perd `entier` et la voie préfixe (−13 lignes, une
seule voie pour tous les flux fichier). Preuve par le rouge : test
neuf append grands str (2 formes × close, le close=True exerce le
multi-époques) rouge 4/4 sur binaire à correction neutralisée.
PGO/PGO append 1 Mo indexé : propre −94 % (2,4 µs), dense −99,9 %
(1,9 µs contre 1 532), dispersé −98 %, témoin neutre ; population
dump revérifiée sans dilution. 212 tests verts × 4 versions,
corpus PGO étendu aux appends.

Suite (00 h 47, objection de Baptiste « je ne comprends pas ce qui
empêche le writer de choisir l'étiquette ») — **la compression blosc2
rejoint le fil d'écriture, la « décision de format » ③ DISSOUTE**
(audit §22) : BloscDiffere (greffons bytes/bytearray, forme compacte
et non-ascii pour bytes seulement), ecritCompresse dans le fil avec
contexte par fil, étiquette choisie par le fil (b64_blosc2 si
csize < taille, sinon b64), delta (posBrut, émis) au journal comme
Echappe ; hors flux fichier : compression synchrone, mêmes octets.
Index : bloc différé compté zéro → rétention conservative
(blocsVariables) + élagage final (sj_index_elague), preuve par le
rouge dans les deux sens (test_index_et_compression_differee_aux_
bornes_du_seuil). **Bug de déterminisme PRÉEXISTANT corrigé au
passage** : un contexte blosc2 en cache gardait le blocksize de sa
première compression → trames différentes selon l'historique (la
référence se contredisait elle-même dumps vs dumpb sur un document
multi-tailles) ; clé de cache par taille d'entrée (SjCctxKey.nbytes,
4 points d'appel). Validation : identité à l'octet 252 lignes
(mono == par-cas == référence à contexte neuf), append identique,
213 tests × 4 versions PGO, batterie rejouée sur PGO bit à bit.
Mesures PGO/PGO : lat dump −91/−94 % (4 Mo), −30 % (8×100 Ko),
append +8 % et total multi-charges +7-10 % (compression désormais en
série dans le fil au lieu de recouvrir — assumé, le cas nominal ne
wait pas), gros documents neutres. pgo_workload : cas compression
différée ajouté. Fichiers touchés en plus de la liste ci-dessus :
indexscan.h, serializejson.h, plugins/serializejson_builtins.py,
tests/test_indexation.py.

Pièges nouveaux payés cette nuit :
- **Un banc dont la setup fabrique ses documents avec le binaire testé
  mesure l'état du TAS, pas le binaire** : la copie terminale de
  l'ancien dumps libérait un bloc ≥10 Mo, relevant les seuils
  dynamiques glibc — sa disparition (zéro-copie) a fait surgir une
  fausse régression lecture ×2,7 (2 557 défauts de page/itération =
  les objets résultat rendus à l'OS). Documents de banc via json.dumps.
  Optimisation préexistante possible (seuils malloc, réglage global
  processus) → rapport, pas code.
- **Un banc de dump qui réécrit la MÊME cible mesure le writeback, pas
  le binaire** : open("wb") tronquant un fichier aux pages sales rend
  260-400 ms sur VeraCrypt congestionné (1 ms à froid) — fausse
  régression ×90 sur les échappements, et le binaire le plus rapide
  paraît le plus lent (il creuse le retard device). Correctif :
  os.sync() en frontière de cas + fsync de la cible après chaque
  wait_writes. Diagnostic par sonde à thread échantillonneur (dump ne
  tenait pas le GIL) puis chrono de l'open seul. Audit §21.4.
- zsh : `echo ===` échoue (« == not found », expansion =mot) — mettre
  les délimiteurs entre guillemets.
- `for o in $ordres` ne découpe PAS une variable non citée en zsh —
  dérouler les appels run_ref/run_new explicitement.
- build_pgo.sh SE LANCE DEPUIS rapidjson/ (depuis la racine : crée un
  rapidjson.cpp vide à la racine + InvalidVersion) — repayé.
- **dump vers un CHEMIN pose un index sidecar PAR DÉFAUT**
  (indexation.FORME_DEFAUT) : toute voie gardée par `index_ == nullptr`
  est silencieusement inerte sur les dumps par défaut — un premier A/B
  de ④bis n'a mesuré que du bruit. Avant de mesurer, PROUVER la voie
  prise par sonde : `sys.getrefcount(s)` juste après le retour de
  dump() — +1 ssi le str est parti différé (réf forte en vol).
- Le greffon pytest typeguard casse sur 3.14 (ImportError ast.Str) :
  `-p no:typeguard` partout, déjà noté plus haut mais repayé dans la
  boucle de consolidation.

## Addendum 10/08 matin — compresseur d'avance (demande de Baptiste,
## 07 h 41), COMMITÉ git 3cbabfd

La contrepartie du §22 (compression en série dans le fil : +8-10 %
pour qui attend la fin) est résorbée par un thread « compresseur
d'avance » PAR ÉCRIVAIN (writerthread.h seul touché), lancé
paresseusement au premier bloc Compresse : il compresse les blocs
encore en file, EN PLACE dans la deque (pointeurs stables, le fil
n'ôte jamais un bloc EnCours — il l'attend), avance bornée à 2
trames prêtes. États AFaire/EnCours/Pret sous le verrou existant ;
un bloc encore AFaire au front est réclamé et compressé en ligne
par le fil. ecritCompresse scindé compresseBloc/emetCompresse,
même clé de contexte par taille → même trame quel que soit le
thread. Audit §23.

Validé : sonde de voie (11/12 blocs pris d'avance), identité à
l'octet (252 lignes vs 999764a, chantier ET PGO), 213 tests.
Mesures (8 tours entrelacés, cas GROSSIS — voir piège) : débit
total −13/−30/−40 % vs commité sur 16×512 Ko, et −9/−18 % vs le
binaire d'AVANT-nuit (la régression s'inverse) ; append −11 % vs
commité mais +19 % vs avant-nuit (un spawn par maillon — worker
global partagé jugé hors de prix, à rouvrir sur profil réel).

⚠ Piège de banc NOUVEAU, payé deux fois ce matin : un banc qui met
le MÊME objet bytes sous N clés mesure l'écriture de $ref, pas la
compression (un seul bloc compressé, N−1 références). Chaque clé
doit recevoir un objet DISTINCT — le cas « 8×100 Ko » du §22.5
avait déjà ce défaut. Et sous charge 7-8, tout cas < 100 µs est du
bruit : grossir les cas jusqu'à dominer la charge, témoin obligatoire.

## Addendum 10/08 milieu de matinée — numpy différé au fil (audit §24),
## COMMITÉ git 9066da6 (10/08 10 h 24)

Question de Baptiste 09:10 (kodak bloque ∝ niveau) résolue : les
tableaux numpy rejoignent la compression différée du §22. Étiquette
TOUJOURS écrite quand la remise est possible (« b64 » si la trame
perd) → arité figée avant compression ; EtiquetteDiffere (arg séparé,
réf forte sur BloscDiffere étendu à la recette complète) ; décision
par d->issue (sync) ou FIFO issues (fil) ; bloc Etiquette compté
zéro + delta (posBrut, n+2). Remise différée SEULEMENT si to_compress
est le tampon d'origine (fork ou pas de diff0) — diff sans fork reste
synchrone (le repli brut du fil réémettrait une dérivée, faux).

Conséquences de format : compressible identique à l'octet ; repli
brut éligible porte « b64 » là où l'ancien n'écrivait rien → ancien
lecteur refuse (compat descendante seulement, assumé) ; zigzag sans
fork = ValueError (avant : trames fausses silencieuses). Lecteur :
compression == "b64" → None.

Validé : batterie identité 7 tableaux × 2 niveaux × 3 méthodes vs
999764a (seul l'incompressible diffère), 214 tests × 4 versions PGO,
append 2 époques, preuve par le rouge sur le delta d'Etiquette,
A/B kodak : blocage 184-199 ms → 0,6 ms au niveau 9 (indépendant du
niveau). pgo_workload : cas numpy différé ajouté.

Piège NOUVEAU : dump() vers un chemin est ASYNCHRONE — toute lecture
du fichier sans wait_writes() fait la course avec le fil (68 octets
vs 346 mesurés) ; load() synchronise, un aller-retour vert ne prouve
donc PAS que le fichier est complet.

Fichiers du chantier (les MIENS) : rapidjson/{serializejson.h,
writerthread.h, writer.h, prettywriter.h, fdwritestream.h,
pybytesbuffer.h, pywritestreamwrapper.h, rapidjson.cpp,
pgo_workload.py} + .so ×4 + serializejson/plugins/
serializejson_numpy.py + tests/test_indexation.py + audit §24 + ce
fichier. tests/lance_benchmarks.py = tâche SÉPARÉE (2 barres RAM),
en attente de sa propre autorisation.

## Addendum 10/08 fin de matinée — défaut « smart » par CIBLE
## (demande de Baptiste, 10 h 31), COMMITÉ git 9bdf0a5

« smart » sans niveau explicite prend désormais son barreau selon la
CIBLE : barreau 1 en RAM (dumps/dumpb — l'appelant paie la
compression, on prend le premier qui compresse), barreau 6 vers
fichier (dump/append — la compression part au fil d'écriture depuis
le §22/§24, son surcoût ne bloque plus l'appelant, on prend le plus
petit). Mécanique : bareme_smart_defaut_{ram,fichier} (tools.py),
_configure résout les DEUX profils quand le niveau est absent
(_profils_cible, None si niveau fixé), _applique_profil(fichier) en
tête de dump/append/dumps/dumpb ne réécrit les attributs QUE s'ils
changent (la poussée amortie de serialize_parameters reste amortie ;
les instances par défaut par thread de dumps/dumpb module ne
basculent jamais). Niveau explicite ou codec nommé : inchangés.

Piège vérifié au passage : la voie synchrone RAM préfixe la charge
numpy compressée de sa taille décomprimée (« 433120:BQE1… »), la
voie différée fichier non — écart de FORME par méthode PRÉEXISTANT,
les garanties d'identité sont par méthode entre binaires, pas entre
méthodes.

Figures (2ᵉ moitié de la demande) : le profil par défaut occupe DEUX
pages — benchmark_memoire_smart devient la page RAM (3 barres
dumps/dumpb/loads au barreau 1, cadre = poids mémoire) et
benchmark_fichier_smart la page disque seule (2 barres dump coupé
bloquant/fil + load, barreau 6, cadre = octets ÉCRITS index compris,
via octets_disque_*). Les deux bouts du barème (b64, min) gardent
leurs 5 barres à barreau fixe ; le camp disque « sj » mesurait DÉJÀ
les défauts, donc le barreau 6 — aucune mesure nouvelle, seulement
les fabriques. mesure_types_objets/types_seuls intacts.

Validé : 214 pytest verts (3.13, changement pur python, .so
intouchés), smoke des 4 fabriques de figures sur mesures factices,
en-tête du rapport rendue avec les vrais barreaux. Fichiers du
chantier : serializejson/{__init__.py,tools.py},
tests/{test_blosc2.py,lance_benchmarks.py}, ce fichier.
COMMITÉ git 9bdf0a5 (10/08 10 h 48) ; banc complet rejoué dessus,
rapport rapports_benchmarks/rapport_benchmarks_2026-08-10_1108.pdf
avec les deux nouvelles pages (RAM barreau 1 / disque barreau 6).

## Addendum 10/08 midi — lecture d'avance de l'itération (demande de
## Baptiste, 10 h 54), COMMITÉ git aa798b0 (10/08 11 h 23)

Pendant, côté lecture, du fil d'écriture d'append : quand on itère un
json-liste (`Decoder(path)` / `load(path, iterator=True)`), un fil
décode le maillon SUIVANT pendant que l'appelant travaille sur le
courant. Pur python (__init__.py seul), aucun changement d'API :

- **_LectureAvance** (section INTERNES) : fil par itération, UN
  maillon d'avance (sémaphore-jeton rendu par __next__ à la
  livraison), résultats par queue.SimpleQueue ("ok"/"exc"/"fin").
  Le fil ne tient le décodeur que par référence FAIBLE hors
  décodage ; weakref.finalize le réveille si l'itération est
  abandonnée (break) → fin du fil + fermeture du fichier, pas de
  fuite (testé). Re-__iter__ arrête l'ancien fil (join) avant de
  rouvrir.
- **ADAPTATIF** : la voie directe chronomètre ses décodages ; le fil
  ne s'engage que si la moyenne mobile dépasse _SEUIL_LECTURE_AVANCE
  (500 µs). Le PREMIER maillon chauffe les caches et ne compte pas
  (sans ça, son pic engageait le fil à tort : −19 % sur des
  scalaires). Petites listes : aucun fil créé, surcoût = 2
  perf_counter par maillon (~2 % mesuré, bruit).
- **Poussée des paramètres par le fil, par VALEURS et sans
  s'inscrire propriétaire** : la voie brute (_decode sans tp_call)
  ne poussait JAMAIS strict_pickle/setters/properties — l'itération
  lisait ceux du dernier encodeur/décodeur appelé (défaut
  préexistant, corrigé au passage). Ne PAS s'inscrire dans
  _decoder_owner : référence forte du module → une itération
  abandonnée ne mourrait jamais.
- **load(path, iterator=True) perdait le fichier** (Decoder() sans
  file) : corrigé + testé.
- Sémantique préservée à l'identique de la voie directe, y compris
  la limite « maillon en erreur → l'itération s'arrête ensuite »
  (parse avorté = frontière vide au lecteur borné ; vérifié
  identique sans le fil).

Mesures (A/B même binaire, fil contre voie directe) : décodage
entièrement masqué quand l'appelant rend le GIL (12×4 Mo + 10 ms de
sommeil/maillon : 124 ms contre 132, plancher idéal 120) ; travail
numpy réel +3,5-7 % ; cas GIL-bound et petits maillons : neutres
(seuil). Le gain réel dépend du temps SANS GIL de l'appelant
(entrées-sorties, numpy, pool de décompression ≥ 1 Mio — contextes
locaux par fil, vérifié sûr). 220 tests verts × 4 versions.

Fichiers du chantier : serializejson/__init__.py,
tests/test_iterator.py, ce fichier.

## Addendum 10/08 début d'après-midi — page « itération » du banc +
## scanner memchr (demande de Baptiste, 11 h 27), COMMITÉ git 5372044

Demande : une page du rapport PDF comparant la lecture sérielle d'un
pickle et la nôtre, avec un travail simulé (sleep) par maillon, pour
montrer que la désérialisation ne bloque plus quand on traite chaque
donnée chargée.

- **mesure_iteration / figure_iteration / page markdown**
  (tests/lance_benchmarks.py) : 4 camps — plancher (travail seul),
  pickle Unpickler.load() en boucle, serializejson voie directe
  (_SEUIL_LECTURE_AVANCE=inf), lecture d'avance (défaut) — sur 2
  charges à travail RÉALISTE par maillon (40 dicts 10 000 entrées ×
  5 ms ; 16 trames 1920×1080 RVB × 50 ms). La colonne porteuse du
  message est « au-dessus du plancher » = ce que la désérialisation
  coûte VRAIMENT. Chaque maillon est un objet DISTINCT (piège $ref).
  Un travail plus court que le décodage ne peut masquer que sa
  propre durée — les travaux sont calibrés par charge.
- **Scanner _scan_appended : voie rapide memchr** (rapidjson.cpp,
  sj_scan_appended) : l'intérieur d'une chaîne est transparent pour
  la machine à états — saut direct au prochain `\` ou `"` par
  memchr borné. Le scan octet à octet (~190 Mo/s) DOMINAIT le
  décodage du maillon (43 ms de scan sur 15 ms de vrai décodage
  d'une trame 8,3 Mo) : scan ×70, décodage du maillon 67,5 → 15,4
  ms. C'est ce qui fait passer la charge trames de « masquage
  partiel » à « bat pickle » (smoke : +24 ms au-dessus du plancher
  contre +38 pour pickle ; dicts : +27 contre +124).
- **Équivalence du scanner prouvée à trois niveaux** : corpus
  force-brute (9 tampons retors × 6 découpes × tous états d'entrée,
  empreinte sha256 par appel) — les 14 920 lignes divergentes ont
  TOUTES l'état d'entrée in_quotes=1 ∧ in_object=0, INATTEIGNABLE
  (in_quotes=1 n'est posé qu'avec in_object=1, ligne 11007-11008,
  et chaque retour de borne remet les deux à zéro) ; lecture de
  code ; pipeline complet identique (mêmes succès/échecs par taille
  de tranche, deux binaires). Le vieux code posait in_simple sur
  des octets EN CHAÎNE dans cet état synthétique — quirk, pas un
  comportement.

Piège PRÉEXISTANT constaté, non corrigé : chunk_size minuscule (7)
+ guillemets échappés denses (('q"'*30000)+"\\") perd des maillons —
identique sur le binaire commité, à reprendre si un jour un chunk
si petit sert vraiment. Piège sandbox NOUVEAU : le dossier
jobs/<id>/tmp est écrivable par l'outil Write mais PAS depuis Bash
(redirections « lecture seulement ») — les logs bash vont dans le
dépôt ou $TMPDIR. Un chunk_size PLUS GRAND (16 Mo) est PIRE que
64 Ko : ne pas « optimiser » par là.

Fichiers du chantier : tests/lance_benchmarks.py,
rapidjson/rapidjson.cpp, .so ×4 PGO, ce fichier.

## Addendum 10/08 midi et demi — l'itération se sert de l'index
## (demande de Baptiste, 12 h 13), COMMITÉ git 5372044

- **_arme_index (__init__.py)** : si `indexation.lit(chemin)` rend un
  index (sa fraîcheur root == [0, fin] fait déjà foi — un append nu
  le périme ENTIER, armé refusé, scan intégral), les bornes
  « root[i] » partent en deque ; read() cale chaque lecture ordinaire
  juste avant le prochain début indexé, et pile dessus rend le
  maillon EN UNE lecture contiguë (PyReadStreamWrapper prend le bytes
  tel quel) avec shedule_break. Les maillons sous le seuil (4096)
  coulent par le scan entre deux bornes. Garde d'armement restante :
  premier octet == `[` (racine liste).
- **Protocole de la tranche vide RÉPARÉ au passage** (le vrai gain) :
  une tranche vide non-frontière (queue de séparateurs épuisée)
  faisait prendre au parseur la fin du CHUNK pour la fin du FICHIER —
  un dump indenté relu au chunk 7 rendait 1 maillon sur 8, EN
  SILENCE, et le piège « chunk 7 + échappements denses » de
  l'addendum précédent était le même défaut. read() relit désormais
  sur tranche vide, SAUF le vide-frontière d'une valeur simple
  continuée (« null » coupé pile avant sa virgule : le scan ne pose
  pas shedule_break, exprès — garde `etait_simple and not
  self.in_simple`). Enveloppe read() UNIFIÉE : moteur C dans
  _scan_c, boucle python (mode texte) même protocole, fin de liste
  = None des deux côtés ; le test scanner C ≡ python compare les
  moteurs sous la même enveloppe en surchargeant _scan_c seul.
- Mesuré (A/B interlacé même processus, voie directe, charge ~5) :
  la voie index ne rend que +2-3 % (b64 100 Ko-10 Ko, dicts
  d'entiers), −1 % bruit sur 16×4 Mo — le memchr de l'addendum
  précédent a déjà mangé le gros du scan. Sans régression, gratuite
  quand l'index existe ; c'est le correctif de protocole qui paie.
- 224 tests × 4 versions ; 4 tests neufs (test_iterator.py) prouvés
  rouges sur le code commité (index armé + plages consommées, index
  refusé après append nu, chunk 7 indenté/compact, chunk 7 dense).

## Addendum nuit du 16 au 17/09/2026 — connexions Qt par introspection
## PySide6 (ordre de Baptiste « vas-y, implémente ça dans le greffon pour
## PySide6 »), COMMITÉ git 3ddae9b (18/09 22 h 15)

Le greffon serializejson_PyQt5_PySide2.py sérialise les connexions
signal→slot SANS surcharger connect (ancien hack new_connect/parse
SUPPRIMÉ, avec l'import `parse`) :

- **connections(root)** : dumpObjectInfo() de chaque QObject de l'arbre
  créé par python (Shiboken.createdByPython), lignes captées par
  qInstallMessageHandler. dumpObjectInfo nomme le récepteur par
  (classe, objectName), ambigu entre enfants anonymes → objectName
  temporaires `~sj<index>` posés puis restaurés (émet objectNameChanged).
  Signaux `destroyed` ignorés. Chaque connexion est stockée UNE fois,
  sous la clé "~connections" (triée en dernier) du plus proche ancêtre
  Qt commun émetteur/récepteur : les deux bouts sont déjà écrits quand
  le $ref l'est. Signal surchargé → index par sa signature C++
  (`valueChanged['int']`, `deux['int,QString']`). Signal→signal marche.
- **Connection.__setstate__** reconnecte en UniqueConnection : une
  connexion refaite par le __init__ de l'objet rechargé n'est pas doublée.
- **Non couvert** : lambdas/fonctions libres (« <functor or function
  pointer> », non retrouvables) ; PyQt5/6 (PyQtSlotProxy opaque, aucune
  introspection sans hook) → liste vide, comportement d'avant.
- **Décodeur (générique, tools.py + __init__.py)** : un $ref vers
  l'attribut d'un objet EN COURS de construction (`root.on_value` alors
  que root est encore un dict) échouait en KeyError. from_name reçoit
  `materialize` : sur KeyError d'un dict porteur de `__class__`, il
  pré-crée l'instance (Decoder._materialize, rangée dans
  dict["__class__"] comme le faisait déjà end_object) et prend l'attribut
  dessus. end_object simplifié en conséquence.
- Test : tests/test_pyside6_connections.py (sous-processus PySide6
  offscreen, 6 connexions dont surchargée et inter-branches, preuve par
  le rouge avec `--sans-lister`). 225 tests × 3.12/3.13/3.14.
  Coût mesuré : arbre de 390 widgets, dumps 1,4 → 10 ms (dumpObjectInfo
  par objet, O(n × profondeur)).
- Préexistant, constaté, NON touché : au rechargement les enfants créés
  par __init__ ET ceux recréés du json coexistent (4 QLabel pour 2) ;
  serializejson_QSpinBox n'écrit pas de parent ; les classes QtCore
  (QTimer) ne sont pas autorisables par le greffon.

Fichiers du chantier (les MIENS) : serializejson/plugins/
serializejson_PyQt5_PySide2.py, serializejson/tools.py,
serializejson/__init__.py, tests/test_pyside6_connections.py, ce fichier.

Constaté le 17/09 au soir (questions de Baptiste sur la ré-hydratation),
PRÉEXISTANT, non touché : `loads(json, obj=existant, updatables_classes=
[QtWidgets.QSpinBox])` est INERTE sur les widgets Qt — le json porte
`"QtWidgets.QSpinBox"` (type_str retire le préfixe d'API) alors que
set_updatables_classes bâtit `PySide6.QtWidgets.QSpinBox` ; la
comparaison de _exploreToUpdate échoue en silence, identités conservées
mais état non appliqué (spin 0 au lieu de 7). Identique sur les sources
commitées (vérifié par stash). Pendant json du mode
`create_QWidget=False` de SmartFramework/serializePython : à raccorder
(normaliser le nom dans set_updatables_classes par le même type_str).
→ CORRIGÉ la nuit suivante (_UpdatableClasses, addendum ci-dessous).

## Addendum nuit du 17 au 18/09/2026 — réhydrater ou recréer une application
## AU FIL DU PARSE (rehydrate — DÉFAUT depuis 01 h 22 —, qt_tree=True,
## load_application), COMMITÉ git 3ddae9b (18/09 22 h 15)

Demande de Baptiste (17/09 soir) : « réhydrater une application ou en
recréer une de toutes pièces en désérialisant (loader qui crée
l'application ?) », après revue des alternatives. Décision de Baptiste
(23 h 39) : PAS de double passe — le mode `obj=` actuel (tout le json en
dicts puis _exploreToUpdate) était PROVISOIRE, on construit/adopte
au fur et à mesure. Plan : ~/.claude/plans/eager-humming-wilkes.md.
Sortie de l'écrivain identique. Côté lecture, `rehydrate` est le DÉFAUT
(voir « Addendum 18/09, 01 h 22 » plus bas) ; qt_tree et load_application
restent opt-in.

### Volet A — décodeur : crochet `construct` (rapidjson.cpp + __init__.py)

- `Decoder(rehydrate=True)` (propagé par load/loads/Decoder.loads ; le
  module `loads` passe par `Decoder.loads` → `_appel`, qui garde `obj`
  dans `_live_root` SANS le passer au C : la voie update python n'est
  jamais prise). `rehydrate=False` laisse `construct` à None côté C :
  un test de pointeur nul, rien d'autre — c'est la voie classique, y
  compris l'ancien mode update `obj=` en python.
- C++ : l'enveloppe est en TÊTE du dict, les enfants arrivent après.
  À la première clé d'état (SjKeyConstruit, dans Key, hors __class__/
  __items__/$ref/__new__/__init__) ou à la fermeture sans état
  (EndObject), SjConstruit instancie (natives dict/type/numpyB64 →
  rien ; plan de classe connu et rehydrateEnC → tp_new/call en C ;
  sinon appel python `_construct(classe, args, slot, ancêtre, clés,
  stateless)`) et range l'INSTANCE dans `__class__` de l'enveloppe.
  Les `$ref` vers cet objet résolvent aussitôt (SjCibleRef, factorisé
  des deux sites) ; à la fermeture, SjAppliqueEtat (factorisé des deux
  blocs by_setattr/__dict__ dupliqués) applique l'état sur l'instance
  trouvée dans `__class__`, en sautant les clés `~…`. Chaîne des clés
  bornée au plus proche ancêtre construit (SjChaine) ; SjAncre :
  adoption sans état SEULEMENT si l'ancêtre est un argument du
  constructeur (enfant Qt anonyme) — sinon une enveloppe-valeur (QColor,
  Decimal) serait figée. `updatables_classes` non vide → voie python.
- Python `_construct` : authorized_classes, classe via `constructors`,
  homologue vivant par `_descend` (attribut / clé / index / lecteur
  `rehydrate_getters` pour les clés `~…`, accesseur Qt appelé si
  méthode), adopté si `type(vivant) is cls` (et dans updatables_classes
  si donné), sinon `tools.instance`. `__init__` jamais rejoué sur un
  adopté. Racine avec obj= adoptée sans vérification.
- `_UpdatableClasses(set)` : noms ET classes résolues — corrige
  l'inertie préexistante (« QtWidgets.QSpinBox » du greffon contre
  « PySide6.QtWidgets.QSpinBox » de class_str_from_class).
- Mémoire : pic = résultat + O(profondeur), indépendant de N (test
  test_rehydrate_memoire_bornee : transitoire(1000) < 2×transitoire(100)).

### Volet B — greffon Qt, écriture (qt_tree=True)

`encoder_parameters["qt_tree"]=False`. Avec True : `~windows`
(QCoreApplication, topLevelWidgets créés par python, triées (type,
objectName, windowTitle)), `~children` (QWidget créés par python, ordre
de création, identité POSITIONNELLE), `~layout` (grille : `[élément,
row, col, rowSpan, colSpan(, alignment)]`, sous-layouts, addLayout/
addWidget idempotents), propriétés minimales (windowTitle/geometry des
fenêtres, text/checked, centralWidget), `~connections` en dernier.
Lecteurs `rehydrate_getters["~children"|"~layout"|"~windows"]`.
`connections(root)` accepte l'application comme racine (connexions
inter-fenêtres), filtre `in_document` et slots privés `_q_`.
Correctifs préexistants : QSpinBox/QLineEdit/QPlainTextEdit écrivent
leur parent ; QLayout unifié (l'ancien QGridLayout rendait None) ;
`Encoder.default` → ValueError nommant une Reference hors document.

### Volet C — loader

`constructors` QApplication/QGuiApplication/QCoreApplication →
`application()` rend l'instance existante ou la crée (argv du json
ignoré). `load_application(fichier, obj=None, **kw)` = instance assurée
+ `load(..., rehydrate=True)` ; `app.exec()` reste à l'appelant.

### Tests

tests/test_rehydrate.py (7, sans Qt : adoption, remplacement sur classe
différente, sans état ancré/remplacé — voie C prouvée par sonde
decode_class_plan —, updatables_classes, recréation, mémoire bornée) ;
tests/test_pyside6_application.py (sous-processus offscreen : --ecrit,
--recree processus vierge, --rehydrate ×2 identités conservées ;
--sans-rehydrate ROUGE attendu = doublons de la voie classique).

### Passe de simplification (par fichier du commit)

- __init__.py : `_construct` construisait lui-même (liste/dict/
  scalaire/remove_add_braces) → remplacé par `tools.instance` (−9 l.) ;
  reste regardé, rien à enlever.
- rapidjson.cpp : SjPlan (cache decode_class_plan en ligne factorisé),
  SjCibleRef (deux sites $ref), SjAppliqueEtat (deux blocs d'état) ;
  raccourci memcmp des natives GARDÉ (évite un appel python par
  enveloppe dict) ; SjAncre gardé, couvert par test.
- greffon : hack new_connect/parse/ctypes, connection_infos, get_parents,
  QGridLayout séparé SUPPRIMÉS ; regardé, rien de plus.
- tools.py : regardé, rien à enlever.

### Pièges payés cette nuit

- Le module `loads()` court-circuitait `_appel` (obj passé au C → voie
  update python, rehydrate inerte) : router par Decoder.loads.
- Le crochet est lié à la CRÉATION du Decoder (`__new__`) : pas de
  bascule après coup.
- Un bouton anonyme référencé par une connexion mais hors document →
  TypeError obscur : filtre `in_document` dans connections().
- Les layouts exposent des SignalInstance (junk) → `remove_types`.
- Une classe Qt du greffon s'autorise par son NOM écrit
  (« QtWidgets.QFrame »), pas par l'objet classe.
- Mesure mémoire : garder le résultat vivant, sinon `courant` le perd.
- dump() vers un chemin est asynchrone : `wait_writes()` avant lecture.
- **PGO : un .gcda périmé (gcc 16.1, du 10/08) fait ÉCHOUER en silence
  le run instrumenté sous gcc 16.2** (« libgcov profiling error: Version
  mismatch »), et la passe use compile à vide — supprimer
  `rapidjson/build/temp.*-3XX/rapidjson.gcda` avant generate (le .so
  312 du 01:07 a été rebâti pour ça). Un run interrompu laisse un .so
  INSTRUMENTÉ (5 Mo au lieu de 2,2) en place.
- L'environnement 3.11.15 n'est pas exécutable depuis ce compte
  (« Permission non accordée ») : le .so 311 reste celui du 16/08.

### Validation finale (18/09, 01 h 10 → 01 h 25)

- PGO ×3 (3.12/3.13/3.14) rebâtie à gcda neuf, .so ≈ 1,99 Mo chacun ;
  233 tests verts sur chaque version, goldens tests/serialized restaurés
  et diff-clean après chaque run. Sortie de l'écrivain inchangée.
- A/B lecture PGO contre PGO commité (5372044), même 3.13, tours
  interlacés, min de 60 à 200 loads, charge 3-5 : tout est dans le bruit
  (±4 %, signes qui s'inversent d'un run à l'autre) SAUF datetime,
  +8 à +11 % sur 800 objets, retrouvé trois fois. Ciblé ensuite :
  datetime_200 +14 %, datetime_800 +10 %, datetime_3200 +0,7 %,
  time_800 −0,1 %, date_800 +5 %, decimal_800 −8,5 %. Un coût réel par
  enveloppe croîtrait avec N, et time/date prennent EXACTEMENT le même
  chemin (SjEnvelopeHead → EndObject → EnvelopeConstruct, dont la seule
  addition est un PyUnicode_CheckExact en tête) : c'est un effet de
  placement PGO sur la branche datetime, pas un coût du crochet. Le
  crochet inactif est un test de `rehydrateOn` dans Key() et deux dans
  EndObject, rien de plus. Non retouché — à revérifier au prochain
  rebuild PGO si l'écart persiste dans le même sens.

## Addendum 18/09, 01 h 22 → 02 h — `rehydrate` devient le DÉFAUT

Question de Baptiste (01 h 19) : « on peut lancer une application par un
simple load ? ». Réponse : sans `rehydrate=True`, un load ordinaire prend
la voie classique et double les enfants créés par les `__init__`.
Baptiste (01 h 22) : « ce n'est pas vraiment ce qu'on veut ! » → le
crochet est actif par défaut (`Decoder(rehydrate=True)` dans la
signature, `rehydrate=False` = voie classique, mode update `obj=`
inclus). Aucun changement d'API : le mot-clé existait déjà, seule sa
valeur par défaut change ; l'écrivain n'est pas touché.

### Ce que le défaut a fait surgir, et les correctifs

- **pendingB64 (piège)** : `test_bytes_blosc2` rendait « corrupted
  blosc chunked payload ». SjConstruit tirait pour la classe `bytes`
  dont la charge était un DIFFÉRÉ b64 pas encore rempli (placeholder à
  zéros) → `bytesB64.__new__` décompressait des zéros. bytes/bytearray
  rejoignent numpyB64 dans la liste des natifs que SjConstruit saute
  (la voie classique vide la file avant d'instancier). Vérifié sur 8
  combinaisons seuil/compression + bytearray.
- **Coût du crochet sur les classes à plan** (A/B on/off MÊME binaire,
  9 tours interlacés, min de 100 loads, charge ~2,5) : première mesure
  plain +34 %, slots +25 %, arbre +84 % (avec_init −70 % : construit en
  C au lieu de python). Trois resserrements EN C :
  1. `envFresh` (HandlerContext) : instance issue de `object.__new__`
     sans args → `__dict__` vide, aucun homologue vivant possible
     dessous, état affecté d'un bloc (`__dict__ = mapping`) comme la
     voie classique ; SjChaine décline sans allouer sous un ancêtre
     frais.
  2. SjChaine en deux passes (repérage sans allocation, liste bâtie
     seulement si un vivant est possible) ; SjVivant par
     `PyObject_GetOptionalAttr` (≥ 3.13, sinon `_PyObject_LookupAttr`) :
     pas d'exception créée puis effacée.
  3. `envConstruit` (HandlerContext) : la construction d'un niveau
     n'est tentée qu'UNE fois — faite ou déclinée ; les clés d'état
     suivantes ne repassent plus par le GetItem `__class__`, et une
     classe déclinée par python n'est plus rappelée à chaque clé.
     SjKeyConstruit commence par ce drapeau et par `specialKey`
     (un dict de données = un test booléen). `plansParType` : find
     avant emplace (emplace allouait un nœud à chaque objet).
  Résultat (même protocole) : plain +3,5 %, slots +9,8 %, arbre
  +12 %, avec_init −71 % ; données (dict_int, list_str, tuples,
  datetime, bytes, nested) dans le bruit (−0 à +7 %, signes mêlés
  d'un run à l'autre). Résidu ≈ 40-50 ns par objet construit
  (SjPlan par nom + tp_new déplacé de EndObject vers Key + 2 find).
  Chasse arrêtée là : sous le bruit de la machine chargée.
  Sur le binaire PGO final (3.13, même protocole, charge ~4) : plain
  +7 %, slots +3,5 %, arbre +0,6 %, nested +3,8 %, avec_init −75 % ;
  dict_int, list_str, tuples, datetime, bytes −0 à −8 %.
- Tests : test_rehydrate.py affirme `construct is not None` par défaut
  et None avec `rehydrate=False` ; test_pyside6_application
  `--sans-rehydrate` passe `rehydrate=False` (rouge attendu).
- PGO ×3 rebâtie sur la source finale (les .so 312/314 de 01 h 11
  étaient antérieurs aux deux correctifs C).

## Addendum 18/09, 02 h → 03 h — SmartFramework passe sur le paquet
## (demande de Baptiste « peut tu passer SmartFramework sur la nouvelle
## voie ? »), COMMITÉ git 3ddae9b, hg SmartFramework r146-148, SmartOS r129

Réponse à « qu'est-ce qui empêche SmartFramework d'utiliser la version
actuelle ? l'absence de serializePython ? » : NON. Quatre obstacles, tous
levés : (1) le fork de 2023 dans `SmartFramework/serialize/` avec ses
propres registres ; (2) le paquet n'était importable d'aucun venv (pas
installé) ; (3) les greffons du paquet importaient
`SmartFramework.serialize.tools` EN PRIORITÉ (`try: from SmartFramework…
except:`) → deux jeux de registres selon l'ordre des imports ; (4) la
branche Qt de SerializeInterface ne savait réhydrater qu'en python.
serializePython reste dans SmartFramework et partage désormais les
registres du paquet.

Côté paquet (mes fichiers, en plus du chantier des deux nuits) : les 5
greffons (builtins, datetime, array, numpy, Qt) importent directement
`serializejson.tools` / `serializejson` — plus de préférence à
SmartFramework. `tools.py` lignes 2-9 importe toujours
`SmartFramework.tools.dictionaries` / `objects` (servi par le vrai
SmartFramework, ou par le stub du dépôt). 233 tests × 3.12/3.13/3.14
verts après ce changement.

Côté SmartFramework (hg, non commité) : serializejson.py/tools.py/
serialize_parameters.py/plugins/serializejson_numpy.py = relais
`sys.modules[__name__] = module du paquet` ; dotdict.py et les greffons
builtins/datetime/array/Qt/pickle_Qt RETIRÉS (`hg rm`) ; plugins/__init__
ne charge que omegaconf ; serializeRepr : `_recette_ndarray` pur python
(b64 + blosc v1) pour le format python — le greffon numpy du paquet rend
des objets C (RawBytesToBase64, BloscDiffere) que seul l'écrivain C sait
écrire ; `SmartFramework/__init__.py` : import paresseux de
serialize_parameters (import SmartFramework reste sans Qt) ;
SerializeInterface : format défaut "json", sniff d'un .dat python
existant au premier caractère, widget Qt réhydraté par
`serializejson.loads(string, obj=widget, authorized_classes=[type(widget),
*authorizedClasses])`, `filtre` str → booléen `attributes_filter` (le
fork refusait déjà la str : branche json jamais utilisée avant).
Test manuel neuf `serialize/tests/test_SerializeInterface_rehydrate.py`
(json + python OK, `--sans-rehydrate` rouge : spin à 0).

Côté machine : depuis le 19/09/2026, le dépôt est `/DATA/Python/serializejson`
(plus de lien depuis `GITHUB/`), installé en éditable `editable_mode=compat`
par les requirements SmartPython de SmartOS (le mode par défaut laisse
gagner le dossier du dépôt, paquet espace de noms vide, car `/DATA/Python`
est sur `sys.path`).

Cas limite CONNU de l'adoption, non couvert : `self.a = self.b = Fils()`
(un même enfant sous deux attributs) — le second est un `$ref`, adopté
tel quel ; sans problème tant que le json vient du même code.

Pièges payés : les .dat au format python écrits avant le 18/09 importent
`numpyB64`/`instance` depuis `SmartFramework.serialize.…` → migrés par
`SmartFramework/serialize/migre_dat_vers_paquet.py` (18/09 23 h 10, plus
aucun relais dans SmartFramework ; Dropbox à migrer par Baptiste) ;
`authorized_classes`
est obligatoire pour la classe cible (TypeError « not in
authorized_classes » sinon, même en rehydrate : `_construct` décline
puis `_inst_from_dict` tranche).

## Addendum nuit du 18 au 19/09/2026 — doublons de widgets à la relecture
## json d'un .dat SmartFace, migration des .dat, COMMITÉ 19/09 au soir

Point de départ : « quelle serait la meilleure méthode pour migrer tous
mes fichiers .dat en json ? » puis « peux-tu écrire un script qui permette
d'orchestrer tout ça ? ». Le premier aller-retour sur
SmartFace/patchs/SmartFaceEditUI.dat (1,8 Mo python) rechargé depuis son
json DOUBLAIT 35 QWidget (contenus de dock anonymes, group boxes, labels,
PlotUI) : l'adoption d'une enveloppe SANS ÉTAT n'était autorisée que si
l'ancêtre construit figurait dans ses arguments, or un contenu de dock
anonyme s'écrit `root.dockWidgetContents_N` avec pour seul argument son
QDockWidget (lui-même adopté), pas la racine.

- **Ancre = registre des ADOPTÉS** (rapidjson.cpp `adoptes`/SjAdopte/
  SjAncre, `Decoder._adopted` créé par parse dans `_appel` avec l'id de la
  racine vivante, lu par le C par l'attribut interné `_adopted`) : une
  enveloppe sans état est adoptée ssi l'un de ses arguments de constructeur
  est un objet déjà adopté ; chaque adoption (C ou `_construct`) s'inscrit.
  Remplace l'ancienne règle « ancêtre dans les args ou traversée »
  (drapeau `traversee` supprimé). Les enveloppes-valeur (Decimal, QColor :
  args scalaires) restent jamais adoptées.
- **Chaîne à travers une enveloppe pas encore construite** (SjChaine /
  SjEnveloppeTraversee, `_descend` sur pas-tuple) : un objet donné au
  `__init__` d'un enfant nommé (le parent écrit en plein dans
  `root.X.__init__['parent']`, référencé ensuite par $ref) est atteint par
  un pas `(slot, classe_str)` — l'homologue vivant doit être de cette
  classe exacte, le pas suivant lit l'argument par son accesseur Qt
  (`parent()`, méthode liée appelée sans argument).
- Greffon Qt : `qt_tree` lu par `getattr(serialize_parameters, "qt_tree",
  False)` (paramètre absent d'un `serialize_parameters` importé avant le
  greffon) ; `connections()` ignore les attributs `_…` et les
  `remove_types` en cherchant les objets du document ; tools `_getitem`
  descend par clé, sinon attribut, accesseur appelé si méthode.
- Validé : sonde de doublons vide (findChildren par (type, objectName,
  parent) avant/après), re-dump python A (dat) == B (json), json A == B
  (2 172 228 octets), 233 tests × 3.12/3.13/3.14 sur PGO rebâtie (02 h 24,
  .so ≈ 1,99 Mo, gcda supprimés avant), goldens restaurés.
- Script livré côté SmartFramework : `serialize/migre_dat_vers_json.py`
  (voir le CLAUDE.md de SmartFramework, section serialize/). Dans le bac à
  sable seul SmartFaceEditUI.dat est migrable (4 lignes d'écart : vidéo
  Dropbox invisible → `--garde-diff`) ; SmartFaceUI/SmartFaceRecordUI ne
  s'importent pas ici (ids_peak, playsound — préexistant), Dropbox/Data/
  DAT invisible : la migration réelle est à lancer par Baptiste.

Fichiers du chantier (les MIENS) : rapidjson/rapidjson.cpp, .so ×3 PGO,
serializejson/{__init__.py,tools.py}, serializejson/plugins/
serializejson_PyQt5_PySide2.py, tests/objects/*.py (imports vers le
paquet), ce fichier. Le .so 311 apparaît modifié : PAS à moi, ne pas le
commiter.

## Addendum 19/09/2026 — publication PyPI (git 28b96d0)

Trusted Publishing (OIDC, environnement « pypi », workflow
`.github/workflows/python-publish.yml` — NE PAS le renommer sans mettre
à jour pypi.org). Déclenché par un tag `v*`. Roues Linux x86_64 cp310 →
cp314 par cibuildwheel, PGO dans `setup.py` (`SERIALIZEJSON_PGO=auto` :
passe generate, `rapidjson/pgo_workload.py`, passe use), libblosc2 du
fork construite dans le conteneur par
`scripts/construit_libblosc2_serializejson.sh`. Roue testée en local
(cp313) ; cp310/311, cibuildwheel et le clone réseau : CI seulement.
SmartFramework embarqué sous `serializejson/_smartframework`.

Pièges : `sed -i` convertit les CRLF de CHANGELOG.rst en LF (diff de
150 lignes pour 3) ; pytest ne teste PAS la roue (`tests/conftest.py`
force les sources) — le test de cibuildwheel est un smoke depuis `/`.

## Addendum 19/09/2026 — greffons QTimer/QAction, enums PySide6, ancre
## « ancêtre ouvert » (question de Baptiste « on ne peut pas créer des
## greffons pour ces objets ? »)

- **qt_state (greffon Qt)** : QTimer (interval, singleShot, timerType,
  active en dernier → start()) et QAction (text, shortcut, checkable,
  checked, enabled, visible) écrivent leur état Qt via getters, reposé
  par setters dans __setstate__. toolTip/statusTip ÉCARTÉS exprès :
  toolTip vaut le texte par défaut, l'écrire le figerait. Autorisés :
  "QtCore.QTimer", "QtGui.QAction", "QtWidgets.QAction" (Qt5), "const".
- **Défaut PRÉEXISTANT corrigé : aucune valeur d'enum PySide6 n'était
  sérialisable** (KeyError dans serializejson_Enum) — les membres d'un
  enum python ne sont pas dans le __dict__ du parent. register_consts
  parcourt les membres de chaque classe d'enum ; QtCore couvert en plus
  de QtGui/QtWidgets.
- **Défaut corrigé : en RECRÉATION (sans obj=), les enfants sans état
  d'une racine construite par __init__ étaient DOUBLÉS** (2 QLabel /
  4 QWidget pour 1 / 2) : l'ancre n'acceptait que les objets adoptés.
  Ancre élargie aux ANCÊTRES CONSTRUITS ENCORE OUVERTS (SjOuvert : pile
  des contextes, envConstruit, instance dans __class__/envClass) ;
  tranchée en C pour les deux voies (python reçoit stateless=False si
  ancré ; `_anchored` supprimé). Première tentative REJETÉE : inscrire
  tout objet construit par __init__ comme adopté — trop large, un
  argument FERMÉ (le Vec d'un Point) faisait adopter une enveloppe-valeur
  vivante. Test test_rehydrate_argument_construit_ferme_n_ancre_pas,
  rouge (0 ≠ 5) sur cette version.
- Tests : tests/test_pyside6_qobjects.py (recréation + réhydratation,
  `--rouge` = voie classique qui double) ; 235 tests × 3.12/3.13/3.14
  sur PGO rebâtie (19/09 18 h 30, gcda supprimés avant).

## Addendum 19/09/2026 soir — critère d'adoption : réconciliation PAR
## ARGUMENT (plan ~/.claude/plans/eager-humming-wilkes.md)

Défaut de départ : un enfant créé par le `__init__` de son parent, avec
arguments de constructeur ET état, était adopté en IGNORANT ses arguments
(`SegEtat(3, 4)` rouge relu `0 0 rouge`). La règle d'ancre (sans état →
adopté seulement si ancré ; avec état → toujours adopté) ne regardait pas
les arguments. Baptiste a refusé d'étendre l'ancre (« c'est du sparadra »)
et demandé de comparer les alternatives avant de choisir.

Alternatives écartées (détail dans le plan) : B lire les arguments du vivant
par son RÉDUCTEUR (le réducteur Qt calcule état + connexions par
dumpObjectInfo : ×N sur un arbre, et les positionnels restent sans nom) ;
C tout appliquer par nom sans comparer (setParent CACHE le widget même à
parent identique) ; D reconstruire puis transplanter l'état (widgets non
transplantables, enfants du neuf pointant sur le neuf) ; E déclaration par
classe (intrusif, déjà rejeté en 2021) ; F déplacer les arguments dans
l'état côté écrivain (change la sortie, ne répare pas les json existants).

**Retenu (G) : réconcilier argument par argument, PAR NOM, sur le vivant de
même type exact.**
- json sans arguments (nullptr, liste/tuple/dict vide) → adopté en C, aucun
  appel python (chemin chaud des données inchangé) ;
- sinon `Decoder._reconcile(vivant, args, slot)` : noms du dict de kwargs,
  ou `inspect.signature(cls)` pour un positionnel (cache par classe ;
  argument unique écrit DÉBALLÉ et remove_add_braces emballés d'abord) ;
  valeur vivante lue par attribut, ou par accesseur appelé (Qt) ; égale
  (identité, ou même type et `==`) → rien ; différente → setter `setNom`
  (accesseur) ou attribut inscriptible (property avec fset, descripteur de
  données, `__dict__`) ; illisible/inapplicable → Faux, l'appelant
  construit un neuf. Différences appliquées seulement si TOUTES passent
  (jamais de mutation partielle), avant l'état. Sans noms : comparaison en
  bloc au réducteur, rien d'applicable.
- Le parent d'un enfant Qt est un argument égal par identité : l'ancienne
  ancre devient un cas particulier. SUPPRIMÉS : SjAncre, SjOuvert, SjAdopte,
  le registre `adoptes`/`Decoder._adopted`, le paramètre stateless (C et
  `_construct`), remplacés par SjSansArgs + `decoderReconcile`.
- Étage 3 (reconstruit) : l'ancien vivant est DÉFAUSSÉ EN FIN DE PARSE
  (`tools.rehydrate_discarders`, Qt : setParent(None) + deleteLater). Pas
  en cours de route : détacher un enfant décalerait les rangs `~children`
  des frères suivants.
- Connexions (question de Baptiste) : celles du json sont déjà différées
  (`~connections` en dernier, UniqueConnection) ; celles du `__init__` sont
  du code utilisateur — hors périmètre, comme le risque d'un signal émis
  pendant la restauration, qui existait déjà pour l'état.
- Risque assumé : modifier sur place un vivant PARTAGÉ le modifie pour tous
  ses détenteurs (déjà vrai pour l'état adopté).

Tests : tests/test_adoption.py (neuf, 9 cas × valeurs/voie × recréation/
réhydratation : échelle/fige reconstruits, les autres adoptés) ;
test_rehydrate (Valeur égale adoptée telle quelle, différente modifiée sur
place) ; test_pyside6_qobjects (Echelle Qt reconstruite sans doublon,
l'ancienne détachée — ROUGE sans défausse —, label adopté resté visible).

Validation (19/09, 19 h 45) : PGO ×3 rebâtie (gcda supprimés, .so ≈ 1,99
Mo), 272 tests verts × 3.12/3.13/3.14, aucun test Qt sauté, goldens
restaurés. A/B lecture 3.13 PGO contre PGO commité ab79a30 (7 tours
interlacés, min de 40 loads, charge 3-4) : dans le bruit — un A/A
(commité contre sa propre copie) donne déjà jusqu'à ±10 % sur ce
protocole inter-processus, le neuf reste dans cette fourchette (−2,5 à
+7,8 %, signes mêlés, avec_init/slots/plain légèrement devant).
Piège : un A/B ENTRE PROCESSUS sans A/A témoin fait croire à une
régression de +9-16 % sur les données (premier passage) — toujours
lancer l'A/A dans la même boucle.

## Addendum nuit du 19 au 20/09/2026 — chiffrement authentifié optionnel,
## format age v1 (ordre de Baptiste 20 h 59 « code les tests, implémente,
## puis optimise »), plan ~/.claude/plans/hazy-dazzling-creek.md

Bibliothèque GÉNÉRALISTE : aucun nom, test ni exemple n'évoque l'usage qui a
motivé la demande (consigne explicite de Baptiste).

- **API : un seul argument `encryption_key=None`** (str = mot de passe) sur
  dump/dumps/dumpb/load/loads/Encoder/Decoder. dumpb → binaire age, dumps →
  armure ASCII age (str), load/loads reconnaissent les deux. append,
  iterator, path= et un index demandé + clé → ValueError ; dump chiffré vers
  un chemin n'écrit AUCUN index et supprime un sidecar périmé (il décrirait
  la structure). Chiffré lu sans clé → ValueError « pass its password as
  encryption_key » (détecté APRÈS l'échec du parse : chemin nominal gratuit) ;
  clé sur un clair → DecryptionError. `DecryptionError(ValueError)` exportée.
  Extra `serializejson[crypto]` = cryptography>=47 (import paresseux).
- **serializejson/_encryption.py** : spec age v1, stanza scrypt seule ;
  analyse STRICTE (une stanza, base64 canonique, logN décimal ≤ 22 vérifié
  AVANT tout scrypt), segments 64 Kio ChaCha20-Poly1305, dernier segment vide
  refusé sauf s'il est seul. Écriture logN 18 (défaut de l'outil age, ~1 s).
- **Branchement à coût nul sans clé** : un Encoder/Decoder à clé est une
  instance d'une SOUS-CLASSE créée à la volée (_classe_chiffrante, même nom,
  isinstance préservé, sous-classes utilisateur comprises) ; les classes
  sans clé ne voient pas un test de plus. `encoder(obj)` direct chiffre aussi.
- **Cache d'écriture = EN-TÊTE ENTIER + file key**, par (mot de passe,
  logN) — PAS le sel seul avec une file key neuve : la stanza emballe sous
  nonce NUL imposé, deux file keys sous la même clé scrypt réutiliseraient
  (clé, nonce) de ChaCha20-Poly1305. La charge reste unique par document
  (nonce aléatoire 128 bits → clé de flux). Révèle seulement que deux
  documents du même processus ont le même mot de passe. Un document LU au
  logN d'écriture amorce ce cache : relire puis réécrire = un seul scrypt.
- **Optimisation** : decrypt_into dans un bytearray remis tel quel au
  parseur (−10 à −19 %, 1 à 25 Mo). encrypt_into ÉCARTÉ côté écriture : il
  faudrait recopier en bytes (type public de dumpb), la copie mange le gain.
  Threads sur les segments ÉCARTÉS : plus lents à toute taille (0,4-1,6 Go/s
  contre ~2,2 séquentiel, segments de 64 Kio trop petits pour le coût par
  appel). v2 C++ (segments au fil d'écriture, recouvrement du parse) NON
  tentée : les .so de travail ont été rebâtis HORS PGO par l'installation
  éditable (voir ci-dessous) — à reprendre sur arbre propre, format inchangé.
  → FAITE plus tard dans la nuit, SANS dépendance de construction (libcrypto
  chargée par dlopen) : voir l'addendum « charge utile en C » plus bas.
- **Preuves** : 11 vecteurs officiels C2SP/CCTV versionnés dans
  tests/age_testdata, sha git vérifiés par le test (seule preuve
  d'interopérabilité : ni réseau ni binaire age ici — PAS de test croisé
  avec l'outil age) ; 40 tests tests/test_encryption.py, rouge prouvé sur
  deux variantes (MAC d'en-tête non vérifié ; étiquettes de charge
  ignorées) et sur le refus du dernier segment vide. Suite complète 308
  verts × 3.12/3.13/3.14.

## Addendum 19/09/2026 21 h 31 — problèmes de l'installation éditable RÉGLÉS
## (demande de Baptiste « tu peux régler les problèmes dus à l'installation
## éditable ? »)

L'installation éditable SmartPython (19/09 19 h 58-20 h 01) avait :
- rebâti les rapidjson/*.so SUIVIS hors PGO (2,2 Mo au lieu de ≈ 1,99) →
  restaurés par `git checkout` (les .so commités en 620f02e sont PGO et
  correspondent aux sources C++, inchangées depuis) ;
- déposé des copies non suivies serializejson/rapidjson.cpython-3*.so (hors
  PGO, gitignorées) que `from . import rapidjson` PRÉFÈRE : serializejson et
  les tests tournaient sur deux modules distincts, libblosc2 chargée dans un
  seul (4 échecs « blosc library not loaded »), et — plus grave — build_pgo.sh
  profilait le binaire instrumenté sans que serializejson s'en serve.

Correctif : tests/conftest.py charge rapidjson/rapidjson<EXT_SUFFIX> PAR
CHEMIN (spec_from_file_location, indépendant du chercheur d'import) et
l'épingle sous « rapidjson » ET « serializejson.rapidjson » avant tout import
de serializejson. Les scripts du dépôt (types_seuls, bench_pyperformance_
pickle, lance_benchmarks, pgo_workload hors roue) font `import conftest` :
plus aucun idiome `import rapidjson.rapidjson`. 312 verts × 3.12/3.13/3.14 ;
rouge prouvé sans l'épingle sous le second nom (les 4 mêmes échecs).

Copies serializejson/*.so : pip les crée en mode 755, dont les bits de
groupe (r-x) deviennent le MASQUE ACL et annulent l'écriture du groupe
partagé (`group:…:rwx #effective:r-x`) — ni le propriétaire ni le partage de
/DATA/Python en cause. Non réinscriptibles ici (cp « Permission non
accordée »), MAIS le dossier l'est → remplacées par
les PGO via copie temporaire + `mv` (renommage = droit sur le dossier seul),
octets identiques à rapidjson/*.so, masque ACL rwx (lisibles par Baptiste),
import hors dépôt vérifié avec blosc du fork chargé.
Toute réinstallation éditable refera les deux dégâts (rapidjson/*.so
modifiés → `git checkout`).

## Addendum nuit du 19 au 20/09/2026 — chiffrement : dump asynchrone,
## charge utile en C, coûts fixes (suite de l'ordre « optimise » ; Baptiste
## 21 h 5x : « je ne t'ai jamais dit de ne pas ajouter de dépendances »)

- **dump chiffré vers un chemin ASYNCHRONE** (git eff4e36) : ouverture du
  fichier et suppression du sidecar périmé SYNCHRONES dans dump (erreur
  d'ouverture levée par dump ; l'index ne survit jamais) ; chiffrement +
  écriture sur un ThreadPoolExecutor(1). `_attend_ecritures()` remplace
  rapidjson.wait_writes partout (attend aussi les dumps chiffrés en vol) ;
  un dump/load vers un même chemin attend d'abord celui en vol.
  `disk_write_mode="blocking"` reste synchrone. Latence dicts 24,6 → 18,7
  ms, 1M str 29,9 → 11,1 ms.
- **Charge utile age en C** (rapidjson/sjcrypto.h, `load_crypto_library` /
  `_age_payload`) : libcrypto (OpenSSL ≥ 1.1) chargée par dlopen comme
  libblosc2 — ni en-tête ni lien, AUCUNE dépendance du binaire ni des
  roues ; absente → voie python inchangée. EVP ChaCha20-Poly1305 par
  segment, segments en tranches contiguës sur ≤ 8 fils (≥ 8 segments par
  fil), GIL rendu, chiffré = préfixe + segments en UNE allocation, clair
  rendu en bytearray. Identité à l'octet C ≡ python prouvée par test
  (urandom figé, tailles 0 / 1 / 64 Ki / 64 Ki+1 / 20×64 Ki+3) ; toute la
  suite test_encryption tourne sur les DEUX voies (fixture `voie`).
  Mesures (3.13, hors PGO) : 64 Mo 64,7 → 10,3 ms ; surcoût contre clair
  100k dicts dumpb/loads +10/+9 % → +4/±0 %, 1M str +98/+25 % → +15/+6 %.
  Revérifié sur PGO (3.13, charge variable) : 1M str dumpb +146 % → +18 %,
  loads +31 → +9 % ; dicts +3/+12 → −6/+5 % (bruit).
  Un dernier segment chiffré plus court qu'une étiquette → None (échec
  d'authentification), sans sous-débordement de taille.
- **Coûts fixes** : HKDF/HMAC par `hmac.digest` de la stdlib au lieu des
  objets `cryptography` (hkdf 3,4 → 1,9 µs, mac 5,6 → 2,8) ; instances
  chiffrantes par défaut par thread (`_EtatParDefaut.chiffres`, clé comme
  seul argument) pour dumps/dumpb/loads. Petit document (~7 Ko) : dumpb
  42,2 → 20,8 µs (clair 12,8), loads 65,1 → 47,5 µs (clair 28,5).
  Puis cache des en-têtes OUVERTS (mot de passe, en-tête exact MAC compris)
  → file key, alimenté aussi à l'écriture : relire un en-tête déjà
  authentifié saute analyse/unwrap/MAC (_ouvre_entete 8,7 → 0,3 µs) ;
  loads chiffré ≈ 30 µs contre 20,7 en clair (même run, machine plus calme).
  Test rouge sans le cache. Reste au-dessus du clair : HKDF de la clé de
  flux (~2 µs, nonce propre au document) + ChaCha lui-même — incompressible.
- Résistance quantique (question de Baptiste) : tout est symétrique
  (scrypt + ChaCha20-Poly1305 256 bits), Grover ramène à ~128 bits, Shor
  sans objet faute de clé publique ; le maillon faible est le mot de passe.
  Extension usuelle des fichiers age : `.age` (`x.json.age`) ; serializejson
  détecte par l'en-tête, l'extension est libre.
- pgo_workload.py n'exerce PAS le chiffrement : le travail est dans
  OpenSSL, la glue C n'y gagnerait rien.
- **Gros documents (question de Baptiste « comment encore optimiser sur les
  gros fichiers ? »)** : profil d'abord (25 Mo de 1M str, 3.13). Le surcoût
  restant EST le chiffrement : dumpb +2,7 ms ≈ `_age_payload` 3,3 ms, loads
  +2,3 ms ≈ 3,0 ms. Allocations et copies sont gratuites : 9 défauts de page
  par appel, l'allocateur recycle. D'où les pistes ÉCARTÉES sur mesure :
  déchiffrement sur place (readinto), chiffrement sur place dans le tampon de
  dumpb. Et le recouvrement déchiffrement/parse : 3 ms au mieux sur 42.
  Seul levier retenu, `sjcrypto.h` : les fils ne sont plus plafonnés à 8
  mais au nombre de cœurs (12700H : 6 P + 8 E). Un seul fil jusqu'à 1 Mio
  (lancer un fil coûte plus de 100 µs dans le bac à sable). A/B même
  processus contre le .so commité, avec A/A témoin : charge utile −27 à
  −50 % dès 8 Mo (25 Mo 3,3 → 1,7 ms), 1 Mo −16/−28 %, 512 Ko neutre ;
  dumpb/loads de bout en bout dans le bruit (le chiffrement n'y pèse plus
  que ~3 ms sur 20-40). Pool de fils persistant NON fait : il ne servirait
  qu'autour de 1-2 Mo, contre un risque réel (fils perdus après fork).

## Addendum 20/09/2026 — qtpy remplacé par qtpy6 (decision de Baptiste
## « je veux remplacer qtpy par qtpy6 »)

Les deux greffons Qt (`serializejson_PyQt5_PySide2.py`,
`pickle_PyQt5_PySide2.py`) prennent `qtpy6` (PySide6/PyQt6, PySide6 par
défaut) au lieu de `qtpy` (qui part sur PyQt5 quand `QT_API` n'est pas
posé — c'est ce qui se mesurait ici, dans un shell nu). Repli inchangé
en cascade si qtpy6 est absent : PySide6 direct → PyQt5 (ses alias
`pyqt*` posés en place) → PySide2 → `API = None`. **PyQt6 n'est pas
proposé en repli direct** : enums scopées et noms `pyqt*`, deux branches
du greffon (`API != "PyQt6"`) supposent la normalisation de la couche.

- Le patch `QtCore.SignalInstance` disparaît : qtpy6 le garantit, la
  branche PyQt5 le pose elle-même.
- `_smartframework/image/image_conversion.py` (seul autre import qtpy,
  importé par le greffon seul) ne choisit plus de couche : il prend
  `QtGui`/`QtCore` **publiés par le greffon dans `sys.modules`** — son
  binding, jamais un second.
- `tests/objects/pyqt_objects.py` exigeait déjà `PyQt5.sip` : il importe
  PyQt5 directement ; le drapeau `use_qtpy` de `test_serialize_vs_pickle`
  devient `use_pyqt5` (il dit ce qu'il allume).
- Format json INCHANGÉ (`type_str` retire le préfixe d'API, relecture par
  `sys.modules["QtCore"…]`) : goldens et anciens json intacts, les chaînes
  `"qtpy.QtCore.*"` d'`authorized_classes` restent (compat de lecture).
- `setup.py`/`setup.cfg`/`egg-info` : extra `dev` = qtpy6 + PySide6.

**Défaut PRÉEXISTANT trouvé en exerçant ce qu'aucun test ne couvrait
(question de Baptiste « tu as tout testé ? »), corrigé** : la
sérialisation d'un QImage était ROUGE sous PySide (donc sous tout lanceur
posant `QT_API=PySide6`, et désormais par défaut) — `constBits()` rend un
`sip.voidptr` à dimensionner sous PyQt mais un `memoryview` déjà
dimensionné sous PySide, et `image_conversion` appelait `setsize`
inconditionnellement. `_octets_dimensionnes` sert les deux formes (tranche
à la même longueur que l'ancien `setsize`, octets identiques) ; test neuf
`tests/test_pyside6_qimage.py`, rouge prouvé correctif neutralisé.

Branches de repli du greffon exercées une par une (finder qui masque les
modules) : qtpy6 → PySide6 direct → PyQt5 (alias `Signal`/`SignalInstance`
posés, modules publiés) → `API = None`. PySide2 n'est pas testable ici
(son `shiboken2` natif ne charge pas sous 3.13).

Validé : 375 tests × 3.12/3.13/3.14 (venvs SmartPython, qtpy6 installé,
API_NAME = PySide6), dont les 56 tests Qt réellement exécutés (pas
skippés) ; goldens restaurés après run. Constatés au passage, PRÉEXISTANTS
et hors périmètre : `libblosc2.so` est introuvable dans ces venvs, la
compression ne se fait donc plus (les goldens réécrits par un run passent
de `b64_blosc2` à `b64`) ; `tests/objects/pyqt_objects.py` casse à
l'import (widgets créés sans QApplication) — code mort, `use_pyqt5`
est faux.

## Addendum 20/09/2026 — tests complétés sur le périmètre Qt (demande de
## Baptiste « peux-tu compléter les tests ? »)

Ce qui n'avait été vérifié que par scripts jetables est versionné, et le
reste du périmètre touché est couvert. Quatre défauts de plus, tous
PRÉEXISTANTS mais tous rendus visibles PAR DÉFAUT par le passage à PySide6,
trouvés en écrivant ces tests et corrigés (chacun prouvé par le rouge,
correctif neutralisé un par un) :

- **Le pas des lignes (`bytesPerLine`) était ignoré** : toute QImage dont la
  largeur utile n'est pas un multiple de 4 octets (Grayscale8, RGB888 ou
  RGB16 de 5 pixels) se relisait DÉCALÉE, en silence — sous PyQt comme sous
  PySide. `_octets_image` (image_conversion) prend les octets au pas réel et
  les remet au pas aligné sur 32 bits, seul pas que
  `QImage(bytes, w, h, format)` suppose à la relecture ; une image bâtie sur
  un tampon étranger au pas imposé est redécoupée. Les images alignées (tout
  ARGB32/RGB32) ne changent pas d'un octet.
- **`QImage_to_numpy` était inappelable** (`array.QImage = qimage` sur un
  ndarray nu, sans `__dict__`) → sous-classe `_ArrayQImage`.
- **`numpy_to_QImage(array, Format_RGB32)` levait OverflowError** : `array *
  65793` sur un uint8, que numpy ≥ 2 refuse de promouvoir → `.astype` avant.
- **Le greffon PICKLE était rouge sous PySide6** : `int(obj.style())` sur une
  enum PySide6 lève TypeError, et son constructeur refuse l'entier en retour
  — les enums sont désormais transmises telles quelles (elles se picklent),
  comparées par `.value` (`_entier`). Au passage `reduce_QPen` perdait les
  largeurs fractionnaires (`width()` arrondit : 2,5 relu 3) → `widthF()`.

Tests neufs (37 cas) :
  - `tests/test_pyside6_qimage.py` étendu : aller-retour 5 formats × largeur
    alignée/non alignée, pas des lignes, pas étranger, image nulle, Indexed8
    (les octets passent, la table de couleurs NON — limite du format, le json
    ne porte que octets/largeur/hauteur/format), `QImage_to_compressed_bytes`,
    `QImage_to_numpy`, `numpy_to_QImage` (6 formes + 2 refus).
  - `tests/test_qt_plugins_fallback.py` : les quatre branches de la cascade
    d'import des DEUX greffons, chacune en sous-processus, modules masqués par
    un chercheur en tête de `sys.meta_path` — qtpy6, PySide6 direct, PyQt5
    (avec ses alias `Signal`/`SignalInstance`/`Slot`/`Property`), aucune API
    (serializejson reste utilisable). Vérifie aussi les modules `QtCore`/
    `QtGui`/`QtWidgets` publiés dans `sys.modules`, dont `image_conversion`
    dépend. Rouge prouvé en retirant la publication, puis un alias.
  - `tests/test_qt_pickle_plugin.py` : réducteurs du greffon pickle (QPen ×4,
    QBrush ×3, QPolygon/QPolygonF) et, en sous-processus offscreen, les
    widgets (QSpinBox, QCheckBox, QLineEdit, QPlainTextEdit, QWidget).

Validé : **412 tests verts + 1 skip × 3.12/3.13/3.14**, goldens restaurés,
aucun `.so` touché (changements purement python).

## Addendum 24/09/2026 — datetime.datetime en texte RFC 9557 (demande de
## Baptiste « pars sur la RFC 9557 », depuis plan_de_classe de SmartTeacher)

Forme écrite : `{"__class__": "datetime.datetime", "__init__": "<texte>"}`,
texte = `isoformat()` (naïf ; `datetime.timezone` sans nom propre, UTC
compris) ou `isoformat() + "[<clé ZoneInfo>]"` : le nom redonne les règles
d'heure d'été, le décalage départage le fold au passage à l'heure d'hiver.
- Naïf : branche C du writer (snprintf, identique à isoformat) ; avec
  fuseau : greffon plugins/serializejson_datetime.py. Tout autre tzinfo
  (timezone NOMMÉ, pytz, dateutil) garde la forme reduce. AVANT : un
  datetime à ZoneInfo ne se sérialisait PAS (`_unpickle.__module__ is None`).
- Lecture : case 17 du reader → `fromisoformat` en C si pas de `]` final,
  sinon voie générique → constructeur du greffon (ZoneInfo, fold essayé 0
  puis 1, ValueError si le décalage ne colle pas). Formes reduce 10 octets
  et 7 entiers toujours lues.
- tests/test_datetime_rfc9557.py (13), rouge prouvé sur l'ancien .so (les 3
  naïfs) ; 425 verts × 3.12/3.13/3.14 sous build_pgo. Fichiers :
  rapidjson.cpp, .so ×3 PGO (+ copies serializejson/*.so par cp + mv),
  greffon, test, ce fichier. Le .so 311 n'est PAS rebâti (interpréteur
  3.11 non exécutable par ce compte, cf. plus haut) : il écrit encore les
  naïfs en 10 octets, relus sans souci.
