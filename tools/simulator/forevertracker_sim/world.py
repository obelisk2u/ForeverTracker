"""Simulate a population of Forever characters running dungeons, and the addon users among them.

The simulation has two layers:

1. **Ground truth**: characters, groups, dungeon runs, boss pulls, deaths and meter totals.
2. **Observations**: what each ForeverTracker user in a group would have recorded, with the
   imperfections real data will have: late entry, leaving early, secret or partial meters,
   name-only identities, in-progress records later superseded, occasional disagreement
   (tampering or bugs), and duplicate uploads.

Only layer 2 is uploaded. Layer 1 is returned too so tests can check reconciliation against
the truth.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Any

SYNTHETIC_MAP_BASE = 990_000
DAY = 86_400

# The nine dungeons Blizzard announced for Forever (names and level ranges from public
# previews). Map IDs and bosses are SYNTHETIC: the real IDs are unknown until launch.
DUNGEONS = [
    ("Hall of Thanes", 13, 18, 4),
    ("Ruins of Lordaeron", 15, 20, 4),
    ("Excavation Site", 24, 29, 4),
    ("City of Dalaran", 28, 33, 5),
    ("The Drowned City", 35, 40, 4),
    ("Krol'dok Stronghold", 40, 45, 5),
    ("Alcaz Prison", 48, 53, 5),
    ("Blackmaw Hold", 55, 60, 5),
    ("Shaper's Terrace", 58, 60, 4),
]

CLASSES = {
    "WARRIOR": ("TANK", "DAMAGER"),
    "PALADIN": ("TANK", "HEALER", "DAMAGER"),
    "HUNTER": ("DAMAGER",),
    "ROGUE": ("DAMAGER",),
    "PRIEST": ("HEALER", "DAMAGER"),
    "SHAMAN": ("HEALER", "DAMAGER"),
    "MAGE": ("DAMAGER",),
    "WARLOCK": ("DAMAGER",),
    "DRUID": ("TANK", "HEALER", "DAMAGER"),
}
ALLIANCE = ["Human", "Dwarf", "NightElf", "Gnome", "Skyborne"]
HORDE = ["Orc", "Scourge", "Tauren", "Troll"]
NAMESPACES = [((1, "pve"), 0.5), ((1, "hardcore"), 0.15), ((3, "pve"), 0.25), ((3, "rp"), 0.10)]

SYL_A = ["Ae", "Bra", "Cael", "Dor", "El", "Fen", "Gar", "Hal", "Isa", "Jor", "Kae", "Lio", "Mar", "Nyl", "Or", "Pel", "Quin",
         "Ral", "Syl", "Tor", "Ul", "Var", "Wyn", "Xa", "Yor", "Zel", "Ash", "Bel", "Cor", "Dra", "Eri", "Fae", "Gwen", "Ith"]
SYL_B = ["a", "ar", "en", "ia", "in", "is", "on", "or", "ra", "ric", "wen", "wyn", "ys", "eth", "ael", "dor", "mir", "ros", "th", "vin"]
SURNAMES = ["Redleaf", "Beardlong", "Longhorn", "Brightvale", "Stonefist", "Ashgrove", "Ironvein", "Duskwhisper", "Emberfall",
            "Frostmane", "Goldhammer", "Highcliff", "Moonbrook", "Nightbloom", "Oakenshield", "Proudmoore", "Quickstep",
            "Ravenhill", "Silverleaf", "Thornwood", "Underbough", "Valewind", "Wildmane", "Yewbranch", "Brackwater",
            "Cinderhelm", "Deepforge", "Fairwind", "Greymoor", "Hollowell", "Kettleby", "Lightwater", "Marshfield"]


@dataclass
class SimConfig:
    seed: int = 42
    characters: int = 2500
    runs: int = 1200
    days: int = 35
    addon_user_share: float = 0.12
    end_time: int = 1_792_800_000  # 2026-10-24T00:00:00Z: inside the beta window, before "now"
    conflict_rate: float = 0.03
    duplicate_upload_rate: float = 0.04


@dataclass
class Character:
    idx: int
    guid: str
    name: str
    surname: str
    class_file: str
    race_file: str
    faction: str
    region_id: int
    ruleset: str
    roles: tuple[str, ...]
    level: float
    ilvl: float
    skill: float
    clumsiness: float
    cluster: int
    installation: str | None = None
    rename_to: tuple[str, int] | None = None  # (new first name, time)

    def name_at(self, t: int) -> str:
        if self.rename_to and t >= self.rename_to[1]:
            return self.rename_to[0]
        return self.name


@dataclass
class TruthRun:
    key: str
    dungeon: int
    namespace: tuple[int, str]
    start: int
    end: int
    members: list[Character]
    roles: dict[int, str]
    outcome: str
    verified: bool
    pulls: list[dict]
    deaths: list[tuple[int, int, int | None]]  # (char idx, time, encounter id)
    meter: dict[int, dict[str, float]]
    combat_seconds: float
    presence: dict[int, tuple[int, int]]
    party_guid: str
    levels: dict[int, int] = field(default_factory=dict)  # level of each member at the time of the run
    ilvls: dict[int, float] = field(default_factory=dict)


@dataclass
class SimResult:
    batches: list[tuple[int, dict[str, Any]]] = field(default_factory=list)  # (upload time, batch)
    truth: list[TruthRun] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)


def _first_name(rng: random.Random) -> str:
    return (rng.choice(SYL_A) + rng.choice(SYL_B)).capitalize()


def build_population(cfg: SimConfig, rng: random.Random) -> list[Character]:
    taken: set[tuple[int, str, str]] = set()
    chars: list[Character] = []
    ns_choices = [ns for ns, _ in NAMESPACES]
    ns_weights = [w for _, w in NAMESPACES]
    clusters_per_ns = max(4, cfg.characters // 40)
    for i in range(cfg.characters):
        region_id, ruleset = rng.choices(ns_choices, ns_weights)[0]
        faction = rng.choice(["Alliance", "Horde"])
        race = rng.choice(ALLIANCE if faction == "Alliance" else HORDE)
        class_file = rng.choice(list(CLASSES))
        for _ in range(50):
            name, surname = _first_name(rng), rng.choice(SURNAMES)
            if (region_id, name, surname) not in taken:  # full names are unique per region
                break
        taken.add((region_id, name, surname))
        chars.append(
            Character(
                idx=i,
                guid="",  # assigned deterministically below
                name=name,
                surname=surname,
                class_file=class_file,
                race_file=race,
                faction=faction,
                region_id=region_id,
                ruleset=ruleset,
                roles=CLASSES[class_file],
                level=rng.uniform(12, 58),
                ilvl=0,
                skill=max(0.55, min(1.6, rng.gauss(1.0, 0.18))),
                clumsiness=max(0.2, min(3.0, rng.lognormvariate(0, 0.45))),
                cluster=rng.randrange(clusters_per_ns),
            )
        )
    # Deterministic GUIDs (Python's hash() is salted per process).
    for c in chars:
        digest = hashlib.sha256(f"{cfg.seed}:{c.idx}".encode()).hexdigest()[:8].upper()
        c.guid = f"Player-99{c.region_id}{0 if c.ruleset == 'pve' else 1}-{digest}"
        c.ilvl = round(c.level * 1.1 + rng.uniform(-2, 4), 1)

    # Name collisions across namespaces: copy some full names into the other region.
    for c in rng.sample(chars, k=max(3, cfg.characters // 120)):
        other_region = 3 if c.region_id == 1 else 1
        twin = next((x for x in chars if x.region_id == other_region and (other_region, c.name, c.surname) not in taken), None)
        if twin:
            taken.discard((twin.region_id, twin.name, twin.surname))
            twin.name, twin.surname = c.name, c.surname
            taken.add((twin.region_id, twin.name, twin.surname))
    # A few renames during the simulated period.
    end = cfg.end_time
    for c in rng.sample(chars, k=max(2, cfg.characters // 400)):
        c.rename_to = (_first_name(rng), end - rng.randrange(5, cfg.days - 5) * DAY)

    installations: list[str] = []
    for c in chars:
        if rng.random() < cfg.addon_user_share:
            # One in five addon users plays an alt on the same installation (account-wide file).
            if installations and rng.random() < 0.2:
                c.installation = rng.choice(installations)
            else:
                c.installation = "sim-" + hashlib.sha256(f"{cfg.seed}:inst:{c.idx}".encode()).hexdigest()[:16]
                installations.append(c.installation)
    return chars


def _pick_group(rng: random.Random, pool: list[Character], level_lo: int, level_hi: int, cluster_bias: bool) -> dict[str, Character] | None:
    eligible = [c for c in pool if level_lo - 2 <= c.level <= level_hi + 2]
    if len(eligible) < 5:
        return None
    if cluster_bias:
        cluster = rng.choice(eligible).cluster
        friends = [c for c in eligible if c.cluster == cluster]
        if len(friends) >= 3:
            extra = [c for c in rng.sample(eligible, k=min(len(eligible), 15)) if c.cluster != cluster]
            eligible = friends + extra
    rng.shuffle(eligible)
    group: dict[str, Character] = {}
    used: set[int] = set()
    for role in ("TANK", "HEALER"):
        for c in eligible:
            if c.idx not in used and role in c.roles:
                group[role] = c
                used.add(c.idx)
                break
        else:
            return None
    dps = [c for c in eligible if c.idx not in used and "DAMAGER" in c.roles][:3]
    if len(dps) < 3:
        return None
    for i, c in enumerate(dps):
        group[f"DAMAGER{i}"] = c
    return group


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def simulate_truth(cfg: SimConfig, rng: random.Random, chars: list[Character]) -> list[TruthRun]:
    start_time = cfg.end_time - cfg.days * DAY
    times = sorted(rng.randrange(start_time, cfg.end_time - 4 * 3600) for _ in range(cfg.runs * 2))
    by_pool: dict[tuple[int, str, str], list[Character]] = {}
    for c in chars:
        by_pool.setdefault((c.region_id, c.ruleset, c.faction), []).append(c)
    pools = list(by_pool.items())
    busy_until: dict[int, int] = {}
    runs: list[TruthRun] = []
    addon_pool_weights = [sum(1 for c in p if c.installation) + 1 for _, p in pools]
    for t in times:
        if len(runs) >= cfg.runs:
            break
        (region_id, ruleset, _), pool = rng.choices(pools, addon_pool_weights)[0]
        free = [c for c in pool if busy_until.get(c.idx, 0) < t]
        if len(free) < 5:
            continue
        # Bias towards groups that contain an addon user: those are the runs that get observed.
        seed_char = rng.choice([c for c in free if c.installation] or free)
        dungeon_idx = min(range(len(DUNGEONS)), key=lambda i: abs((DUNGEONS[i][1] + DUNGEONS[i][2]) / 2 - seed_char.level))
        name, lo, hi, bosses = DUNGEONS[dungeon_idx]
        group = _pick_group(rng, [seed_char] + [c for c in free if c.idx != seed_char.idx], lo, hi, cluster_bias=rng.random() < 0.6)
        if group is None or not any(c.installation for c in group.values()):
            continue
        run = _play(cfg, rng, t, dungeon_idx, (region_id, ruleset), group, len(runs))
        for c in run.members:
            busy_until[c.idx] = run.end + 300
            c.level = min(60.0, c.level + rng.uniform(0.15, 0.6))
            c.ilvl = round(min(80.0, c.ilvl + rng.uniform(0.0, 0.8)), 1)
        runs.append(run)
    return runs


def _play(cfg, rng, start, dungeon_idx, namespace, group, n) -> TruthRun:
    name, lo, hi, bosses = DUNGEONS[dungeon_idx]
    members = list(group.values())
    roles = {c.idx: ("DAMAGER" if role.startswith("DAMAGER") else role) for role, c in group.items()}
    group_skill = sum(c.skill for c in members) / len(members)
    clumsiness = sum(c.clumsiness for c in members) / len(members)
    t = start + rng.randrange(30, 120)
    pulls: list[dict] = []
    deaths: list[tuple[int, int, int | None]] = []
    combat = 0.0
    roll = rng.random()
    outcome = "completed" if roll < 0.80 else "left" if roll < 0.90 else "abandoned" if roll < 0.95 else "disconnected"
    stop_after = bosses if outcome == "completed" else rng.randrange(0, bosses)
    presence = {c.idx: (start, 0) for c in members}
    # One in ten groups loses a member mid-run.
    leaver = rng.choice(members) if rng.random() < 0.10 and outcome == "completed" else None
    for b in range(bosses):
        # Trash before each boss.
        trash = rng.randrange(3, 7)
        for _ in range(trash):
            dur = rng.uniform(15, 45) / group_skill
            combat += dur
            for c in members:
                if rng.random() < 0.012 * c.clumsiness * (1.8 if roles[c.idx] == "TANK" else 1.0):
                    deaths.append((c.idx, int(t + dur * 0.7), None))
            t += int(dur + rng.uniform(20, 70))
        if b >= stop_after:
            break
        encounter_id = SYNTHETIC_MAP_BASE * 100 + (dungeon_idx + 1) * 10 + b + 1
        attempts = 0
        while True:
            attempts += 1
            dur = rng.uniform(60, 150) / group_skill
            success_chance = min(0.97, 0.55 + 0.35 * (group_skill - 0.6) - 0.08 * (clumsiness - 1)) + 0.15 * (attempts - 1)
            success = rng.random() < success_chance
            pull = {"encounter_id": encounter_id, "name": f"{name} · Boss {b + 1}", "start": int(t), "end": int(t + dur), "success": success}
            pulls.append(pull)
            combat += dur
            if success:
                for c in members:
                    if rng.random() < 0.06 * c.clumsiness:
                        deaths.append((c.idx, int(t + dur * rng.uniform(0.3, 0.9)), encounter_id))
            else:
                # A wipe: everyone dies within a few seconds.
                for i, c in enumerate(members):
                    deaths.append((c.idx, int(t + dur - 6 + i * 1.5), encounter_id))
            t += int(dur + rng.uniform(45, 120))
            if success or attempts >= 4:
                break
        if leaver and b == 1:
            presence[leaver.idx] = (start, int(t))
    end = int(t + rng.uniform(30, 120))
    for idx, (s, e) in presence.items():
        if e == 0:
            presence[idx] = (s, end)
    meter: dict[int, dict[str, float]] = {}
    for c in members:
        role = roles[c.idx]
        p_start, p_end = presence[c.idx]
        share = (p_end - p_start) / max(1, end - start)
        base_dps = (6 + c.level * 1.9) * (1 + c.ilvl / 120) * c.skill
        dps = base_dps * {"TANK": 0.6, "HEALER": 0.12, "DAMAGER": 1.0}[role] * rng.uniform(0.9, 1.1)
        hps = base_dps * (0.95 if role == "HEALER" else 0.02) * rng.uniform(0.9, 1.1)
        meter[c.idx] = {
            "damage_done": round(dps * combat * share),
            "healing_done": round(hps * combat * share),
            "absorbs": round(hps * combat * share * (0.15 if role == "HEALER" else 0.0)),
            "interrupts": float(_poisson(rng, (4.5 if role == "DAMAGER" else 2.0) * c.skill * share)),
            "dispels": float(_poisson(rng, 3.0 * share) if role == "HEALER" else 0),
            "damage_taken": round(base_dps * combat * share * (1.6 if role == "TANK" else 0.35)),
            "avoidable_damage_taken": round(base_dps * combat * share * 0.05 * c.clumsiness),
            "deaths": float(sum(1 for d in deaths if d[0] == c.idx)),
        }
    verified = outcome == "completed" and rng.random() < 0.88
    return TruthRun(
        key=f"truth-{n}",
        dungeon=dungeon_idx,
        namespace=namespace,
        start=start,
        end=end,
        members=members,
        roles=roles,
        outcome=outcome,
        verified=verified,
        pulls=pulls,
        deaths=deaths,
        meter=meter,
        combat_seconds=round(combat, 1),
        presence=presence,
        party_guid=f"Party-99-{hashlib.sha256(f'{start}:{n}'.encode()).hexdigest()[:12].upper()}",
        levels={c.idx: int(c.level) for c in members},
        ilvls={c.idx: c.ilvl for c in members},
    )


def observe(cfg: SimConfig, rng: random.Random, run: TruthRun, observer: Character, seq: int) -> list[dict[str, Any]]:
    """What one ForeverTracker user in the group recorded (one or two revisions)."""
    name, *_ = DUNGEONS[run.dungeon]
    entry = run.start + rng.randrange(0, 90)
    obs_end = run.presence[observer.idx][1]
    leaves_early = rng.random() < 0.06
    if leaves_early:
        obs_end = entry + int((obs_end - entry) * rng.uniform(0.4, 0.8))
    refs: dict[int, str] = {}
    roster = []
    for i, c in enumerate(run.members, 1):
        refs[c.idx] = f"u{i}"
        p_start, p_end = run.presence[c.idx]
        start, end = max(p_start, entry), min(p_end, obs_end)
        if end <= start:
            start, end = entry, entry + 1
        identity_roll = rng.random() if c.idx != observer.idx else 1.0
        member = {
            "ref": f"u{i}",
            "guid": None if identity_roll < 0.02 else c.guid,
            "name": None if identity_roll < 0.005 else c.name_at(run.start),
            "surname": None if identity_roll < 0.005 else c.surname,
            "identity_status": "secret" if identity_roll < 0.005 else "ok",
            "class_file": c.class_file,
            "race_file": c.race_file,
            "level": run.levels[c.idx],
            "role": run.roles[c.idx] if rng.random() > 0.15 else "NONE",
            "is_observer": c.idx == observer.idx,
            "presence": [{"start": start, "end": end}],
        }
        if member["identity_status"] == "secret":
            member["guid"] = None
        roster.append(member)

    collect_deaths = rng.random() < 0.95
    deaths = []
    if collect_deaths:
        for idx, at, enc in run.deaths:
            if entry <= at <= obs_end:
                deaths.append({"unit_ref": refs[idx], "at": at + rng.choice([0, 0, 1]), "source": "player_dead" if idx == observer.idx else "unit_state", "encounter_id": enc})
    encounters = [
        {"encounter_id": p["encounter_id"], "name": p["name"], "difficulty_id": 1, "group_size": 5,
         "started_at": p["start"], "ended_at": p["end"], "success": p["success"]}
        for p in run.pulls
        if entry <= p["start"] <= obs_end
    ]

    meter_roll = rng.random()
    covered = (obs_end - entry) / max(1, run.end - run.start)
    sessions_n = max(1, int(run.combat_seconds / 40))
    session_len = run.combat_seconds / sessions_n
    seen = max(1, int(sessions_n * min(1.0, covered)))
    if meter_roll < 0.03:
        meter: dict[str, Any] = {"status": "disabled", "sessions": [], "totals": [], "death_entries": []}
    elif meter_roll < 0.06:
        meter = {"status": "secret", "combat_seconds": 0, "sessions": [{"session_id": 1000 + i, "status": "secret"} for i in range(seen)],
                 "totals": [], "death_entries": []}
    else:
        partial = meter_roll < 0.14 or leaves_early
        captured = seen if not partial else max(1, int(seen * rng.uniform(0.5, 0.9)))
        fraction = captured / sessions_n
        sessions = [
            {"session_id": 1000 + i, "duration_sec": round(session_len, 1), "status": "captured" if i < captured else "secret", "captured_at": entry + 60 * (i + 1)}
            for i in range(seen)
        ]
        totals = []
        death_entries = []
        for c in run.members:
            truth = run.meter[c.idx]
            metrics = {}
            for metric, value in truth.items():
                v = value * fraction if metric not in ("deaths",) else value
                if metric in ("interrupts", "dispels"):
                    v = round(v)
                metrics[metric] = {"value": float(round(v)), "status": "observed" if captured == seen and not partial else "partial", "sessions": captured}
            totals.append({"unit_ref": refs[c.idx], "guid": c.guid, "name": c.name_at(run.start), "class_file": c.class_file, "metrics": metrics})
            for k in range(int(truth["deaths"])):
                death_entries.append({"unit_ref": refs[c.idx], "guid": c.guid, "session_id": 1000 + k, "death_time_sec": 12.0, "death_recap_id": 5000 + k, "total": 1.0})
        meter = {"status": "observed" if captured == seen and not partial else "partial",
                 "combat_seconds": round(session_len * captured, 1), "sessions": sessions, "totals": totals, "death_entries": death_entries}
        if rng.random() < cfg.conflict_rate and totals:
            victim = rng.choice(totals)
            victim["metrics"]["damage_done"]["value"] = float(round(victim["metrics"]["damage_done"]["value"] * rng.uniform(1.15, 1.6)))

    state = run.outcome
    if leaves_early and state == "completed":
        state = "left"
    completed = state == "completed" and run.verified and run.presence[observer.idx][1] >= run.end - 60
    if state == "completed" and not completed:
        state = "unknown"
    if state == "disconnected" and rng.random() < 0.5:
        state = "left"
    ended = obs_end if state != "completed" else run.end
    timeline = [{"at": entry, "kind": "entered", "detail": {"map_id": SYNTHETIC_MAP_BASE + run.dungeon + 1}}]
    for p in run.pulls:
        if entry <= p["start"] <= obs_end:
            timeline.append({"at": p["start"], "kind": "encounter_start", "detail": {"encounter_id": p["encounter_id"]}})
            timeline.append({"at": p["end"], "kind": "encounter_end", "detail": {"encounter_id": p["encounter_id"], "success": 1 if p["success"] else 0}})
    if completed:
        timeline.append({"at": run.end - 30, "kind": "completed", "detail": {"source": "lfg_completion_reward"}})
    timeline.append({"at": ended, "kind": "left_instance", "detail": {}})

    base = {
        "type": "dungeon_run",
        "observation_id": f"r-{run.start}-{seq}",
        "revision": 2,
        "recorded_by": {"guid": observer.guid, "name": observer.name_at(run.start), "surname": observer.surname, "identity_status": "ok"},
        "namespace": {"region_id": run.namespace[0], "region_name": "US" if run.namespace[0] == 1 else "EU", "ruleset": run.namespace[1]},
        "realm_label": "70",
        "client_build": "70532",
        "instance": {"map_id": SYNTHETIC_MAP_BASE + run.dungeon + 1, "name": name, "instance_type": "party",
                     "difficulty_id": 1, "difficulty_name": "Normal", "max_players": 5},
        "party_guid": run.party_guid if rng.random() < 0.7 else None,
        "timing": {"started_at": entry, "ended_at": ended, "last_updated_at": ended, "clock": "server", "local_clock_offset": rng.randrange(-3, 4)},
        "state": state,
        "completion": {"status": "verified" if completed else "none",
                       "evidence": [{"kind": "lfg_completion_reward", "at": run.end - 30}] if completed else []},
        "timeline": timeline,
        "roster": roster,
        "encounters": encounters,
        "deaths": deaths,
        "meter": meter,
        "collection": {"identity": "active", "roster": "active", "encounters": "active",
                       "deaths_unit_state": "active" if collect_deaths else "disabled",
                       "meter": {"observed": "active", "disabled": "disabled", "secret": "partial"}.get(meter["status"], "partial"),
                       "inspect": "active", "talents": "disabled"},
        "flags": {},
    }
    out = []
    if rng.random() < 0.08:
        # A /reload mid-run saved an in-progress revision that was uploaded before the final one.
        mid = entry + (ended - entry) // 2
        early = _truncate(base, mid)
        out.append(early)
    out.append(base)
    return out


def _truncate(obs: dict[str, Any], at: int) -> dict[str, Any]:
    import copy

    early = copy.deepcopy(obs)
    early["revision"] = 1
    early["state"] = "in_progress"
    early["completion"] = {"status": "none", "evidence": []}
    early["timing"]["ended_at"] = None
    early["timing"]["last_updated_at"] = at
    early["timeline"] = [e for e in early["timeline"] if e["at"] <= at]
    early["encounters"] = [e for e in early["encounters"] if e["started_at"] <= at and (e["ended_at"] or 0) <= at]
    early["deaths"] = [d for d in early["deaths"] if d["at"] <= at]
    for m in early["roster"]:
        m["presence"] = [{"start": p["start"], "end": None} for p in m["presence"] if p["start"] <= at] or [{"start": at - 1, "end": None}]
    meter = early["meter"]
    if meter.get("totals"):
        for t in meter["totals"]:
            for v in t["metrics"].values():
                if v["value"] is not None:
                    v["value"] = float(round(v["value"] / 2))
        meter["combat_seconds"] = round((meter.get("combat_seconds") or 0) / 2, 1)
        meter["sessions"] = meter["sessions"][: max(1, len(meter["sessions"]) // 2)]
        meter["death_entries"] = []
    return early


def _snapshot(char: Character, observer: Character, run: TruthRun, t: int, source: str, seq: int, rng: random.Random) -> dict[str, Any]:
    ilvl, level = run.ilvls[char.idx], run.levels[char.idx]
    slots = [1, 3, 5, 6, 7, 8, 9, 10, 15, 16]
    items = [{"slot": s, "item_id": 900000 + char.idx * 20 + s + int(ilvl) * 1000, "item_level": max(1, int(ilvl + rng.uniform(-3, 3))),
              "enchant_id": 7000 + s if rng.random() < 0.3 else None, "gem_ids": [], "quality": 3 if ilvl > 30 else 2, "link": None}
             for s in slots]
    return {
        "type": "character_snapshot",
        "observation_id": f"s-{t}-{seq}",
        "revision": 1,
        "recorded_by": {"guid": observer.guid, "name": observer.name_at(t), "surname": observer.surname, "identity_status": "ok"},
        "namespace": {"region_id": char.region_id, "region_name": "US" if char.region_id == 1 else "EU", "ruleset": char.ruleset},
        "realm_label": "70",
        "client_build": "70532",
        "observed_at": t,
        "source": source,
        "subject": {"guid": char.guid, "name": char.name_at(t), "surname": char.surname, "identity_status": "ok",
                    "class_file": char.class_file, "race_file": char.race_file, "level": level},
        "equipment": {"status": "observed", "average_item_level": ilvl, "items": items},
        "talents": {"status": "disabled"},
    }


def _batch(installation: str, observations: list[dict[str, Any]], created_at: int) -> dict[str, Any]:
    digest = hashlib.sha256((installation + repr([(o["observation_id"], o["revision"]) for o in observations])).encode()).hexdigest()
    return {
        "format": "forevertracker.batch",
        "schema_version": 1,
        "batch_id": f"sim-{digest[:40]}",
        "installation_id": installation,
        "created_at": created_at,
        "synthetic": True,
        "addon": {"name": "ForeverTracker", "version": "0.1.0-sim", "schema_version": 1},
        "client": {"game_version": "1.60.1", "build": "70532", "interface": 16001, "locale": "enUS", "project_id": 1},
        "observations": observations,
    }


def simulate(cfg: SimConfig | None = None) -> SimResult:
    cfg = cfg or SimConfig()
    rng = random.Random(cfg.seed)
    chars = build_population(cfg, rng)
    # Snapshot the starting level/ilvl so observations can reflect progression over time.
    truth = simulate_truth(cfg, rng, chars)
    pending: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    seq = 0
    for run in truth:
        for observer in [c for c in run.members if c.installation]:
            seq += 1
            for obs in observe(cfg, rng, run, observer, seq):
                upload_at = obs["timing"]["last_updated_at"] + rng.randrange(600, 3 * DAY)
                if obs["revision"] == 1:
                    upload_at = obs["timing"]["last_updated_at"] + rng.randrange(60, 900)
                pending.setdefault(observer.installation, []).append((upload_at, obs))
            seq += 1
            t = run.end + 30
            pending[observer.installation].append((t + rng.randrange(600, 2 * DAY), _snapshot(observer, observer, run, t, "self", seq, rng)))
            for other in run.members:
                if other.idx != observer.idx and rng.random() < 0.35:
                    seq += 1
                    pending[observer.installation].append((t + rng.randrange(600, 2 * DAY), _snapshot(other, observer, run, run.start + 300, "inspect", seq, rng)))

    result = SimResult(truth=truth, characters=chars)
    for installation, items in pending.items():
        items.sort(key=lambda x: x[0])
        # Uploads happen in bursts (after logging out): group by day.
        by_day: dict[int, list[tuple[int, dict[str, Any]]]] = {}
        for at, obs in items:
            by_day.setdefault(at // DAY, []).append((at, obs))
        for _, group in sorted(by_day.items()):
            at = max(a for a, _ in group)
            observations = [o for _, o in group]
            for i in range(0, len(observations), 150):
                batch = _batch(installation, observations[i : i + 150], at)
                result.batches.append((at, batch))
                if rng.random() < cfg.duplicate_upload_rate:
                    result.batches.append((at + rng.randrange(60, DAY), batch))  # the same upload, twice
    result.batches.sort(key=lambda x: x[0])
    return result
