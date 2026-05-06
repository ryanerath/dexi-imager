"""Generate the DEXI Imager OS list manifest.

Builds the JSON file that DEXI Imager loads at startup. Each entry points to
a dexi-os image on Cloudflare R2.

Per-image data we collect (no full download of the 7+ GB zips):
  - image_download_size: HEAD request -> Content-Length of the .img.zip
  - extract_size: a handful of HTTP Range requests against the end of the
    .img.zip, parsed by Python's zipfile. Without this the imager falls
    back to the compressed size for its progress bar (so progress climbs
    past 100% during the write).

`extract_sha256` is intentionally omitted; verification will be added when
the dexi-os build pipeline emits its own checksum file.

Usage:
    python3 dexi/build_manifest.py --version v0.20

The manifest is committed to the repo and served via raw.githubusercontent.com.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import zipfile
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
        description="DEXI 3 — OS image for Raspberry Pi Compute Module 5",
        target="cm5",
    ),
    DexiModel(
        name="DEXI 5 (CM4)",
        description="DEXI 5 — OS image for Raspberry Pi Compute Module 4",
        target="ark_cm4",
    ),
    DexiModel(
        name="DEXI 10 (Pi 5)",
        description="DEXI 10 — OS image for Raspberry Pi 5",
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


class CurlRangeFile(io.RawIOBase):
    """File-like object backed by HTTP Range requests via curl.

    Lets `zipfile.ZipFile` read the central directory of a remote zip without
    downloading the whole archive. We use curl (not urllib) to dodge macOS
    Python's broken SSL cert verification.
    """

    def __init__(self, url: str, total_size: int) -> None:
        self._url = url
        self._size = total_size
        self._pos = 0

    def readable(self) -> bool: return True
    def seekable(self) -> bool: return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self._size + offset
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._size - self._pos
        if size <= 0 or self._pos >= self._size:
            return b""
        end = min(self._pos + size, self._size) - 1
        data = subprocess.check_output(
            ["curl", "-sSL", "--fail-with-body", "-r", f"{self._pos}-{end}", self._url],
        )
        self._pos += len(data)
        return data


def remote_extract_size(url: str, total_size: int) -> int:
    """Read the .img member's uncompressed size from the remote zip's directory.

    For our >4 GB images zipfile transparently uses the zip64 extra fields,
    so this works regardless of whether the file is zip32 or zip64.
    """
    rf = CurlRangeFile(url, total_size)
    with zipfile.ZipFile(rf) as zf:
        img_members = [m for m in zf.infolist() if m.filename.endswith(".img")]
        if len(img_members) != 1:
            raise RuntimeError(
                f"expected exactly one .img member in {url}, found {[m.filename for m in img_members]}"
            )
        return img_members[0].file_size


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
        print("  reading remote zip directory for uncompressed size...", flush=True)
        extract_size = remote_extract_size(url, download_size)
        print(f"  download={download_size:,}  extract={extract_size:,}", flush=True)
        entries.append({
            "name": model.name,
            "description": model.description,
            "url": url,
            "icon": "",
            "release_date": args.version,
            "image_download_size": download_size,
            "extract_size": extract_size,
            # extract_sha256 intentionally omitted; verification is skipped when
            # the imager sees an empty hash. Add when dexi-os emits checksums.
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
