"""Feature extractor: converts a completed FlowState into a 76-feature vector
matching the CICFlowMeter column names used by the SentinelAI Random Forest model.

The 76 features include:
- Flow-level stats (duration, bytes/s, packets/s)
- Per-direction packet length stats (min, max, mean, std)
- Inter-arrival time stats (flow-level and per-direction)
- TCP flag counts (total and per-direction PSH/URG)
- Header lengths, initial window sizes
- Bulk rate averages
- Subflow stats (same as totals for single-subflow)
- Active/idle period stats
"""

from __future__ import annotations

import statistics
from collections import OrderedDict
from typing import Dict, List

from .flow_state import FlowState, _safe_mean, _safe_stdev, _safe_variance


# ======================================================================
#  The exact 76 column names the model expects, in order
# ======================================================================
MODEL_COLUMNS: List[str] = [
    "Flow Duration",                # 0
    "Total Fwd Packet",             # 1
    "Total Bwd packets",            # 2
    "Total Length of Fwd Packet",    # 3
    "Total Length of Bwd Packet",    # 4
    "Fwd Packet Length Max",         # 5
    "Fwd Packet Length Min",         # 6
    "Fwd Packet Length Mean",        # 7
    "Fwd Packet Length Std",         # 8
    "Bwd Packet Length Max",         # 9
    "Bwd Packet Length Min",         # 10
    "Bwd Packet Length Mean",        # 11
    "Bwd Packet Length Std",         # 12
    "Flow Bytes/s",                  # 13
    "Flow Packets/s",                # 14
    "Flow IAT Mean",                 # 15
    "Flow IAT Std",                  # 16
    "Flow IAT Max",                  # 17
    "Flow IAT Min",                  # 18
    "Fwd IAT Total",                 # 19
    "Fwd IAT Mean",                  # 20
    "Fwd IAT Std",                   # 21
    "Fwd IAT Max",                   # 22
    "Fwd IAT Min",                   # 23
    "Bwd IAT Total",                 # 24
    "Bwd IAT Mean",                  # 25
    "Bwd IAT Std",                   # 26
    "Bwd IAT Max",                   # 27
    "Bwd IAT Min",                   # 28
    "Fwd PSH Flags",                 # 29
    "Bwd PSH Flags",                 # 30
    "Fwd URG Flags",                 # 31
    "Bwd URG Flags",                 # 32
    "Fwd Header Length",             # 33
    "Bwd Header Length",             # 34
    "Fwd Packets/s",                 # 35
    "Bwd Packets/s",                 # 36
    "Packet Length Min",             # 37
    "Packet Length Max",             # 38
    "Packet Length Mean",            # 39
    "Packet Length Std",             # 40
    "Packet Length Variance",        # 41
    "FIN Flag Count",                # 42
    "SYN Flag Count",                # 43
    "RST Flag Count",                # 44
    "PSH Flag Count",                # 45
    "ACK Flag Count",                # 46
    "URG Flag Count",                # 47
    "CWR Flag Count",                # 48
    "ECE Flag Count",                # 49
    "Down/Up Ratio",                 # 50
    "Average Packet Size",           # 51
    "Fwd Segment Size Avg",          # 52
    "Bwd Segment Size Avg",          # 53
    "Fwd Bytes/Bulk Avg",            # 54
    "Fwd Packet/Bulk Avg",           # 55
    "Fwd Bulk Rate Avg",             # 56
    "Bwd Bytes/Bulk Avg",            # 57
    "Bwd Packet/Bulk Avg",           # 58
    "Bwd Bulk Rate Avg",             # 59
    "Subflow Fwd Packets",           # 60
    "Subflow Fwd Bytes",             # 61
    "Subflow Bwd Packets",           # 62
    "Subflow Bwd Bytes",             # 63
    "FWD Init Win Bytes",            # 64
    "Bwd Init Win Bytes",            # 65
    "Fwd Act Data Pkts",             # 66
    "Fwd Seg Size Min",              # 67
    "Active Mean",                   # 68
    "Active Std",                    # 69
    "Active Max",                    # 70
    "Active Min",                    # 71
    "Idle Mean",                     # 72
    "Idle Std",                      # 73
    "Idle Max",                      # 74
    "Idle Min",                      # 75
]


def _us(seconds: float) -> float:
    """Convert seconds to microseconds."""
    return seconds * 1_000_000.0


