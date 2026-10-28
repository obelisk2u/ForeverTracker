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
