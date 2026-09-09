from fastapi import FastAPI, Request, Depends, Form, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import Environment, FileSystemLoader, select_autoescape
import secrets
import os
import tempfile
from pathlib import Path

from .database import engine, get_db, Base
from .models import Usuario, Persona, Carga, DatoNacional
from .auth import create_default_user, authenticate_user, DEFAULT_USER
from .processing import procesar_excel, FUENTES_VALIDAS, EQUIPOS_CARGA, MOTIVOS_NO_INSTALADA

# Ruta base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Crear tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="InfoMIRA Censo - Carvajal", docs_url=None, redoc_url=None)

# Middleware de sesión (clave fija desde variable de entorno en producción)
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Archivos estáticos (crea la carpeta si no existe)
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Plantillas
from jinja2.utils import htmlsafe_json_dumps
import json

jinja_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0
)
# Asegurar filtro tojson
jinja_env.filters["tojson"] = lambda v: htmlsafe_json_dumps(v)
templates = Jinja2Templates(env=jinja_env)


@app.on_event("startup")
def on_startup():
    # Crear tablas nuevas si no existen
    Base.metadata.create_all(bind=engine)
    # Migración simple SQLite: columna cargado_por en cargas
    try:
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            cols = [r[1] for r in conn.execute(sql_text("PRAGMA table_info(cargas)")).fetchall()]
            if "cargado_por" not in cols:
                conn.execute(sql_text("ALTER TABLE cargas ADD COLUMN cargado_por VARCHAR(100)"))
                conn.commit()
                print("Columna cargas.cargado_por agregada")
            pcols = [r[1] for r in conn.execute(sql_text("PRAGMA table_info(personas)")).fetchall()]
            if "motivo" not in pcols:
                conn.execute(sql_text("ALTER TABLE personas ADD COLUMN motivo VARCHAR(100)"))
                conn.commit()
                print("Columna personas.motivo agregada")
            if "motivo_detalle" not in pcols:
                conn.execute(sql_text("ALTER TABLE personas ADD COLUMN motivo_detalle VARCHAR(255)"))
                conn.commit()
                print("Columna personas.motivo_detalle agregada")
    except Exception as e:
        print(f"Migración: {e}")

    db = next(get_db())
    create_default_user(db)
    db.close()


