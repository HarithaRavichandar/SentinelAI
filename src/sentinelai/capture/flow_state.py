"""Flow state accumulator for SentinelAI live capture.

FlowState tracks every per-packet metric needed to compute CICFlowMeter-style
features (76 columns) once a flow expires. The model expects features like
"Flow Duration", "Fwd Packet Length Max", "Flow IAT Mean", TCP flag counts, etc.

FlowSummary is a lightweight record for optional cross-flow analysis.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
#  TCP flag bit masks
# ---------------------------------------------------------------------------
FIN = 0x01
SYN = 0x02
RST = 0x04
PSH = 0x08
ACK = 0x10
URG = 0x20
ECE = 0x40
CWR = 0x80


def _safe_mean(vals: List[float]) -> float:
    return statistics.mean(vals) if vals else 0.0


def _safe_stdev(vals: List[float]) -> float:
    return statistics.pstdev(vals) if len(vals) >= 2 else 0.0


def _safe_variance(vals: List[float]) -> float:
    return statistics.pvariance(vals) if len(vals) >= 2 else 0.0


# ---------------------------------------------------------------------------
#  FlowState — mutable per-flow accumulator
# ---------------------------------------------------------------------------
@dataclass
class FlowState:
    """Accumulates per-packet statistics for a single bidirectional flow.

    A flow is keyed by a canonicalised 5-tuple (smaller IP always *src*).
    When a packet arrives the caller decides direction (fwd vs rev) by
    comparing the packet's source IP against ``src_ip``.

    Tracks all metrics needed for the 76 CICFlowMeter features.
    """

    # --- identity (set once at creation) ---
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int                    # IP protocol number (6=TCP, 17=UDP)

    # --- timing ---
    first_seen: float = field(default_factory=time.time)
    last_seen: float = 0.0

    # --- per-packet payload size lists (for min/max/mean/std) ---
    _fwd_pkt_sizes: List[int] = field(default_factory=list, repr=False)
    _bwd_pkt_sizes: List[int] = field(default_factory=list, repr=False)

    # --- inter-arrival time lists ---
    _flow_iat: List[float] = field(default_factory=list, repr=False)
    _fwd_iat: List[float] = field(default_factory=list, repr=False)
    _bwd_iat: List[float] = field(default_factory=list, repr=False)

    # Last packet timestamps per direction
    _last_pkt_time: float = 0.0
    _last_fwd_time: float = 0.0
    _last_bwd_time: float = 0.0

    # --- TCP flag counters (per-direction and total) ---
    fwd_psh_flags: int = 0
    bwd_psh_flags: int = 0
    fwd_urg_flags: int = 0
    bwd_urg_flags: int = 0
    fin_flag_count: int = 0
    syn_flag_count: int = 0
    rst_flag_count: int = 0
    psh_flag_count: int = 0
    ack_flag_count: int = 0
    urg_flag_count: int = 0
    cwr_flag_count: int = 0
    ece_flag_count: int = 0

    # --- header lengths (cumulative per direction) ---
    fwd_header_bytes: int = 0
    bwd_header_bytes: int = 0

    # --- TCP initial window sizes ---
    fwd_init_win: int = -1          # -1 = not seen yet
    bwd_init_win: int = -1

    # --- forward data packets (payload > 0) ---
    fwd_act_data_pkts: int = 0

    # --- forward segment sizes (for Fwd Seg Size Min) ---
    _fwd_seg_sizes: List[int] = field(default_factory=list, repr=False)

    # --- active / idle period tracking ---
    _active_times: List[float] = field(default_factory=list, repr=False)
    _idle_times: List[float] = field(default_factory=list, repr=False)
    _activity_start: float = 0.0
    _activity_threshold: float = 1.0  # seconds: gap > this = idle

    # --- bulk transfer tracking (4+ consecutive same-direction packets) ---
    _bulk_last_dir: str = ""         # "F" or "B"
    _fwd_consec_count: int = 0
    _fwd_consec_bytes: int = 0
    _fwd_consec_start: float = 0.0
    _fwd_consec_last: float = 0.0
    _bwd_consec_count: int = 0
    _bwd_consec_bytes: int = 0
    _bwd_consec_start: float = 0.0
    _bwd_consec_last: float = 0.0
    # Accumulated bulk totals
    fwd_bulk_count: int = 0
    fwd_bulk_total_bytes: int = 0
    fwd_bulk_total_pkts: int = 0
    fwd_bulk_total_dur: float = 0.0
    bwd_bulk_count: int = 0
    bwd_bulk_total_bytes: int = 0
    bwd_bulk_total_pkts: int = 0
    bwd_bulk_total_dur: float = 0.0

    # --- flow expiry helpers ---
    _fin_count: int = 0
    _rst_seen: bool = False

    # ------------------------------------------------------------------
    #  Packet ingestion
    # ------------------------------------------------------------------
    def update_forward(
        self,
        ts: float,
        ip_len: int,
        ttl: int,
        tcp_flags: int = 0,
        tcp_seq: int = 0,
        tcp_win: int = 0,
        payload_len: int = 0,
        header_len: int = 0,
    ) -> None:
        """Process a packet travelling src -> dst (forward direction)."""
        # Flow IAT (before updating last_seen)
        if self._last_pkt_time > 0:
            self._flow_iat.append(ts - self._last_pkt_time)
        self._last_pkt_time = ts

        # Active/idle tracking (uses flow IAT)
        self._update_activity(ts)

        self.last_seen = ts
        self._fwd_pkt_sizes.append(payload_len)
        self._fwd_seg_sizes.append(payload_len)

        # Forward data packets (payload > 0)
        if payload_len > 0:
            self.fwd_act_data_pkts += 1

        # Header length
        self.fwd_header_bytes += header_len

        # Initial TCP window (first forward packet only)
        if self.fwd_init_win == -1 and self.protocol == 6:
            self.fwd_init_win = tcp_win

        # Forward IAT
        if self._last_fwd_time > 0:
            self._fwd_iat.append(ts - self._last_fwd_time)
        self._last_fwd_time = ts

        # TCP flag counting
        self._count_flags(tcp_flags, is_fwd=True)

        # Bulk transfer tracking
        self._track_bulk("F", ts, payload_len)

        # TCP termination
        if tcp_flags & FIN:
            self._fin_count += 1
        if tcp_flags & RST:
            self._rst_seen = True

    def update_reverse(
        self,
        ts: float,
        ip_len: int,
        ttl: int,
        tcp_flags: int = 0,
        tcp_seq: int = 0,
        tcp_win: int = 0,
        payload_len: int = 0,
        header_len: int = 0,
    ) -> None:
        """Process a packet travelling dst -> src (reverse direction)."""
        # Flow IAT (before updating last_seen)
        if self._last_pkt_time > 0:
            self._flow_iat.append(ts - self._last_pkt_time)
        self._last_pkt_time = ts

        # Active/idle tracking
        self._update_activity(ts)

        self.last_seen = ts
        self._bwd_pkt_sizes.append(payload_len)

        # Header length
        self.bwd_header_bytes += header_len

        # Initial TCP window (first backward packet only)
        if self.bwd_init_win == -1 and self.protocol == 6:
            self.bwd_init_win = tcp_win

        # Backward IAT
        if self._last_bwd_time > 0:
            self._bwd_iat.append(ts - self._last_bwd_time)
        self._last_bwd_time = ts

        # TCP flag counting
        self._count_flags(tcp_flags, is_fwd=False)

        # Bulk transfer tracking
        self._track_bulk("B", ts, payload_len)

        # TCP termination
        if tcp_flags & FIN:
            self._fin_count += 1
        if tcp_flags & RST:
            self._rst_seen = True

    # ------------------------------------------------------------------
    #  Bulk transfer tracking
    # ------------------------------------------------------------------
    BULK_THRESHOLD = 4

    def _track_bulk(self, direction: str, ts: float, payload_len: int) -> None:
        """Track consecutive same-direction packets for bulk features."""
        if direction == "F":
            if self._bulk_last_dir == "F":
                # Extend current forward run
                self._fwd_consec_count += 1
                self._fwd_consec_bytes += payload_len
                self._fwd_consec_last = ts
            else:
                # Direction changed: finalize any backward run, start forward
                self._finalize_run("B")
                self._fwd_consec_count = 1
                self._fwd_consec_bytes = payload_len
                self._fwd_consec_start = ts
                self._fwd_consec_last = ts
        else:
            if self._bulk_last_dir == "B":
                self._bwd_consec_count += 1
                self._bwd_consec_bytes += payload_len
                self._bwd_consec_last = ts
            else:
                self._finalize_run("F")
                self._bwd_consec_count = 1
                self._bwd_consec_bytes = payload_len
                self._bwd_consec_start = ts
                self._bwd_consec_last = ts
        self._bulk_last_dir = direction

    def _finalize_run(self, direction: str) -> None:
        """If the just-ended run meets the bulk threshold, record it."""
        if direction == "F" and self._fwd_consec_count >= self.BULK_THRESHOLD:
            self.fwd_bulk_count += 1
            self.fwd_bulk_total_bytes += self._fwd_consec_bytes
            self.fwd_bulk_total_pkts += self._fwd_consec_count
            dur = self._fwd_consec_last - self._fwd_consec_start
            self.fwd_bulk_total_dur += dur
        elif direction == "B" and self._bwd_consec_count >= self.BULK_THRESHOLD:
            self.bwd_bulk_count += 1
            self.bwd_bulk_total_bytes += self._bwd_consec_bytes
            self.bwd_bulk_total_pkts += self._bwd_consec_count
            dur = self._bwd_consec_last - self._bwd_consec_start
            self.bwd_bulk_total_dur += dur

    def finalize_bulk(self) -> None:
        """Finalize any pending bulk run (call before feature extraction)."""
        self._finalize_run(self._bulk_last_dir)
        # Reset so double-call is safe
        self._fwd_consec_count = 0
        self._bwd_consec_count = 0

    # ------------------------------------------------------------------
    #  TCP flag counting
    # ------------------------------------------------------------------
    def _count_flags(self, flags: int, is_fwd: bool) -> None:
        """Count individual TCP flags (total and per-direction)."""
        if flags & FIN:
            self.fin_flag_count += 1
        if flags & SYN:
            self.syn_flag_count += 1
        if flags & RST:
            self.rst_flag_count += 1
        if flags & PSH:
            self.psh_flag_count += 1
            if is_fwd:
                self.fwd_psh_flags += 1
            else:
                self.bwd_psh_flags += 1
        if flags & ACK:
            self.ack_flag_count += 1
        if flags & URG:
            self.urg_flag_count += 1
            if is_fwd:
                self.fwd_urg_flags += 1
            else:
                self.bwd_urg_flags += 1
        if flags & CWR:
            self.cwr_flag_count += 1
        if flags & ECE:
            self.ece_flag_count += 1

    # ------------------------------------------------------------------
    #  Active / idle period tracking
    # ------------------------------------------------------------------
    def _update_activity(self, ts: float) -> None:
        """Track active and idle periods based on inter-packet gaps."""
        if self._activity_start == 0.0:
            self._activity_start = ts
            return

        if not self._flow_iat:
            return

        gap = self._flow_iat[-1]  # most recent IAT

        if gap > self._activity_threshold:
            # End of active period, start of idle
            # Active duration = time from activity start to previous packet
            active_dur = (ts - gap) - self._activity_start
            if active_dur > 0:
                self._active_times.append(active_dur * 1_000_000.0)  # microseconds
            self._idle_times.append(gap * 1_000_000.0)  # microseconds
            self._activity_start = ts

    # ------------------------------------------------------------------
    #  Derived helpers
    # ------------------------------------------------------------------
    @property
    def duration(self) -> float:
        """Flow duration in seconds."""
        return max(self.last_seen - self.first_seen, 0.0)

    @property
    def duration_us(self) -> float:
        """Flow duration in microseconds (CICFlowMeter convention)."""
        return self.duration * 1_000_000.0

    @property
    def spkts(self) -> int:
        return len(self._fwd_pkt_sizes)

    @property
    def dpkts(self) -> int:
        return len(self._bwd_pkt_sizes)

    @property
    def sbytes(self) -> int:
        return sum(self._fwd_pkt_sizes)

    @property
    def dbytes(self) -> int:
        return sum(self._bwd_pkt_sizes)

    @property
    def is_tcp_finished(self) -> bool:
        return self._rst_seen or self._fin_count >= 2


# ---------------------------------------------------------------------------
#  FlowSummary — lightweight record for optional cross-flow analysis
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FlowSummary:
    """Immutable summary of a completed flow."""
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int
    duration: float
    fwd_pkts: int
    bwd_pkts: int
    timestamp: float

    @classmethod
    def from_flow(cls, flow: FlowState) -> "FlowSummary":
        return cls(
            src_ip=flow.src_ip,
            dst_ip=flow.dst_ip,
            src_port=flow.src_port,
            dst_port=flow.dst_port,
            protocol=flow.protocol,
            duration=flow.duration,
            fwd_pkts=flow.spkts,
            bwd_pkts=flow.dpkts,
            timestamp=flow.last_seen,
        )