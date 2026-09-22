#!/usr/bin/env python3
"""Restore this lossless experiment archive. Standard library; no API or fitting."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(name):
    value = PurePosixPath(name)
    require(not value.is_absolute() and bool(value.parts)
            and all(part not in {".", ".."} and not part.startswith(".") for part in value.parts),
            "Unsafe archive path")
    require(str(value) == name, "Noncanonical archive path")
    return value


def original_json(value):
    # This is the frozen runner's serialization, including dictionary order.
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def restore_records(value, bank):
    if not isinstance(value, dict):
        return
    if "records" in value:
        reference = value["records"]
        require(isinstance(reference, dict) and set(reference) == {"bank", "order"},
                "Malformed candidate-bank reference")
        require(reference["bank"] == bank["case_id"], "Candidate bank identity mismatch")
        records = {}
        for model_id, version in reference["order"]:
            require(model_id not in records, "Duplicate model reference")
            candidates = bank["candidates"][model_id]
            require(isinstance(version, int) and 0 <= version < len(candidates), "Invalid candidate version")
            record = candidates[version]
            require(record["model_id"] == model_id, "Candidate model identity mismatch")
            records[model_id] = record
        value["records"] = records
    for attempt in value.get("previous_attempts", []):
        restore_records(attempt, bank)


def verify_package(package):
    manifest_path = package / "SHA256SUMS"
    require(manifest_path.is_file(), "Missing package checksum manifest")
    listed = {}
    for line in manifest_path.read_text().splitlines():
        checksum, name = line.split("  ", 1)
        safe_path(name)
        require(name not in listed and len(checksum) == 64, "Malformed package checksum manifest")
        listed[name] = checksum
        path = package / name
        require(path.is_file() and not path.is_symlink(), f"Missing regular package file: {name}")
        require(file_sha(path) == checksum, f"Package checksum mismatch: {name}")
    return listed


def restore(package, output):
    package, output = package.resolve(), output.resolve()
    require(not output.exists(), "Output directory must not exist")
    require(package not in output.parents and output not in package.parents,
            "Output must be outside the package directory")
    verify_package(package)
    manifest = json.loads((package / "manifest.json").read_text())
    require(manifest["format"] == "live-salmon-lossless-candidate-bank-v1", "Unsupported archive format")
    expected = manifest["restored_files"]
    for name in expected:
        safe_path(name)
    output.mkdir(parents=True)
    written = set()

    # Extract only regular, explicitly manifested files; no links or path traversal.
    with tarfile.open(package / "supporting-files.tar.gz", "r:gz") as archive:
        for member in archive:
            name = str(safe_path(member.name))
            require(member.isfile() and not member.issym() and not member.islnk(), "Unsafe tar member")
            require(name in expected and name not in written, "Unexpected or duplicate supporting member")
            payload = archive.extractfile(member).read()
            require(len(payload) == expected[name]["bytes"] and sha(payload) == expected[name]["sha256"],
                    f"Supporting file mismatch: {name}")
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            written.add(name)

    bank_cache = {}
    episode_count = 0
    stage_counts = {}
    with gzip.open(package / "episodes.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            name = str(safe_path(item["path"]))
            require(name in expected and name not in written, "Unexpected or duplicate episode")
            case_id = item["case_id"]
            require(case_id in manifest["banks"], "Unrecognized candidate bank")
            if case_id not in bank_cache:
                bank_path = package / safe_path(manifest["banks"][case_id]["path"])
                with gzip.open(bank_path, "rt", encoding="utf-8") as source:
                    bank_cache[case_id] = json.load(source)
            bank = bank_cache[case_id]
            value = item["body"]
            require(value["data_fingerprint"] == bank["data_fingerprint"], "Episode fingerprint mismatch")
            restore_records(value, bank)
            payload = original_json(value)
            require(len(payload) == expected[name]["bytes"] and sha(payload) == expected[name]["sha256"],
                    f"Restored episode byte hash mismatch: {name}")
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            written.add(name)
            episode_count += 1
            stage = PurePosixPath(name).parts[1]
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

    require(episode_count == manifest["episode_count"], "Restored episode count differs")
    require(stage_counts == manifest["stage_episode_counts"], "Restored stage counts differ")
    require(written == set(expected), "Manifest files are missing after restoration")
    freeze = json.loads((output / "raw/freeze.json").read_text())
    for relative, checksum in freeze["source_file_sha256"].items():
        require(file_sha(output / "source/live-salmon" / safe_path(relative)) == checksum,
                f"Frozen source hash differs: {relative}")
    result = {"restored_files": len(written), "episodes": episode_count, "stage_counts": stage_counts,
              "every_restored_file_sha256_matches": True, "frozen_source_file_sha256_matches": True}
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New output directory outside this package")
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    restore(args.package, args.output)


if __name__ == "__main__":
    main()
