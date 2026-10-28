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
