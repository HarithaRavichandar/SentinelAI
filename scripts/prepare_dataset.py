# scripts/prepare_dataset.py
"""Prepare the SentinelAI dataset for model training.

This script loads the raw feature matrix and label vector, performs a leak‑resistant
split that respects duplicate feature groups, saves the boolean masks for the three
partitions, and writes a human‑readable report.
"""

from pathlib import Path
import sys

# Ensure the project's ``src`` directory is on the import path so that ``sentinelai`` can be imported.
project_root = Path(__file__).resolve().parents[1]
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Verify import of the split module; give a clear message if it fails.
try:
    from sentinelai.data.split import prepare_and_split
except ImportError as exc:
    raise ImportError(
        "Failed to import sentinelai module. Ensure the repository root contains a 'src' directory with the package and that this script is run from the repository root."
    ) from exc


def main() -> None:
    # Repository layout (project root is two levels up from this script)
    base = Path(__file__).resolve().parents[1]
    data_path = base / "data" / "raw" / "Data.csv"
    label_path = base / "data" / "raw" / "Label.csv"
    readme_path = base / "data" / "raw" / "Readme.txt"
    output_dir = base / "data" / "processed"
    report_path = base / "reports" / "split_report.md"
    prepare_and_split(data_path, label_path, readme_path, output_dir, report_path)


if __name__ == "__main__":
    main()
