"""Festivos Colombia (ley Emiliani + fechas fijas)."""
from datetime import date, timedelta


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _next_monday(d: date) -> date:
    if d.weekday() == 0:
        return d
    return d + timedelta(days=(7 - d.weekday()))


def festivos_colombia(year: int) -> set[date]:
    pascua = _easter(year)
    fijos = {
        date(year, 1, 1),
        date(year, 5, 1),
        date(year, 7, 20),
        date(year, 8, 7),
        date(year, 12, 8),
        date(year, 12, 25),
    }
    emiliani = {
        _next_monday(date(year, 1, 6)),
        _next_monday(date(year, 3, 19)),
        _next_monday(pascua - timedelta(days=3)),
        pascua - timedelta(days=2),
        pascua,
        pascua + timedelta(days=43),
        _next_monday(pascua + timedelta(days=60)),
        _next_monday(pascua + timedelta(days=68)),
        _next_monday(date(year, 6, 29)),
        _next_monday(date(year, 8, 15)),
        _next_monday(date(year, 10, 12)),
        _next_monday(date(year, 11, 1)),
        _next_monday(date(year, 11, 11)),
    }
    return fijos | emiliani


def es_festivo(d: date) -> bool:
    return d in festivos_colombia(d.year)
