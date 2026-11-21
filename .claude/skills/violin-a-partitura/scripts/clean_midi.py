#!/usr/bin/env python3
"""clean_midi.py  entrada.mid salida.mid [opciones]

Limpia la salida de un transcriptor automatico (MUSC, basic-pitch...) para que la
partitura de un instrumento melodico (violin, flauta, voz) quede legible.
Trabaja sobre eventos de nota en segundos, ANTES de cuantizar.

Reglas, en este orden (cada una se puede ajustar o apagar por flag):
  1. rango      descarta notas fuera del rango del instrumento o muy debiles.
  2. graves     descarta notas muy por debajo del contorno melodico local
                (tipico: sangrado del piano/bajo en el stem separado).
  3. mono       colapsa todo a una sola linea: notas a <=2 semitonos que suenan
                juntas son vibrato/deriva -> gana la mas saliente; notas debiles
                contenidas dentro de una nota fuerte se van; si entra una nota nueva,
                la anterior se corta (legato). Dobles cuerdas solo con --dyads.
  4. unir       une fragmentos consecutivos de la misma altura separados por un hueco
                chico cuando uno de los dos es corto (re-arcada / vibrato partido).
  5. cortas     descarta notas mas cortas que --min-dur.
  6. aisladas   descarta notas cortas sin vecinos cerca (blips).
  7. cromatico  (opcional, --snap) lleva notas cortas fuera de la escala a la nota
                de la escala mas cercana al contorno.
  8. legato     estira cada nota hasta la siguiente si el silencio es chico.
"""
import argparse
import sys
from dataclasses import dataclass

import numpy as np
import pretty_midi

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
# perfiles Krumhansl-Kessler
KK_MAJ = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KK_MIN = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


@dataclass
class N:
    start: float
    end: float
    pitch: int
    vel: int

    @property
    def dur(self):
        return self.end - self.start

    @property
    def sal(self):  # saliencia: fuerte y largo gana
        return self.vel * np.sqrt(max(self.dur, 1e-3))


def load(path):
    pm = pretty_midi.PrettyMIDI(path)
    ns = [N(n.start, n.end, n.pitch, n.velocity) for i in pm.instruments if not i.is_drum for n in i.notes]
    return sorted(ns, key=lambda n: (n.start, -n.sal))


def save(ns, path, program=40):
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=program, name="clean")
    inst.notes = [pretty_midi.Note(n.vel, n.pitch, n.start, n.end) for n in ns]
    pm.instruments.append(inst)
    pm.write(path)


def estimate_key(ns):
    """(tonica, 'major'|'minor') por correlacion Krumhansl con histograma ponderado por duracion."""
    h = np.zeros(12)
    for n in ns:
        h[n.pitch % 12] += n.dur
    best = None
    for t in range(12):
        for prof, mode in ((KK_MAJ, "major"), (KK_MIN, "minor")):
            r = np.corrcoef(h, np.roll(prof, t))[0, 1]
            if best is None or r > best[0]:
                best = (r, t, mode)
    return best[1], best[2]


def scale_pcs(tonic, mode):
    rel = tonic if mode == "major" else (tonic + 3) % 12  # menor -> relativa mayor
    pcs = {(rel + s) % 12 for s in MAJOR}
    if mode == "minor":
        pcs.add((tonic + 11) % 12)  # sensible de la menor armonica (A# en si menor)
    return pcs


