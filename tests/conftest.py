"""Rend rapidjson importable quand la racine du dépôt est sur sys.path.

Le dossier rapidjson/ du dépôt (fork de python-rapidjson) masque alors le module
compilé : Python le voit comme un namespace package, sans classe Encoder. On importe
donc explicitement le module compilé qu'il contient et on l'enregistre sous le nom
"rapidjson" avant tout import de serializejson.
"""

import sys
from pathlib import Path

racine = str(Path(__file__).resolve().parent.parent)
if racine not in sys.path:
    sys.path.insert(0, racine)
if "rapidjson" not in sys.modules:
    import rapidjson.rapidjson as _rapidjson_compile

    sys.modules["rapidjson"] = _rapidjson_compile
