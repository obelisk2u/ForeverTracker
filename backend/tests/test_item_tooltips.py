"""Item tooltips as the addon read them in game: stored per item, shown on any gear with that item."""

from sqlalchemy import select

from app.models import EquipmentSnapshot, ItemTooltipReport, RawObservation
from app.services.items import item_key
from app.services.runs import run_detail
from tests.factories import T0, RunSpec, batch, gear_snapshot, party, run_observation
from tests.helpers import ingest, runs

HELM = [{"left": "Test Item 1", "color": "1eff00"}, {"left": "Binds when equipped"}, {"left": "Head", "right": "Plate"}]


def with_tooltip(snap: dict, slot: int, lines: list[dict]) -> dict:
    snap["equipment"]["items"][slot - 1]["tooltip"] = lines
    return snap


def served_gear(db, settings, name: str):
    (run,) = runs(db)
    return next(p.gear for p in run_detail(db, settings, run.public_id).participants if p.character.full_name == name)


def test_a_tooltip_is_stored_for_its_item_and_shown_with_the_gear(db, settings):
    autumn, mah, *_ = party()
    snap = with_tooltip(gear_snapshot("s-1", autumn, mah, T0 + 600, [22] * 2), 1, HELM)
    result = ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1")), snap]))
    assert [o.status for o in result.observations] == ["accepted", "accepted"]

    (report,) = db.scalars(select(ItemTooltipReport)).all()
    assert (report.item_key, report.item_id) == ("1001", 1001)
    (gear,) = db.scalars(select(EquipmentSnapshot)).all()
    assert all("tooltip" not in item for item in gear.items), "kept per item, not with each character's gear"
    raw = db.scalar(select(RawObservation).where(RawObservation.type == "character_snapshot"))
    assert raw.payload["equipment"]["items"][0]["tooltip"], "the upload itself is kept whole"

    helm, gloves = served_gear(db, settings, "Mah Beardlong").items
    assert [(line.left, line.color, line.right) for line in helm.tooltip] == [
        ("Test Item 1", "1eff00", None),
        ("Binds when equipped", None, None),
        ("Head", None, "Plate"),
    ]
    assert gloves.tooltip is None


def test_gear_recorded_without_tooltips_shows_one_recorded_later_for_the_same_item(db, settings):
    autumn, mah, thalen, *_ = party()
    old = gear_snapshot("s-1", autumn, mah, T0 + 600, [22])  # by an addon that read no tooltips
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1")), old]))
    assert served_gear(db, settings, "Mah Beardlong").items[0].tooltip is None

    # Days later another player wears the same item, and their addon reads its tooltip.
    later = with_tooltip(gear_snapshot("s-9", thalen, thalen, T0 + 86_400 * 3, [22], source="self"), 1, HELM)
    ingest(db, settings, batch("install-bbbb2222", [later]))
    assert served_gear(db, settings, "Mah Beardlong").items[0].tooltip[0].left == "Test Item 1"


def test_the_version_most_installations_agree_on_is_shown(db, settings):
    autumn, mah, thalen, asha, *_ = party()
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1"))]))
    altered = [{"left": "Test Item 1"}, {"left": "+500 Stamina"}]
    uploads = [
        ("install-aaaa1111", gear_snapshot("s-1", autumn, mah, T0 + 600, [22]), HELM),
        ("install-bbbb2222", gear_snapshot("s-2", thalen, mah, T0 + 700, [22]), HELM),
        ("install-cccc3333", gear_snapshot("s-3", asha, mah, T0 + 800, [22]), altered),
        # One installation repeating itself still counts once.
        ("install-cccc3333", gear_snapshot("s-4", asha, asha, T0 + 900, [22], source="self"), altered),
    ]
    for installation, snap, lines in uploads:
        ingest(db, settings, batch(installation, [with_tooltip(snap, 1, lines)]))
    assert [line.left for line in served_gear(db, settings, "Mah Beardlong").items[0].tooltip] == [
        "Test Item 1",
        "Binds when equipped",
        "Head",
    ]


def test_a_tooltip_naming_another_item_is_not_stored(db, settings):
    autumn, mah, *_ = party()
    snap = with_tooltip(gear_snapshot("s-1", autumn, mah, T0 + 600, [22]), 1, [{"left": "Some Other Item"}, {"left": "Head"}])
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1")), snap]))
    assert db.scalars(select(ItemTooltipReport)).all() == []
    assert served_gear(db, settings, "Mah Beardlong").items[0].tooltip is None


def test_game_escapes_are_removed_from_tooltip_text(db, settings):
    autumn, mah, *_ = party()
    lines = [{"left": "Test Item 1"}, {"left": "|cff1eff00Equip:|r Increases |Hspell:1|hdefense|h by 3."}]
    snap = with_tooltip(gear_snapshot("s-1", autumn, mah, T0 + 600, [22]), 1, lines)
    ingest(db, settings, batch("install-aaaa1111", [run_observation(RunSpec("r-1", observer="u1")), snap]))
    assert served_gear(db, settings, "Mah Beardlong").items[0].tooltip[1].left == "Equip: Increases defense by 3."


def test_item_keys_leave_out_who_holds_the_item():
    # The addon keys items the same way (addon/tests: "keys a tooltip by the item and what changes it").
    real = "|cnIQ2:|Hitem:2985::::::::18:1484::1::1:28:5240:::::|h[Inscribed Leather Breastplate]|h|r"
    assert item_key(real, 2985) == "2985" + ":" * 11 + "1::1:28:5240"
    assert item_key("|Hitem:6591:0:0:0:0:0:772:123456:25:0|h[Battleforge Wristguards of the Whale]|h", 6591) == "6591:0:0:0:0:0:772"
    assert item_key("|Hitem:100:0:0:0:0:0:-12:99:25|h[X]|h", 100) == "100:0:0:0:0:0:-12:99"
    assert item_key("|Hitem:7|h[Y]|h", 7) == "7"
    assert item_key(None, 42) == "42"
