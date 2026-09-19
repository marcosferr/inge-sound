"""Catalog of every Demucs model and CLI option this wrapper exposes.

This module is the single source of truth. The API publishes it at
``GET /api/capabilities`` and the frontend builds its form from it, so adding a
new Demucs flag means adding one entry here and one branch in
``runner.build_argv``.

Reference: ``python -m demucs --help`` (demucs >= 4.0).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

FOUR_STEMS = ["drums", "bass", "other", "vocals"]
SIX_STEMS = ["drums", "bass", "other", "vocals", "guitar", "piano"]


@dataclass(frozen=True)
class ModelInfo:
    """A pretrained Demucs model.

    ``sub_models`` is how many networks a bag model averages. Demucs restarts its
    progress bar once per network, which is how ``runner`` turns the bar into a
    single monotonic percentage.
    """

    name: str
    label: str
    stems: list[str]
    sub_models: int
    description: str
    quality: Literal["good", "better", "best"]
    speed: Literal["fast", "medium", "slow", "very_slow"]
    default: bool = False


MODELS: list[ModelInfo] = [
    ModelInfo(
        name="htdemucs",
        label="Hybrid Transformer Demucs",
        stems=FOUR_STEMS,
        sub_models=1,
        description="Modelo por defecto. Mejor relación calidad/velocidad.",
        quality="better",
        speed="fast",
        default=True,
    ),
    ModelInfo(
        name="htdemucs_ft",
        label="Hybrid Transformer Demucs (fine-tuned)",
        stems=FOUR_STEMS,
        sub_models=4,
        description="Versión afinada de htdemucs. La mejor calidad; ~4x más lento.",
        quality="best",
        speed="very_slow",
    ),
    ModelInfo(
        name="htdemucs_6s",
        label="Hybrid Transformer Demucs (6 pistas)",
        stems=SIX_STEMS,
        sub_models=1,
        description="Añade guitarra y piano. El piano todavía es experimental.",
        quality="good",
        speed="fast",
    ),
    ModelInfo(
        name="hdemucs_mmi",
        label="Hybrid Demucs v3 (MMI)",
        stems=FOUR_STEMS,
        sub_models=1,
        description="Demucs v3 reentrenado sobre MusDB + 800 canciones.",
        quality="better",
        speed="fast",
    ),
    ModelInfo(
        name="mdx",
        label="MDX (track A)",
        stems=FOUR_STEMS,
        sub_models=4,
        description="Ganador de la MDX Challenge, entrenado solo con MusDB HQ.",
        quality="better",
        speed="slow",
    ),
    ModelInfo(
        name="mdx_extra",
        label="MDX Extra (track B)",
        stems=FOUR_STEMS,
        sub_models=4,
        description="MDX con datos extra de entrenamiento. 2º puesto en track B.",
        quality="best",
        speed="slow",
    ),
    ModelInfo(
        name="mdx_q",
        label="MDX (cuantizado)",
        stems=FOUR_STEMS,
        sub_models=4,
        description="mdx cuantizado: mucho más liviano, calidad ligeramente menor.",
        quality="good",
        speed="medium",
    ),
    ModelInfo(
        name="mdx_extra_q",
        label="MDX Extra (cuantizado)",
        stems=FOUR_STEMS,
        sub_models=4,
        description="mdx_extra cuantizado. Buena opción para servidores sin GPU.",
        quality="better",
        speed="medium",
    ),
]

MODELS_BY_NAME: dict[str, ModelInfo] = {m.name: m for m in MODELS}
DEFAULT_MODEL = next(m.name for m in MODELS if m.default)

#: Stems a two-stems separation can be pivoted on, per model.
ALL_STEMS = SIX_STEMS


def model_stems(name: str) -> list[str]:
    """Stems produced by ``name``, falling back to the 4-stem layout.

    Custom signatures (``--sig``) are not in the catalog, so they get the common
    layout; the real stem list is discovered from the output files anyway.
    """
    info = MODELS_BY_NAME.get(name)
    return list(info.stems) if info else list(FOUR_STEMS)


def model_sub_models(name: str) -> int:
    info = MODELS_BY_NAME.get(name)
    return info.sub_models if info else 1


# --------------------------------------------------------------------------- #
# Options
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Option:
    """One exposed Demucs CLI flag, described well enough to render a widget."""

    key: str
    flag: str
    label: str
    help: str
    type: Literal["enum", "int", "float", "bool", "string"]
    default: Any = None
    choices: list[dict[str, Any]] = field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    group: str = "general"
    advanced: bool = False
    #: Only meaningful when another option has one of these values.
    depends_on: dict[str, list[Any]] | None = None
    #: CLI flags the host's Demucs must accept for this option to be usable.
    #: Defaults to ``flag`` split on "/". An empty list means "always usable".
    requires: list[str] | None = None
    #: Flag whose ``{a,b}`` choice set constrains this option's values.
    choices_flag: str | None = None

    @property
    def required_flags(self) -> list[str]:
        if self.requires is not None:
            return self.requires
        return [part for part in self.flag.split("/") if part.startswith("-")]


OPTIONS: list[Option] = [
    Option(
        key="model",
        flag="-n",
        label="Modelo",
        help="Modelo preentrenado o firma de un entrenamiento propio.",
        type="enum",
        default=DEFAULT_MODEL,
        choices=[{"value": m.name, "label": m.label} for m in MODELS],
        group="model",
        requires=[],
    ),
    Option(
        key="signature",
        flag="-s",
        label="Firma local (SIG)",
        help="Firma de un experimento entrenado localmente. Reemplaza al modelo.",
        type="string",
        group="model",
        advanced=True,
    ),
    Option(
        key="repo",
        flag="--repo",
        label="Repositorio de modelos",
        help="Carpeta del servidor con modelos preentrenados propios.",
        type="string",
        group="model",
        advanced=True,
    ),
    Option(
        key="device",
        flag="-d",
        label="Dispositivo",
        help="Hardware de inferencia. 'auto' usa GPU si hay.",
        type="enum",
        default="auto",
        choices=[
            {"value": "auto", "label": "Automático"},
            {"value": "cuda", "label": "GPU NVIDIA (CUDA)"},
            {"value": "mps", "label": "GPU Apple (MPS)"},
            {"value": "cpu", "label": "CPU"},
        ],
        group="performance",
    ),
    Option(
        key="shifts",
        flag="--shifts",
        label="Shifts",
        help=(
            "Desplazamientos aleatorios para estabilización equivariante. "
            "Multiplica el tiempo de proceso por este número; 10 es el valor del paper."
        ),
        type="int",
        default=1,
        minimum=0,
        maximum=20,
        step=1,
        group="quality",
    ),
    Option(
        key="overlap",
        flag="--overlap",
        label="Solapamiento",
        help="Solapamiento entre bloques. Más alto = mejores transiciones y más lento.",
        type="float",
        default=0.25,
        minimum=0.0,
        maximum=0.99,
        step=0.05,
        group="quality",
    ),
    Option(
        key="split",
        flag="--no-split",
        label="Dividir en bloques",
        help="Desactivarlo procesa la pista entera de una vez: mucha más memoria.",
        type="bool",
        default=True,
        group="performance",
        advanced=True,
    ),
    Option(
        key="segment",
        flag="--segment",
        label="Tamaño de bloque (s)",
        help="Segundos por bloque. Bajalo si te quedás sin memoria de GPU.",
        type="int",
        minimum=1,
        maximum=3600,
        step=1,
        group="performance",
        advanced=True,
        depends_on={"split": [True]},
    ),
    Option(
        key="jobs",
        flag="-j",
        label="Procesos paralelos",
        help="Núcleos usados en paralelo. Acelera en CPU a costa de memoria.",
        type="int",
        default=1,
        minimum=1,
        maximum=32,
        step=1,
        group="performance",
    ),
    Option(
        key="two_stems",
        flag="--two-stems",
        label="Separación en 2 pistas",
        help="Extrae solo esta pista y su complemento (modo karaoke).",
        type="enum",
        default=None,
        choices=[{"value": s, "label": s} for s in ALL_STEMS],
        group="output",
    ),
    Option(
        key="other_method",
        flag="--other-method",
        label="Cálculo del complemento",
        help=(
            "Cómo construir 'no_<pista>': sumando el resto (add), restando del "
            "original (minus) o no generarlo (none)."
        ),
        type="enum",
        default="add",
        choices=[
            {"value": "add", "label": "Sumar las demás pistas"},
            {"value": "minus", "label": "Original menos la pista"},
            {"value": "none", "label": "No generar complemento"},
        ],
        group="output",
        advanced=True,
        depends_on={"two_stems": ALL_STEMS},
        requires=["--other-method"],
    ),
    Option(
        key="format",
        flag="--mp3/--flac",
        label="Formato de salida",
        help="Contenedor de las pistas separadas.",
        type="enum",
        default="wav",
        choices=[
            {"value": "wav", "label": "WAV (sin pérdida)"},
            {"value": "flac", "label": "FLAC (sin pérdida, comprimido)"},
            {"value": "mp3", "label": "MP3 (con pérdida, liviano)"},
        ],
        group="output",
    ),
    Option(
        key="bit_depth",
        flag="--int24/--float32",
        label="Profundidad del WAV",
        help="Solo aplica al formato WAV. float32 pesa el doble.",
        type="enum",
        default="int16",
        choices=[
            {"value": "int16", "label": "16 bits (por defecto)"},
            {"value": "int24", "label": "24 bits"},
            {"value": "float32", "label": "32 bits float"},
        ],
        group="output",
        advanced=True,
        depends_on={"format": ["wav"]},
    ),
    Option(
        key="mp3_bitrate",
        flag="--mp3-bitrate",
        label="Bitrate MP3 (kbps)",
        help="Bitrate del MP3 resultante.",
        type="int",
        default=320,
        minimum=64,
        maximum=320,
        step=8,
        group="output",
        advanced=True,
        depends_on={"format": ["mp3"]},
    ),
    Option(
        key="mp3_preset",
        flag="--mp3-preset",
        label="Preset del codificador MP3",
        help="2 = máxima calidad, 7 = máxima velocidad.",
        type="int",
        default=2,
        minimum=2,
        maximum=7,
        step=1,
        group="output",
        advanced=True,
        depends_on={"format": ["mp3"]},
        choices_flag="--mp3-preset",
    ),
    Option(
        key="clip_mode",
        flag="--clip-mode",
        label="Manejo de clipping",
        help="Qué hacer si la señal se sale de rango: reescalar, recortar o nada.",
        type="enum",
        default="rescale",
        choices=[
            {"value": "rescale", "label": "Reescalar la señal"},
            {"value": "clamp", "label": "Recorte duro"},
            {"value": "none", "label": "No hacer nada"},
        ],
        group="output",
        advanced=True,
        choices_flag="--clip-mode",
    ),
    Option(
        key="filename",
        flag="--filename",
        label="Plantilla de nombre",
        help=(
            "Variables disponibles: {track}, {trackext}, {stem}, {ext}. "
            "Por defecto: {track}/{stem}.{ext}"
        ),
        type="string",
        default="{track}/{stem}.{ext}",
        group="output",
        advanced=True,
    ),
    Option(
        key="verbose",
        flag="-v",
        label="Log detallado",
        help="Agrega salida de diagnóstico al log del trabajo.",
        type="bool",
        default=False,
        group="general",
        advanced=True,
    ),
]

OPTIONS_BY_KEY: dict[str, Option] = {o.key: o for o in OPTIONS}

OPTION_GROUPS = [
    {"key": "model", "label": "Modelo"},
    {"key": "quality", "label": "Calidad"},
    {"key": "performance", "label": "Rendimiento"},
    {"key": "output", "label": "Salida"},
    {"key": "general", "label": "General"},
]


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #

PRESETS: list[dict[str, Any]] = [
    {
        "key": "fast",
        "label": "Rápido",
        "description": "htdemucs con ajustes mínimos. Ideal para previsualizar.",
        "options": {"model": "htdemucs", "shifts": 0, "overlap": 0.1, "format": "mp3"},
    },
    {
        "key": "balanced",
        "label": "Equilibrado",
        "description": "Valores por defecto de Demucs. Buen punto de partida.",
        "options": {"model": "htdemucs", "shifts": 1, "overlap": 0.25, "format": "wav"},
    },
    {
        "key": "best",
        "label": "Máxima calidad",
        "description": "htdemucs_ft con shifts. Muy lento, pensado para GPU.",
        "options": {"model": "htdemucs_ft", "shifts": 5, "overlap": 0.5, "format": "wav"},
    },
    {
        "key": "karaoke",
        "label": "Karaoke",
        "description": "Solo voz y acompañamiento, con el complemento por resta.",
        "options": {
            "model": "htdemucs",
            "two_stems": "vocals",
            "other_method": "minus",
            "shifts": 1,
            "format": "mp3",
        },
    },
    {
        "key": "six_stems",
        "label": "6 pistas",
        "description": "Suma guitarra y piano a las cuatro pistas clásicas.",
        "options": {"model": "htdemucs_6s", "shifts": 1, "format": "wav"},
    },
]


def serialize_models() -> list[dict[str, Any]]:
    return [asdict(m) for m in MODELS]


def serialize_options() -> list[dict[str, Any]]:
    """Options with runtime support annotated.

    Each option gets ``supported`` (does this Demucs accept the flag?) and each
    enum choice gets ``supported`` too, so the client never offers a value the
    host would reject.
    """
    from . import probe

    payload: list[dict[str, Any]] = []
    for option in OPTIONS:
        data = asdict(option)
        data.pop("requires", None)
        data["supported"] = all(probe.flag_supported(f) for f in option.required_flags)
        if option.choices_flag:
            data["choices"] = [
                {
                    **choice,
                    "supported": probe.choice_supported(
                        option.choices_flag, str(choice["value"])
                    ),
                }
                for choice in data["choices"]
            ]
        else:
            data["choices"] = [{**choice, "supported": True} for choice in data["choices"]]
        payload.append(data)
    return payload


def unsupported_reasons(values: dict[str, Any]) -> list[str]:
    """Human-readable reasons why ``values`` cannot run on this host.

    Only flags the user actually moved off the default are reported: a default
    that maps to a missing flag is simply never emitted.
    """
    from . import probe

    reasons: list[str] = []
    for option in OPTIONS:
        if option.key not in values:
            continue
        value = values[option.key]
        if value is None or value == option.default:
            continue
        missing = [f for f in option.required_flags if not probe.flag_supported(f)]
        if missing:
            reasons.append(
                f"'{option.label}' requiere {', '.join(missing)}, que esta versión "
                f"de Demucs no acepta."
            )
            continue
        if option.choices_flag and not probe.choice_supported(
            option.choices_flag, str(value)
        ):
            allowed = ", ".join(probe.flag_choices().get(option.choices_flag, ()))
            reasons.append(
                f"'{option.label}' no acepta el valor '{value}' en esta versión de "
                f"Demucs. Valores válidos: {allowed}."
            )
    return reasons
