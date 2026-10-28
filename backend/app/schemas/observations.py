"""The ForeverTracker observation contract, schema version 1.

This is the single source of truth for what an addon export may contain. It is exported as
JSON Schema to ``schema/observation-batch.v1.schema.json`` (``python -m app.cli export-schema``)
and documented in ``docs/OBSERVATION_SCHEMA.md``.

Everything here is *structural* validation of untrusted input. Plausibility checks that
quarantine rather than reject live in ``app/integrity/sanity.py``.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter

BATCH_FORMAT = "forevertracker.batch"
SCHEMA_VERSION = 1


def _empty_list_as_dict(value: Any) -> Any:
    # Lua cannot distinguish an empty array from an empty map; the SavedVariables parser
    # yields [] for both.
    return {} if value == [] else value


def _dict_as_list(value: Any) -> Any:
    if isinstance(value, dict) and all(isinstance(k, int) for k in value):
        return [value[k] for k in sorted(value)]
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Epoch = Annotated[int, Field(ge=0, le=4_102_444_800)]  # <= 2100-01-01
NameStr = Annotated[str, Field(min_length=1, max_length=48, pattern=r"^[^\x00-\x1f\x7f]+$")]
ShortText = Annotated[str, Field(max_length=120, pattern=r"^[^\x00-\x1f\x7f]*$")]
Guid = Annotated[str, Field(min_length=3, max_length=96, pattern=r"^[A-Za-z0-9-]+$")]
UnitRef = Annotated[str, Field(min_length=1, max_length=16, pattern=r"^[a-z0-9_]+$")]
ObservationId = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9:_.-]+$")]
ClassFile = Annotated[str, Field(min_length=2, max_length=24, pattern=r"^[A-Z_]+$")]
RaceFile = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[A-Za-z_]+$")]
Role = Literal["TANK", "HEALER", "DAMAGER", "NONE"]
IdentityStatus = Literal["ok", "secret", "unavailable"]
Ruleset = Literal["pve", "pvp", "rp", "hardcore", "unknown"]
Amount = Annotated[float, Field(ge=0, le=1e13)]

DetailValue = Union[str, int, float, bool, None]


def _list(max_len: int, item: Any) -> Any:
    return Annotated[list[item], BeforeValidator(_dict_as_list), Field(max_length=max_len)]


class NamespaceInfo(Strict):
    """Where a character name is unique. Forever is realmless; names are unique per region (and ruleset)."""

    region_id: int | None = Field(default=None, ge=0, le=1000)
    region_name: str | None = Field(default=None, max_length=16, pattern=r"^[A-Za-z]*$")
    ruleset: Ruleset = "unknown"


class CharacterRef(Strict):
    guid: Guid | None = None
    name: NameStr | None = None
    surname: NameStr | None = None
    identity_status: IdentityStatus = "ok"


class Interval(Strict):
    start: Epoch
    end: Epoch | None = None


class RosterMember(Strict):
    ref: UnitRef
    guid: Guid | None = None
    name: NameStr | None = None
    surname: NameStr | None = None
    identity_status: IdentityStatus = "ok"
    class_file: ClassFile | None = None
    class_id: int | None = Field(default=None, ge=0, le=100)
    race_file: RaceFile | None = None
    race_id: int | None = Field(default=None, ge=0, le=1000)
    level: int | None = Field(default=None, ge=1, le=200)
    role: Role | None = None
    is_observer: bool = False
    presence: _list(64, Interval) = Field(default_factory=list)
    connection_drops: int = Field(default=0, ge=0, le=1000)


class InstanceInfo(Strict):
    map_id: int = Field(ge=0, le=100_000_000)
    name: ShortText | None = None
    instance_type: Literal["party", "raid", "scenario", "pvp", "arena", "none"] = "party"
    difficulty_id: int | None = Field(default=None, ge=0, le=1000)
    difficulty_name: ShortText | None = None
    max_players: int | None = Field(default=None, ge=1, le=80)
    lfg_dungeon_id: int | None = Field(default=None, ge=0, le=100_000_000)


class RunTiming(Strict):
    started_at: Epoch
    ended_at: Epoch | None = None
    last_updated_at: Epoch
    clock: Literal["server"] = "server"
    local_clock_offset: int | None = Field(default=None, ge=-86_400 * 366, le=86_400 * 366)


class CompletionEvidence(Strict):
    kind: Literal["lfg_completion_reward", "scenario_completed", "challenge_mode_completed"]
    at: Epoch


class Completion(Strict):
    status: Literal["verified", "none"] = "none"
    evidence: _list(10, CompletionEvidence) = Field(default_factory=list)


TimelineKind = Literal[
    "entered", "left_instance", "reentered", "reload", "login", "logout", "group_joined", "group_left",
    "roster_changed", "encounter_start", "encounter_end", "completed", "abandon_vote", "disconnected",
    "meter_reset", "probe",
]


class TimelineEvent(Strict):
    at: Epoch
    kind: TimelineKind
    detail: Annotated[
        dict[Annotated[str, Field(max_length=32, pattern=r"^[a-z0-9_]+$")], DetailValue],
        BeforeValidator(_empty_list_as_dict),
        Field(max_length=12),
    ] = Field(default_factory=dict)


class Encounter(Strict):
    encounter_id: int = Field(ge=0, le=100_000_000)
    name: ShortText | None = None
    difficulty_id: int | None = Field(default=None, ge=0, le=1000)
    group_size: int | None = Field(default=None, ge=0, le=80)
    started_at: Epoch
    ended_at: Epoch | None = None
    success: bool | None = None


class Death(Strict):
    unit_ref: UnitRef
    at: Epoch
    source: Literal["unit_state", "player_dead", "unit_died_event"]
    encounter_id: int | None = Field(default=None, ge=0, le=100_000_000)


MeterMetric = Literal[
    "damage_done", "healing_done", "absorbs", "interrupts", "dispels",
    "damage_taken", "avoidable_damage_taken", "deaths",
]
MeterValueStatus = Literal["observed", "secret", "unavailable", "partial"]


class MeterValue(Strict):
    value: Amount | None = None
    status: MeterValueStatus
    sessions: int = Field(default=0, ge=0, le=10_000)


class MeterUnitTotals(Strict):
    unit_ref: UnitRef | None = None
    guid: Guid | None = None
    name: NameStr | None = None
    class_file: ClassFile | None = None
    metrics: Annotated[dict[MeterMetric, MeterValue], BeforeValidator(_empty_list_as_dict)] = Field(
        default_factory=dict
    )


class MeterSession(Strict):
    session_id: int = Field(ge=0, le=2**31)
    duration_sec: float | None = Field(default=None, ge=0, le=86_400)
    status: Literal["captured", "secret", "missed", "partial"]
    captured_at: Epoch | None = None
    encounter_id: int | None = Field(default=None, ge=0, le=100_000_000)


class MeterDeathEntry(Strict):
    unit_ref: UnitRef | None = None
    guid: Guid | None = None
    session_id: int = Field(ge=0, le=2**31)
    death_time_sec: float | None = Field(default=None, ge=-1, le=86_400)
    death_recap_id: int | None = Field(default=None, ge=0, le=2**31)
    total: Amount | None = None


class MeterData(Strict):
    status: Literal["observed", "partial", "secret", "unavailable", "disabled"]
    reason: ShortText | None = None
    combat_seconds: float | None = Field(default=None, ge=0, le=86_400)
    sessions: _list(400, MeterSession) = Field(default_factory=list)
    totals: _list(40, MeterUnitTotals) = Field(default_factory=list)
    death_entries: _list(500, MeterDeathEntry) = Field(default_factory=list)


CollectorName = Literal[
    "identity", "roster", "encounters", "deaths_unit_state", "deaths_unit_died", "meter", "inspect", "talents"
]
CollectorStatus = Literal["active", "partial", "unavailable", "disabled", "error"]


class _ObservationBase(Strict):
    observation_id: ObservationId
    revision: int = Field(ge=1, le=100_000)
    recorded_by: CharacterRef
    namespace: NamespaceInfo = Field(default_factory=NamespaceInfo)
    realm_label: ShortText | None = None
    client_build: Annotated[str, Field(max_length=16, pattern=r"^[0-9.]*$")] | None = None


class DungeonRunObservation(_ObservationBase):
    type: Literal["dungeon_run"]
    instance: InstanceInfo
    party_guid: Guid | None = None
    timing: RunTiming
    state: Literal["in_progress", "completed", "left", "abandoned", "disconnected", "unknown"]
    completion: Completion = Field(default_factory=Completion)
    timeline: _list(400, TimelineEvent) = Field(default_factory=list)
    roster: Annotated[list[RosterMember], BeforeValidator(_dict_as_list), Field(min_length=1, max_length=40)]
    encounters: _list(100, Encounter) = Field(default_factory=list)
    deaths: _list(500, Death) = Field(default_factory=list)
    meter: MeterData | None = None
    collection: Annotated[dict[CollectorName, CollectorStatus], BeforeValidator(_empty_list_as_dict)] = Field(
        default_factory=dict
    )
    flags: Annotated[
        dict[Annotated[str, Field(max_length=32, pattern=r"^[a-z0-9_]+$")], bool],
        BeforeValidator(_empty_list_as_dict),
        Field(max_length=16),
    ] = Field(default_factory=dict)


class EquippedItem(Strict):
    slot: int = Field(ge=1, le=19)
    item_id: int = Field(ge=1, le=100_000_000)
    item_level: int | None = Field(default=None, ge=0, le=2000)
    enchant_id: int | None = Field(default=None, ge=0, le=100_000_000)
    gem_ids: _list(4, Annotated[int, Field(ge=0, le=100_000_000)]) = Field(default_factory=list)
    quality: int | None = Field(default=None, ge=0, le=10)
    link: Annotated[str, Field(max_length=400, pattern=r"^[^\x00-\x1f\x7f]*$")] | None = None


class Equipment(Strict):
    status: Literal["observed", "partial", "unavailable"]
    average_item_level: float | None = Field(default=None, ge=0, le=2000)
    items: _list(19, EquippedItem) = Field(default_factory=list)


class Talents(Strict):
    status: Literal["observed", "unavailable", "disabled"]
    spec_id: int | None = Field(default=None, ge=0, le=100_000)
    import_string: Annotated[str, Field(max_length=2000, pattern=r"^[A-Za-z0-9+/=_-]*$")] | None = None


class SnapshotSubject(CharacterRef):
    class_file: ClassFile | None = None
    race_file: RaceFile | None = None
    level: int | None = Field(default=None, ge=1, le=200)


class CharacterSnapshotObservation(_ObservationBase):
    type: Literal["character_snapshot"]
    observed_at: Epoch
    source: Literal["self", "inspect"]
    subject: SnapshotSubject
    equipment: Equipment | None = None
    talents: Talents | None = None


class ProbeResult(Strict):
    check: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]
    status: Literal["pass", "fail", "warn", "skip", "info"]
    detail: Annotated[str, Field(max_length=300, pattern=r"^[^\x00-\x08\x0b-\x1f\x7f]*$")] | None = None


class ProbeReportObservation(_ObservationBase):
    type: Literal["probe_report"]
    observed_at: Epoch
    results: _list(300, ProbeResult) = Field(default_factory=list)


Observation = Annotated[
    Union[DungeonRunObservation, CharacterSnapshotObservation, ProbeReportObservation],
    Field(discriminator="type"),
]
observation_adapter: TypeAdapter[Observation] = TypeAdapter(Observation)


class AddonInfo(Strict):
    name: Literal["ForeverTracker"] = "ForeverTracker"
    version: Annotated[str, Field(max_length=32, pattern=r"^[A-Za-z0-9.+_-]*$")] = "unknown"
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=100)


class ClientInfo(BaseModel):
    """Client build information. Unknown keys from newer addon versions are ignored."""

    model_config = ConfigDict(extra="ignore")

    game_version: Annotated[str, Field(max_length=16, pattern=r"^[0-9.]*$")] | None = None
    build: Annotated[str, Field(max_length=16, pattern=r"^[0-9.]*$")] | None = None
    interface: int | None = Field(default=None, ge=0, le=10_000_000)
    locale: Annotated[str, Field(max_length=8, pattern=r"^[A-Za-z]*$")] | None = None
    project_id: int | None = Field(default=None, ge=0, le=1000)
    game_type: Annotated[str, Field(max_length=24, pattern=r"^[A-Za-z_]*$")] | None = None


class ObservationBatchEnvelope(Strict):
    """The upload envelope. Observations are validated one by one after the envelope."""

    format: Literal["forevertracker.batch"]
    schema_version: Literal[1]
    batch_id: Annotated[str, Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9:_.-]+$")]
    installation_id: Annotated[str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    created_at: Epoch | None = None
    synthetic: bool = False
    addon: AddonInfo = Field(default_factory=AddonInfo)
    client: Annotated[ClientInfo, BeforeValidator(_empty_list_as_dict)] = Field(default_factory=ClientInfo)
    observations: Annotated[list[dict[str, Any]], BeforeValidator(_dict_as_list), Field(min_length=1)]


def observation_json_schema() -> dict[str, Any]:
    envelope = ObservationBatchEnvelope.model_json_schema()
    envelope["$defs"] = envelope.get("$defs", {})
    obs_schema = observation_adapter.json_schema(ref_template="#/$defs/{model}")
    envelope["$defs"].update(obs_schema.pop("$defs", {}))
    envelope["properties"]["observations"]["items"] = obs_schema
    envelope["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    envelope["$id"] = "https://forevertracker.example/schema/observation-batch.v1.schema.json"
    envelope["title"] = "ForeverTracker observation batch, schema version 1"
    return envelope
