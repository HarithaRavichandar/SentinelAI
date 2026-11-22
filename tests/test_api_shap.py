import json, pathlib
from fastapi.testclient import TestClient
from sentinelai.api import app

client = TestClient(app)
fixture_path = pathlib.Path('tests/fixtures/sample_features.json')
payload = json.loads(fixture_path.read_text(encoding='utf-8'))

def test_triage_shap_response():
    response = client.post('/triage?explain_shap=true', json=payload)
    assert response.status_code == 200
    data = response.json()
    # Must contain either shap_explanations or shap_status
    assert ('shap_explanations' in data) or ('shap_status' in data)
    # If shap_explanations present, it should be a dict
    if 'shap_explanations' in data:
        assert isinstance(data['shap_explanations'], dict)
    # class_id and class_label must be present
    assert 'class_id' in data
    assert 'class_label' in data
