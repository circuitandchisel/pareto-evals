import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import arxivmath_config as config
from scripts import update_arxivmath as updater


def manifest_fixture():
    return {"dataset": "MathArena/arxivmath-0526", "revision": "a" * 40,
            "edition": "2026-05", "split": "train", "rows": 40, "license": "cc-by-sa-4.0"}


class ManifestTests(unittest.TestCase):
    def test_checked_in_manifest_is_valid(self):
        self.assertEqual(config.configuration(), json.loads((config.ROOT / "arxivmath.json").read_text()))


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pin = manifest_fixture()
        self.pin["rows"] = 1
        self.write_pin()
        (self.root / "datasets").mkdir()
        self.artifact = self.root / "datasets" / config.artifact_name(self.pin)
        self.artifact.write_text(json.dumps([{"id": "1", "problem": "Question", "answer": "1"}]))
        self.patcher = patch.object(config, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def write_pin(self):
        (self.root / "arxivmath.json").write_text(json.dumps(self.pin))

    def test_same_edition_new_revision_cannot_load_old_artifact(self):
        self.assertEqual(len(config.load_items()), 1)
        self.pin["revision"] = "b" * 40
        self.write_pin()
        with self.assertRaises(FileNotFoundError):
            config.load_items()
        with self.assertRaises(ValueError):
            config.load_items(self.artifact)
        self.assertTrue(self.artifact.exists())

    def test_legacy_filename_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            config.load_items(self.root / "datasets/arxivmath_0526.json")

    def test_current_revision_and_external_absolute_path_work(self):
        self.assertEqual(config.load_items(), config.load_items(self.artifact))

    def test_invalid_manifest_fails_closed(self):
        for change in ({"revision": "bad"}, {"edition": "2026-06"}, {"rows": True}, {"license": "unknown"}):
            with self.subTest(change=change):
                (self.root / "arxivmath.json").write_text(json.dumps({**self.pin, **change}))
                with self.assertRaises(ValueError):
                    config.configuration()

    def test_bad_prepared_records_fail_closed(self):
        for rows in ([], [{"id": "1", "problem": "", "answer": "1"}], [{"id": 1, "problem": "Q", "answer": "1"}]):
            self.artifact.write_text(json.dumps(rows))
            with self.assertRaises(ValueError):
                config.load_items()


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.current = manifest_fixture()
        self.metadata = {"id": "MathArena/arxivmath-0926", "sha": "a" * 40,
            "private": False, "gated": False, "disabled": False, "cardData": {
                "license": "cc-by-sa-4.0", "dataset_info": {
                    "features": [{"name": name, "dtype": "string"} for name in ("problem_idx", "problem", "answer")],
                    "splits": [{"name": "train", "num_examples": 53}]}}}

    def read(self, url):
        if "cursor=" in url:
            return [{"id": "MathArena/arxivmath-0926"}], ""
        if "?" in url:
            return [{"id": identifier} for identifier in (
                "MathArena/arxivmath-0526", "MathArena/arxivmath-1225", "MathArena/arxivmath-0127",
                "MathArena/arxivmath-training", "MathArena/arxivmath-1026_outputs")], \
                '<https://huggingface.co/api/datasets?cursor=next>; rel="next"'
        return copy.deepcopy(self.metadata), ""

    def test_biweekly_calendar(self):
        self.assertTrue(updater.due(date(2026, 11, 2)))
        self.assertFalse(updater.due(date(2026, 11, 9)))
        self.assertTrue(updater.due(date(2026, 11, 16)))
        self.assertFalse(updater.due(date(2026, 11, 1)))

    def test_pagination_filtering_and_pinned_metadata(self):
        result = updater.candidate(self.current, date(2026, 11, 2), self.read)
        self.assertEqual((result["edition"], result["rows"]), ("2026-09", 53))

    def test_revision_update_and_no_change(self):
        current = updater.candidate(self.current, date(2026, 11, 2), self.read)
        self.assertEqual(updater.candidate(current, date(2026, 11, 2), self.read), current)
        self.metadata["sha"] = "b" * 40
        self.assertNotEqual(updater.candidate(current, date(2026, 11, 2), self.read)["revision"], current["revision"])

    def test_metadata_drift_rejected(self):
        def read(url):
            data, links = self.read(url)
            if "/revision/" in url:
                data["sha"] = "b" * 40
            return data, links
        with self.assertRaises(ValueError):
            updater.candidate(self.current, date(2026, 11, 2), read)

    def test_downgrade_rejected(self):
        with self.assertRaises(ValueError):
            updater.candidate({**self.current, "dataset": "MathArena/arxivmath-1026"}, date(2026, 11, 2), self.read)

    def test_changed_license_and_invalid_counts_rejected(self):
        for count in (0, True, 10001):
            self.metadata["cardData"]["dataset_info"]["splits"][0]["num_examples"] = count
            with self.assertRaises(ValueError):
                updater.validated_metadata(self.metadata["id"], self.metadata)
        self.metadata["cardData"]["license"] = "unknown"
        with self.assertRaises(ValueError):
            updater.validated_metadata(self.metadata["id"], self.metadata)

    def test_pagination_cycle_rejected(self):
        def read(url):
            return [], f'<{url}>; rel="next"'
        with self.assertRaises(ValueError):
            updater.discover(read)
