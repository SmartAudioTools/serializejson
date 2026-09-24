"""datetime.datetime en texte RFC 9557 : lisible, et relu à l'identique.

Naïf (branche C du writer) : "2026-09-24T18:26:00" ; décalage fixe :
"...+05:00" ; ZoneInfo : "...+02:00[Europe/Paris]", le décalage départageant
les deux 02:30 du passage à l'heure d'hiver (fold). Les anciennes formes
reduce (10 octets, 7 entiers) doivent rester lisibles.
"""

import datetime as d
import json
from zoneinfo import ZoneInfo

import pytest
import serializejson

PARIS = ZoneInfo("Europe/Paris")


def identique(a, b):
    return (a == b and type(a) is type(b) and a.tzinfo == b.tzinfo
            and a.fold == b.fold and a.utcoffset() == b.utcoffset())


@pytest.mark.parametrize("dt, texte", [
    (d.datetime(2026, 9, 24, 18, 26), "2026-09-24T18:26:00"),
    (d.datetime(2026, 9, 24, 18, 26, 0, 5), "2026-09-24T18:26:00.000005"),
    (d.datetime(5, 1, 2, 3, 4, 5), "0005-01-02T03:04:05"),
    (d.datetime(2026, 9, 24, 18, 26, tzinfo=PARIS),
     "2026-09-24T18:26:00+02:00[Europe/Paris]"),
    (d.datetime(2026, 10, 25, 2, 30, tzinfo=PARIS),
     "2026-10-25T02:30:00+02:00[Europe/Paris]"),
    (d.datetime(2026, 10, 25, 2, 30, fold=1, tzinfo=PARIS),
     "2026-10-25T02:30:00+01:00[Europe/Paris]"),
    (d.datetime(2026, 9, 24, tzinfo=d.timezone.utc), "2026-09-24T00:00:00+00:00"),
    (d.datetime(2026, 9, 24, tzinfo=d.timezone(d.timedelta(hours=-5))),
     "2026-09-24T00:00:00-05:00"),
])
def test_texte_et_aller_retour(dt, texte):
    s = serializejson.dumps(dt)
    assert json.loads(s) == {"__class__": "datetime.datetime", "__init__": texte}
    assert identique(serializejson.loads(s), dt)


def test_dans_un_conteneur():
    # la branche C du writer n'est prise que sous un pathTracker
    x = {"a": [d.datetime(2026, 9, 24, 18, 26), d.datetime(2026, 9, 24, tzinfo=PARIS)]}
    y = serializejson.loads(serializejson.dumps(x))
    assert all(identique(a, b) for a, b in zip(x["a"], y["a"]))


def test_timezone_nommee_reste_reduce():
    # "CET" ne tient pas dans le texte : forme reduce, relue à l'identique
    dt = d.datetime(2026, 9, 24, tzinfo=d.timezone(d.timedelta(hours=1), "CET"))
    s = serializejson.dumps(dt)
    assert isinstance(json.loads(s)["__init__"], list)
    assert identique(serializejson.loads(s), dt)


@pytest.mark.parametrize("ancien", [
    '{"__class__":"datetime.datetime","__init__":{"__class__":"bytes","__new__":["B+QDChEeAAAAAA==","b64"]}}',
    '{"__class__":"datetime.datetime","__init__":[2020,3,10,17,30,0,0]}',
])
def test_formes_anciennes_lisibles(ancien):
    assert identique(serializejson.loads(ancien), d.datetime(2020, 3, 10, 17, 30))


def test_decalage_incompatible_avec_la_zone():
    with pytest.raises(Exception):
        serializejson.loads('{"__class__":"datetime.datetime",'
                            '"__init__":"2026-09-24T18:26:00+05:00[Europe/Paris]"}')
