# InfoMIRA Censo - Comunidad de Carvajal

Sistema interno de seguimiento del censo de instalación de la App InfoMIRA.

**Versión actual: `v1.1.0`** (agosto 2026)

## Historial de versiones

| Tag | Descripción |
|-----|-------------|
| `v1.0.0-mvp` | Primera versión estable en producción (~15 días) |
| `v1.1.0` | Mejoras operativas: Excel robusto, Personas, dato nacional, historial, seguimiento No instalada, UX móvil |

### Cambios en v1.1.0

- Procesamiento de Excel tolerante a duplicados en el mismo archivo
- Base de personas con filtros (Instalada / No instalada / pendientes)
- Registro del dato oficial de la sede nacional y diferencia con el registro interno
- Historial de cargas (archivo, fuente, equipo que carga, resultados)
- Seguimiento de personas **No instalada** con motivos predefinidos
- Regla de oro: no revertir a No instalada si ya estaba Instalada
- Eliminar pendientes de celular erróneos
- Campo “Equipo que carga” (Coordinación, Gestión Documental, Formación y Capacitación)
- Backup usando `DATABASE_PATH` (producción en `/data`)
- Menú unificado y mejor uso en celular
- Meta visible del equipo: **500** (agosto)

## Requisitos

- Python 3.10 o superior

## Instalación local

```bash
python -m venv env

# Windows:
env\Scripts\activate
# Mac/Linux:
source env/bin/activate

pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abrir: http://127.0.0.1:8000/login

Credenciales por defecto (cambiar en producción con variables de entorno):
- Usuario: `gestion`
- Contraseña: `infomira2026`

## Formato del Excel

Columnas (orden y mayúsculas no importan):

| Nombre | Celular | Estado |
|--------|---------|--------|
| María Pérez | 3115712505 | Instalada |
| Juan Pérez | 3001234567 | No instalada |

- **Instalada** → cuenta para la meta (si el celular es válido)
- **No instalada** → seguimiento; el motivo se asigna en la aplicación
- Celular: 10 dígitos

## Variables de entorno (producción)

| Variable | Uso |
|----------|-----|
| `APP_USER` | Usuario de acceso |
| `APP_PASSWORD` | Contraseña |
| `SECRET_KEY` | Firma de sesiones (fija, no cambiar entre reinicios) |
| `DATABASE_PATH` | Ruta del `.db` (en Railway: `/data/infomira_censo.db`) |

## Despliegue en Railway

1. Conectar el repositorio de GitHub al servicio.
2. Variables de entorno (arriba).
3. Volumen persistente con **Mount path: `/data`**.
4. `DATABASE_PATH=/data/infomira_censo.db`
5. Dominio público en Networking.

Cada `git push` a la rama conectada dispara un nuevo deploy automáticamente.

## Notas

- La base de datos no debe subirse a GitHub (está en `.gitignore`).
- Antes de cada deploy importante: descargar respaldo desde la app o desde el volumen en Railway.
- Para volver a la versión anterior: redeploy del tag `v1.0.0-mvp` en Railway (y restaurar `.db` si hiciera falta).

## Próximas mejoras (recomendación de proceso)

- Entregar de a un tema por deploy
- Checklist de prueba tras cada despliegue
- Tag + respaldo de BD antes de subir a producción
