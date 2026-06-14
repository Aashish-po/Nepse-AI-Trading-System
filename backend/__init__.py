# backend/__init__.py
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import models ONLY from app.models
from app.models import *  # noqa: F401, F403, E402
