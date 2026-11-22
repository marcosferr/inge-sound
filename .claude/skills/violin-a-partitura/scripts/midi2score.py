#!/usr/bin/env python3
"""midi2score.py  notas.mid pulsos.beats salida.musicxml [GRID] [TS] [TITULO] [opciones]

Convierte un MIDI "en segundos" (salida de MUSC/basic-pitch, idealmente ya pasado por
clean_midi.py) en partitura cuantizada, usando la grilla de pulsos de beat_this para
absorber el rubato.

  GRID   resolucion en pulsos (0.3333333333 = corchea en 6/8; 0.25 = semicorchea en x/4)
  TS     compas, p.ej. "6/8" (pulso = negra con puntillo) o "3/4"
"""
import argparse

import numpy as np
import pretty_midi
from music21 import chord, instrument, key, metadata, meter, note, stream, tempo

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("mid")
ap.add_argument("beats")
ap.add_argument("out")
ap.add_argument("grid", nargs="?", type=float, default=0.25)
ap.add_argument("ts", nargs="?", default=None)
ap.add_argument("title", nargs="?", default="Violin")
ap.add_argument("--min-dur", type=float, default=0.07, help="descarta notas mas cortas (s)")
ap.add_argument("--low", type=int, default=55)
ap.add_argument("--high", type=int, default=103)
ap.add_argument("--no-regularize", action="store_true",
                help="no limpiar la grilla de pulsos (por defecto: saca pulsos duplicados y rellena huecos)")
ap.add_argument("--offset", type=float, default=0.0,
                help="corre todo N pulsos (para ajustar donde cae la barra de compas)")
ap.add_argument("--chords", action="store_true",
                help="permitir acordes si dos notas caen en el mismo ataque (por defecto: monodico)")
ap.add_argument("--composer", default="Transcripción automática (MUSC + beat_this)")
a = ap.parse_args()
GRID, TS = a.grid, a.ts

# --- pulsos y compases (archivo .beats de beat_this: tiempo \t numero_de_pulso) ---
b = np.loadtxt(a.beats, ndmin=2)
beats, pos = b[:, 0], b[:, 1].astype(int)
step = np.median(np.diff(beats))
first_down_t = beats[np.where(pos == 1)[0][0]] if (pos == 1).any() else beats[0]
if not a.no_regularize:
    # 1) pulsos pegados (<0.6 pulso) son duplicados; 2) huecos de k pulsos se subdividen
    clean = [beats[0]]
    for t in beats[1:]:
        if t - clean[-1] >= 0.6 * step:
            clean.append(t)
    filled = [clean[0]]
    for t in clean[1:]:
        k = int(round((t - filled[-1]) / step))
        if k > 1:
            filled += list(np.linspace(filled[-1], t, k + 1)[1:-1])
        filled.append(t)
    beats = np.array(filled)
    step = np.median(np.diff(beats))
bpm = 60.0 / step
if TS:
    num, den = map(int, TS.split("/"))
    beats_per_bar = num // 3 if den == 8 and num % 3 == 0 else num
else:
    d = np.where(pos == 1)[0]
    beats_per_bar = int(np.median(np.diff(d))) if len(d) > 1 else 4
first_down = int(np.argmin(np.abs(beats - first_down_t)))

idx = np.arange(len(beats), dtype=float)


def sec2beat(t):
    """segundos -> pulsos, interpolando entre pulsos detectados (sigue el rubato)."""
    if t < beats[0]:
        return (t - beats[0]) / step
    if t > beats[-1]:
        return idx[-1] + (t - beats[-1]) / step
    return float(np.interp(t, beats, idx))


def q(x):
    return round(x / GRID) * GRID


# --- leer notas, filtrar, cuantizar ---
pm = pretty_midi.PrettyMIDI(a.mid)
evs = []
for inst in pm.instruments:
    for n in inst.notes:
        if n.end - n.start < a.min_dur or not (a.low <= n.pitch <= a.high):
            continue
        on, off = q(sec2beat(n.start)), q(sec2beat(n.end))
        if off <= on:
            off = on + GRID
        evs.append([on, off, n.pitch, (n.end - n.start) * n.velocity])

# desplazar para que el primer downbeat caiga en el inicio de compas (anacrusa incluida)
min_rel = min(e[0] for e in evs) - first_down
shift = -first_down + beats_per_bar * int(np.ceil(max(0.0, -min_rel) / beats_per_bar)) + a.offset
for e in evs:
    e[0] += shift
    e[1] += shift
evs = sorted((e for e in evs if e[0] >= 0), key=lambda e: (e[0], -e[3]))

# colisiones de cuantizacion: dos notas en el mismo ataque. En modo monodico la mas
# saliente se queda el ataque y la otra se corre a la siguiente casilla libre si le alcanza
# la duracion; si no, se descarta.
groups, dropped, moved = {}, 0, 0
for on, off, p, sal in evs:
    if on in groups and not a.chords:
        prev = groups[on][0]
        if p == prev[1]:
            continue
        # la que ataca despues en el tiempo real pasa a la casilla siguiente
        nxt = on + GRID
        if nxt < off and nxt not in groups:
            groups[nxt] = [(off, p)]
            moved += 1
        else:
            dropped += 1
        continue
    groups.setdefault(on, []).append((off, p))
onsets = sorted(groups)

BEAT_QL = 1.5 if TS and TS.split("/")[1] == "8" else 1.0
part = stream.Part()
part.insert(0, instrument.Violin())
part.insert(0, meter.TimeSignature(TS or f"{beats_per_bar}/4"))
part.insert(0, tempo.MetronomeMark(number=round(bpm), referent=BEAT_QL))
raw = []
for i, on in enumerate(onsets):
    off = max(o for o, _ in groups[on])
    if i + 1 < len(onsets):
        off = min(off, onsets[i + 1])
    pitches = sorted({p for _, p in groups[on]})[-2:]  # violin: max 2 cuerdas
    raw.append((on, max(GRID, off - on), pitches))

# tonalidad -> ortografia (A# en si menor, no Bb)
tmp = stream.Stream()
for on, dur, ps in raw:
    for p in ps:
        n = note.Note(p)
        n.quarterLength = dur
        tmp.append(n)
k = tmp.analyze("key")
names = SHARPS if k.sharps >= 0 else FLATS


def mk(p):
    return note.Note(f"{names[p % 12]}{p // 12 - 1}")


cursor = 0.0
for on, dur, ps in raw:
    if on > cursor + 1e-6:  # silencios explicitos (si no, MuseScore los deja invisibles)
        r = note.Rest()
        r.quarterLength = (on - cursor) * BEAT_QL
        part.insert(cursor * BEAT_QL, r)
    el = mk(ps[0]) if len(ps) == 1 else chord.Chord([mk(p) for p in ps])
    el.quarterLength = dur * BEAT_QL
    part.insert(on * BEAT_QL, el)
    cursor = on + dur

part.insert(0, key.KeySignature(k.sharps))
score = stream.Score()
score.insert(0, metadata.Metadata(title=a.title, composer=a.composer))
score.insert(0, part)
score = score.makeNotation()
score.write("musicxml", a.out)
print(f"tempo~{bpm:.0f} bpm, compas {TS or beats_per_bar}, tonalidad {k}, "
      f"notas {len(onsets)} (colisiones: {moved} corridas, {dropped} descartadas)")
