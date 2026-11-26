import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir and no real API key before the app is imported.
os.environ["PVP_SCANNER_HOME"] = tempfile.mkdtemp(prefix="pvp-test-")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
