import pathlib
import joblib
import json

# Resolve project root (two levels up from this script)
project_root = pathlib.Path(__file__).resolve().parents[1]
preproc_path = project_root / 'data' / 'processed' / 'preprocessor_balanced.pkl'

# Load preprocessor artifact
payload = joblib.load(preproc_path)
if isinstance(payload, dict):
    columns = payload['columns']
else:
    columns = payload.columns

# Verify we have exactly 76 feature names
if len(columns) != 76:
    raise ValueError(f'Expected 76 features, found {len(columns)}')

# Create synthetic numeric values (e.g., 0.1 for every feature)
features = {col: 0.1 for col in columns}

# Write the fixture JSON file
fixtures_dir = project_root / 'tests' / 'fixtures'
fixtures_dir.mkdir(parents=True, exist_ok=True)
fixture_path = fixtures_dir / 'sample_features.json'
with open(fixture_path, 'w', encoding='utf-8') as f:
    json.dump(features, f, indent=2)

print(f'Fixture written to {fixture_path} with {len(features)} features')
