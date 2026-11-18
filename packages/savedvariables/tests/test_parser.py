import pytest

from forevertracker_sv import ParseLimits, SavedVariablesError, parse_savedvariables

WOW_STYLE = """
ForeverTrackerDB = {
["format"] = "forevertracker.savedvariables",
["schema_version"] = 1,
["negative"] = -12.5,
["flag"] = true,
["off"] = false,
["list"] = {
{
["name"] = "Autumn",
["surname"] = "Redleaf",
}, -- [1]
"second", -- [2]
3, -- [3]
},
["sparse"] = {
[2] = "b",
[5] = "e",
},
["escaped"] = "line1\\nline2 \\"quoted\\" back\\\\slash \\065",
["empty"] = {
},
}
OtherAddonDB = nil
"""


def test_parses_wow_style_file():
    result = parse_savedvariables(WOW_STYLE)
    db = result["ForeverTrackerDB"]
    assert "OtherAddonDB" not in result
    assert db["schema_version"] == 1
    assert db["negative"] == -12.5
    assert db["flag"] is True and db["off"] is False
    assert db["list"][0] == {"name": "Autumn", "surname": "Redleaf"}
    assert db["list"][1:] == ["second", 3]
    assert db["sparse"] == {2: "b", 5: "e"}
    assert db["escaped"] == 'line1\nline2 "quoted" back\\slash A'
    assert db["empty"] == []


def test_accepts_bom_bytes_and_block_comments():
    data = b'\xef\xbb\xbf--[==[ header ]==]\nX = { 1, 2; 3, }\n'
    assert parse_savedvariables(data) == {"X": [1, 2, 3]}


def test_utf8_strings_survive():
    assert parse_savedvariables('X = "Pok\xe9zeroth"') == {"X": "Pokézeroth"}
    assert parse_savedvariables(b'X = "\\195\\169"') == {"X": "é"}


@pytest.mark.parametrize(
    "source",
    [
        "X = os.execute('rm')",
        "X = loadstring('return 1')()",
        "X = 1 + 2",
        "X = Y",
        "X = function() end",
        "X = { [{}] = 1 }",
        "X = { a = }",
        'X = "unterminated',
        "X = 1e999",
        "local X = 1",
        "X = { [nil] = 1 }",
    ],
)
def test_rejects_anything_but_data(source):
    with pytest.raises(SavedVariablesError):
        parse_savedvariables(source)


def test_depth_and_size_limits():
    deep = "X = " + "{" * 60 + "}" * 60
    with pytest.raises(SavedVariablesError, match="nested"):
        parse_savedvariables(deep)
    with pytest.raises(SavedVariablesError, match="size"):
        parse_savedvariables("X = 1", ParseLimits(max_bytes=3))
    with pytest.raises(SavedVariablesError, match="string"):
        parse_savedvariables('X = "' + "a" * 100 + '"', ParseLimits(max_string_bytes=10))
    with pytest.raises(SavedVariablesError, match="too many"):
        parse_savedvariables("X = {1,2,3,4,5}", ParseLimits(max_values=3))


def test_reports_line_numbers():
    with pytest.raises(SavedVariablesError) as err:
        parse_savedvariables("A = 1\nB = {\n  1,\n  bad\n}")
    assert err.value.line == 4


# --- Bounded work (tokens are counted as they are read, never all held) -------------------------

from pathlib import Path  # noqa: E402

from forevertracker_sv.parser import _tokens  # noqa: E402
from forevertracker_sv.writer import to_savedvariables  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "savedvariables" / "ForeverTracker.sample.lua"


def test_token_limit_stops_a_dense_file_early():
    flood = "X = {" + "1," * 10_000 + "}"
    with pytest.raises(SavedVariablesError, match=r"too many tokens \(limit 500\)"):
        parse_savedvariables(flood, ParseLimits(max_tokens=500))
    # The default is a third of max_bytes: '1,' packs one token into 1 byte, so it is refused.
    with pytest.raises(SavedVariablesError, match="too many tokens"):
        parse_savedvariables(flood, ParseLimits(max_bytes=len(flood) + 10))


def test_tokens_are_produced_lazily():
    stream = _tokens("X = {" + "1," * 1000 + "}", ParseLimits(max_tokens=5))
    assert [next(stream).text for _ in range(5)] == ["X", "=", "{", "1", ","]
    with pytest.raises(SavedVariablesError, match="too many tokens"):
        next(stream)


def test_block_comments_are_skipped_and_an_unterminated_one_is_an_error():
    assert parse_savedvariables("--[==[ a ]] still comment ]==]\nX = 1 --[[ b ]] Y = 2") == {"X": 1, "Y": 2}
    with pytest.raises(SavedVariablesError, match=r"unexpected input .*\(line 3\)"):
        parse_savedvariables("--[[ one\ntwo ]]\n X = @")  # line numbers survive a skipped comment
    # Unterminated: an error at once (it used to be read as a line comment, rescanning to the end for
    # every opener, which took quadratic time).
    with pytest.raises(SavedVariablesError, match=r"unterminated block comment \(line 2\)"):
        parse_savedvariables("X = 1\n" + "--[[\n" * 50_000)


def test_addon_files_parse_well_inside_the_default_token_budget():
    # The committed fixture was written by the real addon code; repeat its records up to ~2 MB.
    db = parse_savedvariables(FIXTURE.read_bytes())["ForeverTrackerDB"]
    records = db["observations"]
    db["observations"] = [{**o, "observation_id": f"{o['observation_id']}-{i}"} for i in range(160) for o in records]
    text = to_savedvariables({"ForeverTrackerDB": db})
    limits = ParseLimits(max_bytes=len(text.encode()))  # token budget = bytes / 3
    tokens = sum(1 for _ in _tokens(text, ParseLimits()))
    assert len(text.encode()) / tokens > 3.3
    assert len(parse_savedvariables(text, limits)["ForeverTrackerDB"]["observations"]) == 160 * len(records)
