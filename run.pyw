"""Entry point. .pyw extension = pythonw runs it with NO console window.

Double-click this file (or put a shortcut to it in shell:startup) to run
Word Lookup in the background. Quit from the tray icon.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kannada_lookup.main import main

main()
