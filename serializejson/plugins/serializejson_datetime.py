try:
    from SmartFramework.serialize.tools import authorized_classes
except:
    from serializejson.tools import authorized_classes
from ..tools import serializejson_
import datetime

authorized_classes.update(
    {"decimal.Decimal", "datetime.datetime", "datetime.timedelta", "datetime.date", "datetime.time", "time.struct_time"}
)


def serializejson_datetime(inst):
    return (
        inst.__class__,
        (
            inst.year,
            inst.month,
            inst.day,
            inst.hour,
            inst.minute,
            inst.second,
            inst.microsecond,
        ),
        None,
    )


serializejson_[datetime.datetime] = serializejson_datetime