class FeatureExtractor:
    """Extract CICFlowMeter feature vectors from completed flows.

    Returns an OrderedDict with the exact 76 column names and order
    that the SentinelAI Random Forest model expects.
    """

    def __init__(self) -> None:
        self._columns = list(MODEL_COLUMNS)

    def extract(self, flow: FlowState) -> OrderedDict[str, float]:
        """Compute the full 76-feature vector for a completed flow.

        Parameters
        ----------
        flow : FlowState
            The completed flow with all accumulated packet stats.

        Returns
        -------
        OrderedDict mapping feature name -> numeric value, in the order
        the model expects.
        """
        f = flow
        dur_s = f.duration
        dur_us = f.duration_us
        dur_safe = dur_s if dur_s > 0 else 1e-9  # avoid div by zero

        fwd = f._fwd_pkt_sizes
        bwd = f._bwd_pkt_sizes
        all_pkts = fwd + bwd

        total_fwd_bytes = sum(fwd)
        total_bwd_bytes = sum(bwd)
        total_bytes = total_fwd_bytes + total_bwd_bytes
        total_pkts = len(all_pkts)

        # IATs in microseconds (CICFlowMeter convention)
        flow_iat_us = [_us(x) for x in f._flow_iat]
        fwd_iat_us = [_us(x) for x in f._fwd_iat]
        bwd_iat_us = [_us(x) for x in f._bwd_iat]

        features = OrderedDict()

        # 0: Flow Duration (microseconds)
        features["Flow Duration"] = dur_us

        # 1-2: Packet counts
        features["Total Fwd Packet"] = float(len(fwd))
        features["Total Bwd packets"] = float(len(bwd))

        # 3-4: Total bytes per direction
        features["Total Length of Fwd Packet"] = float(total_fwd_bytes)
        features["Total Length of Bwd Packet"] = float(total_bwd_bytes)

        # 5-8: Forward packet length stats
        features["Fwd Packet Length Max"] = float(max(fwd)) if fwd else 0.0
        features["Fwd Packet Length Min"] = float(min(fwd)) if fwd else 0.0
        features["Fwd Packet Length Mean"] = _safe_mean([float(x) for x in fwd])
        features["Fwd Packet Length Std"] = _safe_stdev([float(x) for x in fwd])

        # 9-12: Backward packet length stats
        features["Bwd Packet Length Max"] = float(max(bwd)) if bwd else 0.0
        features["Bwd Packet Length Min"] = float(min(bwd)) if bwd else 0.0
        features["Bwd Packet Length Mean"] = _safe_mean([float(x) for x in bwd])
        features["Bwd Packet Length Std"] = _safe_stdev([float(x) for x in bwd])

        # 13-14: Flow rates
        features["Flow Bytes/s"] = total_bytes / dur_safe
        features["Flow Packets/s"] = total_pkts / dur_safe

        # 15-18: Flow IAT stats (microseconds)
        features["Flow IAT Mean"] = _safe_mean(flow_iat_us)
        features["Flow IAT Std"] = _safe_stdev(flow_iat_us)
        features["Flow IAT Max"] = max(flow_iat_us) if flow_iat_us else 0.0
        features["Flow IAT Min"] = min(flow_iat_us) if flow_iat_us else 0.0

        # 19-23: Forward IAT stats (microseconds)
        features["Fwd IAT Total"] = sum(fwd_iat_us)
        features["Fwd IAT Mean"] = _safe_mean(fwd_iat_us)
        features["Fwd IAT Std"] = _safe_stdev(fwd_iat_us)
        features["Fwd IAT Max"] = max(fwd_iat_us) if fwd_iat_us else 0.0
        features["Fwd IAT Min"] = min(fwd_iat_us) if fwd_iat_us else 0.0

        # 24-28: Backward IAT stats (microseconds)
        features["Bwd IAT Total"] = sum(bwd_iat_us)
        features["Bwd IAT Mean"] = _safe_mean(bwd_iat_us)
        features["Bwd IAT Std"] = _safe_stdev(bwd_iat_us)
        features["Bwd IAT Max"] = max(bwd_iat_us) if bwd_iat_us else 0.0
        features["Bwd IAT Min"] = min(bwd_iat_us) if bwd_iat_us else 0.0

        # 29-32: Per-direction PSH/URG flags
        features["Fwd PSH Flags"] = float(f.fwd_psh_flags)
        features["Bwd PSH Flags"] = float(f.bwd_psh_flags)
        features["Fwd URG Flags"] = float(f.fwd_urg_flags)
        features["Bwd URG Flags"] = float(f.bwd_urg_flags)

        # 33-34: Header lengths
        features["Fwd Header Length"] = float(f.fwd_header_bytes)
        features["Bwd Header Length"] = float(f.bwd_header_bytes)

        # 35-36: Per-direction packet rates
        features["Fwd Packets/s"] = len(fwd) / dur_safe
        features["Bwd Packets/s"] = len(bwd) / dur_safe

        # 37-41: Overall packet length stats
        all_float = [float(x) for x in all_pkts]
        features["Packet Length Min"] = float(min(all_pkts)) if all_pkts else 0.0
        features["Packet Length Max"] = float(max(all_pkts)) if all_pkts else 0.0
        features["Packet Length Mean"] = _safe_mean(all_float)
        features["Packet Length Std"] = _safe_stdev(all_float)
        features["Packet Length Variance"] = _safe_variance(all_float)

        # 42-49: TCP flag counts
        features["FIN Flag Count"] = float(f.fin_flag_count)
        features["SYN Flag Count"] = float(f.syn_flag_count)
        features["RST Flag Count"] = float(f.rst_flag_count)
        features["PSH Flag Count"] = float(f.psh_flag_count)
        features["ACK Flag Count"] = float(f.ack_flag_count)
        features["URG Flag Count"] = float(f.urg_flag_count)
        features["CWR Flag Count"] = float(f.cwr_flag_count)
        features["ECE Flag Count"] = float(f.ece_flag_count)

        # 50: Down/Up Ratio
        if len(fwd) > 0:
            features["Down/Up Ratio"] = float(len(bwd)) / float(len(fwd))
        else:
            features["Down/Up Ratio"] = 0.0

        # 51: Average Packet Size (all packets)
        features["Average Packet Size"] = (
            total_bytes / total_pkts if total_pkts > 0 else 0.0
        )

        # 52-53: Segment size averages (same as packet length mean for us)
        features["Fwd Segment Size Avg"] = features["Fwd Packet Length Mean"]
        features["Bwd Segment Size Avg"] = features["Bwd Packet Length Mean"]

        # 54-59: Bulk rate features
        # CICFlowMeter: "bulk" = 4+ consecutive packets in one direction.
        f.finalize_bulk()  # flush any pending run

        if f.fwd_bulk_count > 0:
            features["Fwd Bytes/Bulk Avg"] = (
                f.fwd_bulk_total_bytes / f.fwd_bulk_count
            )
            features["Fwd Packet/Bulk Avg"] = (
                f.fwd_bulk_total_pkts / f.fwd_bulk_count
            )
            features["Fwd Bulk Rate Avg"] = (
                f.fwd_bulk_total_bytes / f.fwd_bulk_total_dur
                if f.fwd_bulk_total_dur > 0 else 0.0
            )
        else:
            features["Fwd Bytes/Bulk Avg"] = 0.0
            features["Fwd Packet/Bulk Avg"] = 0.0
            features["Fwd Bulk Rate Avg"] = 0.0

        if f.bwd_bulk_count > 0:
            features["Bwd Bytes/Bulk Avg"] = (
                f.bwd_bulk_total_bytes / f.bwd_bulk_count
            )
            features["Bwd Packet/Bulk Avg"] = (
                f.bwd_bulk_total_pkts / f.bwd_bulk_count
            )
            features["Bwd Bulk Rate Avg"] = (
                f.bwd_bulk_total_bytes / f.bwd_bulk_total_dur
                if f.bwd_bulk_total_dur > 0 else 0.0
            )
        else:
            features["Bwd Bytes/Bulk Avg"] = 0.0
            features["Bwd Packet/Bulk Avg"] = 0.0
            features["Bwd Bulk Rate Avg"] = 0.0

        # 60-63: Subflow stats (single subflow = same as totals)
        features["Subflow Fwd Packets"] = float(len(fwd))
        features["Subflow Fwd Bytes"] = float(total_fwd_bytes)
        features["Subflow Bwd Packets"] = float(len(bwd))
        features["Subflow Bwd Bytes"] = float(total_bwd_bytes)

        # 64-65: Initial TCP window sizes
        features["FWD Init Win Bytes"] = float(
            f.fwd_init_win if f.fwd_init_win >= 0 else -1
        )
        features["Bwd Init Win Bytes"] = float(
            f.bwd_init_win if f.bwd_init_win >= 0 else -1
        )

        # 66: Forward active data packets
        features["Fwd Act Data Pkts"] = float(f.fwd_act_data_pkts)

        # 67: Forward segment size minimum
        features["Fwd Seg Size Min"] = (
            float(min(f._fwd_seg_sizes)) if f._fwd_seg_sizes else 0.0
        )

        # 68-71: Active period stats (microseconds)
        features["Active Mean"] = _safe_mean(f._active_times)
        features["Active Std"] = _safe_stdev(f._active_times)
        features["Active Max"] = max(f._active_times) if f._active_times else 0.0
        features["Active Min"] = min(f._active_times) if f._active_times else 0.0

        # 72-75: Idle period stats (microseconds)
        features["Idle Mean"] = _safe_mean(f._idle_times)
        features["Idle Std"] = _safe_stdev(f._idle_times)
        features["Idle Max"] = max(f._idle_times) if f._idle_times else 0.0
        features["Idle Min"] = min(f._idle_times) if f._idle_times else 0.0

        return features

    def feature_names(self) -> List[str]:
        """Return the ordered feature column names."""
        return list(self._columns)