def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        return None
    return user


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    if authenticate_user(db, username, password):
        request.session["user"] = username
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Usuario o contraseña incorrectos"}
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    from collections import defaultdict

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    total_instaladas = db.query(Persona).filter(
        Persona.pendiente_revision == False,
        Persona.estado == "Instalada"
    ).count()

    total_no_instalada = db.query(Persona).filter(
        Persona.estado == "No instalada"
    ).count()

    # Pendientes de celular (Instalada sin celular válido)
    pendientes_celular = db.query(Persona).filter(
        Persona.pendiente_revision == True,
        Persona.estado == "Instalada",
    ).order_by(Persona.id.desc()).all()

    # Seguimiento No instalada sin motivo asignado
    seguimiento_no_instalada = db.query(Persona).filter(
        Persona.estado == "No instalada",
        (Persona.motivo.is_(None) | (Persona.motivo == "")),
    ).order_by(Persona.id.desc()).all()

    pendientes = pendientes_celular  # compat

    meta = 500

    # Título de periodo automático (mes actual)
    MESES_TITULO = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }
    ahora = datetime.now()
    periodo_titulo = f"Resultados · {MESES_TITULO[ahora.month]} {ahora.year}"

    # === Datos para gráfica diaria ===
    MESES_ES = {
        1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
        7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"
    }

    personas = db.query(Persona).filter(
        Persona.pendiente_revision == False,
        Persona.estado == "Instalada"
    ).all()

    labels = []
    data = []

    if personas:
        # Agrupar por día usando fecha_listado (o fecha_primera_carga como respaldo)
        dias = defaultdict(int)
        for p in personas:
            if p.fecha_listado:
                clave = p.fecha_listado.strftime("%Y-%m-%d")
            elif p.fecha_primera_carga:
                fecha = p.fecha_primera_carga
                if hasattr(fecha, "tzinfo") and fecha.tzinfo is not None:
                    fecha = fecha.replace(tzinfo=None)
                clave = fecha.strftime("%Y-%m-%d")
            else:
                continue
            dias[clave] += 1

        # Ordenar días y calcular acumulado
        dias_ordenados = sorted(dias.keys())
        acumulado = 0
        for clave in dias_ordenados:
            acumulado += dias[clave]
            fecha_dia = datetime.strptime(clave, "%Y-%m-%d")
            etiqueta = f"{fecha_dia.day:02d} {MESES_ES[fecha_dia.month]}"
            labels.append(etiqueta)
            data.append(acumulado)

    # Último dato de sede nacional
    dato_nacional = db.query(DatoNacional).order_by(
        DatoNacional.fecha_dato.desc(), DatoNacional.id.desc()
    ).first()
    diferencia_nacional = None
    if dato_nacional:
        diferencia_nacional = dato_nacional.total_reportado - total_instaladas

    # Avance principal: sede nacional si existe; si no, registro interno
    usa_dato_nacional = dato_nacional is not None
    if usa_dato_nacional:
        avance_principal = dato_nacional.total_reportado
    else:
        avance_principal = total_instaladas

    porcentaje = round((avance_principal / meta) * 100, 1) if meta > 0 else 0
    if porcentaje > 100:
        porcentaje_barra = 100
    else:
        porcentaje_barra = porcentaje

    # Color de barra según cercanía a la meta
    if porcentaje >= 100:
        barra_color = "bg-green-600"
        barra_track = "bg-green-100"
    elif porcentaje >= 70:
        barra_color = "bg-green-500"
        barra_track = "bg-green-50"
    elif porcentaje >= 40:
        barra_color = "bg-amber-400"
        barra_track = "bg-amber-50"
    else:
        barra_color = "bg-red-500"
        barra_track = "bg-red-50"

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "total_instaladas": total_instaladas,
            "total_no_instalada": total_no_instalada,
            "meta": meta,
            "porcentaje": porcentaje,
            "porcentaje_barra": porcentaje_barra,
            "avance_principal": avance_principal,
            "usa_dato_nacional": usa_dato_nacional,
            "barra_color": barra_color,
            "barra_track": barra_track,
            "periodo_titulo": periodo_titulo,
            "pendientes": pendientes_celular,
            "pendientes_celular": pendientes_celular,
            "seguimiento_no_instalada": seguimiento_no_instalada,
            "chart_labels": labels,
            "chart_data": data,
            "dato_nacional": dato_nacional,
            "diferencia_nacional": diferencia_nacional,
        }
    )


# ========== ETAPA 3: Carga de Excel ==========

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "user": user,
            "fuentes": FUENTES_VALIDAS,
            "equipos": EQUIPOS_CARGA,
            "error": None
        }
    )


@app.post("/upload", response_class=HTMLResponse)
async def upload_submit(
    request: Request,
    fuente: str = Form(...),
    fecha_listado: str = Form(...),
    cargado_por: str = Form(...),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Validaciones básicas
    if fuente not in FUENTES_VALIDAS:
        return templates.TemplateResponse(
            request, "upload.html",
            {"user": user, "fuentes": FUENTES_VALIDAS, "equipos": EQUIPOS_CARGA, "error": "Fuente no válida."}
        )

    if cargado_por not in EQUIPOS_CARGA:
        return templates.TemplateResponse(
            request, "upload.html",
            {"user": user, "fuentes": FUENTES_VALIDAS, "equipos": EQUIPOS_CARGA, "error": "Equipo no válido."}
        )

    if not archivo.filename:
        return templates.TemplateResponse(
            request, "upload.html",
            {"user": user, "fuentes": FUENTES_VALIDAS, "equipos": EQUIPOS_CARGA, "error": "Debes seleccionar un archivo."}
        )

    # Solo aceptar .xlsx
    if not archivo.filename.lower().endswith((".xlsx", ".xls")):
        return templates.TemplateResponse(
            request, "upload.html",
            {"user": user, "fuentes": FUENTES_VALIDAS,
             "error": "Solo se permiten archivos Excel (.xlsx)."}
        )

    # Guardar temporalmente
    try:
        suffix = Path(archivo.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await archivo.read()
            # Límite de tamaño ~5 MB
            if len(content) > 5 * 1024 * 1024:
                return templates.TemplateResponse(
                    request, "upload.html",
                    {"user": user, "fuentes": FUENTES_VALIDAS,
                     "error": "El archivo es demasiado grande (máximo 5 MB)."}
                )
            tmp.write(content)
            tmp_path = tmp.name

        # Parsear fecha del listado
        from datetime import datetime as dt
        try:
            fecha_obj = dt.strptime(fecha_listado, "%Y-%m-%d").date()
        except ValueError:
            return templates.TemplateResponse(
                request, "upload.html",
                {"user": user, "fuentes": FUENTES_VALIDAS,
                 "error": "Fecha del listado inválida."}
            )

        # Procesar
        resumen = procesar_excel(
            file_path=tmp_path,
            fuente=fuente,
            nombre_archivo=archivo.filename,
            fecha_listado=fecha_obj,
            db=db,
            cargado_por=cargado_por,
        )

    except Exception as e:
        return templates.TemplateResponse(
            request, "upload.html",
            {"user": user, "fuentes": FUENTES_VALIDAS,
             "error": f"Error al procesar el archivo: {str(e)}"}
        )
    finally:
        # Limpiar archivo temporal
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "user": user,
            "resumen": resumen,
            "nombre_archivo": archivo.filename,
            "fuente": fuente
        }
    )


