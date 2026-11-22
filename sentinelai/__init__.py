import os
import pathlib
import sys

# Resolve the project root (directory containing this package's sibling 'src')
_project_root = pathlib.Path(__file__).resolve().parents[1]

# Path to the actual source implementation
_src_pkg = _project_root / "src" / "sentinelai"

# Ensure the source package is on sys.path for imports
if str(_src_pkg) not in sys.path:
    sys.path.insert(0, str(_src_pkg))

# Extend this package's __path__ so that submodules are discoverable
if str(_src_pkg) not in __path__:
    __path__.append(str(_src_pkg))
