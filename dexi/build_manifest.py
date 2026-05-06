"""Generate the DEXI Imager OS list manifest.

Builds the JSON file that DEXI Imager loads at startup. Each entry points to
a dexi-os image on Cloudflare R2. We only HEAD the URLs to read Content-Length;
no hashing or downloading. Add `extract_sha256` later when we wire up auto-builds.

Usage:
    python3 dexi/build_manifest.py --version v0.20

The manifest is committed to the repo and served via raw.githubusercontent.com.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

R2_BASE = "https://pub-7efc16585b2a4b5ab550489e8d8d5b33.r2.dev"


@dataclass(frozen=True)
class DexiModel:
    name: str           # User-facing label
    description: str
    target: str         # dexi-os build target -> filename component


MODELS: list[DexiModel] = [
    DexiModel(
        name="DEXI 3 (CM5)",
        description="DEXI 3 — flight controller image for Raspberry Pi Compute Module 5",
        target="cm5",
    ),
    DexiModel(
        name="DEXI 5 (CM4)",
        description="DEXI 5 — flight controller image for Raspberry Pi Compute Module 4",
        target="ark_cm4",
    ),
    DexiModel(
        name="DEXI 10 (Pi 5)",
        description="DEXI 10 — flight controller image for Raspberry Pi 5",
        target="pi5",
    ),
]

# Show every entry on every hardware family so the imager doesn't filter our
# images out of the list. Refine later if we want per-model filtering.
DEVICES_ALL = [
    "pi5-64bit", "pi5-32bit",
    "pi4-64bit", "pi4-32bit",
    "pi3-64bit", "pi3-32bit",
    "pi2-32bit", "pi1-32bit",
    "cm5-64bit", "cm4-64bit",
]


def image_url(version: str, target: str) -> str:
    return f"{R2_BASE}/{version}/dexi_raspberry_pi_os_{target}.img.zip"


def head_size(url: str) -> int:
    """Return Content-Length via `curl -sI`. Avoids macOS Python SSL cert issues."""
    out = subprocess.check_output(["curl", "-sIL", "--fail-with-body", url], text=True)
    for line in out.splitlines():
        if line.lower().startswith("content-length:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"No Content-Length for {url}\n{out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="dexi-os version tag, e.g. v0.20")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "dexi_os_list.json",
    )
    args = parser.parse_args()

    entries = []
    for model in MODELS:
        url = image_url(args.version, model.target)
        print(f"HEAD {url}", flush=True)
        download_size = head_size(url)
        entries.append({
            "name": model.name,
            "description": model.description,
            "url": url,
            "icon": "",
            "release_date": args.version,
            # extract_size and extract_sha256 intentionally omitted for now.
            # The imager treats them as optional; verification is skipped when
            # extract_sha256 is empty. Add when we automate manifest builds.
            "image_download_size": download_size,
            "devices": DEVICES_ALL,
        })

    manifest = {
        "imager": {
            "latest_version": "1.0.0",
            "url": "https://github.com/ryanerath/dexi-imager",
        },
        # Flat list — DEXI 3 / 5 / 10 appear directly on the picker, no nesting.
        "os_list": entries,
    }

    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {args.out}  ({len(entries)} entries, version {args.version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