# ========== ETAPA 4: Edición de pendientes ==========

@app.get("/pendiente/{persona_id}", response_class=HTMLResponse)
async def editar_pendiente_page(request: Request, persona_id: int, db: Session = Depends(get_db)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    persona = db.query(Persona).filter(
        Persona.id == persona_id,
        Persona.pendiente_revision == True
    ).first()

    if not persona:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "editar_pendiente.html",
        {
            "user": user,
            "persona": persona,
            "error": None
        }
    )


@app.post("/pendiente/{persona_id}", response_class=HTMLResponse)
async def editar_pendiente_submit(
    request: Request,
    persona_id: int,
    nombre: str = Form(...),
    celular: str = Form(...),
    db: Session = Depends(get_db)
):
    from .processing import normalizar_celular, normalizar_nombre

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    persona = db.query(Persona).filter(
        Persona.id == persona_id,
        Persona.pendiente_revision == True
    ).first()

    if not persona:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    nombre_limpio = normalizar_nombre(nombre)
    celular_limpio = normalizar_celular(celular)

    if not nombre_limpio:
        return templates.TemplateResponse(
            request, "editar_pendiente.html",
            {"user": user, "persona": persona, "error": "El nombre no puede estar vacío."}
        )

    if not celular_limpio:
        return templates.TemplateResponse(
            request, "editar_pendiente.html",
            {"user": user, "persona": persona,
             "error": "El celular debe tener exactamente 10 dígitos válidos (ejemplo: 3115712505)."}
        )

    # Verificar que el celular no esté ya usado por otra persona
    existente = db.query(Persona).filter(
        Persona.celular == celular_limpio,
        Persona.id != persona.id
    ).first()

    if existente:
        return templates.TemplateResponse(
            request, "editar_pendiente.html",
            {"user": user, "persona": persona,
             "error": f"Ese celular ya está registrado a nombre de: {existente.nombre}"}
        )

    # Actualizar y quitar de pendientes
    persona.nombre = nombre_limpio
    persona.celular = celular_limpio
    persona.pendiente_revision = False
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


# ========== ETAPA 6: Informe semanal ==========

