# InfoMIRA Censo - Comunidad de Carvajal

Sistema interno de seguimiento del censo de instalación de la App InfoMIRA.

## Requisitos

- Python 3.10 o superior

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv env

# 2. Activar entorno virtual
# Windows:
env\Scripts\activate
# Mac/Linux:
source env/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar el servidor
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Acceso

Abrir en el navegador: http://127.0.0.1:8000/login

**Credenciales por defecto:**
- Usuario: `gestion`
- Contraseña: `infomira2026`

> Cambia la contraseña en producción editando `app/auth.py`.

## Formato del Excel

El archivo debe tener exactamente estas columnas (el orden y mayúsculas no importan):

| Nombre | Celular | Estado |
|--------|---------|--------|
| María Pérez | 3115712505 | Instalada |

- Solo se cargan registros con **Estado = Instalada**
- El celular debe tener 10 dígitos

## Funcionalidades del MVP

- Login con usuario compartido
- Dashboard con total, avance a la meta (500) y gráfica diaria
- Carga de Excel + selección de fuente y fecha
- Detección de duplicados por celular
- Pendientes de revisión (edición manual)
- Generación de informe semanal para WhatsApp

## Notas

- La base de datos (`infomira_censo.db`) se crea automáticamente
- No subas este archivo a repositorios públicos (contiene datos personales)

## Despliegue en Railway

### 1. Crear cuenta y proyecto
1. Entra a [railway.app](https://railway.app) y crea una cuenta
2. New Project → Deploy from GitHub repo (o sube el código)

### 2. Variables de entorno
En la pestaña **Variables** del servicio agrega:

| Variable | Valor recomendado |
|----------|-------------------|
| `APP_USER` | `gestion` |
| `APP_PASSWORD` | *(elige una contraseña segura)* |
| `SECRET_KEY` | *(una cadena larga y aleatoria)* |

Para generar un SECRET_KEY seguro puedes usar:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Volumen persistente (importante para SQLite)
1. En el servicio → **Settings** → **Volumes**
2. Add Volume
3. Mount path: `/app`  (o la ruta donde se genera el .db)
4. Esto evita que se pierdan los datos al reiniciar

> Nota: Si el volumen se monta en otra ruta, ajusta `app/database.py` para que apunte a esa ruta.

### 4. Dominio
En **Settings → Networking → Generate Domain** obtendrás una URL pública tipo:
`https://infomira-censo-production.up.railway.app`

### 5. Arranque
Railway detectará el `Procfile` o el `railway.toml` y arrancará con:
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

