#!/usr/bin/env python3
"""Prepare an immutable data asset from a snapshot, without crawling or publishing."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from datetime import date
from pathlib import Path

DATA_FILES = ("undergraduate_courses.csv", "graduate_courses.csv", "term_offerings.csv", "catalog_meta.json")
REPOSITORY = "qazybekb/openmind"


def prepare(data: Path, out: Path) -> dict[str, str]:
    """Build a reproducible archive and write the matching public manifest locally."""
    contents = {name: (data / name).read_bytes() for name in DATA_FILES}
    manifest = json.loads(contents["catalog_meta.json"])
    captured = date.fromisoformat(manifest["catalog_as_of"]).isoformat()
    manifest.pop("asset_url", None)
    manifest.pop("data_sha256", None)
    contents["catalog_meta.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    identity = hashlib.sha256()
    for name, content in sorted(contents.items()):
        identity.update(name.encode() + b"\0" + str(len(content)).encode() + b"\0" + content)
    tag = f"data-{captured}-{identity.hexdigest()[:16]}"
    name = f"catalog-{captured}.tar.gz"
    manifest["asset_url"] = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    # An archive cannot contain its own hash. The outer manifest gets the verified hash.
    manifest["data_sha256"] = ""
    contents["catalog_meta.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, filename="", mode="wb", mtime=0) as compressed, \
         tarfile.open(fileobj=compressed, mode="w") as archive:
        for filename, content in sorted(contents.items()):
            member = tarfile.TarInfo(filename)
            member.size = len(content)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(content))
    body = buffer.getvalue()
    digest = hashlib.sha256(body).hexdigest()
    out.mkdir(parents=True, exist_ok=True)
    asset = out / name
    asset.write_bytes(body)
    manifest["data_sha256"] = digest
    rendered = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    target = data / "catalog_meta.json"
    if target.read_bytes() != rendered:
        target.write_bytes(rendered)
    return {"date": captured, "tag": tag, "name": name, "file": str(asset.resolve()), "sha": digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("src/openmind/data"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    result = prepare(args.data, args.out)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            for key, value in result.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("GitHub output values must be single-line")
                handle.write(f"{key}={value}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
