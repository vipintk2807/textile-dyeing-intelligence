"""Make the ``src`` directory importable for Streamlit pages and scripts.

Streamlit puts the folder of ``app.py`` on ``sys.path``; importing this module from a
page or script then adds ``src`` so ``import textile_dyeing_intelligence`` works without
installing the package.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
