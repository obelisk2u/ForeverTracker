"""Safe SavedVariables parsing and ForeverTracker export extraction.

SavedVariables files are Lua source written by the WoW client. They are untrusted input:
users can edit them freely. This package parses the *data subset* of Lua that the client
writes (assignments of literals and table constructors) and never executes anything.
"""

from forevertracker_sv.errors import SavedVariablesError
from forevertracker_sv.export import ExportSummary, extract_batches, summarize_export
from forevertracker_sv.parser import ParseLimits, parse_savedvariables

__all__ = [
    "ExportSummary",
    "ParseLimits",
    "SavedVariablesError",
    "extract_batches",
    "parse_savedvariables",
    "summarize_export",
]
