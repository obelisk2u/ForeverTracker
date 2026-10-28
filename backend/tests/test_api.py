import json

import pytest

from app.config import Settings, get_settings
from tests.factories import T0, Member, RunSpec, batch, party, run_observation

ADMIN = {"Authorization": "Bearer dev-admin-token"}


def post_batch(client, payload):
    return client.post("/api/v1/ingest/batches", content=json.dumps(payload), headers={"Content-Type": "application/json"})


def two_observer_run(client, observation_suffix="1", start=T0, **kwargs):
    a = RunSpec(f"a-{observation_suffix}", observer="u1", start=start, **kwargs)
    b = RunSpec(f"b-{observation_suffix}", observer="u3", start=start + 20, duration=1780, **kwargs)
    assert post_batch(client, batch("install-aaaa1111", [run_observation(a)])).status_code == 200
    assert post_batch(client, batch("install-bbbb2222", [run_observation(b)])).status_code == 200


def test_health_and_meta(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/health/ready").json()
    assert ready["status"] == "ok" and ready["migration"] == "0002"
    meta = client.get("/api/v1/meta").json()
    assert meta["addon_interface"] == 16001 and meta["synthetic_data_present"] is False
    assert client.get("/metrics").status_code == 200


def test_upload_search_profile_history_run_flow(client):
    two_observer_run(client)
    meta = client.get("/api/v1/meta").json()
    assert meta["synthetic_data_present"] is True

    search = client.get("/api/v1/search", params={"q": "bright"}).json()
    assert search["total"] == 2  # Asha and Thalen Brightvale share a surname, not an identity
    asha = next(r for r in search["results"] if r["name"] == "Asha")
    assert asha["namespace"] == "us-pve" and asha["identity_confidence"] == "guid_confirmed"

    exact = client.get("/api/v1/search", params={"q": "asha", "exact": "true"}).json()
    assert [r["full_name"] for r in exact["results"]] == ["Asha Brightvale"]
    assert client.get("/api/v1/search", params={"q": "nobody here"}).json()["total"] == 0
    assert client.get("/api/v1/search", params={"q": "a"}).status_code == 422

    profile = client.get(f"/api/v1/characters/us-pve/{asha['id']}").json()
    assert profile["canonical_path"] == f"/character/us-pve/{asha['id']}"
    assert profile["stats"]["runs_observed"]["value"] == 1
    assert profile["stats"]["completions_confirmed"]["value"] == 1
    assert profile["freshness"]["last_observed_at"]
    assert any("Observed history only" in n for n in profile["notices"])

    history = client.get(f"/api/v1/characters/us-pve/{asha['id']}/runs").json()
    assert history["total"] == 1
    row = history["items"][0]
    assert row["dungeon"]["name"] == "Hall of Thanes" and len(row["party"]) == 5
    assert row["party"][0]["character"]["id"] == asha["id"]  # the profile's character first
    assert row["metrics"]["dps"]["resolution"] == "corroborated"
    assert row["observers"] == 2

    run = client.get(f"/api/v1/runs/{row['run_id']}").json()
    assert run["match_status"] == "reconciled" and len(run["sources"]) == 2
    assert {s["observer"] for s in run["sources"]} == {"Observer A", "Observer B"}
    tank = next(p for p in run["participants"] if p["role"] == "TANK")
    assert len(tank["candidates"]["damage_done"]) == 2
    assert "contributor_key" not in json.dumps(run)

    companions = client.get(f"/api/v1/characters/us-pve/{asha['id']}/companions").json()
    assert len(companions) == 4 and all(c["runs_together"] == 1 for c in companions)
    prog = client.get(f"/api/v1/characters/us-pve/{asha['id']}/progression").json()
    assert prog["level"][0]["value"] == 18 and len(prog["runs"]) == 1


def test_history_filters_and_pagination(client):
    for i in range(3):
        two_observer_run(client, str(i), start=T0 + i * 7200)
    search = client.get("/api/v1/search", params={"q": "Autumn Redleaf", "exact": "true"}).json()
    cid = search["results"][0]["id"]
    page = client.get(f"/api/v1/characters/us-pve/{cid}/runs", params={"page_size": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert page["items"][0]["started_at"] > page["items"][1]["started_at"]
    page2 = client.get(f"/api/v1/characters/us-pve/{cid}/runs", params={"page_size": 2, "page": 2}).json()
    assert len(page2["items"]) == 1
    assert client.get(f"/api/v1/characters/us-pve/{cid}/runs", params={"role": "HEALER"}).json()["total"] == 0
    assert client.get(f"/api/v1/characters/us-pve/{cid}/runs", params={"dungeon": "hall-of-thanes"}).json()["total"] == 3
    assert client.get("/api/v1/characters/us-pve/doesnotexist").status_code == 404


def test_savedvariables_upload(client):
    from tests.lua_sv import to_savedvariables

    obs = run_observation(RunSpec("r-1", observer="u1"))
    text = to_savedvariables(
        {
            "ForeverTrackerDB": {
                "format": "forevertracker.savedvariables",
                "schema_version": 1,
                "installation_id": "install-svsv0001",
                "addon_version": "0.1.0",
                "synthetic": True,
                "client": {"build": "70532", "interface": 16001},
                "observations": [obs],
            }
        }
    )
    files = {"file": ("ForeverTracker.lua", text.encode(), "text/plain")}
    res = client.post("/api/v1/ingest/savedvariables", files=files)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["summary"]["dungeon_runs"] == 1 and body["summary"]["characters_observed"] == 5
    assert body["batches"][0]["counts"] == {"accepted": 1}
    again = client.post("/api/v1/ingest/savedvariables", files=files).json()
    assert again["batches"][0]["duplicate_batch"] is True
    bad = client.post("/api/v1/ingest/savedvariables", content=b"ForeverTrackerDB = os.execute('x')")
    assert bad.status_code == 422


def test_malformed_and_oversized_uploads(client, monkeypatch):
    assert client.post("/api/v1/ingest/batches", content=b"{not json").status_code == 422
    assert post_batch(client, {"format": "forevertracker.batch"}).status_code == 422
    big = b'{"x": "' + b"a" * 2_100_000 + b'"}'
    assert client.post("/api/v1/ingest/batches", content=big).status_code == 413
    # Individually invalid observations are rejected without sinking the batch.
    good = run_observation(RunSpec("r-1", observer="u1"))
    evil = {**run_observation(RunSpec("r-2", observer="u1", start=T0 + 9000)), "instance": {"map_id": -5}}
    res = post_batch(client, batch("install-aaaa1111", [good, evil])).json()
    assert res["status"] == "partially_accepted"
    assert [o["status"] for o in res["observations"]] == ["accepted", "rejected"]


def test_rate_limit(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_uploads_per_hour", 2)
    payloads = [batch("install-aaaa1111", [run_observation(RunSpec(f"r-{i}", observer="u1", start=T0 + i * 7200))]) for i in range(3)]
    codes = [post_batch(client, p).status_code for p in payloads]
    assert codes == [200, 200, 429]


def test_uploader_release_is_published_only_when_configured(client, monkeypatch):
    assert client.get("/api/v1/uploader/latest").status_code == 404
    settings = get_settings()
    url = "https://forevertracker.example/ForeverTracker-Setup-0.2.0.exe"
    monkeypatch.setattr(settings, "uploader_latest_version", "0.2.0")
    monkeypatch.setattr(settings, "uploader_download_url", url)
    monkeypatch.setattr(settings, "uploader_sha256", "AB" * 32)
    release = client.get("/api/v1/uploader/latest").json()
    assert release == {"version": "0.2.0", "download_url": url, "sha256": "ab" * 32, "signed": False}


def test_synthetic_rejected_when_not_allowed(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "allow_synthetic_data", False)
    res = post_batch(client, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    assert res.status_code == 422 and res.json()["detail"]["error"] == "synthetic_not_allowed"


def test_production_settings_refuse_unsafe_defaults():
    with pytest.raises(ValueError):
        Settings(environment="production")
    with pytest.raises(ValueError):
        Settings(environment="production", admin_token="x" * 40, contributor_id_salt="s", allow_synthetic_data=True)
    ok = Settings(environment="production", admin_token="x" * 40, contributor_id_salt="salt-123")
    assert ok.allow_synthetic_data is False


def test_suppression_and_reports(client):
    two_observer_run(client)
    cid = client.get("/api/v1/search", params={"q": "Phineas"}).json()["results"][0]["id"]
    report = client.post("/api/v1/reports", json={"kind": "suppression_request", "character_id": cid, "message": "Please hide my profile."})
    assert report.status_code == 201
    assert client.post(f"/api/v1/admin/characters/{cid}/visibility", json={"visibility": "suppressed"}).status_code == 401
    res = client.post(f"/api/v1/admin/characters/{cid}/visibility", json={"visibility": "suppressed", "note": "owner request"}, headers=ADMIN)
    assert res.status_code == 200
    assert client.get(f"/api/v1/characters/us-pve/{cid}").status_code == 410
    assert client.get("/api/v1/search", params={"q": "Phineas"}).json()["total"] == 0
    other = client.get("/api/v1/search", params={"q": "Autumn"}).json()["results"][0]["id"]
    run_id = client.get(f"/api/v1/characters/us-pve/{other}/runs").json()["items"][0]["run_id"]
    run = client.get(f"/api/v1/runs/{run_id}").json()
    hidden = [p for p in run["participants"] if p["character"].get("hidden")]
    assert len(hidden) == 1 and hidden[0]["metrics"] == {}
    reports = client.get("/api/v1/admin/reports", headers=ADMIN).json()
    assert reports[0]["kind"] == "suppression_request"


def test_admin_invalidation_recomputes(client):
    two_observer_run(client)
    quarantine = client.get("/api/v1/admin/quarantine", headers=ADMIN).json()
    assert quarantine == []
    cid = client.get("/api/v1/search", params={"q": "Mah"}).json()["results"][0]["id"]
    run_id = client.get(f"/api/v1/characters/us-pve/{cid}/runs").json()["items"][0]["run_id"]
    contributors = client.get("/api/v1/admin/contributors", headers=ADMIN).json()
    target = contributors[0]["contributor_id"]
    res = client.post(
        f"/api/v1/admin/contributors/{target}/status",
        json={"status": "banned", "reason": "fabricated uploads", "invalidate_all": True},
        headers=ADMIN,
    ).json()
    assert res["invalidated"] == 1
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["observation_count"] == 1 and run["match_status"] == "single"
    tank = next(p for p in run["participants"] if p["role"] == "TANK")
    assert tank["metrics"]["damage_done"]["resolution"] == "single_source"
    # A banned contributor cannot upload again.
    again = post_batch(client, batch("install-aaaa1111" if target == 1 else "install-bbbb2222", [run_observation(RunSpec("new-1", observer="u1", start=T0 + 90000))]))
    assert again.status_code == 403
