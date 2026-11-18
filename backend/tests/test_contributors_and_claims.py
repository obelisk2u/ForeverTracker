"""Contributor flagging survives a restore only on new evidence; identity conflicts are claims for review."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.models import AuditLog, Character, Contributor, IdentityClaim, RawObservation
from tests.factories import T0, Member, RunSpec, batch, gear_snapshot, party, run_observation

ADMIN = {"Authorization": "Bearer dev-admin-token"}


def post(client, payload):
    res = client.post("/api/v1/ingest/batches", content=json.dumps(payload), headers={"Content-Type": "application/json"})
    assert res.status_code == 200, res.text
    return res.json()


def implausible(i: int) -> dict:
    """A run quarantined for something the uploader's own data shows (a level above the cap)."""
    members = [Member("u1", "Lone", "Wolf", "Player-1-00000Z", level=99)]
    return run_observation(RunSpec(f"bad-{i}", observer="u1", members=members, start=T0 + i * 7200))


def contributor(db) -> Contributor:
    db.expire_all()
    return db.scalar(select(Contributor).where(Contributor.is_synthetic.is_(True)))


def test_a_restored_contributor_stays_restored_until_new_evidence(client, db, settings):
    for i in range(settings.contributor_flag_threshold):
        post(client, batch("install-aaaa1111", [implausible(i)]))
    c = contributor(db)
    assert (c.status, c.flag_evidence_count, c.quarantined_count) == ("flagged", 5, 5)
    held = post(client, batch("install-aaaa1111", [run_observation(RunSpec("good-1", observer="u1", start=T0 + 50 * 7200))]))
    assert held["observations"][0]["reasons"] == ["contributor_flagged"]  # held while flagged

    res = client.post(f"/api/v1/admin/contributors/{c.id}/status", json={"status": "active", "reason": "reviewed: test data"}, headers=ADMIN)
    assert res.status_code == 200 and res.json()["previous_status"] == "flagged" and res.json()["flag_evidence_count"] == 5

    # Clean uploads after the restore: still active (before, the next batch flagged it again at once).
    for i in range(3):
        out = post(client, batch("install-aaaa1111", [run_observation(RunSpec(f"good-{i + 2}", observer="u1", start=T0 + (60 + i) * 7200))]))
        assert out["observations"][0]["status"] == "accepted"
    c = contributor(db)
    assert (c.status, c.flag_evidence_count, c.restored_at is not None) == ("active", 0, True)
    assert c.quarantined_count == 6  # history kept: the 5 implausible runs and the one held while flagged

    # New qualifying evidence flags it again.
    for i in range(settings.contributor_flag_threshold):
        post(client, batch("install-aaaa1111", [implausible(100 + i)]))
    assert contributor(db).status == "flagged"
    actions = [a.details for a in db.scalars(select(AuditLog).where(AuditLog.action == "set_contributor_status"))]
    assert actions[0]["previous_status"] == "flagged" and actions[0]["status"] == "active"


def test_identity_conflicts_never_flag_the_uploader(client, db, settings):
    post(client, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    me, mah = party()[0], party()[1]
    mah.class_file = "MAGE"  # contradicts what the first upload established
    honest = [gear_snapshot(f"s-{i}", me, mah, T0 + 3600 + i, [20, 21]) for i in range(settings.contributor_flag_threshold + 2)]
    out = post(client, batch("install-bbbb2222", honest))
    assert {o["status"] for o in out["observations"]} == {"quarantined"}
    assert {tuple(o["reasons"]) for o in out["observations"]} == {("guid_class_conflict",)}
    second = db.scalar(select(Contributor).order_by(Contributor.id.desc()))
    db.refresh(second)
    assert (second.status, second.flag_evidence_count) == ("active", 0)
    (claim,) = db.scalars(select(IdentityClaim)).all()  # one claim per contributor, counted
    assert (claim.kind, claim.value, claim.observation_count, claim.contributor_id) == ("class", "MAGE", 7, second.id)
    assert db.get(RawObservation, claim.raw_observation_id).status == "quarantined"


def test_claims_are_listed_and_a_moderator_decides(client, db):
    post(client, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    renamed = party()
    renamed[0].name = "Autumne"
    post(client, batch("install-cccc3333", [run_observation(RunSpec("r-2", observer="u1", members=renamed, start=T0 + 86400))]))
    assert client.get("/api/v1/admin/identity-claims").status_code == 401
    (claim,) = client.get("/api/v1/admin/identity-claims", headers=ADMIN).json()
    assert claim["kind"] == "name" and claim["claimed"] == "Autumne Redleaf" and claim["character"]["full_name"] == "Autumn Redleaf"

    res = client.post(f"/api/v1/admin/identity-claims/{claim['claim_id']}/resolve", json={"status": "accepted", "note": "confirmed rename"}, headers=ADMIN)
    assert res.status_code == 200 and res.json()["full_name"] == "Autumne Redleaf"
    assert client.get("/api/v1/admin/identity-claims", headers=ADMIN).json() == []
    again = client.post(f"/api/v1/admin/identity-claims/{claim['claim_id']}/resolve", json={"status": "rejected"}, headers=ADMIN)
    assert again.status_code == 409
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "resolve_identity_claim"))
    assert audit.details["before"]["full_name"] == "Autumn Redleaf" and audit.details["status"] == "accepted"
    assert db.scalar(select(Character).where(Character.full_name == "Autumne Redleaf")) is not None
