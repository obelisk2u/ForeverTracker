"""PyInstaller entry point. Kept tiny so the spec has a single, obvious script to analyse.

The installer registers ``ForeverTrackerUploader.exe background`` to run at login; running the
exe with no arguments does the same, so a double-click behaves sensibly too.
"""

import sys

from forevertracker_uploader.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["background"]))
