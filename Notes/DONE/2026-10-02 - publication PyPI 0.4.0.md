# Publication PyPI 0.4.0 — préparation (02/10/2026)

## Demandes de Baptiste

- « faut-il déclarer une nouvelle version pour un déploiement sur pypi ? » — non : PyPI est à
  0.3.4, la 0.4.0 n'a jamais été publiée ni étiquetée. CHANGELOG 0.4.0 complété (rehydrate,
  Qt, datetime RFC 9557, `etat_sans_defauts`, `__setstate__` en C), commit 7439441.
- « Peux-tu mettre à jour le README, le commit, et faire tout ce qu'il faut pour que je puisse
  vraiment publier sur PyPI » (dicté).

## Livré

- **README.rst** : description technique remise à jour (extension C++ dérivée de
  python-rapidjson, c-blosc2 embarquée au lieu de python-blosc, roues Linux x86_64 3.10-3.14) ;
  « Python 3.7 » → 3.10+ ; la ligne « 2x/3x plus lent que pickle, optimisation à venir »
  remplacée par l'état mesuré (la plupart des types sous ×2, certains plus rapides — chiffres de
  la table finale de l'audit, renvoi aux figures) ; la ligne « update … ⚠ not yet well tested »
  remplacée par la réhydratation au fil du parse (défaut) ; puces neuves Qt et datetime RFC 9557.
  La section « Load one object from a big json » et la puce index, écrites par une autre
  instance le 26/09 et restées non commitées, sont gardées et partent dans ce commit.
- **MANIFEST.in** : `prune`/`exclude` explicites. Mesuré : sur cette machine, un sdist faisait
  **21 Mo** (images de banc, Notes .rtf, tests, CLAUDE.md…) parce que setuptools_scm, installé
  dans le python système, ajoute tous les fichiers suivis par git. La CI (`pipx run build
  --sdist`, environnement isolé sans setuptools_scm) n'aurait sans doute pas eu le problème,
  mais le contenu du sdist ne doit pas dépendre de l'environnement : 569 Ko après.
- **Tag v0.4.0** déplacé sur le commit final (il n'avait pas été poussé).

## Choix

- **Figures SVG non commitées** : `docs_source/images/*.svg` modifiées le 13/08 par le banc
  d'une autre instance. Le README les cite par URL absolue `raw.githubusercontent.com/…/master`,
  donc PyPI affiche toujours les figures de master au moment de la lecture : les mettre à jour
  ne demande PAS de nouvelle version. Écarté de ce commit pour ne pas publier des figures du
  13/08 (antérieures au `__setstate__` en C) sans relecture ; à régénérer par un banc complet.
- **Pas d'extra `crypto`** : le chiffrement passe par libsodium liée en statique, aucune
  dépendance à déclarer.

## Niveau de preuve

- Rendu reStructuredText du `long_description` exact (README + « History » + CHANGELOG, même
  concaténation que setup.py) : docutils 0.22, niveau avertissement, aucun message. `twine`/
  `readme_renderer` absents d'ici : non vérifié par eux.
- sdist construit depuis un clone propre (fichiers suivis seulement) : contenu listé.
- Roue construite depuis CE sdist, hors ligne (clone libsodium et libblosc2 fournis à la main,
  que la CI clone par le réseau), PGO auto (gcda produit), cp313 : installée dans un venv neuf,
  importée depuis `/`, fork blosc2 chargé, aller-retour bytes compressés + datetime ZoneInfo, et
  dumpb/loads chiffrés : **vert**.
- **Jamais exécuté** : le workflow GitHub lui-même (aucun tag n'a encore été poussé),
  cibuildwheel dans le conteneur manylinux, les clones réseau de c-blosc2 et libsodium, cp310/311.

## Premier passage de la CI (tag v0.4.0 poussé, run 37021264476) : ÉCHEC, corrigé

- Le job `sources` est passé ; `roues_linux` a échoué dès cp310 à la compilation :
  `serializejson.h:1020: '_mm_extract_epi8' was not declared` (SSE4.1, dans `sj_prefix_u8`).
  Rien n'a été publié (job de publication sauté).
- Cause : `serializejson.h` n'incluait que `<tmmintrin.h>` (SSSE3). En local, le python de
  CachyOS compile avec `-march=x86-64-v3` (CFLAGS de sysconfig, repris par setup.py), qui amenait
  l'en-tête SSE4.1 indirectement ; la CI manylinux compile avec `-msse4.2` seul. Le smoke de la
  roue fait ici (voir plus haut) héritait des mêmes CFLAGS : il ne pouvait pas voir le défaut.
- Correctif : `#include <nmmintrin.h>` sous `RAPIDJSON_SSE42`, à côté de `<tmmintrin.h>`.
  Alternative écartée : ajouter `-msse4.1`/`-march` à la CI — l'erreur est un en-tête manquant,
  pas un jeu d'instructions manquant (`-msse4.2` implique SSE4.1).
- Preuve : erreur REPRODUITE en local en compilant avec les drapeaux exacts de la CI
  (`-std=c++11 -O3 -msse4.2`, sans les CFLAGS de sysconfig) contre les en-têtes 3.11, 3.12, 3.13
  et 3.14, avec g++ 15 ; disparue avec le correctif sur les quatre. Code généré inchangé (un
  include de plus, déjà présent indirectement ici) : les `.so` PGO commités ne sont pas rebâtis.
  La CI elle-même reste la seule preuve complète (gcc-toolset-14, clones réseau).

## Points ouverts

- Le Trusted Publisher doit exister côté pypi.org pour ce dépôt, workflow
  `python-publish.yml`, environnement `pypi` — sinon l'étape d'envoi échoue (les roues sont
  quand même construites et visibles dans les artefacts de la CI).
- setuptools avertit que les classifiers de licence sont dépréciés (SPDX) : avertissement
  seulement, sans effet sur la publication.
