#!/usr/bin/env bash
# Stem de violin (u otro instrumento melodico) -> partitura PDF.
#   transcribir.sh STEM.wav SALIDA_DIR ["6/8"] [GRID] ["Titulo"]
# Variables:
#   PY       python del venv            (default: python3)
#   MUSC_DIR clon de MTG/violin-transcription (obligatorio salvo que ya exista violin.mid)
#   MIX      audio para detectar pulsos (default: suma de todos los .wav junto al stem)
#   MSCORE   binario de MuseScore       (default: el de /Applications en macOS)
#   CLEAN_ARGS  flags extra para clean_midi.py, p.ej. "--snap --key Bm"
set -euo pipefail
STEM=$1; OUT=$2; TS=${3:-6/8}; GRID=${4:-}; TITLE=${5:-Violín}
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-python3}
MSCORE=${MSCORE:-"/Applications/MuseScore 4.app/Contents/MacOS/mscore"}
if [[ -z "$GRID" ]]; then
  [[ ${TS#*/} == 8 ]] && GRID=0.3333333333 || GRID=0.25   # corchea en x/8, semicorchea en x/4
fi
mkdir -p "$OUT"

echo "1/6 preproceso (mono 44.1k, pasa-altos 180 Hz contra el sangrado grave)"
ffmpeg -y -loglevel error -i "$STEM" -ac 1 -ar 44100 -af highpass=f=180 "$OUT/stem_mono.wav"

echo "2/6 transcripcion MUSC"
if [[ ! -s "$OUT/violin.mid" ]]; then
  "$PY" "$HERE/musc_transcribe.py" "$OUT/stem_mono.wav" "$OUT/violin.mid"
else echo "   (usa $OUT/violin.mid existente)"; fi

echo "3/6 pulsos con beat_this sobre la mezcla"
if [[ -z "${MIX:-}" ]]; then
  shopt -s nullglob; WAVS=("$(dirname "$STEM")"/*.wav); shopt -u nullglob
  if (( ${#WAVS[@]} > 1 )); then
    ARGS=(); for w in "${WAVS[@]}"; do ARGS+=(-i "$w"); done
    ffmpeg -y -loglevel error "${ARGS[@]}" -filter_complex "amix=inputs=${#WAVS[@]}:normalize=0,aformat=channel_layouts=mono" -ar 44100 "$OUT/mix.wav"
    MIX="$OUT/mix.wav"
  else MIX="$STEM"; fi
fi
"$(dirname "$PY")/beat_this" "$MIX" -o "$OUT/mix.beats" --gpu -1 2>/dev/null || "$PY" -m beat_this.cli "$MIX" -o "$OUT/mix.beats" --gpu -1

echo "4/6 limpieza"
"$PY" "$HERE/clean_midi.py" "$OUT/violin.mid" "$OUT/violin_clean.mid" ${CLEAN_ARGS:-}

echo "5/6 cuantizacion"
"$PY" "$HERE/midi2score.py" "$OUT/violin_clean.mid" "$OUT/mix.beats" "$OUT/partitura.musicxml" "$GRID" "$TS" "$TITLE"

echo "6/6 PDF con MuseScore"
"$MSCORE" -o "$OUT/partitura.pdf" "$OUT/partitura.musicxml" 2>/dev/null
echo "listo: $OUT/partitura.pdf"
