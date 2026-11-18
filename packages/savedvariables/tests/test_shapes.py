"""Mixed Lua array/hash tables at the SavedVariables and export boundaries (forevertracker_sv.shapes)."""

import json

import pytest

from forevertracker_sv import SavedVariablesError, ShapeError, extract, normalize, parse_savedvariables, summarize_export


def sv(observations: str, extra: str = "") -> str:
    return (
        'ForeverTrackerDB = { format = "forevertracker.savedvariables", schema_version = 1, '
        f'installation_id = "ft-0123456789abcdef", {extra} observations = {{ {observations} }} }}'
    )


def run(oid: str, extra: str = "") -> str:
    return f'{{ type = "dungeon_run", observation_id = "{oid}", revision = 2, {extra} }}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([1, {"a": 1}], [1, {"a": 1}]),
        ({"a": 1, "b": [2]}, {"a": 1, "b": [2]}),
        ({3: "c", 1: "a"}, ["a", "c"]),  # a Lua list with a hole
        ({}, {}),
        ([], []),
    ],
)
def test_unambiguous_shapes_are_normalized(value, expected):
    assert normalize(value) == expected


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ({1: "x", "a": True}, "mixes list positions (1) with named fields ('a')"),
        ({True: 1}, "has a key that is neither a name nor a list position (True)"),
        ({1.5: 1}, "has a key that is neither a name nor a list position (1.5)"),
        ({0: "zero"}, "has a key that is neither a name nor a list position (0)"),
        ({-1: "x"}, "has a key that is neither a name nor a list position (-1)"),
    ],
)
def test_ambiguous_shapes_raise_a_controlled_error_with_the_path(value, problem):
    with pytest.raises(ShapeError) as err:
        normalize({"outer": [value]}, "obs")
    assert err.value.path == "obs.outer[1]" and err.value.problem == problem
    assert isinstance(err.value, SavedVariablesError)


def test_export_json_list_positions_are_read_like_lua_keys():
    assert normalize({"1": "a", "3": "c"}, string_indices=True) == ["a", "c"]
    assert normalize({"1": "a", "3": "c"}) == {"1": "a", "3": "c"}  # a JSON batch is taken as written
    with pytest.raises(ShapeError):
        normalize({"1": "x", "a": True}, string_indices=True)


def test_a_mixed_table_rejects_only_its_record_and_the_rest_still_upload():
    text = sv(run("r-bad", 'flags = { "x", a = true },') + "," + run("r-good"))
    result = extract(parse_savedvariables(text))  # used to raise TypeError in canonical_json
    (batch,) = result.batches
    assert [o["observation_id"] for o in batch["observations"]] == ["r-good"]
    (rejected,) = result.rejected
    assert rejected.observation_id == "r-bad" and rejected.index == 1
    assert "ForeverTrackerDB.observations[1].flags: mixes list positions (1) with named fields ('a')" in rejected.reason
    json.dumps(batch, sort_keys=True)  # every key is a string now


def test_a_list_with_holes_inside_a_record_becomes_a_list():
    text = sv(run("r-1", 'roster = { [1] = { ref = "u1" }, [3] = { ref = "u3" } },'))
    (obs,) = extract(parse_savedvariables(text)).batches[0]["observations"]
    assert obs["roster"] == [{"ref": "u1"}, {"ref": "u3"}]


def test_an_ambiguous_container_rejects_the_file():
    text = 'ForeverTrackerDB = { format = "forevertracker.savedvariables", schema_version = 1, installation_id = "ft-0123456789abcdef", observations = { { observation_id = "r-1", revision = 1 }, extra = true } }'
    with pytest.raises(ShapeError, match=r"ForeverTrackerDB.observations: is not a list of records"):
        extract(parse_savedvariables(text))
    with pytest.raises(ShapeError, match=r"ForeverTrackerDB.client"):
        extract(parse_savedvariables(sv(run("r-1"), 'client = { "x", build = "1" },')))


def test_the_disclosure_names_records_that_will_not_be_sent():
    summary = summarize_export(parse_savedvariables(sv(run("r-bad", "detail = { [true] = 1 },"))))
    assert summary.dungeon_runs == 0
    assert [r.observation_id for r in summary.rejected_records] == ["r-bad"]
    assert any("Not sent" in line and "r-bad" in line for line in summary.disclosure_lines())


def test_export_string_with_a_mixed_table_is_rejected_per_record():
    exported = {
        "format": "forevertracker.savedvariables",
        "schema_version": 1,
        "installation_id": "ft-0123456789abcdef",
        "observations": [{"type": "dungeon_run", "observation_id": "r-bad", "revision": 1, "flags": {"1": "x", "a": True}}],
        "active_run": {"type": "dungeon_run", "observation_id": "r-live", "revision": 1, "roster": {"1": {"ref": "u1"}, "2": {"ref": "u2"}}},
    }
    result = extract({"ForeverTrackerDB": json.loads(json.dumps(exported))}, string_indices=True)
    assert [r.observation_id for r in result.rejected] == ["r-bad"]
    (obs,) = result.batches[0]["observations"]
    assert obs["roster"] == [{"ref": "u1"}, {"ref": "u2"}]