@app.get("/informe", response_class=HTMLResponse)
async def generar_informe(request: Request, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    from sqlalchemy import func as sqlfunc

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Total acumulado
    total_instaladas = db.query(Persona).filter(
        Persona.pendiente_revision == False,
        Persona.estado == "Instalada"
    ).count()

    meta = 500

    # Semana actual (lunes a domingo) — cruza meses sin problema
    hoy = datetime.now().date()
    lunes = hoy - timedelta(days=hoy.weekday())
    domingo = lunes + timedelta(days=6)

    MESES = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }

    def formato_fecha(d):
        return f"{d.day} de {MESES[d.month]}"

    rango_semana = f"{formato_fecha(lunes)} al {formato_fecha(domingo)}"

    # Fuentes de la semana = cargas hechas lun-dom (solo personas NUEVAS)
    cargas_semana = db.query(Carga).filter(
        sqlfunc.date(Carga.fecha_carga) >= lunes,
        sqlfunc.date(Carga.fecha_carga) <= domingo,
    ).all()

    desglose = {}
    for c in cargas_semana:
        if not c.fuente:
            continue
        desglose[c.fuente] = desglose.get(c.fuente, 0) + (c.nuevos or 0)
    # Quitar fuentes en cero para no ensuciar el mensaje
    desglose = {f: n for f, n in desglose.items() if n > 0}

    # Dato sede nacional (si existe)
    datos_nac = db.query(DatoNacional).order_by(
        DatoNacional.fecha_dato.desc(), DatoNacional.id.desc()
    ).all()
    dato_nacional = datos_nac[0] if datos_nac else None
    dato_nacional_prev = datos_nac[1] if len(datos_nac) > 1 else None

    if dato_nacional:
        avance = dato_nacional.total_reportado
        etiqueta_avance = "sede nacional"
    else:
        avance = total_instaladas
        etiqueta_avance = "registro interno"

    porcentaje = round((avance / meta) * 100, 1) if meta > 0 else 0

    alerta = []
    if dato_nacional and dato_nacional_prev:
        actual = dato_nacional.total_reportado
        anterior = dato_nacional_prev.total_reportado
        if actual == anterior:
            alerta = [
                "",
                "⚠️ *Atención: el dato de sede nacional no aumentó.*",
                f"Sigue en {actual}. Se sugiere buscar nuevas estrategias que promuevan la instalación de la App.",
            ]
        elif actual < anterior:
            delta = anterior - actual
            alerta = [
                "",
                "⚠️ *Atención: el dato de sede nacional bajó.*",
                f"Pasó de {anterior} a {actual} (−{delta}). Revisar posibles desinstalaciones.",
            ]

    lineas = [
        "📊 *Informe Semanal – Censo App InfoMIRA*",
        f"📅 Semana: {rango_semana}",
        "",
        f"🎯 *Avance del equipo ({etiqueta_avance})*",
        f"• {avance} / {meta} personas",
        f"• {porcentaje} %",
    ]
    lineas.extend(alerta)
    lineas.extend([
        "",
        f"🗂 Registro interno: {total_instaladas} personas censadas",
    ])

    if desglose:
        lineas.extend(["", "📥 *Fuentes de la semana:*"])
        for fuente, cant in desglose.items():
            lineas.append(f"• {fuente}: {cant}")

    texto_informe = "\n".join(lineas)

    return templates.TemplateResponse(
        request,
        "informe.html",
        {
            "user": user,
            "texto_informe": texto_informe,
            "rango_semana": rango_semana,
            "total_instaladas": total_instaladas,
            "porcentaje": porcentaje,
        }
    )








@app.post("/pendiente/{persona_id}/eliminar")
async def eliminar_pendiente(
    request: Request,
    persona_id: int,
    db: Session = Depends(get_db),
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    persona = db.query(Persona).filter(
        Persona.id == persona_id,
        Persona.pendiente_revision == True,
    ).first()

    if persona:
        db.delete(persona)
        db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)



@app.get("/seguimiento/{persona_id}", response_class=HTMLResponse)
async def seguimiento_page(request: Request, persona_id: int, db: Session = Depends(get_db)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    persona = db.query(Persona).filter(
        Persona.id == persona_id,
        Persona.estado == "No instalada",
    ).first()
    if not persona:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "seguimiento.html",
        {
            "user": user,
            "persona": persona,
            "motivos": MOTIVOS_NO_INSTALADA,
            "error": None,
        },
    )


@app.post("/seguimiento/{persona_id}", response_class=HTMLResponse)
async def seguimiento_submit(
    request: Request,
    persona_id: int,
    motivo: str = Form(...),
    motivo_detalle: str = Form(""),
    celular: str = Form(""),
    db: Session = Depends(get_db),
):
    from .processing import normalizar_celular, normalizar_nombre

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    persona = db.query(Persona).filter(
        Persona.id == persona_id,
        Persona.estado == "No instalada",
    ).first()
    if not persona:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    if motivo not in MOTIVOS_NO_INSTALADA:
        return templates.TemplateResponse(
            request, "seguimiento.html",
            {"user": user, "persona": persona, "motivos": MOTIVOS_NO_INSTALADA,
             "error": "Motivo no válido."},
        )

    if motivo == "Otro" and not (motivo_detalle or "").strip():
        return templates.TemplateResponse(
            request, "seguimiento.html",
            {"user": user, "persona": persona, "motivos": MOTIVOS_NO_INSTALADA,
             "error": "Si eliges «Otro», describe la situación."},
        )

    cel = normalizar_celular(celular) if celular else None
    if cel:
        otro = db.query(Persona).filter(Persona.celular == cel, Persona.id != persona.id).first()
        if otro:
            return templates.TemplateResponse(
                request, "seguimiento.html",
                {"user": user, "persona": persona, "motivos": MOTIVOS_NO_INSTALADA,
                 "error": f"Ese celular ya está registrado a: {otro.nombre}"},
            )
        persona.celular = cel
        persona.pendiente_revision = False
    elif persona.pendiente_revision:
        # Sigue sin celular válido
        pass

    persona.motivo = motivo
    persona.motivo_detalle = (motivo_detalle or "").strip() or None
    db.commit()

    return RedirectResponse(
        url="/personas?estado=no_instalada",
        status_code=status.HTTP_303_SEE_OTHER,
    )

