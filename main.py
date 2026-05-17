import os
import sys

ROOT = os.path.dirname(__file__)
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from backend.main import app