def parse_key(s):
    s = s.strip()
    mode = "minor" if s.endswith("m") else "major"
    name = s[:-1] if mode == "minor" else s
    flats = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    name = flats.get(name, name)
    return NAMES.index(name), mode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--low", type=int, default=55, help="nota MIDI mas grave (55=G3, cuerda al aire del violin)")
    ap.add_argument("--high", type=int, default=100, help="nota MIDI mas aguda (100=E7)")
    ap.add_argument("--min-vel", type=int, default=50, help="velocity minima")
    ap.add_argument("--low-outlier", type=float, default=7,
                    help="semitonos por debajo de la mediana local para considerar una nota sangrado grave (0=apaga)")
    ap.add_argument("--outlier-window", type=float, default=3.0, help="ventana (s) para la mediana local")
    ap.add_argument("--dyads", action="store_true",
                    help="permitir dobles cuerdas reales (intervalo >= --dyad-min, ambas sostenidas)")
    ap.add_argument("--dyad-min", type=int, default=3, help="intervalo minimo de una doble cuerda (semitonos)")
    ap.add_argument("--dyad-dur", type=float, default=0.4, help="duracion minima de ambas notas de la doble cuerda")
    ap.add_argument("--onset-tol", type=float, default=0.08, help="dos ataques a menos de esto son simultaneos (s)")
    ap.add_argument("--weak-ratio", type=float, default=0.75,
                    help="una nota contenida en otra y con velocity < ratio*la otra se descarta")
    ap.add_argument("--merge-gap", type=float, default=0.08, help="hueco maximo para unir misma altura (s)")
    ap.add_argument("--frag", type=float, default=0.2,
                    help="se une si alguno de los dos fragmentos dura menos que esto (s)")
    ap.add_argument("--min-dur", type=float, default=0.1, help="duracion minima de nota (s)")
    ap.add_argument("--isolated", type=float, default=1.0, help="sin vecinos a menos de X s = aislada")
    ap.add_argument("--isolated-dur", type=float, default=0.3, help="...y mas corta que esto -> se descarta")
    ap.add_argument("--snap", action="store_true", help="ajustar notas cortas fuera de escala a la escala")
    ap.add_argument("--snap-dur", type=float, default=0.25, help="solo notas mas cortas que esto (s)")
    ap.add_argument("--key", default=None, help="tonalidad para --snap, p.ej. Bm o D (si no, se estima)")
    ap.add_argument("--legato", type=float, default=0.3, help="rellenar silencios menores a esto (s); 0=apaga")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args(argv)

    ns = load(a.inp)
    stats = [("entrada", len(ns))]

    # 1. rango y velocity
    ns = [n for n in ns if a.low <= n.pitch <= a.high and n.vel >= a.min_vel]
    stats.append(("rango/velocity", len(ns)))

    # 2. graves fuera de contorno (sangrado)
    if a.low_outlier > 0 and ns:
        gmed = np.median([n.pitch for n in ns])
        keep = []
        for n in ns:
            nb = [m for m in ns if m is not n and abs(m.start - n.start) <= a.outlier_window]
            if nb:
                w = np.array([m.dur * m.vel for m in nb])
                p = np.array([m.pitch for m in nb])
                order = np.argsort(p)
                cw = np.cumsum(w[order])
                med = p[order][np.searchsorted(cw, cw[-1] / 2)]
            else:
                med = gmed
            if n.pitch < med - a.low_outlier:
                continue
            keep.append(n)
        ns = keep
    stats.append(("graves fuera de contorno", len(ns)))

    # 3. monofonia
    out = []
    for n in ns:
        if not out:
            out.append(n)
            continue
        k = out[-1]
        if n.start >= k.end - 1e-3:  # no se solapan
            out.append(n)
            continue
        interval = abs(n.pitch - k.pitch)
        simult = abs(n.start - k.start) <= a.onset_tol
        contained = n.end <= k.end + a.onset_tol
        if (a.dyads and simult and interval >= a.dyad_min
                and min(n.dur, k.dur) >= a.dyad_dur):
            out.append(n)  # doble cuerda real
            continue
        if simult or (interval <= 2 and (contained or n.sal < k.sal)):
            # mismo instante o cluster de semitono/tono: gana la mas saliente
            if n.sal <= k.sal:
                continue
            if k.start >= n.start - a.min_dur:
                out[-1] = n  # k casi no llego a sonar sola: reemplazar
            else:
                k.end = n.start
                out.append(n)
            continue
        if contained and n.vel < a.weak_ratio * k.vel:
            continue  # blip debil dentro de una nota larga
        if n.pitch == k.pitch:
            k.end = max(k.end, n.end)  # misma nota solapada: unir
            continue
        k.end = n.start  # nota nueva de la melodia: cortar la anterior
        if k.dur < 1e-3:
            out.pop()
        out.append(n)
    ns = out
    stats.append(("monofonia", len(ns)))

    # 4. unir fragmentos de la misma altura
    out = []
    for n in ns:
        if out:
            k = out[-1]
            if (n.pitch == k.pitch and n.start - k.end <= a.merge_gap
                    and min(n.dur, k.dur) < a.frag):
                k.end = max(k.end, n.end)
                k.vel = max(k.vel, n.vel)
                continue
        out.append(n)
    ns = out
    stats.append(("fragmentos unidos", len(ns)))

    # 5. cortas
    # tambien fragmentos cortos y debiles pegados a una nota fuerte (armonico/ataque falso)
    keep = []
    for i, n in enumerate(ns):
        nb = [m.vel for m in ns[max(0, i - 1):i + 2] if m is not n and
              (abs(m.start - n.end) <= a.merge_gap or abs(n.start - m.end) <= a.merge_gap)]
        if n.dur < a.min_dur or (n.dur <= a.frag and nb and n.vel < a.weak_ratio * max(nb)):
            continue
        keep.append(n)
    ns = keep
    stats.append(("cortas", len(ns)))

    # 6. aisladas
    keep = []
    for i, n in enumerate(ns):
        prev_gap = n.start - ns[i - 1].end if i > 0 else np.inf
        next_gap = ns[i + 1].start - n.end if i + 1 < len(ns) else np.inf
        if min(prev_gap, next_gap) > a.isolated and n.dur < a.isolated_dur:
            continue
        keep.append(n)
    ns = keep
    stats.append(("aisladas", len(ns)))

    # 7. cromatismos cortos -> escala
    tonic, mode = parse_key(a.key) if a.key else estimate_key(ns)
    snapped = 0
    if a.snap:
        pcs = scale_pcs(tonic, mode)
        for i, n in enumerate(ns):
            if n.pitch % 12 in pcs or n.dur >= a.snap_dur:
                continue
            ref = [m.pitch for m in ns[max(0, i - 1):i + 2] if m is not n] or [n.pitch]
            cands = [n.pitch - 1, n.pitch + 1]
            cands = [c for c in cands if c % 12 in pcs] or cands
            n.pitch = min(cands, key=lambda c: (min(abs(c - r) for r in ref), c))
            snapped += 1
        # una nota ajustada puede quedar igual a su vecina: unir de nuevo
        out = []
        for n in ns:
            if out and n.pitch == out[-1].pitch and n.start - out[-1].end <= a.merge_gap and \
                    min(n.dur, out[-1].dur) < a.frag:
                out[-1].end = max(out[-1].end, n.end)
                continue
            out.append(n)
        ns = out
    stats.append((f"cromaticos ajustados={snapped}", len(ns)))

    # 8. legato
    if a.legato > 0:
        for k, n in zip(ns, ns[1:]):
            if 0 < n.start - k.end <= a.legato:
                k.end = n.start

    save(ns, a.out)
    if not a.quiet:
        prev = stats[0][1]
        print(f"tonalidad estimada: {NAMES[tonic]} {'mayor' if mode == 'major' else 'menor'}")
        for name, c in stats:
            print(f"  {name:32s} {c:4d}  ({c - prev:+d})" if name != "entrada" else f"  {name:32s} {c:4d}")
            prev = c
    return ns


if __name__ == "__main__":
    main()
