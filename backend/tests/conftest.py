import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Prevent model re-registration
os.environ["SQLALCHEMY_ECHO"] = "false"

# Don't auto-import models
