from __future__ import annotations

import pytest

from app import catalog
from app.schemas import SeparationOptions


def test_every_option_maps_to_a_schema_field():
    """The catalog drives the UI; a key with no field would render a dead widget."""
    fields = set(SeparationOptions.model_fields)
    for option in catalog.OPTIONS:
        assert option.key in fields, f"{option.key} no existe en SeparationOptions"


def test_option_defaults_match_the_schema():
    defaults = SeparationOptions()
    for option in catalog.OPTIONS:
        if option.default is None:
            continue
        assert getattr(defaults, option.key) == option.default, option.key


def test_enum_choices_are_accepted_by_the_schema():
    for option in catalog.OPTIONS:
        if option.type != "enum" or option.key in {"model", "signature", "repo"}:
            continue
        for choice in option.choices:
            # two_stems is only valid against a model that produces that stem.
            extra = {"model": "htdemucs_6s"} if option.key == "two_stems" else {}
            SeparationOptions(**{option.key: choice["value"]}, **extra)


def test_every_model_accepts_its_own_stems_as_two_stems():
    for model in catalog.MODELS:
        for stem in model.stems:
            SeparationOptions(model=model.name, two_stems=stem)


def test_presets_only_use_known_options():
    fields = set(SeparationOptions.model_fields)
    for preset in catalog.PRESETS:
        assert set(preset["options"]) <= fields, preset["key"]
        SeparationOptions(**preset["options"])


def test_option_groups_cover_every_option():
    known = {group["key"] for group in catalog.OPTION_GROUPS}
    assert {option.group for option in catalog.OPTIONS} <= known


def test_six_stem_model_exposes_guitar_and_piano():
    assert catalog.model_stems("htdemucs_6s") == [
        "drums", "bass", "other", "vocals", "guitar", "piano",
    ]
    assert "guitar" not in catalog.model_stems("htdemucs")


def test_bag_models_declare_their_sub_model_count():
    assert catalog.model_sub_models("htdemucs_ft") == 4
    assert catalog.model_sub_models("htdemucs") == 1
    assert catalog.model_sub_models("una-firma-desconocida") == 1


def test_two_stems_rejected_when_the_model_cannot_produce_it():
    with pytest.raises(ValueError, match="no produce la pista"):
        SeparationOptions(model="htdemucs", two_stems="piano")
    SeparationOptions(model="htdemucs_6s", two_stems="piano")


def test_filename_template_must_be_contained_and_named():
    with pytest.raises(ValueError, match="incluir"):
        SeparationOptions(filename="{track}.{ext}")
    with pytest.raises(ValueError, match="salir del directorio"):
        SeparationOptions(filename="../{stem}.{ext}")


# --- runtime adaptation ----------------------------------------------------


def test_serialize_options_marks_unsupported_flags(legacy_demucs):
    options = {option["key"]: option for option in catalog.serialize_options()}
    assert options["other_method"]["supported"] is False
    assert options["two_stems"]["supported"] is True
    clip_choices = {c["value"]: c["supported"] for c in options["clip_mode"]["choices"]}
    assert clip_choices == {"rescale": True, "clamp": True, "none": False}


def test_serialize_options_on_a_newer_demucs(modern_demucs):
    options = {option["key"]: option for option in catalog.serialize_options()}
    assert options["other_method"]["supported"] is True
    assert all(choice["supported"] for choice in options["clip_mode"]["choices"])


def test_everything_is_supported_when_demucs_cannot_be_probed(unprobeable_demucs):
    assert all(option["supported"] for option in catalog.serialize_options())


def test_unsupported_reasons_only_flags_non_default_values(legacy_demucs):
    assert catalog.unsupported_reasons({}) == []
    # 'add' is the default, so it is never emitted and never a problem.
    assert catalog.unsupported_reasons({"other_method": "add"}) == []

    reasons = catalog.unsupported_reasons({"other_method": "minus"})
    assert len(reasons) == 1 and "--other-method" in reasons[0]

    reasons = catalog.unsupported_reasons({"clip_mode": "none"})
    assert len(reasons) == 1 and "rescale, clamp" in reasons[0]


def test_unsupported_reasons_are_empty_on_a_newer_demucs(modern_demucs):
    assert catalog.unsupported_reasons({"other_method": "minus", "clip_mode": "none"}) == []


def test_presets_drop_options_the_host_cannot_run(legacy_demucs):
    """Otherwise the karaoke preset would set a flag the submit then rejects."""
    karaoke = next(p for p in catalog.serialize_presets() if p["key"] == "karaoke")
    assert "other_method" not in karaoke["options"]
    assert karaoke["dropped"] == ["Cálculo del complemento"]
    # The rest of the preset survives.
    assert karaoke["options"]["two_stems"] == "vocals"
    assert catalog.unsupported_reasons(karaoke["options"]) == []


def test_presets_keep_everything_on_a_newer_demucs(modern_demucs):
    karaoke = next(p for p in catalog.serialize_presets() if p["key"] == "karaoke")
    assert karaoke["options"]["other_method"] == "minus"
    assert karaoke["dropped"] == []


def test_every_preset_is_submittable_as_served(legacy_demucs):
    for preset in catalog.serialize_presets():
        assert catalog.unsupported_reasons(preset["options"]) == []
        SeparationOptions(**preset["options"])
