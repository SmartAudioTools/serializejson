from serializejson.tools import authorized_classes, constructors, serializejson_
import datetime
from zoneinfo import ZoneInfo

authorized_classes.update(
    {
        "decimal.Decimal",
        "datetime.datetime",
        "datetime.timedelta",
        "datetime.timezone",
        "datetime.date",
        "datetime.time",
        "time.struct_time",
    }
)


# datetime.datetime s'écrit en texte RFC 9557 (lisible, standard) :
# "2026-09-24T18:26:00" (naïf), "2026-09-24T18:26:00+02:00" (décalage fixe,
# datetime.timezone), "2026-09-24T18:26:00+02:00[Europe/Paris]" (ZoneInfo : le
# nom redonne les règles d'heure d'été, le décalage lève l'ambiguïté du
# passage à l'heure d'hiver, donc fold). Les naïfs sont écrits par la branche
# C du writer, à l'identique de isoformat() ; ce greffon sert les autres.
# Tout autre tzinfo (pytz, dateutil, timezone NOMMÉ) garde la forme reduce.
# Lecture : les formes reduce (10 octets, 7 entiers) restent comprises.


def _texte_rfc9557(dt):
    tz = dt.tzinfo
    if tz is None:
        return dt.isoformat()
    if type(tz) is datetime.timezone:
        # un nom propre (timezone(d, "CET")) ne tiendrait pas dans le texte
        if tz.tzname(None) == datetime.timezone(tz.utcoffset(None)).tzname(None):
            return dt.isoformat()
        return None
    if type(tz) is ZoneInfo and tz.key is not None:
        return f"{dt.isoformat()}[{tz.key}]"
    return None


def serializejson_datetime(dt):
    texte = _texte_rfc9557(dt)
    if texte is None:
        return "datetime.datetime", dt.__reduce_ex__(2)[1], None
    return "datetime.datetime", (texte,), None


def datetime_depuis(*args):
    if len(args) != 1 or type(args[0]) is not str:
        return datetime.datetime(*args)  # formes reduce
    texte = args[0]
    if not texte.endswith("]"):
        return datetime.datetime.fromisoformat(texte)
    texte, zone = texte[:-1].split("[", 1)
    decale = datetime.datetime.fromisoformat(texte)
    local = decale.replace(tzinfo=ZoneInfo(zone.removeprefix("!")))
    for fold in (0, 1):
        local = local.replace(fold=fold)
        if local.utcoffset() == decale.utcoffset():
            return local
    raise ValueError(f"{args[0]} : décalage incompatible avec le fuseau {zone}")


serializejson_[datetime.datetime] = serializejson_datetime
constructors["datetime.datetime"] = datetime_depuis
