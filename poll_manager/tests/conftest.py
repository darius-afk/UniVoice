import os
import sys

# Make `poll_manager/` importable as a top-level module path for tests.
THIS_DIR = os.path.dirname(__file__)
POLL_MANAGER_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
if POLL_MANAGER_DIR not in sys.path:
    sys.path.insert(0, POLL_MANAGER_DIR)

# Also make repo root importable (for importing sibling services like profile_service).
REPO_ROOT = os.path.abspath(os.path.join(POLL_MANAGER_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)
