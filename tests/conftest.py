import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session")
def qapp():
    """Own one QApplication for the complete Qt test session."""
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    yield application
