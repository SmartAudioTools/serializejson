# Passation — nuit du 05 au 06/08/2026

Deux missions successives cette nuit, dictées par Baptiste :
« chaque type sous ×2 de pickle » (20 h 26), puis à 00 h 59 la barre
remontée : « optimise jusqu'à 8 h, jusqu'aux performances de pickle »
(« mieux que pickle c'est bien aussi »). Récit détaillé dans
`Notes/AUDIT 2026-08-02 ... .md`, sections 17 decies → quaterdecies ;
ce fichier est le résumé opérationnel.

## État (tout commité, batterie verte à chaque commit)

- Batterie : 117 tests × 5 versions (3.10 → 3.14), goldens identiques.
- Écriture : ZÉRO rappel python par objet, toutes catégories. Têtes
  d'enveloppe fusionnées (EnvelopeHead, un bloc brut + niveau
  pré-compté), inliner scalaire dans huit boucles chaudes (None/bool/
  int64/float fini sans garde ni dispatch), cache des graphies de
  flottants par motif de bits, cache classe→nom des valeurs de type,
  sets/tuples/collections/datetime par branches natives directes.
- Lecture : décodage AU VOL des clés non-str (état 7 : le dict
  d'enveloppe EST le dict final), EnvelopeConstruct aiguillé par
  longueur de nom, caches par parse (clés exotiques, chemins $ref
  résolus), interception b64 dès 2 caractères.
- dumps/dumpb/loads réutilisent une instance PAR DÉFAUT par thread
  (~11/7 µs de construction par appel économisés ; réentrance gérée ;
  greffon enregistré entre deux appels : vu à la prochaine
  invalidation d'owner seulement — enregistrement à l'import en
  pratique).
- DÉCISION DE FORMAT (00 h-02 h) : datetime.datetime s'écrit en forme
  reduce OCTETS (10 octets b64, comme date/time) — tzinfo désormais
  transporté (avant : perdu), datetime.timezone autorisé par défaut,
  ancienne forme 7 entiers toujours lue. Le greffon python datetime a
  été SUPPRIMÉ (reduce natif). Deux bugs de toujours corrigés en
  chemin : la branche time native était morte (champ tzinfo brut lu
  sans hastzinfo), et les $ref vers l'intérieur des enveloppes de
  dicts non-str / collections plantaient (résolution décode-d'abord,
  chemins échappés — sections 17 duodecies).
- Le hack SingleLine des __init__/__new__ est SUPPRIMÉ : la règle vit
  dans le writer ; SingleLine ne sert plus qu'au repli numpy qui porte
  un number_mode par sous-arbre (réponse à la question de Baptiste).

## Le mur restant, à consigner tel quel

Format texte lisible contre opcodes binaires : sur micro-objets purs
(tuple de 2 ints ≈ 40 octets de json contre ~10 d'opcodes), plancher
×3-5 malgré zéro python et enveloppes au memcpy. Sur charges réelles,
l'écart s'efface. bytes ≥ seuil = prix de la compression zstd
(5,2 µs/512 o contre memcpy), échange octets↔µs assumé.

## Reste à faire

1. TABLE FINALE AU CALME : la charge externe (3 à 11 de load, quelqu'un
   travaillait) a interdit toute mesure absolue après 23 h. Relancer
   `rapidjson/consolide_nuit.sh` (PGO ×5 + batterie) puis
   `tests/types_seuls.py` sur machine calme, remplacer le marqueur
   TABLE_FINALE_ICI de l'audit (§17 duodecies) par la table, et
   committer audit + CLAUDE.md + binaires PGO.
2. Les binaires committés en cours de nuit sont des builds RAPIDES
   (sauf consolidations intermédiaires) : la consolidation finale les
   remplace.
3. Si des catégories restent > ×2 au calme : ce qui reste est le mur
   de format ci-dessus — consigner en exceptions chiffrées, ne pas
   repartir en chasse sans nouveau profil.

## Pièges (à ne pas repayer)

- pytest et les scripts de tests depuis la RACINE ; le cwd du Bash
  PERSISTE — un build lancé du mauvais dossier échoue en SILENCE
  (« grep -c » rend 0 pour zéro erreur COMME pour zéro build : vérifier
  la ligne « copying »). Payé plusieurs fois cette nuit.
- Ne PAS éditer les sources pendant qu'une consolidation/un build
  d'arrière-plan tourne : binaires mélangés, une PGO a écrasé un build
  de chantier en course.
- Sous charge : cibles au COMPTE D'OPÉRATIONS et A/B interlacés dans
  le MÊME processus ; jamais de ratios absolus.
- PyLong_FromString exige un tampon TERMINÉ : depuis le tampon de
  parse, copie bornée d'abord (int relu en float sinon — attrapé par
  le test des types de clés).
- matplotlib : parse_math=False sur tout texte porteur de `$`.
- Les scripts d'outillage ne vivent PAS dans /tmp (nettoyeur).
