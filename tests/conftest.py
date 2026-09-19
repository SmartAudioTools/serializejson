"""Épingle le module compilé du dépôt (rapidjson/rapidjson.<abi>.so, celui que
build_pgo.sh construit et que git suit) sous DEUX noms, avant tout import de
serializejson : « rapidjson » et « serializejson.rapidjson ».

- Le dossier rapidjson/ du dépôt masque le module compilé quand la racine est
  sur sys.path (namespace package, sans classe Encoder) ; selon l'installation,
  « import rapidjson » y rend l'un ou l'autre : on charge donc par CHEMIN.
- L'installation éditable (pip install -e) recopie un module compilé HORS PGO
  dans serializejson/, que « from . import rapidjson » préférerait : sans
  l'épingle sous le second nom, serializejson et les tests tournaient sur deux
  modules distincts (libblosc2 chargée dans un seul), et le profil PGO de
  build_pgo.sh n'exerçait pas le binaire instrumenté.

Importé aussi par les scripts du dépôt (bancs, pgo_workload.py) : même binaire.
"""

import importlib.util
import sys
import sysconfig
from pathlib import Path

racine = str(Path(__file__).resolve().parent.parent)
if racine not in sys.path:
    sys.path.insert(0, racine)
if "rapidjson" not in sys.modules:
    _chemin = Path(racine, "rapidjson", "rapidjson" + sysconfig.get_config_var("EXT_SUFFIX"))
    _spec = importlib.util.spec_from_file_location("rapidjson", _chemin)
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    sys.modules["rapidjson"] = _module
sys.modules.setdefault("serializejson.rapidjson", sys.modules["rapidjson"])
