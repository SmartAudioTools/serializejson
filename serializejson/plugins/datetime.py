def tuple_from_datetime(inst):
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
