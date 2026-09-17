# InfoMIRA Censo

Aplicación web interna para el censo de instalación de la App InfoMIRA en la comunidad de Carvajal.

Acceso restringido (login). No es un sitio público.

## Qué hace

- Carga listados Excel y evita contar dos veces a la misma persona (identificador: celular).
- Dashboard de avance (meta del equipo: 500), con el dato de sede nacional como métrica principal.
- Consulta de personas, seguimiento de quienes no han instalado la App y historial de cargas.
- Informe semanal listo para copiar a WhatsApp.

## Requisitos

- Python 3.10 o superior
- Git

## Instalación local (Linux)

```bash
git clone https://github.com/crearbots/censo.git
cd censo
git checkout master

python3 -m venv env
source env/bin/activate
pip install -r requirements.txt

python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abrir: http://127.0.0.1:8000/login

Las credenciales se definen con variables de entorno (`APP_USER`, `APP_PASSWORD`). En local, si no las defines, la app usa valores de desarrollo.

La base `infomira_censo.db` se crea sola. No la subas a GitHub.

## Formato del Excel

Columnas (el orden y las mayúsculas no importan): **Nombre**, **Celular**, **Estado**.

| Estado | Qué ocurre |
|--------|------------|
| Instalada | Entra al censo si el celular es válido (10 dígitos) |
| No instalada | Queda en seguimiento; el motivo se asigna en la app |

Reglas importantes:

- El celular es el identificador. Si ya existe, se actualiza; no se duplica.
- Si la persona ya es Instalada, un listado posterior en “No instalada” no la revierte.
- `fecha_listado` se guarda la primera vez y **no se pisa** al volver a subir el mismo listado.

Al cargar hay que indicar: fuente, fecha del listado y equipo que carga.

## Variables de entorno (producción)

| Variable | Uso |
|----------|-----|
| `APP_USER` | Usuario de acceso |
| `APP_PASSWORD` | Contraseña |
| `SECRET_KEY` | Firma de sesiones (fija entre reinicios) |
| `DATABASE_PATH` | Ruta del archivo `.db` |

En Railway el volumen va en `/data` y `DATABASE_PATH=/data/infomira_censo.db`.

## Despliegue

Fuente de verdad: GitHub, rama **`master`**. Un push a `master` dispara el deploy en Railway.

Antes de un deploy:

1. Descargar respaldo de la base (producción).
2. Probar en local.
3. `git pull origin master` y luego push a `master`.
4. Verificar el deploy y hacer login + una carga de prueba.

## Versiones

| Tag | Qué incluye |
|-----|-------------|
| `v1.0.0-mvp` | Primera versión en producción |
| `v1.1.0` | Personas, dato nacional, historial, No instalada, Excel robusto |
| `v1.2.0` | Dashboard de informe mensual; avance con dato nacional |

## Privacidad

No subir a GitHub bases `.db`, respaldos ni Excel con datos reales de la comunidad.


## UI: botones

- Un primario azul por pantalla.
- WhatsApp / copiar informe: verde.
- Eliminar: rojo y siempre con confirmación.
