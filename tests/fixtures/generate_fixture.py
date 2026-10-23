import json
import pathlib
import joblib

# Resolve project root relative to this file
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
PREPROC_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessor_balanced.pkl"

payload = joblib.load(PREPROC_PATH)
if isinstance(payload, dict):
    columns = payload["columns"]
else:
    columns = payload.columns

# Create a simple synthetic feature dict (zeros)
features = {col: 0.0 for col in columns}

fixtures_dir = PROJECT_ROOT / "tests" / "fixtures"
fixtures_dir.mkdir(parents=True, exist_ok=True)
fixture_path = fixtures_dir / "sample_features.json"
with open(fixture_path, "w", encoding="utf-8") as f:
    json.dump(features, f, indent=2)
print(f"Fixture written to {fixture_path}")
