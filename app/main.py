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
from .models import Usuario, Persona, Carga
from .auth import create_default_user, authenticate_user, DEFAULT_USER
from .processing import procesar_excel, FUENTES_VALIDAS

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

    pendientes = db.query(Persona).filter(
        Persona.pendiente_revision == True
    ).order_by(Persona.id.desc()).all()

    meta = 500
    porcentaje = round((total_instaladas / meta) * 100, 1) if meta > 0 else 0

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

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "total_instaladas": total_instaladas,
            "meta": meta,
            "porcentaje": porcentaje,
            "pendientes": pendientes,
            "chart_labels": labels,
            "chart_data": data,
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
            "error": None
        }
    )


@app.post("/upload", response_class=HTMLResponse)
async def upload_submit(
    request: Request,
    fuente: str = Form(...),
    fecha_listado: str = Form(...),
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
            {"user": user, "fuentes": FUENTES_VALIDAS, "error": "Fuente no válida."}
        )

    if not archivo.filename:
        return templates.TemplateResponse(
            request, "upload.html",
            {"user": user, "fuentes": FUENTES_VALIDAS, "error": "Debes seleccionar un archivo."}
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
            db=db
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
    porcentaje = round((total_instaladas / meta) * 100, 1) if meta > 0 else 0

    # Semana actual (lunes a domingo)
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

    # Desglose por fuente de la semana
    filas = db.query(
        Persona.fuente_ultima,
        sqlfunc.count(Persona.id)
    ).filter(
        Persona.pendiente_revision == False,
        Persona.estado == "Instalada",
        Persona.fecha_listado >= lunes,
        Persona.fecha_listado <= domingo
    ).group_by(Persona.fuente_ultima).all()

    desglose = {}
    for fuente, cantidad in filas:
        if fuente:
            desglose[fuente] = cantidad

    # Texto del informe
    lineas = [
        "📊 *Informe Semanal – Censo App InfoMIRA*",
        f"📅 Semana: {rango_semana}",
        "",
        f"🎯 Meta del mes: {meta} personas censadas",
        "",
        "👥 *Resultados acumulados:*",
        f"• Personas censadas: {total_instaladas}",
        f"• Avance de la meta: {porcentaje} %",
        "",
        "📥 *Fuentes de información de la semana:*"
    ]

    if desglose:
        for fuente, cant in desglose.items():
            lineas.append(f"• {fuente}: {cant} personas")
    else:
        lineas.append("• Sin registros nuevos esta semana")

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


# ========== ETAPA 7: Respaldo simple ==========

@app.get("/backup")
async def crear_backup(request: Request):
    """Descarga una copia de la base de datos."""
    import shutil
    from fastapi.responses import FileResponse
    from datetime import datetime

    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    db_path = BASE_DIR / "infomira_censo.db"
    if not db_path.exists():
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # Crear copia con fecha
    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_infomira_{fecha}.db"
    backup_path = BASE_DIR / backup_name

    shutil.copy2(db_path, backup_path)

    return FileResponse(
        path=str(backup_path),
        filename=backup_name,
        media_type="application/octet-stream"
    )
