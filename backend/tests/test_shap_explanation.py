import numpy as np

from backend.services.prediction import artifact, explain_prediction


def test_tree_shap_attributions_sum_to_model_prediction():
    stored = artifact()
    assert stored and stored['model'] is not None
    features = {
        'department': '6e9a6576-313c-5398-aef1-4a543b7328dc',
        'queue_ahead': 4,
        'active_staff': 2,
        'recent_service': 12.0,
        'arrivals_30m': 3,
        'hour': 10,
        'weekday': 2,
    }
    prediction = float(stored['model'].predict([features])[0])
    explanation = explain_prediction(stored, features, prediction)
    total = explanation['baseline'] + sum(item['impact'] for item in explanation['contributions'])
    assert explanation['method'] == 'TreeSHAP'
    assert abs(total - prediction) < 0.08
    assert all(item['feature'] != features['department'] for item in explanation['contributions'])
