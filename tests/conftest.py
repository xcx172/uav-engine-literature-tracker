from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.helpers import make_settings  # noqa: E402


@pytest.fixture()
def settings(tmp_path):
    return make_settings(tmp_path)