# ========== Dato oficial sede nacional ==========

@app.get("/dato-nacional", response_class=HTMLResponse)
async def dato_nacional_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    ultimo = db.query(DatoNacional).order_by(
        DatoNacional.fecha_dato.desc(), DatoNacional.id.desc()
    ).first()
    historial = db.query(DatoNacional).order_by(
        DatoNacional.fecha_dato.desc(), DatoNacional.id.desc()
    ).limit(10).all()

    return templates.TemplateResponse(
        request,
        "dato_nacional.html",
        {"user": user, "ultimo": ultimo, "historial": historial, "error": None},
    )


@app.post("/dato-nacional", response_class=HTMLResponse)
async def dato_nacional_submit(
    request: Request,
    fecha_dato: str = Form(...),
    total_reportado: int = Form(...),
    nota: str = Form(""),
    db: Session = Depends(get_db),
):
    from datetime import datetime as dt

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        fecha = dt.strptime(fecha_dato, "%Y-%m-%d").date()
    except ValueError:
        ultimo = db.query(DatoNacional).order_by(DatoNacional.fecha_dato.desc()).first()
        historial = db.query(DatoNacional).order_by(DatoNacional.fecha_dato.desc()).limit(10).all()
        return templates.TemplateResponse(
            request, "dato_nacional.html",
            {"user": user, "ultimo": ultimo, "historial": historial, "error": "Fecha inválida."},
        )

    if total_reportado < 0:
        ultimo = db.query(DatoNacional).order_by(DatoNacional.fecha_dato.desc()).first()
        historial = db.query(DatoNacional).order_by(DatoNacional.fecha_dato.desc()).limit(10).all()
        return templates.TemplateResponse(
            request, "dato_nacional.html",
            {"user": user, "ultimo": ultimo, "historial": historial, "error": "El total no puede ser negativo."},
        )

    registro = DatoNacional(
        fecha_dato=fecha,
        total_reportado=total_reportado,
        nota=(nota or "").strip() or None,
    )
    db.add(registro)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

# ========== Listado consultable de personas ==========


