#!/usr/bin/env python3
"""musc_transcribe.py  audio_mono.wav salida.mid
Transcribe violin solo con MUSC (MTG/violin-transcription, AGPL-3.0).
MUSC no se incluye en este repo: apuntar MUSC_DIR al clon externo."""
import os
import sys

musc_dir = os.environ.get("MUSC_DIR")
if not musc_dir or not os.path.isdir(os.path.join(musc_dir, "musc")):
    sys.exit("MUSC_DIR debe apuntar al clon de https://github.com/MTG/violin-transcription")
sys.path.insert(0, musc_dir)
from musc.model import PretrainedModel  # noqa: E402

wav, out = sys.argv[1:3]
model = PretrainedModel(os.environ.get("MUSC_INSTRUMENT", "violin"))
midi = model.transcribe(wav, batch_size=int(os.environ.get("MUSC_BATCH", "32")),
                        postprocessing="spotify", include_pitch_bends=True)
midi.write(out)
print(f"{out}: {sum(len(i.notes) for i in midi.instruments)} notas")
