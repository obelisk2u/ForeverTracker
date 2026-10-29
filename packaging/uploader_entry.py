"""PyInstaller entry point. Kept tiny so the spec has a single, obvious script to analyse.

The installer registers ``ForeverTrackerUploader.exe background`` to run at login. Running the exe
with no arguments is ``start``, what the shortcuts run: the same, plus a notice that it is running.
"""

import sys

from forevertracker_uploader.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["start"]))
