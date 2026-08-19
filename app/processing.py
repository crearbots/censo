"""
Lógica de procesamiento de archivos Excel según las reglas de negocio del MVP.
"""
import re
from typing import Any, Dict, List
from openpyxl import load_workbook
from sqlalchemy.orm import Session
from datetime import datetime

from .models import Persona, Carga


FUENTES_VALIDAS = [
    "Listado de reunión presencial",
    "Censo virtual"
]


def normalizar_celular(valor: Any) -> str | None:
    """
    Normaliza el número de celular a exactamente 10 dígitos.
    Elimina espacios, guiones, paréntesis y prefijos +57 / 57.
    Retorna None si no se puede normalizar a 10 dígitos.
    """
    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "none", ""):
        return None

    # Quitar todo lo que no sea dígito
    digitos = re.sub(r"\D", "", texto)

    # Quitar prefijo 57 si queda con 12 dígitos
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]

    if len(digitos) == 10:
        return digitos

    return None


def normalizar_nombre(valor: Any) -> str:
    """Normalización ligera de nombre."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto


def normalizar_estado(valor: Any) -> str | None:
    """Solo acepta 'Instalada' (insensible a mayúsculas)."""
    if valor is None:
        return None
    texto = str(valor).strip().lower()
    if texto in ("instalada", "instalado"):
        return "Instalada"
    return None


def mapear_columnas(headers: List) -> Dict[str, int]:
    """Mapea nombres de columna (insensible a mayúsculas) a índices."""
    mapping = {}
    for idx, h in enumerate(headers):
        if h is None:
            continue
        h_lower = str(h).strip().lower()
        if h_lower in ("nombre", "hnos/hnas", "hnos", "hnas", "name"):
            mapping["nombre"] = idx
        elif h_lower in ("celular", "telefono", "teléfono", "tel", "phone", "móvil", "movil"):
            mapping["celular"] = idx
        elif h_lower in ("estado", "status", "tiene app", "instalada"):
            mapping["estado"] = idx
    return mapping


def procesar_excel(
    file_path: str,
    fuente: str,
    nombre_archivo: str,
    fecha_listado,  # date object
    db: Session
) -> Dict[str, Any]:
    """
    Procesa el archivo Excel según las reglas de negocio.
    """
    resumen = {
        "nuevos": 0,
        "actualizados": 0,
        "pendientes": 0,
        "ignorados": 0,
        "errores": [],
        "total_filas": 0
    }

    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
    except Exception as e:
        resumen["errores"].append(f"No se pudo leer el archivo Excel: {str(e)}")
        return resumen

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        resumen["errores"].append("El archivo está vacío.")
        return resumen

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    col_map = mapear_columnas(headers)

    if "nombre" not in col_map or "celular" not in col_map or "estado" not in col_map:
        resumen["errores"].append(
            "No se encontraron las columnas obligatorias: Nombre, Celular y Estado. "
            f"Columnas detectadas: {headers}"
        )
        return resumen

    idx_nombre = col_map["nombre"]
    idx_celular = col_map["celular"]
    idx_estado = col_map["estado"]

    data_rows = rows[1:]
    resumen["total_filas"] = len(data_rows)

    for row_num, row in enumerate(data_rows, start=2):
        try:
            raw_nombre = row[idx_nombre] if idx_nombre < len(row) else None
            raw_celular = row[idx_celular] if idx_celular < len(row) else None
            raw_estado = row[idx_estado] if idx_estado < len(row) else None

            nombre = normalizar_nombre(raw_nombre)
            celular = normalizar_celular(raw_celular)
            estado = normalizar_estado(raw_estado)

            # Solo procesamos registros con Estado = Instalada
            if estado != "Instalada":
                resumen["ignorados"] += 1
                continue

            if not nombre:
                resumen["ignorados"] += 1
                continue

            # Celular inválido o vacío → Pendiente de revisión
            if celular is None:
                # Usamos un placeholder único temporal para respetar el constraint unique
                placeholder = f"TMP{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                persona = Persona(
                    celular=placeholder[:15],
                    nombre=nombre,
                    estado="Instalada",
                    fuente_ultima=fuente,
                    fecha_listado=fecha_listado,
                    pendiente_revision=True
                )
                db.add(persona)
                resumen["pendientes"] += 1
                continue

            # Buscar si ya existe por celular
            existente = db.query(Persona).filter(Persona.celular == celular).first()

            if existente:
                existente.nombre = nombre
                existente.fuente_ultima = fuente
                existente.fecha_listado = fecha_listado
                existente.fecha_ultima_carga = datetime.utcnow()
                existente.pendiente_revision = False
                existente.estado = "Instalada"
                resumen["actualizados"] += 1
            else:
                persona = Persona(
                    celular=celular,
                    nombre=nombre,
                    estado="Instalada",
                    fuente_ultima=fuente,
                    fecha_listado=fecha_listado,
                    pendiente_revision=False
                )
                db.add(persona)
                resumen["nuevos"] += 1

        except Exception as e:
            resumen["errores"].append(f"Fila {row_num}: {str(e)}")

    # Registrar la carga
    carga = Carga(
        nombre_archivo=nombre_archivo,
        fuente=fuente,
        fecha_listado=fecha_listado,
        total_registros=resumen["total_filas"],
        nuevos=resumen["nuevos"],
        actualizados=resumen["actualizados"],
        pendientes=resumen["pendientes"]
    )
    db.add(carga)
    db.commit()

    return resumen
