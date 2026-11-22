---
name: violin-a-partitura
description: Convierte en partitura (MusicXML + PDF) un instrumento melódico solista —sobre todo violín— que inge-sound/Demucs separó en un stem (normalmente `other.wav` con htdemucs_6s). Usala cuando pidan "pasame el violín a partitura", "transcribí la melodía del stem", "sacá las notas del violín", o cuando haya que limpiar una transcripción automática con notas pegadas en semitono, acordes falsos, sangrado del piano o notas fragmentadas.
---

# Violín (stem) → partitura

Pipeline: `ffmpeg` (mono + pasa-altos) → **MUSC** (audio→MIDI) → **beat_this** (pulsos sobre la mezcla) → **clean_midi.py** (limpieza) → **midi2score.py** (cuantización a la grilla de pulsos) → **MuseScore** (PDF).

```bash
PY=/ruta/venv/bin/python MUSC_DIR=/ruta/violin-transcription \
  .claude/skills/violin-a-partitura/scripts/transcribir.sh \
  stems/other.wav salida/ "6/8" "" "Título – violín"
```

Deja en `salida/`: `violin.mid` (crudo), `mix.beats`, `violin_clean.mid`, `partitura.musicxml`, `partitura.pdf`. Si `salida/violin.mid` ya existe no vuelve a correr MUSC, así que para ajustar la limpieza basta re-ejecutar (`CLEAN_ARGS="--snap --key Bm"`). Ejemplo completo en `examples/mis-noches-sin-ti/`.

## Setup (una vez)

```bash
python3.12 -m venv .venv
.venv/bin/pip install "torch<2.9" "torchaudio<2.9" music21 pretty_midi librosa gdown einops \
  rotary-embedding-torch mir_eval beat-this
git clone https://github.com/MTG/violin-transcription   # MUSC: clon externo, NO copiar al repo
```

- **Parche MUSC** (los pesos están guardados en CUDA): en `musc/model.py`, línea ~241, `torch.load(..., map_location='cpu')`. Sin eso falla en Mac/CPU. La primera corrida baja los pesos (~220 MB) con gdown.
- `torch<2.9`: torchaudio 2.9 cambia el backend de carga de audio y rompe MUSC/beat_this.
- **MuseScore 4** (`brew install --cask musescore`). En Linux pasá `MSCORE=mscore4`.
- `ffmpeg` en el PATH.

## Qué hace la limpieza (`clean_midi.py`, todo ajustable por flags, `-h`)

1. **rango/velocity**: fuera de G3–E7 o velocity < 50 → afuera.
2. **graves fuera de contorno**: nota > 7 semitonos debajo de la mediana local (±3 s) = sangrado de piano/bajo.
3. **monofonía**: notas simultáneas a ≤ 2 semitonos (vibrato partido) → gana la más saliente (velocity × √duración); blips débiles dentro de una nota larga se van; la nota anterior se corta cuando entra la siguiente. `--dyads` permite dobles cuerdas reales (≥ 3ª, ambas ≥ 0,4 s).
4. **fragmentos**: misma altura, hueco ≤ 80 ms y uno de los dos < 0,2 s → se unen (re-arcada). Repeticiones reales más largas se respetan.
5. **cortas**: < 0,1 s, o cortas y mucho más débiles que la nota pegada (armónico/ataque falso).
6. **aisladas**: cortas y sin vecinos a menos de 1 s.
7. **cromáticos** (solo con `--snap`): notas < 0,25 s fuera de la escala (+ sensible en menor) → nota de la escala más cercana al contorno.
8. **legato**: rellena silencios < 0,3 s.

`midi2score.py` además: regulariza la grilla de pulsos (saca duplicados, rellena huecos), resuelve colisiones de cuantización sin crear acordes (`--chords` para permitirlos), escribe silencios explícitos y deletrea según la armadura (A♯ en si menor, no B♭). `--offset N` corre las barras de compás N pulsos.

## Consejos

- **Pulsos sobre la mezcla, no sobre el stem**: el script suma todos los `.wav` junto al stem. Sobre el violín solo, beat_this pierde pulsos y el ritmo sale comprimido. Forzá otra fuente con `MIX=cancion.wav`.
- Compás: 6/8 → grilla de corchea (`0.3333333333`); 3/4 o 2/4 → semicorchea (`0.25`). Si la barra cae corrida, probá `--offset 1`.
- Para otro instrumento melódico, ajustá `--low/--high` en `CLEAN_ARGS` (MUSC está entrenado en violín; para otros usá basic-pitch y salteá el paso 2 dejando un `violin.mid` en la salida).

## Limitaciones conocidas

- Es un borrador para corregir en MuseScore, no una partitura final: ritmo aproximado (rubato), sin articulaciones, arcos, dinámicas ni 8va.
- Donde el violín calla y el piano toca (intros, puentes), quedan notas sueltas del sangrado: revisá esos compases a oído.
- La monofonía elimina dobles cuerdas reales salvo `--dyads`.
- Los saltos de octava de MUSC (armónicos) no siempre se detectan.

## Licencias

MUSC (MTG/violin-transcription) es **AGPL-3.0**: se usa como clon externo vía `MUSC_DIR`, sin copiar su código ni pesos a este repo. beat_this es MIT, music21 BSD, pretty_midi MIT. Los scripts de `scripts/` son propios del repo.
