"""The upload contract, layer by layer, without a database.

Lua (the real addon in a Lua 5.1 VM) -> SavedVariables text -> parser -> extractor (shape normalization)
-> batch JSON -> Pydantic (app/schemas/observations.py) and the generated JSON Schema
(schema/observation-batch.v1.schema.json) -> plausibility checks. Every verdict must agree between Pydantic
and the JSON Schema, for the current addon, addon 0.1.0's fixture, and edge cases: missing, null and empty
values, Lua table shapes, limits and enums, old payloads and unknown future versions.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest
from forevertracker_sv import SavedVariablesError, extract, parse_savedvariables
from pydantic import ValidationError

from app.config import get_settings
from app.integrity.sanity import check_observation
from app.schemas.observations import (
    CollectorName,
    CollectorStatus,
    MeterMetric,
    ObservationBatchEnvelope,
    TimelineKind,
    observation_adapter,
    observation_json_schema,
)

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "addon" / "tests"))

import make_fixtures  # noqa: E402
from harness import new_runtime  # noqa: E402

SCHEMA = json.loads((REPO / "schema" / "observation-batch.v1.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
CURRENT = REPO / "fixtures" / "savedvariables" / "ForeverTracker.current.lua"
ADDON_0_1_0 = REPO / "fixtures" / "savedvariables" / "ForeverTracker.sample.lua"
NOW = 1_850_000_000


def batches_of(text: str) -> list[dict]:
    extraction = extract(parse_savedvariables(text))
    assert extraction.rejected == [] and extraction.skipped == 0
    return [json.loads(json.dumps(b)) for b in extraction.batches]  # exactly what the uploader sends


def verdicts(batch: dict) -> tuple[bool, list[bool]]:
    """(JSON Schema accepts the batch, Pydantic accepts each observation)."""
    schema_ok = VALIDATOR.is_valid(batch)
    ObservationBatchEnvelope.model_validate(batch)
    pydantic_ok = []
    for obs in batch["observations"]:
        try:
            observation_adapter.validate_python(obs)
            pydantic_ok.append(True)
        except ValidationError:
            pydantic_ok.append(False)
    return schema_ok, pydantic_ok


def test_the_committed_schema_is_what_the_models_generate():
    assert observation_json_schema() == SCHEMA


def test_the_current_fixture_is_what_the_addon_writes_now():
    text = make_fixtures.current_savedvariables()
    assert CURRENT.read_text(encoding="utf-8") == text, "run: python tools/make_fixtures.py"
    assert (REPO / "fixtures" / "batches" / "current-batch.json").read_text(encoding="utf-8") == make_fixtures.current_batch(text)


@pytest.mark.parametrize("fixture", [CURRENT, ADDON_0_1_0], ids=["current addon", "addon 0.1.0"])
def test_addon_output_passes_every_layer(fixture):
    for batch in batches_of(fixture.read_text(encoding="utf-8")):
        errors = sorted(VALIDATOR.iter_errors(batch), key=str)
        assert errors == [], [f"{list(e.absolute_path)}: {e.message}" for e in errors[:5]]
        schema_ok, pydantic_ok = verdicts(batch)
        assert schema_ok and all(pydantic_ok)
        for obs in batch["observations"]:
            assert check_observation(observation_adapter.validate_python(obs), get_settings(), NOW).reject == []


def test_two_observers_of_the_e2e_scenario_pass_every_layer():
    src = (REPO / "backend" / "tests" / "test_e2e_pipeline.py").read_text(encoding="utf-8")
    scenario = re.search(r'SCENARIO = """(.*?)"""', src, re.S).group(1)
    for index, delay in ((1, 0), (3, 20)):
        lua = new_runtime(seed=1000 + index)
        lua.execute(scenario, index, delay, 1.0)
        from harness import savedvariables_text

        for batch in batches_of(savedvariables_text(lua)):
            assert verdicts(batch) == (True, [True] * len(batch["observations"]))


def _current_run() -> tuple[dict, dict]:
    batch = batches_of(CURRENT.read_text(encoding="utf-8"))[0]
    run = next(o for o in batch["observations"] if o["type"] == "dungeon_run")
    return batch, run


def _variant(change) -> dict:
    batch, run = _current_run()
    run = copy.deepcopy(run)
    change(run)
    return {**batch, "observations": [run]}


VARIANTS = {
    # name: (change, accepted)
    "meter missing": (lambda r: r.pop("meter"), True),
    "meter null": (lambda r: r.__setitem__("meter", None), True),
    "party_guid missing": (lambda r: r.pop("party_guid", None), True),
    "addon_version missing (before 0.2.10)": (lambda r: r.pop("addon_version"), True),
    "addon_version null": (lambda r: r.__setitem__("addon_version", None), True),
    "unmatched_sources missing (before 0.2.11)": (lambda r: r["meter"].pop("unmatched_sources"), True),
    "empty Lua table for flags": (lambda r: r.__setitem__("flags", []), True),
    "empty Lua table for collection": (lambda r: r.__setitem__("collection", []), True),
    "empty Lua table for a timeline detail": (lambda r: r["timeline"][0].__setitem__("detail", []), True),
    "empty Lua table for meter metrics": (lambda r: r["meter"]["totals"][0].__setitem__("metrics", []), True),
    "empty encounters": (lambda r: r.__setitem__("encounters", []), True),
    "empty roster": (lambda r: r.__setitem__("roster", []), False),
    "null where a value is required": (lambda r: r["timing"].__setitem__("started_at", None), False),
    "unknown field": (lambda r: r.__setitem__("future_field", 1), False),
    "unknown timeline kind": (lambda r: r["timeline"][0].__setitem__("kind", "teleported"), False),
    "unknown metric": (lambda r: r["meter"]["totals"][0]["metrics"].__setitem__("overhealing", {"status": "observed"}), False),
    "a list where a map belongs": (lambda r: r.__setitem__("flags", [True]), False),
    "over the roster limit": (lambda r: r.__setitem__("roster", r["roster"] * 9), False),
    "negative amount": (lambda r: r["meter"]["totals"][0]["metrics"]["damage_done"].__setitem__("value", -1), False),
    "tooltip from addon 0.2.6": (lambda r: None, True),
}


@pytest.mark.parametrize("name", list(VARIANTS))
def test_pydantic_and_the_json_schema_agree(name):
    change, accepted = VARIANTS[name]
    batch = _variant(change)
    schema_ok, (pydantic_ok,) = verdicts(batch)
    assert (schema_ok, pydantic_ok) == (accepted, accepted), f"JSON Schema {schema_ok}, Pydantic {pydantic_ok}"


def test_a_tooltip_sent_by_addon_0_2_6_is_accepted_and_dropped():
    batch, _ = _current_run()
    snapshot = next(o for o in batch["observations"] if o["type"] == "character_snapshot" and o.get("equipment"))
    snapshot = copy.deepcopy(snapshot)
    snapshot["equipment"]["items"][0]["tooltip"] = [{"left": "Iron Sword", "r": 1}]
    assert VALIDATOR.is_valid({**batch, "observations": [snapshot]})
    model = observation_adapter.validate_python(snapshot)
    assert "tooltip" not in model.model_dump(mode="json")["equipment"]["items"][0]


def test_unknown_future_versions_are_refused_at_every_layer():
    batch, _ = _current_run()
    future = {**batch, "schema_version": 2}
    assert not VALIDATOR.is_valid(future)
    with pytest.raises(ValidationError):
        ObservationBatchEnvelope.model_validate(future)
    text = CURRENT.read_text(encoding="utf-8").replace('["schema_version"] = 1,', '["schema_version"] = 2,', 1)
    with pytest.raises(SavedVariablesError, match="unsupported schema_version 2"):
        extract(parse_savedvariables(text))
    # Newer client metadata is ignored, not refused.
    assert VALIDATOR.is_valid({**batch, "client": {**batch["client"], "new_field": "x"}})
    ObservationBatchEnvelope.model_validate({**batch, "client": {**batch["client"], "new_field": "x"}})


def _lua_limits() -> dict[str, int]:
    lua = new_runtime()
    lua.execute("boot()")
    limits = lua.eval("Mock.ft.Config.LIMITS")
    return {k: limits[k] for k in limits.keys() if isinstance(limits[k], int)}


def test_the_addons_limits_fit_the_schema():
    from app.schemas.observations import DungeonRunObservation, MeterData

    def max_items(model, field):
        meta = model.model_fields[field].metadata
        return next(m.max_length for m in meta if getattr(m, "max_length", None) is not None)

    limits = _lua_limits()
    assert limits["max_timeline"] <= max_items(DungeonRunObservation, "timeline")
    assert limits["max_deaths"] <= max_items(DungeonRunObservation, "deaths")
    assert limits["max_roster"] <= max_items(DungeonRunObservation, "roster")
    assert limits["max_meter_sessions"] <= max_items(MeterData, "sessions")
    assert limits["max_deaths"] <= max_items(MeterData, "death_entries")
    assert 100 <= max_items(DungeonRunObservation, "encounters")  # Encounters.lua stops at 100


def _literals(annotation) -> set[str]:
    return set(annotation.__args__)


def test_every_value_the_addon_writes_is_in_the_schemas_enums():
    addon = REPO / "addon" / "ForeverTracker"
    source = "\n".join(p.read_text(encoding="utf-8") for p in addon.rglob("*.lua"))
    timeline = set(re.findall(r'\bmark\("([a-z_]+)"', source)) | set(re.findall(r'kind = "([a-z_]+)", detail', source))
    assert timeline and timeline <= _literals(TimelineKind), timeline - _literals(TimelineKind)
    metrics = set(re.findall(r'\{ "([a-z_]+)", "[A-Za-z]+" \}', (addon / "Collectors" / "DamageMeter.lua").read_text(encoding="utf-8")))
    assert metrics == _literals(MeterMetric)
    collection = re.search(r"run\.collection = \{(.*?)\n  \}", (addon / "Sessions" / "RunTracker.lua").read_text(encoding="utf-8"), re.S).group(1)
    assert set(re.findall(r"^\s+([a-z_]+) =", collection, re.M)) <= _literals(CollectorName)
    statuses = set(re.findall(r'"(active|partial|unavailable|disabled|error)"', collection))
    assert statuses <= _literals(CollectorStatus)
