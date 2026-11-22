"""Connection window: ring buffer of recent flows for cross-flow (ct_*) features.

UNSW-NB15's ``ct_*`` features count how many of the *last N completed flows*
share a particular attribute with the current flow (same src IP, same service,
same dst port, etc.).  This module maintains that sliding window.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict

from .flow_state import FlowState, FlowSummary


# TTL bucket boundaries (Argus-style grouping used in ct_state_ttl)
_TTL_BUCKETS = [32, 64, 128, 255]


def _ttl_bucket(ttl: int) -> int:
    """Map a raw TTL value to a bucket index."""
    for i, upper in enumerate(_TTL_BUCKETS):
        if ttl <= upper:
            return i
    return len(_TTL_BUCKETS)


class ConnectionWindow:
    """Fixed-size ring buffer of recently completed flow summaries.

    Default window size is 100, matching the UNSW-NB15 convention for the
    ``ct_*`` feature family.

    Usage::

        window = ConnectionWindow(size=100)

        # When a flow completes:
        ct_features = window.query(completed_flow)
        window.add(completed_flow)
    """

    def __init__(self, size: int = 100):
        self._buffer: deque[FlowSummary] = deque(maxlen=size)

    def query(self, flow: FlowState) -> Dict[str, int]:
        """Compute all eight ``ct_*`` features for *flow* against the window.

        Call this *before* adding the flow to the window.

        Returns
        -------
        dict with keys:
            ct_srv_src, ct_srv_dst, ct_dst_ltm, ct_src_ltm,
            ct_src_dport_ltm, ct_dst_sport_ltm, ct_dst_src_ltm,
            ct_state_ttl
        """
        service = flow.derive_service()
        state = flow.derive_state()
        ttl_b = _ttl_bucket(flow.sttl)

        ct_srv_src = 0
        ct_srv_dst = 0
        ct_dst_ltm = 0
        ct_src_ltm = 0
        ct_src_dport_ltm = 0
        ct_dst_sport_ltm = 0
        ct_dst_src_ltm = 0
        ct_state_ttl = 0

        for entry in self._buffer:
            # ct_srv_src — same src_ip AND same service
            if entry.src_ip == flow.src_ip and entry.service == service:
                ct_srv_src += 1

            # ct_srv_dst — same dst_ip AND same service
            if entry.dst_ip == flow.dst_ip and entry.service == service:
                ct_srv_dst += 1

            # ct_dst_ltm — same dst_ip
            if entry.dst_ip == flow.dst_ip:
                ct_dst_ltm += 1

            # ct_src_ltm — same src_ip
            if entry.src_ip == flow.src_ip:
                ct_src_ltm += 1

            # ct_src_dport_ltm — same src_ip AND same dst_port
            if entry.src_ip == flow.src_ip and entry.dst_port == flow.dst_port:
                ct_src_dport_ltm += 1

            # ct_dst_sport_ltm — same dst_ip AND same src_port
            if entry.dst_ip == flow.dst_ip and entry.src_port == flow.src_port:
                ct_dst_sport_ltm += 1

            # ct_dst_src_ltm — same src_ip AND same dst_ip (pair)
            if entry.src_ip == flow.src_ip and entry.dst_ip == flow.dst_ip:
                ct_dst_src_ltm += 1

            # ct_state_ttl — same state AND same TTL bucket
            if entry.state == state and _ttl_bucket(entry.sttl) == ttl_b:
                ct_state_ttl += 1

        return {
            "ct_srv_src": ct_srv_src,
            "ct_srv_dst": ct_srv_dst,
            "ct_dst_ltm": ct_dst_ltm,
            "ct_src_ltm": ct_src_ltm,
            "ct_src_dport_ltm": ct_src_dport_ltm,
            "ct_dst_sport_ltm": ct_dst_sport_ltm,
            "ct_dst_src_ltm": ct_dst_src_ltm,
            "ct_state_ttl": ct_state_ttl,
        }

    def add(self, flow: FlowState) -> None:
        """Append a completed flow's summary to the ring buffer."""
        self._buffer.append(FlowSummary.from_flow(flow))

    def __len__(self) -> int:
        return len(self._buffer)