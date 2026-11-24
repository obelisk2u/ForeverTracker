import json

import pytest

from forevertracker_sv import SavedVariablesError, extract_batches, summarize_export


def _db(observations, **extra):
    return {
        "ForeverTrackerDB": {
            "format": "forevertracker.savedvariables",
            "schema_version": 1,
            "installation_id": "ft-abcdef0123",
            "addon_version": "0.1.0",
            "client": {"build": "70532", "interface": 16001},
            "observations": observations,
            **extra,
        }
    }


def _run(oid, rev, state="completed"):
    return {
        "type": "dungeon_run",
        "observation_id": oid,
        "revision": rev,
        "state": state,
        "recorded_by": {"name": "Autumn", "surname": "Redleaf"},
        "roster": [{"name": "Autumn", "surname": "Redleaf"}, {"name": "Mah", "surname": "Beardlong"}],
        "timing": {"started_at": 1_790_000_000, "ended_at": 1_790_001_800},
    }


def test_batches_are_deterministic_and_keep_latest_revision():
    parsed = _db([_run("r-1", 1, "in_progress"), _run("r-1", 3), _run("r-2", 1)])
    first = extract_batches(parsed)
    second = extract_batches(parsed)
    assert [b["batch_id"] for b in first] == [b["batch_id"] for b in second]
    (batch,) = first
    assert [(o["observation_id"], o["revision"]) for o in batch["observations"]] == [("r-1", 3), ("r-2", 1)]
    assert batch["installation_id"] == "ft-abcdef0123"
    assert batch["synthetic"] is False


def test_active_run_is_included_and_batches_are_chunked():
    parsed = _db([_run(f"r-{i}", 1) for i in range(5)], active_run=_run("r-live", 2, "in_progress"))
    batches = extract_batches(parsed, max_per_batch=2)
    assert [len(b["observations"]) for b in batches] == [2, 2, 2]
    assert any(o["observation_id"] == "r-live" for b in batches for o in b["observations"])
    assert len({b["batch_id"] for b in batches}) == 3


def _big_run(oid, kilobytes):
    run = _run(oid, 1)
    run["timeline"] = [{"at": 1_790_000_000 + i, "kind": "roster_changed", "detail": {"pad": "x" * 1000}} for i in range(kilobytes)]
    return run


def test_batches_stay_under_the_byte_budget():
    # Raid-sized runs are hundreds of kilobytes each: 200 of them in one batch would pass the server's upload limit.
    parsed = _db([_big_run(f"r-{i}", 300) for i in range(10)])
    batches = extract_batches(parsed, max_batch_bytes=1_000_000)
    sizes = [len(json.dumps(b["observations"], separators=(",", ":")).encode()) for b in batches]
    assert [len(b["observations"]) for b in batches] == [3, 3, 3, 1]
    assert all(s <= 1_000_000 for s in sizes)
    assert [o["observation_id"] for b in batches for o in b["observations"]] == sorted(f"r-{i}" for i in range(10))


def test_a_record_larger_than_the_budget_gets_a_batch_of_its_own():
    parsed = _db([_run("r-a", 1), _big_run("r-b", 50), _run("r-c", 1)])
    batches = extract_batches(parsed, max_batch_bytes=20_000)
    assert [[o["observation_id"] for o in b["observations"]] for b in batches] == [["r-a"], ["r-b"], ["r-c"]]


def test_the_byte_budget_does_not_move_batches_that_fit():
    # Batch IDs come from content: a file that fits is cut as before, so nothing already uploaded is sent again.
    parsed = _db([_run(f"r-{i}", 1) for i in range(450)])
    by_count = extract_batches(parsed, max_batch_bytes=10**12)
    default = extract_batches(parsed)
    assert [b["batch_id"] for b in default] == [b["batch_id"] for b in by_count]
    assert [len(b["observations"]) for b in default] == [200, 200, 50]


def test_changed_content_changes_batch_id():
    a = extract_batches(_db([_run("r-1", 1)]))[0]["batch_id"]
    b = extract_batches(_db([_run("r-1", 2)]))[0]["batch_id"]
    assert a != b


def test_summary_discloses_characters():
    summary = summarize_export(_db([_run("r-1", 1)], active_run=_run("r-2", 1, "in_progress")))
    assert summary.dungeon_runs == 2
    assert summary.in_progress_runs == 1
    assert summary.characters_observed == ["Autumn Redleaf", "Mah Beardlong"]
    assert any("no account name" in line for line in summary.disclosure_lines())


@pytest.mark.parametrize(
    "parsed",
    [
        {},
        {"ForeverTrackerDB": {"format": "something-else"}},
        {"ForeverTrackerDB": {"format": "forevertracker.savedvariables", "schema_version": 99}},
        {"ForeverTrackerDB": {"format": "forevertracker.savedvariables", "schema_version": 1, "installation_id": "x"}},
    ],
)
def test_rejects_non_forevertracker_files(parsed):
    with pytest.raises(SavedVariablesError):
        extract_batches(parsed)
