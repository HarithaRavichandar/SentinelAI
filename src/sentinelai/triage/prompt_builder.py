# src/sentinelai/triage/prompt_builder.py
"""Utility for building Laya prompts used by both Gemini and Groq clients.
The prompt format is deliberately minimal and does not expose raw feature data.
"""

from typing import Dict


def build_prompt(class_id: int, class_label: str, probabilities: Dict[int, float]) -> str:
    """Create a concise, safe prompt describing a model prediction.

    Args:
        class_id: Integer identifier of the predicted class.
        class_label: Human readable label for the class.
        probabilities: Mapping from class IDs to predicted probabilities.

    Returns:
        A multi‑line string suitable for LLM providers.
    """
    lines = [
        "You are a security‑analysis assistant. Explain the following model prediction.",
        f"Class ID: {class_id}",
        f"Class label: {class_label}",
        "Class probability scores (may not be calibrated confidence estimates):",
    ]
    for cid, prob in sorted(probabilities.items()):
        lines.append(f"- {cid}: {prob:.2f}")
    lines.append(
        "Provide a concise, factual explanation. Do NOT invent details, claim feature causes, or suggest actions."
    )
    return "\n".join(lines)
