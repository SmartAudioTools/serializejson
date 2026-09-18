from serializejson.tools import authorized_classes, serializejson_
import datetime

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


# plus de greffon datetime.datetime (retiré le 06/08/2026) : la classe suit
# son __reduce_ex__ natif — forme OCTETS compacte (10 octets, comme date et
# time), tzinfo transporté quand il existe (le greffon 7 entiers le PERDAIT),
# et relecture par le constructeur rapide datetime(bytes). L'ancienne forme
# 7 entiers reste comprise en lecture (fichiers existants).
