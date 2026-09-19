# Inge Sound

Aplicación web para **separación de pistas** (stem separation) construida como
wrapper sobre **[Demucs](https://github.com/adefossez/demucs)**, el modelo de
código abierto de Meta AI.

Subís un archivo, elegís el modelo y obtenés las pistas separadas —voces,
batería, bajo, guitarra, piano y demás— con un reproductor multipista para
escuchar la mezcla antes de descargar.

No reimplementa nada de Demucs: **expone todas sus opciones**. Cada bandera del
CLI está disponible en la API y en la interfaz.

---

## Qué hace

- **Todos los modelos**: `htdemucs`, `htdemucs_ft`, `htdemucs_6s` (6 pistas, con
  guitarra y piano), `hdemucs_mmi`, `mdx`, `mdx_extra` y sus variantes
  cuantizadas, más modelos entrenados localmente vía `--sig` y `--repo`.
- **Todas las opciones**: shifts, solapamiento, tamaño de bloque, dispositivo,
  procesos paralelos, modo dos pistas (karaoke), formato de salida
  (WAV/FLAC/MP3), profundidad de bits, bitrate y preset de MP3, manejo de
  clipping y plantilla de nombres.
- **Presets** para los casos comunes y modo avanzado para el resto.
- **Lotes**: varios archivos por trabajo.
- **Progreso real** mientras corre, con estimación de tiempo restante.
- **Reproductor multipista** sincronizado, con volumen, mute y solo por pista.
- **Descarga** individual o ZIP de todo el trabajo.
- **Cancelar, reintentar y ver el log** completo del proceso.
- **Retención automática**: los archivos se borran solos pasado el plazo.

### Se adapta a la versión de Demucs instalada

El CLI de Demucs cambia entre versiones: la 4.0.1 no tiene `--other-method` y su
`--clip-mode` no acepta `none`, mientras que la rama de desarrollo sí. El
servidor lee `demucs --help` al arrancar y, con eso:

- marca las opciones no disponibles en `GET /api/capabilities`, así la interfaz
  no las ofrece;
- las omite al construir el comando en vez de pasarlas y que Demucs las rechace;
- recorta los presets que las usaban, avisando qué quedó afuera;
- responde `422` con un motivo legible si alguien las pide igual por API.

---

## Arquitectura

```
Frontend (React + Vite)  ──HTTP/SSE──▶  API (FastAPI)  ──▶  Worker  ──▶  python -m demucs
                                             │                 │
                                             └──── DATA_DIR ◀──┘
                                       (job.json, input/, output/, job.log)
```

| Componente | Rol |
|---|---|
| `backend/app/catalog.py` | Describe cada modelo y cada opción. Única fuente de verdad; la UI se genera de acá. |
| `backend/app/runner.py` | Arma el `argv` de Demucs, lanza el subproceso y traduce la barra de progreso. |
| `backend/app/worker.py` | Corre un trabajo de punta a punta y registra el resultado. |
| `backend/app/jobstore.py` | Estado en disco, un directorio por trabajo. Sin base de datos. |
| `backend/app/queue.py` | Despacho: hilos en proceso o Celery + Redis. |
| `frontend/` | Interfaz React que se arma sola desde `/api/capabilities`. |

**Por qué subproceso y no importar la librería**: cada bandera nueva del CLI
queda disponible sin tocar el wrapper, y un out-of-memory o un segfault del
modelo se lleva puesto al hijo, no al servidor.

---

## Arranque rápido (Docker)

```bash
cp .env.example .env
docker compose up --build
```

La app queda en <http://localhost:8080> y la API en <http://localhost:8080/api>.
La primera separación descarga el modelo (unos cientos de MB); queda cacheado en
el volumen `models`.

### Con GPU

Requiere el [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
en el host. El overlay agrega CUDA, Redis y workers Celery separados de la API:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build

# Más workers concurrentes:
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --scale worker=3
```

---

## Desarrollo local

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate

# torch primero, desde el índice que corresponda al hardware:
pip install torch==2.2.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cpu
# (para CUDA 12.1: --index-url https://download.pytorch.org/whl/cu121)

pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Hace falta además **ffmpeg** en el sistema para leer mp3, m4a y contenedores de
video (`apt install ffmpeg` / `brew install ffmpeg`). Sin ffmpeg solo se pueden
procesar los formatos que soporta libsndfile (wav, flac, ogg).

> **Sobre las versiones de torch.** Están fijadas a propósito. `torchaudio >= 2.9`
> eliminó los backends clásicos y exige `torchcodec`, que Demucs 4.0.1 no usa:
> falla con `TorchCodec is required for load_with_torchcodec`. Y `demucs 4.0.1`
> junto con `torch 2.2.x` están compilados contra numpy 1.x.

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, con /api hacia el puerto 8000
```

### Tests

```bash
make test   # o: cd backend && pytest -q
make lint
```

Los tests usan un Demucs simulado, así que corren en segundos y sin descargar
modelos. La superficie del CLI está parametrizada por fixtures (`legacy_demucs`,
`modern_demucs`), de modo que la adaptación a distintas versiones también se
prueba.

---

## API

Documentación interactiva en `/api/docs`.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Estado del servicio. |
| `GET` | `/api/capabilities` | Modelos, opciones, presets y límites del servidor. |
| `POST` | `/api/jobs` | Crea un trabajo. `multipart/form-data` con `files` y `options` (JSON). |
| `GET` | `/api/jobs` | Lista trabajos (`?status=`, `?limit=`, `?offset=`). |
| `GET` | `/api/jobs/{id}` | Estado de un trabajo. |
| `GET` | `/api/jobs/{id}/events` | Progreso en vivo (SSE). |
| `GET` | `/api/jobs/{id}/log` | Salida completa del proceso de Demucs. |
| `POST` | `/api/jobs/{id}/cancel` | Cancela un trabajo en curso. |
| `POST` | `/api/jobs/{id}/retry` | Vuelve a separar los mismos archivos. |
| `DELETE` | `/api/jobs/{id}` | Borra el trabajo y sus archivos. |
| `GET` | `/api/jobs/{id}/stems/{stem}` | Reproduce una pista (soporta `Range`). |
| `GET` | `/api/jobs/{id}/stems/{stem}/download` | Descarga una pista. |
| `GET` | `/api/jobs/{id}/download` | ZIP con todas las pistas. |

### Ejemplo

```bash
# Karaoke en MP3
curl -X POST http://localhost:8080/api/jobs \
  -F "files=@cancion.mp3" \
  -F 'options={"model":"htdemucs","two_stems":"vocals","format":"mp3","mp3_bitrate":320}'

# Seguir el progreso
curl -N http://localhost:8080/api/jobs/<id>/events

# Descargar todo
curl -OJ http://localhost:8080/api/jobs/<id>/download
```

### Opciones de separación

Todas opcionales; los valores por defecto son los de Demucs.

| Campo | Tipo | Bandera | Por defecto |
|---|---|---|---|
| `model` | enum | `-n` | `htdemucs` |
| `signature` | string | `-s` | — |
| `repo` | string | `--repo` | — |
| `device` | `auto\|cuda\|mps\|cpu` | `-d` | `auto` |
| `shifts` | 0–20 | `--shifts` | `1` |
| `overlap` | 0–0.99 | `--overlap` | `0.25` |
| `split` | bool | `--no-split` | `true` |
| `segment` | 1–3600 | `--segment` | — |
| `jobs` | 1–32 | `-j` | `1` |
| `two_stems` | enum de pistas | `--two-stems` | — |
| `other_method` | `add\|minus\|none` | `--other-method` | `add` |
| `format` | `wav\|flac\|mp3` | `--mp3` / `--flac` | `wav` |
| `bit_depth` | `int16\|int24\|float32` | `--int24` / `--float32` | `int16` |
| `mp3_bitrate` | 64–320 | `--mp3-bitrate` | `320` |
| `mp3_preset` | 2–7 | `--mp3-preset` | `2` |
| `clip_mode` | `rescale\|clamp\|none` | `--clip-mode` | `rescale` |
| `filename` | plantilla | `--filename` | `{track}/{stem}.{ext}` |
| `verbose` | bool | `-v` | `false` |

---

## Configuración

Ver [`.env.example`](.env.example). Todas las variables llevan el prefijo `INGE_`.

| Variable | Por defecto | Para qué |
|---|---|---|
| `INGE_DATA_DIR` | `./data` | Dónde viven los trabajos. |
| `INGE_MAX_UPLOAD_MB` | `200` | Tamaño máximo por archivo. |
| `INGE_MAX_FILES_PER_JOB` | `10` | Archivos por trabajo. |
| `INGE_RETENTION_HOURS` | `48` | Cuánto sobreviven los resultados. |
| `INGE_QUEUE_BACKEND` | `thread` | `thread` o `celery`. |
| `INGE_WORKER_CONCURRENCY` | `1` | Separaciones simultáneas (backend `thread`). |
| `INGE_REDIS_URL` | `redis://localhost:6379/0` | Broker de Celery. |
| `INGE_JOB_TIMEOUT_SECONDS` | `10800` | Tope por separación. `0` lo desactiva. |
| `INGE_CORS_ORIGINS` | `localhost:5173,localhost:3000` | Orígenes permitidos. |

---

## Rendimiento

Separar audio con IA en CPU es lento: contá aproximadamente el mismo tiempo que
dura la canción con `htdemucs` y `shifts=1`, y cuatro veces más con
`htdemucs_ft`. Con GPU baja a una fracción.

Palancas, de mayor a menor impacto:

- **GPU** (`device: cuda`): el salto más grande, entre 10 y 20 veces.
- **`shifts`**: multiplica directamente el tiempo. `0` para previsualizar.
- **Modelo**: `htdemucs` es el equilibrio; `htdemucs_ft` corre cuatro redes.
- **`jobs`**: en CPU, subirlo aprovecha más núcleos a costa de memoria.
- **`segment`**: bajalo si la GPU se queda sin memoria.

Con `INGE_QUEUE_BACKEND=celery` los workers escalan aparte de la API, que es lo
que conviene si esperás usuarios concurrentes.

---

## Notas de seguridad

Esta versión no trae autenticación: pensala para una red interna o poné un proxy
con auth adelante. Lo que sí hace:

- Sanea los nombres de archivo y valida extensiones y tamaños antes de escribir.
- Aborta la subida en cuanto supera el límite, sin bufferear el archivo entero.
- Valida las rutas de las pistas contra el directorio del trabajo antes de
  servirlas.
- Nunca pasa la entrada del usuario por una shell: el comando se arma como lista
  de argumentos a partir de opciones ya validadas.

---

## Licencia y créditos

El motor de separación es [Demucs](https://github.com/adefossez/demucs), de Meta
AI, bajo licencia MIT. Los modelos preentrenados se descargan de sus
repositorios oficiales la primera vez que se usan.

Respetá los derechos de autor del material que proceses.
