"""Offline matrix-driver checks; no credentials, model calls, or statistical fits."""

import builtins
from contextlib import redirect_stdout
import hashlib
import io
import itertools
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from experiments.adaptive_analysis.scripts import run_matrix as matrix


class NoCredentialReads(dict):
    def get(self, key, default=None):
        if key == "OPENROUTER_KEY":
            raise AssertionError("Dry-run read credentials")
        # argparse may inspect locale/terminal variables; no real environment is used.
        return super().get(key, default)


real_import = builtins.__import__


def no_execution_imports(name, *args, **kwargs):
    if name in {
        "src.run_ai_scientists", "experiments.adaptive_analysis.analysis",
        "experiments.adaptive_analysis.data", "experiments.adaptive_analysis.evaluate",
    }:
        raise AssertionError("Imported execution-only dependency")
    return real_import(name, *args, **kwargs)


class MatrixTests(unittest.TestCase):
    def test_schedule_matches_original_frozen_216_episode_design(self):
        # Digests were taken from the archived original experiment wrapper.
        expected = [([9010], 2026092201, 36,
                     "947379dd7b35d502ff7b5a65ea7ec2a77ac8937f4ac58df5e3f06acae2ef3926"),
                    (list(range(301, 306)), 2026092202, 180,
                     "39d1ac9f21aff14dad691909274b2a009cc1686e6398edb2a1991c0af22aaaac")]
        for seeds, order, count, digest in expected:
            with self.subTest(seeds=seeds):
                schedule = matrix.jobs(seeds, order)
                self.assertEqual(len(schedule), count)
                self.assertEqual(set(schedule), set(itertools.product(
                    seeds, ["global", "conditional", "null"],
                    ["gpt4.1", "sol_medium", "astra_medium"],
                    ["P0", "P1"], ["fixed", "adaptive"])))
                actual = hashlib.sha256(json.dumps(schedule, separators=(",", ":")).encode()).hexdigest()
                self.assertEqual(actual, digest)

    def test_default_dry_run_does_not_read_credentials_import_execution_or_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "unused"
            stream = io.StringIO()
            with (patch.object(matrix.os, "environ", NoCredentialReads()),
                  patch("builtins.__import__", side_effect=no_execution_imports),
                  patch.object(matrix, "stage") as stage,
                  patch.object(matrix, "freeze_sources") as freeze,
                  patch.object(matrix.run, "run_episode") as episode,
                  redirect_stdout(stream)):
                self.assertEqual(matrix.main(["--output", str(output)]), 0)
            planned = json.loads(stream.getvalue())
            self.assertEqual(planned["mode"], "dry_run")
            self.assertEqual(planned["episode_count"], 216)
            self.assertEqual(planned["development_episode_count"], 36)
            self.assertEqual(planned["formal_episode_count"], 180)
            self.assertEqual(planned["maximum_model_calls"], 1080)
            self.assertEqual(planned["parallel_workers"], 3)
            self.assertEqual(planned["development_seed"], 9010)
            self.assertEqual(planned["seeds"], [301, 302, 303, 304, 305])
            self.assertEqual(planned["prompt_variants"], ["P0", "P1"])
            self.assertEqual(planned["conditions"], ["global", "conditional", "null"])
            self.assertEqual(set(planned["profiles"]), {"gpt4.1", "sol_medium", "astra_medium"})
            for profile, config in planned["profiles"].items():
                self.assertEqual(config["max_completion_tokens"], 8192)
                self.assertEqual(config["max_steps"], 8)
                self.assertEqual(config["temperature"], 0.7 if profile == "gpt4.1" else None)
                self.assertEqual(config["reasoning_effort"], None if profile == "gpt4.1" else "medium")
            self.assertFalse(output.exists())
            stage.assert_not_called()
            freeze.assert_not_called()
            episode.assert_not_called()

    def test_missing_key_stops_before_fits_transport_or_artifact_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "unused"
            stream = io.StringIO()
            with (patch.object(matrix.os, "environ", {}),
                  patch("builtins.__import__", side_effect=no_execution_imports),
                  patch.object(matrix, "stage") as stage,
                  patch.object(matrix, "freeze_sources") as freeze,
                  patch.object(matrix.run, "run_episode") as episode,
                  redirect_stdout(stream)):
                self.assertEqual(matrix.main(["--execute", "--output", str(output)]), 2)
            self.assertIn("OPENROUTER_KEY is required", stream.getvalue())
            self.assertFalse(output.exists())
            stage.assert_not_called()
            freeze.assert_not_called()
            episode.assert_not_called()

    def test_source_archive_contains_exact_hashed_driver_and_experiment_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fingerprint = matrix.run.code_fingerprint()
            driver_hash = matrix.driver_hash()
            with (patch.object(matrix.importlib.metadata, "version", return_value="offline-test"),
                  patch.object(matrix.subprocess, "check_output", return_value="offline-head\n")):
                self.assertTrue(matrix.freeze_sources(base, matrix.plan(base, True),
                                                      fingerprint, driver_hash))
            frozen = json.loads((base / "freeze.json").read_text())
            self.assertEqual(frozen["code_hash"], fingerprint)
            self.assertEqual(frozen["driver_sha256"], driver_hash)
            driver_name = "experiments/adaptive_analysis/scripts/run_matrix.py"
            self.assertEqual(frozen["driver_file"], driver_name)
            self.assertEqual(frozen["source_file_sha256"][driver_name], driver_hash)
            with tarfile.open(base / "source-snapshot.tar.gz") as archive:
                self.assertEqual(set(archive.getnames()), set(frozen["source_file_sha256"]))
                for name, digest in frozen["source_file_sha256"].items():
                    self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(), digest)
            self.assertEqual(len(frozen["development_schedule"]), 36)
            self.assertEqual(len(frozen["formal_schedule"]), 180)

    def test_changed_driver_blocks_worker_before_execution_imports(self):
        job = (301, "global", "gpt4.1", "P0", "fixed")
        with (patch.object(matrix.run, "code_fingerprint", return_value="frozen-code"),
              patch("builtins.__import__", side_effect=no_execution_imports)):
            result = matrix.worker(job, "unused", "frozen-code", "different-driver")
        self.assertEqual(result, {"status": "blocked", "reason": "source_changed", "job": job})

    def test_development_gate_uses_protocol_success_not_accuracy(self):
        for missing_profile in (False, True):
            with self.subTest(missing_profile=missing_profile), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary) / "experiment"
                stages = []

                def fake_stage(output, name, schedule, fingerprint, driver_hash):
                    stages.append(name)
                    if name == "development":
                        (output / name).mkdir()
                        for index, profile in enumerate(matrix.PROFILES):
                            record = {"config": {"profile": profile},
                                      "status": "failed" if missing_profile and index == 0 else "success",
                                      "metrics": {"mechanism_correct": False}}
                            (output / name / f"{index}.json").write_text(json.dumps(record))
                    return True

                with (patch.object(matrix.os, "environ", {"OPENROUTER_KEY": "offline-placeholder"}),
                      patch("builtins.__import__", side_effect=no_execution_imports),
                      patch.object(matrix, "freeze_sources", return_value=True),
                      patch.object(matrix, "stage", side_effect=fake_stage),
                      redirect_stdout(io.StringIO())):
                    result = matrix.main(["--execute", "--output", str(base)])
                self.assertEqual(result, 1 if missing_profile else 0)
                self.assertEqual(stages, ["development"] if missing_profile else ["development", "formal"])


if __name__ == "__main__":
    unittest.main()
