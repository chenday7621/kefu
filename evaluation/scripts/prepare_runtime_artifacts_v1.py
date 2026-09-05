#!/usr/bin/env python3
"""Safely materialize ignored runtime artifacts from committed LFS archives."""
from __future__ import annotations

import hashlib
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _lfs_payload(path: Path) -> Path:
    prefix = path.read_bytes()[:256]
    if not prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        return path
    match = re.search(rb"oid sha256:([0-9a-f]{64})", prefix)
    if not match:
        raise RuntimeError(f"invalid Git LFS pointer: {path}")
    oid = match.group(1).decode("ascii")
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True
    ).strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (ROOT / common_path).resolve()
    payload = common_path / "lfs" / "objects" / oid[:2] / oid[2:4] / oid
    if not payload.is_file():
        raise RuntimeError(
            f"missing local LFS object for {path}; run `git lfs pull` before reproduction"
        )
    return payload


def _extract_chunks() -> None:
    destination = ROOT / "process" / "artifacts"
    manuals = destination / "manuals"
    if manuals.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    archive = _lfs_payload(ROOT / "data" / "build-artifacts.tar.gz")
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(destination, filter="data")


def _extract_images() -> int:
    destination = ROOT / "process" / "data" / "插图"
    destination.mkdir(parents=True, exist_ok=True)
    written = 0
    for relative in ("data/ch-manual/插图.zip", "data/en-manual/插图.zip"):
        archive = _lfs_payload(ROOT / relative)
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                name = Path(info.filename.replace("\\", "/")).name
                if not name or Path(name).suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                data = handle.read(info)
                target = destination / name
                if target.exists():
                    if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(data).digest():
                        raise RuntimeError(f"conflicting image payload for {name}")
                    continue
                target.write_bytes(data)
                written += 1
    return written


def main() -> int:
    _extract_chunks()
    written = _extract_images()
    print(f"runtime artifacts ready; new_images={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
