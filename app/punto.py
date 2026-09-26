from datetime import date, datetime, timedelta, timezone
from .festivos import es_festivo

TZ_CO = timezone(timedelta(hours=-5))
NOMBRES_DIA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def hoy_colombia() -> date:
    return datetime.now(TZ_CO).date()


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def semana_vigente(hoy: date | None = None) -> date:
    """Sábado o domingo: se edita la semana siguiente."""
    hoy = hoy or hoy_colombia()
    if hoy.weekday() >= 5:
        return lunes_de(hoy + timedelta(days=7))
    return lunes_de(hoy)


def dias_semana(lunes: date) -> list[date]:
    return [lunes + timedelta(days=i) for i in range(7)]


def horarios_del_dia(d: date) -> list[str]:
    wd = d.weekday()
    if wd == 5:
        return ["17:00"]
    if wd == 6:
        return ["08:00", "11:00"]
    if es_festivo(d):
        return ["08:00", "17:00"]
    return ["07:00", "18:00"]


def etiqueta_horario(h: str) -> str:
    return {"07:00": "7:00 a.m.", "08:00": "8:00 a.m.", "11:00": "11:00 a.m.",
            "17:00": "5:00 p.m.", "18:00": "6:00 p.m."}.get(h, h)
