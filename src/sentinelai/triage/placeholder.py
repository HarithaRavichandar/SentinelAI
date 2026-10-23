def generate_placeholder_explanation(result: dict) -> str:
    """Return a deterministic placeholder explanation.

    The function receives the prediction dictionary produced by ``InferenceEngine``
    (including ``class_id``, ``class_label`` and ``probabilities``) and builds a
    simple human‑readable message that explicitly mentions it is a placeholder.
    """
    class_id = result.get("class_id")
    class_label = result.get("class_label", "Unknown")
    # The placeholder deliberately omits the actual confidence to avoid exposing model scores.
    prob_str = "N/A"
    return f"[Placeholder] Unable to generate explanation for class '{class_label}' (id={class_id}). Confidence: {prob_str}."
