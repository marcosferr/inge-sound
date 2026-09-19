# Imagen CPU. Para GPU usá backend/Dockerfile.gpu.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_HOME=/models \
    INGE_DATA_DIR=/data

# ffmpeg amplía los formatos de entrada (m4a, mp4, webm…); libsndfile1 es el
# backend que usa soundfile/torchaudio para leer y escribir audio.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch se instala primero desde el índice CPU para no traer las ruedas CUDA
# (unos 2 GB de más).
# requirements.txt chains -r requirements-api.txt, so both must land here.
COPY requirements*.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.2.2 torchaudio==2.2.2 \
    && pip install -r requirements.txt

COPY app ./app

RUN mkdir -p /data /models && useradd --create-home --uid 1000 inge \
    && chown -R inge:inge /data /models /app
USER inge

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
