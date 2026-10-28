"""ForeverTracker desktop uploader.

Guarantees:
* Never writes, renames, locks or deletes anything inside the World of Warcraft folder.
* Reads a SavedVariables file only after it has been stable on disk (WoW writes it on
  logout, exit and /reload; it is never flushed continuously).
* Archives every distinct version it sees, so data survives the next session overwriting
  the file.
* Uploads each batch at most once (the server also deduplicates), over HTTPS.
* Can be paused at any time; `disclose` shows exactly what would be sent.
"""

__version__ = "0.1.0"
