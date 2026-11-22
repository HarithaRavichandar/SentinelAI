"""Flow table: assembles raw packets into bidirectional network flows.

The FlowTable receives parsed packet tuples from the CaptureEngine,
creates or updates FlowState accumulators, and emits completed flows
when a TCP FIN/RST is seen or an idle/active timeout fires.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from .flow_state import FlowState

logger = logging.getLogger(__name__)


# Type alias for the canonical 5-tuple flow key
FlowKey = Tuple[str, str, int, int, int]  # (lo_ip, hi_ip, lo_port, hi_port, proto)

# Safety cap to prevent unbounded memory growth
MAX_ACTIVE_FLOWS = 50_000


class FlowTable:
    """Bidirectional flow assembly with idle/active timeout expiry.

    Parameters
    ----------
    idle_timeout : float
        Seconds of silence before a flow is considered expired (default 120).
    active_timeout : float
        Maximum lifetime of any flow regardless of activity (default 300).
    sweep_interval : float
        How often ``sweep_expired`` checks for timed-out flows (default 10).
    """

    def __init__(
        self,
        idle_timeout: float = 30.0,
        active_timeout: float = 300.0,
        sweep_interval: float = 5.0,
    ):
        self.idle_timeout = idle_timeout
        self.active_timeout = active_timeout
        self.sweep_interval = sweep_interval

        self._flows: Dict[FlowKey, FlowState] = {}
        self._last_sweep: float = time.time()

        # Counters for stats reporting
        self.total_packets: int = 0
        self.total_completed: int = 0

    # ------------------------------------------------------------------
    #  Flow key canonicalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _make_key(
        src_ip: str, dst_ip: str,
        src_port: int, dst_port: int,
        protocol: int,
    ) -> FlowKey:
        """Return a canonical key so both directions map to the same flow.

        Convention: the numerically smaller IP is "lo".  When IPs are equal
        the smaller port is "lo".
        """
        if src_ip < dst_ip or (src_ip == dst_ip and src_port <= dst_port):
            return (src_ip, dst_ip, src_port, dst_port, protocol)
        return (dst_ip, src_ip, dst_port, src_port, protocol)

    @staticmethod
    def _is_forward(
        src_ip: str, src_port: int,
        flow: FlowState,
    ) -> bool:
        """True if this packet is in the forward (src→dst) direction."""
        return src_ip == flow.src_ip and src_port == flow.src_port

    # ------------------------------------------------------------------
    #  Packet processing
    # ------------------------------------------------------------------
    def process_packet(
        self,
        ts: float,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        protocol: int,
        ip_len: int,
        ttl: int,
        tcp_flags: int = 0,
        tcp_seq: int = 0,
        tcp_win: int = 0,
        payload_len: int = 0,
        header_len: int = 0,
    ) -> Optional[FlowState]:
        """Ingest one packet and return a completed FlowState if the flow
        just terminated (TCP FIN/RST).

        Also calls ``sweep_expired`` periodically for idle/active timeouts;
        those expired flows are returned via ``sweep_expired`` directly.
        """
        self.total_packets += 1
        key = self._make_key(src_ip, dst_ip, src_port, dst_port, protocol)

        # --- get or create flow ---
        flow = self._flows.get(key)
        if flow is None:
            if len(self._flows) >= MAX_ACTIVE_FLOWS:
                logger.warning(
                    "Active flow cap (%d) reached — dropping packet",
                    MAX_ACTIVE_FLOWS,
                )
                return None
            # Canonical direction: key's lo_ip is src_ip
            flow = FlowState(
                src_ip=key[0],
                dst_ip=key[1],
                src_port=key[2],
                dst_port=key[3],
                protocol=protocol,
                first_seen=ts,
                last_seen=ts,
            )
            self._flows[key] = flow

        # --- update counters ---
        fwd = self._is_forward(src_ip, src_port, flow)
        if fwd:
            flow.update_forward(
                ts, ip_len, ttl, tcp_flags, tcp_seq, tcp_win, payload_len,
                header_len,
            )
        else:
            flow.update_reverse(
                ts, ip_len, ttl, tcp_flags, tcp_seq, tcp_win, payload_len,
                header_len,
            )

        # --- check TCP termination ---
        if flow.is_tcp_finished:
            del self._flows[key]
            self.total_completed += 1
            return flow

        return None

    # ------------------------------------------------------------------
    #  Timeout-based expiry
    # ------------------------------------------------------------------
    def sweep_expired(self, now: Optional[float] = None) -> List[FlowState]:
        """Expire flows that exceeded idle or active timeout.

        Returns a list of completed FlowState objects.
        """
        now = now or time.time()

        # Rate-limit sweeps
        if now - self._last_sweep < self.sweep_interval:
            return []

        self._last_sweep = now
        expired: List[FlowState] = []
        to_remove: List[FlowKey] = []

        for key, flow in self._flows.items():
            idle = now - flow.last_seen
            active = now - flow.first_seen

            if idle >= self.idle_timeout or active >= self.active_timeout:
                to_remove.append(key)
                expired.append(flow)

        for key in to_remove:
            del self._flows[key]

        self.total_completed += len(expired)
        if expired:
            logger.debug("Swept %d expired flows (%d still active)",
                         len(expired), len(self._flows))

        return expired

    # ------------------------------------------------------------------
    #  Stats
    # ------------------------------------------------------------------
    @property
    def active_flow_count(self) -> int:
        return len(self._flows)

    def get_stats(self) -> dict:
        return {
            "total_packets": self.total_packets,
            "active_flows": self.active_flow_count,
            "total_completed": self.total_completed,
        }