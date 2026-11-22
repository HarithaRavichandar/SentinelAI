"""Download and verify SentinelAI model artifacts.

This script automates the downloading and SHA-256 verification of large serialized
machine learning model artifacts from GitHub Releases or custom mirrors into the
appropriate project directories (data/models/ and data/models_fresh/).

Usage:
    # Verify integrity of existing local model files
    python scripts/download_models.py --verify-only

    # Download missing models from a specified GitHub release tag
    python scripts/download_models.py --tag v0.1.0-artifacts

    # Download from a custom mirror base URL
    python scripts/download_models.py --mirror https://custom-mirror.example.com/models/
"""

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Any

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Model artifact registry: metadata, expected SHA-256 hashes, and target paths
ARTIFACT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "random_forest_balanced.pkl": {
        "description": "Legacy baseline Random Forest model (200 trees, balanced weights)",
        "target_path": PROJECT_ROOT / "data" / "models" / "random_forest_balanced.pkl",
        "expected_sha256": "73f9fc5d7986c1cc935e3dcd072ca3cc655e5539f5fdfeb104419113cb43258f",
        "expected_bytes": 916337113,
        "release_asset": "random_forest_balanced.pkl",
    },
    "preprocessor_balanced.pkl": {
        "description": "Legacy baseline StandardScaler preprocessor artifact",
        "target_path": PROJECT_ROOT / "data" / "processed" / "preprocessor_balanced.pkl",
        "expected_sha256": "2fe879fbf70c3c72fbde6f50c3dc7c86b6e9edf6f450ee39fda8053284965169",
        "expected_bytes": 5881,
        "release_asset": "preprocessor_balanced.pkl",
    },
    "random_forest_fresh.pkl": {
        "description": "Fresh group-aware calibrated Random Forest model (200 trees)",
        "target_path": PROJECT_ROOT / "data" / "models_fresh" / "random_forest_fresh.pkl",
        "expected_sha256": "7573dd297654a7b72517bb1336c03fca78138515decfb3cabc1cad3a4b4f8a24",
        "expected_bytes": 929431545,
        "release_asset": "random_forest_fresh.pkl",
    },
    "preprocessor_fresh.pkl": {
        "description": "Fresh group-aware StandardScaler preprocessor artifact",
        "target_path": PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl",
        "expected_sha256": "0816c8d7488a1d2c0db7b3f4204f8ca01a88534841c669652c207d6e84c47a43",
        "expected_bytes": 5515,
        "release_asset": "preprocessor_fresh.pkl",
    },
}

DEFAULT_REPO = "HarithaRavichandar/SentinelAI"
DEFAULT_RELEASE_TAG = "v0.1.0-artifacts"


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hash of a file efficiently using 1 MB chunks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def verify_artifact(name: str, meta: Dict[str, Any]) -> bool:
    """Verify whether a local artifact exists and matches its expected SHA-256 checksum."""
    target: Path = meta["target_path"]
    if not target.exists():
        print(f"[-] {name}: File missing at {target.relative_to(PROJECT_ROOT)}")
        return False

    actual_size = target.stat().st_size
    print(f"[*] {name}: Verifying {actual_size / (1024*1024):.2f} MB...")
    actual_hash = compute_sha256(target)
    expected_hash = meta["expected_sha256"].lower()

    if actual_hash == expected_hash:
        print(f"[+] {name}: OK (SHA-256: {actual_hash[:16]}...)")
        return True
    else:
        print(f"[!] {name}: CHECKSUM MISMATCH!")
        print(f"    Expected: {expected_hash}")
        print(f"    Actual:   {actual_hash}")
        return False


def download_artifact(url: str, destination: Path, expected_hash: str) -> bool:
    """Download an artifact from a URL with temporary file safety and checksum verification."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(".tmp")

    print(f"[*] Downloading {url} -> {destination.name}...")
    try:
        def progress(count, block_size, total_size):
            if total_size > 0:
                percent = min(100, int(count * block_size * 100 / total_size))
                mb = (count * block_size) / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                sys.stdout.write(f"\r    {mb:.1f} / {total_mb:.1f} MB ({percent}%)")
                sys.stdout.flush()

        urllib.request.urlretrieve(url, tmp_path, reporthook=progress)
        print()
    except Exception as exc:
        print(f"\n[!] Download failed: {exc}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False

    actual_hash = compute_sha256(tmp_path)
    if actual_hash == expected_hash.lower():
        tmp_path.replace(destination)
        print(f"[+] Successfully verified and installed {destination.name}")
        return True
    else:
        print(f"[!] Downloaded file checksum mismatch! Removing corrupt temporary file.")
        tmp_path.unlink()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="SentinelAI Model Artifact Verification and Download Utility"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing local model artifacts without downloading",
    )
    parser.add_argument(
        "--tag",
        default=DEFAULT_RELEASE_TAG,
        help=f"GitHub release tag containing model assets (default: {DEFAULT_RELEASE_TAG})",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository in owner/repo format (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--mirror",
        default=None,
        help="Custom base URL mirror containing model files",
    )

    args = parser.parse_args()

    print("=" * 70)
    print(" SentinelAI Model Artifact Verification & Acquisition Utility")
    print("=" * 70)

    if args.verify_only:
        print("[*] Running in verification-only mode...\n")
        all_valid = True
        for name, meta in ARTIFACT_REGISTRY.items():
            valid = verify_artifact(name, meta)
            all_valid = all_valid and valid
        print("\n" + ("=" * 70))
        if all_valid:
            print("[+] All model artifacts are present and verified.")
            sys.exit(0)
        else:
            print("[!] One or more model artifacts are missing or invalid.")
            sys.exit(1)

    # Download missing or invalid artifacts
    for name, meta in ARTIFACT_REGISTRY.items():
        target: Path = meta["target_path"]
        if target.exists():
            if verify_artifact(name, meta):
                continue
            print(f"[*] Re-downloading corrupt artifact: {name}")

        if args.mirror:
            download_url = f"{args.mirror.rstrip('/')}/{meta['release_asset']}"
        else:
            download_url = f"https://github.com/{args.repo}/releases/download/{args.tag}/{meta['release_asset']}"

        success = download_artifact(download_url, target, meta["expected_sha256"])
        if not success:
            print(f"\n[!] Failed to acquire required artifact '{name}'.")
            print(f"    Please manually download '{meta['release_asset']}' and place it at:")
            print(f"    {target.relative_to(PROJECT_ROOT)}")
            sys.exit(1)

    print("\n[+] All required model artifacts are ready.")


if __name__ == "__main__":
    main()

