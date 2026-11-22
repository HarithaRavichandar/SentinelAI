"""SentinelAI Live Packet Capture Module.

Provides real-time network traffic analysis by:
1. Capturing packets from a network interface (via scapy + Npcap)
2. Assembling packets into bidirectional flows
3. Extracting CICFlowMeter-compatible features (76 columns) from completed flows
4. Feeding features through the ML prediction + triage pipeline
5. Streaming results to the frontend via WebSocket
"""

from .flow_state import FlowState, FlowSummary
from .flow_table import FlowTable
from .feature_extractor import FeatureExtractor
from .engine import CaptureEngine
from .live_session import LiveSession

__all__ = [
    "FlowState",
    "FlowSummary",
    "FlowTable",
    "FeatureExtractor",
    "CaptureEngine",
    "LiveSession",
]