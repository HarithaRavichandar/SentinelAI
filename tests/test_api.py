import json
import pathlib

from fastapi.testclient import TestClient

from sentinelai.api import app

client = TestClient(app)


def load_fixture():
    """Load the sample feature fixture used for predictions."""
    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_success():
    payload = load_fixture()
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Basic structure checks
    assert isinstance(data, dict)
    assert "class_id" in data
    assert "class_label" in data
    assert "probabilities" in data
    assert isinstance(data["probabilities"], dict)


def test_missing_feature_returns_400():
    payload = load_fixture()
    # Remove one required feature
    first_key = next(iter(payload))
    payload.pop(first_key)
    response = client.post("/predict", json=payload)
    assert response.status_code == 400


def test_extra_feature_returns_400():
    payload = load_fixture()
    payload["unexpected_feature"] = 0.1
    response = client.post("/predict", json=payload)
    assert response.status_code == 400


def test_non_numeric_and_non_finite_values():
    payload = load_fixture()
    # Non‑numeric value (string) – can be sent via json param
    first_key = next(iter(payload))
    payload[first_key] = "not-a-number"
    response = client.post("/predict", json=payload)
    assert response.status_code == 400

    # Reset and use NaN – send raw JSON allowing NaN token
    payload = load_fixture()
    payload[first_key] = float("nan")
    raw_body = json.dumps(payload, allow_nan=True)
    response = client.post("/predict", content=raw_body, headers={"Content-Type": "application/json"})
    assert response.status_code == 400

    # Reset and use infinite – also send raw JSON
    payload = load_fixture()
    payload[first_key] = float("inf")
    raw_body = json.dumps(payload, allow_nan=True)
    response = client.post("/predict", content=raw_body, headers={"Content-Type": "application/json"})
    assert response.status_code == 400


def test_sample_endpoint():
    response = client.get("/sample")
    assert response.status_code == 200
    data = response.json()
    assert "features" in data
    assert "label" in data
    assert len(data["features"]) == 76
    assert isinstance(data["label"], str)
    # Ensure sample features can be passed directly to /predict
    pred_response = client.post("/predict", json=data["features"])
    assert pred_response.status_code == 200
    pred_data = pred_response.json()
    assert "class_label" in pred_data


def test_sample_all_supported_classes():
    from sentinelai.api import CLASS_MAP
    for cid, name in CLASS_MAP.items():
        resp = client.get(f"/sample?label={name}")
        assert resp.status_code == 200, f"Failed for {name}: {resp.text}"
        data = resp.json()
        assert data["label"] == name
        assert len(data["features"]) == 76
        # Features should be valid numbers
        for feat, val in data["features"].items():
            assert isinstance(val, (int, float)), f"{feat} has non-numeric value {val}"


def test_sample_case_insensitivity_and_numeric_id():
    # Case insensitivity
    resp_lower = client.get("/sample?label=dos")
    assert resp_lower.status_code == 200
    assert resp_lower.json()["label"] == "DoS"

    resp_upper = client.get("/sample?label=DOS")
    assert resp_upper.status_code == 200
    assert resp_upper.json()["label"] == "DoS"

    # Numeric string id
    resp_id = client.get("/sample?label=3")
    assert resp_id.status_code == 200
    assert resp_id.json()["label"] == "DoS"


def test_sample_invalid_label():
    resp = client.get("/sample?label=NotAValidClass")
    assert resp.status_code == 400
    assert "Invalid label 'NotAValidClass'" in resp.json()["detail"]
    assert "Supported classes:" in resp.json()["detail"]


def test_sample_unavailable_class():
    import sentinelai.api as api
    api._get_sample_pool()
    original_samples = api._SAMPLE_CACHE.get(3, [])
    try:
        # Simulate no samples found for class 3 (DoS)
        api._SAMPLE_CACHE[3] = []
        resp = client.get("/sample?label=DoS")
        assert resp.status_code == 404
        assert "No samples available for class 'DoS'" in resp.json()["detail"]
    finally:
        api._SAMPLE_CACHE[3] = original_samples


def test_sample_feature_label_alignment():
    """Verify that sample feature values come directly from Data.csv and match Label.csv."""
    import csv
    from sentinelai.api import PROJECT_ROOT, CLASS_MAP

    resp = client.get("/sample?label=Exploits")
    assert resp.status_code == 200
    sample_feats = resp.json()["features"]
    assert resp.json()["label"] == "Exploits"

    data_path = PROJECT_ROOT / "data" / "raw" / "Data.csv"
    label_path = PROJECT_ROOT / "data" / "raw" / "Label.csv"

    matched = False
    with open(data_path, newline="") as fd, open(label_path, newline="") as fl:
        rd = csv.DictReader(fd)
        rl = csv.DictReader(fl)
        for i, (r_data, r_label) in enumerate(zip(rd, rl)):
            # Check row match on distinct feature columns
            if (
                float(r_data["Flow Duration"]) == sample_feats["Flow Duration"]
                and float(r_data["Total Fwd Packet"]) == sample_feats["Total Fwd Packet"]
                and float(r_data["Total Length of Fwd Packet"]) == sample_feats["Total Length of Fwd Packet"]
            ):
                label_col = next((c for c in r_label if c.lower() == "label"), None)
                raw_label_val = int(r_label[label_col])
                assert CLASS_MAP[raw_label_val] == "Exploits"
                matched = True
                break
            if i > 50000:
                break
    assert matched, "Sample features must match an exact row in Data.csv with corresponding label in Label.csv"


