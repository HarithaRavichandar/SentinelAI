import os

# Add the src/sentinelai directory to this package's __path__ so that submodules
# (e.g., sentinelai.data.split) can be found without installing the package.
_current_dir = os.path.abspath(os.path.dirname(__file__))
_src_path = os.path.join(_current_dir, "src", "sentinelai")
if os.path.isdir(_src_path):
    __path__.append(_src_path)
