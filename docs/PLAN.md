# Plan — Inge Sound (wrapper web de Demucs)

## 1. Objetivo

Una aplicación web simple, autocontenida, que envuelve **Demucs (Meta AI)** y expone
**todas** sus capacidades de separación de fuentes a través de una UI y una API REST.

No reimplementa nada de Demucs: es un *wrapper* fiel. Cada bandera del CLI de Demucs
está disponible en la API y en la interfaz.

## 2. Arquitectura

```
┌──────────────┐   HTTP/multipart   ┌───────────────┐   dispatch   ┌──────────────┐
│  Frontend    │ ─────────────────► │   FastAPI     │ ───────────► │   Worker     │
│  React + Vite│ ◄───── SSE ─────── │   (API)       │              │ thread│celery │
└──────────────┘                    └───────┬───────┘              └──────┬───────┘
                                            │                             │
                                            ▼                             ▼
                                   ┌────────────────────────────────────────┐
                                   │  DATA_DIR (jobs/<id>/: job.json,       │
                                   │  input/, output/, job.log)             │
                                   └────────────────────────────────────────┘
                                                      │
                                                      ▼
                                             `python -m demucs ...`
```

### Decisiones

| Tema | Decisión | Motivo |
|---|---|---|
| Motor | Demucs vía subproceso `python -m demucs` | Es el *wrapper* más fiel: toda bandera nueva del CLI queda disponible sin tocar el core. Aísla fallos/OOM del proceso API. |
| Progreso | Parseo de la barra `tqdm` en stdout/stderr | No requiere parchear Demucs. Los *bag models* (4 sub-modelos) se detectan por reinicio de la barra. |
| Estado | Un `job.json` atómico por trabajo en disco | Funciona igual con worker en proceso o en otro contenedor. Cero dependencias. |
| Cola | `thread` (por defecto) o `celery` + Redis | Dev con un solo contenedor; producción con workers GPU escalables. Mismo código de ejecución. |
| Streaming | Endpoints con soporte de `Range` | Necesario para el reproductor multipista del navegador. |

## 3. Cobertura de features de Demucs

Todas las banderas de `demucs.separate` quedan expuestas:

`-n/--name`, `-s/--sig`, `--repo`, `-d/--device`, `--shifts`, `--overlap`,
`--no-split`, `--segment`, `--two-stems`, `--other-method`, `--int24`, `--float32`,
`--clip-mode`, `--flac`, `--mp3`, `--mp3-bitrate`, `--mp3-preset`, `-j/--jobs`,
`--filename`, `-v/--verbose`.

Modelos: `htdemucs`, `htdemucs_ft`, `htdemucs_6s`, `hdemucs_mmi`, `mdx`, `mdx_extra`,
`mdx_q`, `mdx_extra_q`, más firmas locales (`--sig` + `--repo`).

El catálogo (`backend/app/catalog.py`) es la única fuente de verdad: describe cada
opción con tipo, rango, valor por defecto y ayuda. La API lo publica en
`GET /api/capabilities` y el frontend **genera el formulario a partir de ahí**, así que
agregar una opción nueva es una sola entrada en el catálogo.

### Adaptación a la versión instalada

La superficie del CLI cambia entre versiones de Demucs: la 4.0.1 publicada **no
tiene** `--other-method` y su `--clip-mode` solo acepta `rescale` y `clamp`,
mientras que la rama de desarrollo agrega ambos. El servidor parsea
`demucs --help` una vez y con eso marca lo no disponible en `/api/capabilities`,
lo omite al construir el comando, recorta los presets afectados y rechaza con un
motivo legible cualquier pedido que lo use. Así el wrapper sirve tanto la versión
publicada como una más nueva sin cambios de código.

## 4. Funcionalidades de la app

- Subida múltiple (batch) con drag & drop; validación de tamaño/extensión.
- Presets (Rápido / Equilibrado / Máxima calidad / Karaoke) + modo avanzado con todas las banderas.
- Cola de trabajos con progreso en vivo (SSE, con *fallback* a polling).
- Reproductor multipista sincronizado: volumen, mute, solo y descarga por pista.
- Descarga individual o ZIP de todo el trabajo.
- Cancelar, reintentar y borrar trabajos; log completo del proceso.
- Limpieza automática por retención (`RETENTION_HOURS`).

## 5. Entregables

1. `backend/` — FastAPI + catálogo + runner + cola + tests (pytest).
2. `frontend/` — React 19 + Vite + TypeScript + Tailwind.
3. `docker-compose.yml` (CPU) y `docker-compose.gpu.yml` (CUDA + Celery + Redis).
4. `README.md` con arranque en local, Docker y despliegue con GPU.
5. CI (GitHub Actions): tests del backend + build del frontend.