@app.get("/persona/{persona_id}", response_class=HTMLResponse)
async def editar_persona_page(request: Request, persona_id: int, db: Session = Depends(get_db)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        return RedirectResponse(url="/personas", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "persona_editar.html",
        {"user": user, "persona": persona, "error": None},
    )


@app.post("/persona/{persona_id}", response_class=HTMLResponse)
async def editar_persona_submit(
    request: Request,
    persona_id: int,
    nombre: str = Form(...),
    celular: str = Form(""),
    estado: str = Form(...),
    db: Session = Depends(get_db),
):
    from .processing import normalizar_celular, normalizar_nombre

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        return RedirectResponse(url="/personas", status_code=status.HTTP_303_SEE_OTHER)

    nombre_limpio = normalizar_nombre(nombre)
    if not nombre_limpio:
        return templates.TemplateResponse(
            request, "persona_editar.html",
            {"user": user, "persona": persona, "error": "El nombre no puede estar vacío."},
        )

    if estado not in ("Instalada", "No instalada"):
        return templates.TemplateResponse(
            request, "persona_editar.html",
            {"user": user, "persona": persona, "error": "Estado no válido."},
        )

    celular_limpio = normalizar_celular(celular) if celular else None

    if estado == "Instalada" and not celular_limpio:
        return templates.TemplateResponse(
            request, "persona_editar.html",
            {"user": user, "persona": persona,
             "error": "Para marcar Instalada el celular debe tener 10 dígitos válidos."},
        )

    if celular_limpio:
        otro = db.query(Persona).filter(
            Persona.celular == celular_limpio,
            Persona.id != persona.id,
        ).first()
        if otro:
            return templates.TemplateResponse(
                request, "persona_editar.html",
                {"user": user, "persona": persona,
                 "error": (
                     f"Ese celular ya está en otro registro: {otro.nombre} "
                     f"({otro.estado}). Elimina uno de los dos en Personas."
                 )},
            )
        persona.celular = celular_limpio
        persona.pendiente_revision = False
    else:
        persona.pendiente_revision = True

    persona.nombre = nombre_limpio
    persona.estado = estado
    if estado == "Instalada":
        persona.motivo = None
        persona.motivo_detalle = None
    db.commit()

    destino = "/personas?estado=no_instalada" if estado == "No instalada" else "/personas?estado=instalada"
    return RedirectResponse(url=destino, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/persona/{persona_id}/eliminar")
async def eliminar_persona(request: Request, persona_id: int, db: Session = Depends(get_db)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if persona:
        db.delete(persona)
        db.commit()
    return RedirectResponse(url="/personas?estado=todos", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/personas", response_class=HTMLResponse)
async def listar_personas(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    fuente: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    estado: str = "",
):
    from datetime import datetime as dt

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = db.query(Persona)

    # Filtro por estado
    # Por defecto: Instalada (censados). "no_instalada" = seguimiento. "todos" = todo.
    estado = (estado or "instalada").strip().lower()
    if estado == "instalada":
        query = query.filter(
            Persona.estado == "Instalada",
            Persona.pendiente_revision == False,
        )
    elif estado == "no_instalada":
        query = query.filter(Persona.estado == "No instalada")
    elif estado == "pendientes":
        query = query.filter(Persona.pendiente_revision == True)
    # estado == "todos" → sin filtro de estado

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Persona.nombre.ilike(like)) | (Persona.celular.ilike(like))
        )

    if fuente and fuente in FUENTES_VALIDAS:
        query = query.filter(Persona.fuente_ultima == fuente)

    if fecha_desde:
        try:
            d = dt.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(Persona.fecha_listado >= d)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            d = dt.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(Persona.fecha_listado <= d)
        except ValueError:
            pass

    total_filtrado = query.count()
    personas = query.order_by(Persona.nombre.asc()).limit(500).all()

    total_instaladas = db.query(Persona).filter(
        Persona.estado == "Instalada",
        Persona.pendiente_revision == False,
    ).count()
    total_no_instalada = db.query(Persona).filter(
        Persona.estado == "No instalada"
    ).count()

    return templates.TemplateResponse(
        request,
        "personas.html",
        {
            "user": user,
            "personas": personas,
            "total_filtrado": total_filtrado,
            "total_instaladas": total_instaladas,
            "total_no_instalada": total_no_instalada,
            "fuentes": FUENTES_VALIDAS,
            "filtros": {
                "q": q,
                "fuente": fuente,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "estado": estado,
            },
            "limitado": total_filtrado > 500,
        },
    )



# ========== Historial de cargas ==========

@app.get("/cargas", response_class=HTMLResponse)
async def historial_cargas(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    cargas = db.query(Carga).order_by(Carga.fecha_carga.desc()).limit(100).all()

    return templates.TemplateResponse(
        request,
        "cargas.html",
        {
            "user": user,
            "cargas": cargas,
        },
    )

# ========== ETAPA 7: Respaldo simple ==========

@app.get("/backup")
async def crear_backup(request: Request):
    """Descarga una copia de la base de datos (usa DATABASE_PATH en producción)."""
    import shutil
    import tempfile
    from fastapi.responses import FileResponse
    from datetime import datetime
    from .database import DB_PATH

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    db_path = Path(DB_PATH)
    if not db_path.exists():
        # Fallback a la ruta local por si no hay variable de entorno
        db_path = BASE_DIR / "infomira_censo.db"
    if not db_path.exists():
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_infomira_{fecha}.db"

    # Copia temporal (en producción /app puede no ser escribible de forma fiable)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    shutil.copy2(db_path, tmp.name)

    return FileResponse(
        path=tmp.name,
        filename=backup_name,
        media_type="application/octet-stream",
    )
