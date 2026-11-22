"""Packet capture engine: sniffs packets from a network interface using scapy.

The engine runs scapy's ``sniff()`` in a dedicated daemon thread and pushes
parsed packet tuples into an asyncio queue for consumption by the LiveSession
orchestrator.  This is strictly *read-only* — no packet injection.

Prerequisites (Windows):
    - Npcap installed with "WinPcap API-compatible mode" enabled
    - Administrator privileges for raw socket access
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import threading
from typing import Optional

logger = logging.getLogger(__name__)


# ======================================================================
#  Npcap / libpcap detection
# ======================================================================

class NpcapNotFoundError(RuntimeError):
    """Raised when Npcap (Windows) or libpcap (Linux/macOS) is missing."""
    pass


def check_pcap_available() -> dict:
    """Check whether the pcap library is available.

    Returns a dict with:
        available (bool): True if capture is possible
        backend (str): "npcap", "winpcap", "libpcap", or "unknown"
        message (str): Human-readable status
        hint (str|None): Install instructions if unavailable

    Raises nothing — always returns a dict.
    """
    system = platform.system().lower()

    if system == "windows":
        return _check_windows_pcap()
    else:
        return _check_unix_pcap()


def _check_windows_pcap() -> dict:
    """Check for Npcap or WinPcap on Windows."""
    # Npcap installs to System32\Npcap
    npcap_dir = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "Npcap",
    )
    npcap_dll = os.path.join(npcap_dir, "wpcap.dll")

    # Legacy WinPcap installs wpcap.dll directly in System32
    sys32 = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
    )
    winpcap_dll = os.path.join(sys32, "wpcap.dll")

    if os.path.isfile(npcap_dll):
        return {
            "available": True,
            "backend": "npcap",
            "message": "Npcap detected",
            "hint": None,
        }
    elif os.path.isfile(winpcap_dll):
        # WinPcap works but is deprecated; Npcap is preferred
        return {
            "available": True,
            "backend": "winpcap",
            "message": "WinPcap detected (Npcap recommended)",
            "hint": (
                "Consider upgrading to Npcap for better performance: "
                "https://npcap.com/#download — install with "
                "\"WinPcap API-compatible mode\" enabled."
            ),
        }
    else:
        return {
            "available": False,
            "backend": "none",
            "message": "No packet capture library found",
            "hint": (
                "Install Npcap from https://npcap.com/#download — "
                "during installation, check \"Install Npcap in "
                "WinPcap API-compatible mode\". Then restart the "
                "SentinelAI backend."
            ),
        }


def _check_unix_pcap() -> dict:
    """Check for libpcap on Linux/macOS."""
    import shutil

    # Check if scapy can import (which needs libpcap)
    # Quick check: look for the shared library or the tcpdump binary
    has_tcpdump = shutil.which("tcpdump") is not None

    # Also try to find libpcap.so / libpcap.dylib
    system = platform.system().lower()
    lib_found = False
    if system == "darwin":
        # macOS ships libpcap by default
        lib_found = os.path.exists("/usr/lib/libpcap.dylib")
    else:
        # Linux: check common paths
        for path in [
            "/usr/lib/x86_64-linux-gnu/libpcap.so",
            "/usr/lib/libpcap.so",
            "/usr/lib64/libpcap.so",
        ]:
            if os.path.exists(path):
                lib_found = True
                break

    if lib_found or has_tcpdump:
        return {
            "available": True,
            "backend": "libpcap",
            "message": "libpcap detected",
            "hint": None,
        }
    else:
        pkg_cmd = (
            "brew install libpcap" if system == "darwin"
            else "sudo apt install libpcap-dev  # Debian/Ubuntu\n"
                 "sudo dnf install libpcap-devel  # Fedora/RHEL"
        )
        return {
            "available": False,
            "backend": "none",
            "message": "libpcap not found",
            "hint": f"Install libpcap:\n{pkg_cmd}",
        }


# Packet tuple fields pushed to the queue
# (ts, src_ip, dst_ip, src_port, dst_port, protocol,
#  ip_len, ttl, tcp_flags, tcp_seq, tcp_win, payload_len)
PacketTuple = tuple


class CaptureEngine:
    """Manages packet capture on a background thread.

    Parameters
    ----------
    interface : str
        Network interface name (e.g. "Ethernet", "Wi-Fi", "lo").
    bpf_filter : str
        Optional BPF filter expression (e.g. "tcp port 80").
    queue : asyncio.Queue
        Async queue to push parsed packets into.
    loop : asyncio.AbstractEventLoop
        The event loop of the calling async context (needed to push
        from the sniff thread into the async queue safely).
    """

    def __init__(
        self,
        interface: str,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        bpf_filter: str = "",
    ):
        self.interface = interface
        self.bpf_filter = bpf_filter
        self._queue = queue
        self._loop = loop
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stats
        self.packets_captured: int = 0
        self.packets_dropped: int = 0

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the capture thread."""
        if self._running:
            logger.warning("Capture already running on %s", self.interface)
            return

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._sniff_loop,
            name=f"capture-{self.interface}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Capture started on interface=%s filter=%r",
                     self.interface, self.bpf_filter)

    def stop(self) -> None:
        """Signal the capture thread to stop and wait for it."""
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("Capture stopped on %s (%d packets captured)",
                     self.interface, self.packets_captured)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    #  Sniff loop (runs in a dedicated thread)
    # ------------------------------------------------------------------
    def _sniff_loop(self) -> None:
        """Thread target: runs scapy.sniff with a packet callback."""
        try:
            # Import scapy lazily so the module can be imported on systems
            # without scapy installed (e.g. for testing flow logic).
            from scapy.all import sniff as scapy_sniff  # type: ignore

            scapy_sniff(
                iface=self.interface,
                filter=self.bpf_filter or None,
                prn=self._handle_packet,
                store=False,          # don't accumulate packets in memory
                stop_filter=lambda _: self._stop_event.is_set(),
            )
        except ImportError:
            logger.error(
                "scapy is not installed. Install with: "
                "pip install scapy>=2.5.0"
            )
            self._running = False
        except PermissionError:
            logger.error(
                "Permission denied. On Windows, run as Administrator. "
                "Ensure Npcap is installed with WinPcap compatibility."
            )
            self._running = False
        except OSError as exc:
            logger.error("Capture error on %s: %s", self.interface, exc)
            self._running = False
        finally:
            self._running = False

    def _handle_packet(self, pkt) -> None:
        """Callback for each captured packet — parse and enqueue."""
        try:
            parsed = self._parse_packet(pkt)
            if parsed is not None:
                self.packets_captured += 1
                # Thread-safe push into the asyncio queue
                self._loop.call_soon_threadsafe(
                    self._queue.put_nowait, parsed,
                )
        except asyncio.QueueFull:
            self.packets_dropped += 1
        except Exception:
            # Never let a parse error kill the capture thread
            self.packets_dropped += 1

    # ------------------------------------------------------------------
    #  Packet parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_packet(pkt) -> Optional[PacketTuple]:
        """Extract fields from a scapy packet into a flat tuple.

        Returns None for non-IP packets (ARP, etc.).
        """
        from scapy.layers.inet import IP, TCP, UDP, ICMP  # type: ignore

        if not pkt.haslayer(IP):
            return None

        ip = pkt[IP]
        ts = float(pkt.time)
        src_ip = ip.src
        dst_ip = ip.dst
        protocol = ip.proto
        ip_len = len(ip)
        ttl = ip.ttl

        src_port = 0
        dst_port = 0
        tcp_flags = 0
        tcp_seq = 0
        tcp_win = 0
        payload_len = 0
        header_len = ip.ihl * 4   # IP header length

        if pkt.haslayer(TCP):
            tcp = pkt[TCP]
            src_port = tcp.sport
            dst_port = tcp.dport
            tcp_flags = int(tcp.flags)
            tcp_seq = tcp.seq
            tcp_win = tcp.window
            tcp_hdr = tcp.dataofs * 4
            header_len += tcp_hdr
            # Payload = IP length minus IP header minus TCP header
            payload_len = max(0, ip_len - (ip.ihl * 4) - tcp_hdr)

        elif pkt.haslayer(UDP):
            udp = pkt[UDP]
            src_port = udp.sport
            dst_port = udp.dport
            header_len += 8        # UDP header is always 8 bytes
            payload_len = max(0, len(udp.payload))

        elif pkt.haslayer(ICMP):
            # ICMP: use type and code as pseudo-ports
            icmp = pkt[ICMP]
            src_port = icmp.type
            dst_port = icmp.code
            header_len += 8        # ICMP header is 8 bytes

        return (
            ts, src_ip, dst_ip, src_port, dst_port, protocol,
            ip_len, ttl, tcp_flags, tcp_seq, tcp_win, payload_len,
            header_len,
        )


# ======================================================================
#  Interface listing utility
# ======================================================================

def list_interfaces() -> list[dict]:
    """List network interfaces with their IPv4 addresses.

    Returns a list of dicts with keys: name, addresses, is_up.
    Uses psutil if available, falls back to scapy.
    """
    interfaces = []

    try:
        import psutil  # type: ignore
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for name, addr_list in addrs.items():
            ipv4_addrs = [
                a.address for a in addr_list
                if a.family.name == "AF_INET"  # IPv4
            ]
            if ipv4_addrs:
                is_up = stats.get(name, None)
                interfaces.append({
                    "name": name,
                    "addresses": ipv4_addrs,
                    "is_up": is_up.isup if is_up else False,
                })

    except ImportError:
        # Fallback: try scapy's interface listing
        try:
            from scapy.all import get_if_list, get_if_addr  # type: ignore
            for iface in get_if_list():
                addr = get_if_addr(iface)
                if addr and addr != "0.0.0.0":
                    interfaces.append({
                        "name": iface,
                        "addresses": [addr],
                        "is_up": True,
                    })
        except Exception:
            pass

    return interfaces