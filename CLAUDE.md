# Passation — nuit du 05 au 06/08/2026, close le 06 à 10 h

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
