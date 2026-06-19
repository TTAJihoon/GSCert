import tempfile
import unittest
from pathlib import Path

from gscert_local_review.project import infer_project_number
from gscert_local_review.local_runner import FAIL, PASS, UNSUPPORTED, run_cached_rules
from gscert_local_review.rule_cache import load_rule_bundle, load_rule_cache, save_rule_cache
from gscert_local_review.scanner import scan_folder


class LocalReviewProjectTests(unittest.TestCase):
    def test_infer_project_number_from_folder_name(self):
        with tempfile.TemporaryDirectory(prefix="TTA-26-00727 sample ") as temp_dir:
            self.assertEqual(infer_project_number(Path(temp_dir)), "TTA-26-00727")

    def test_scan_folder_counts_nested_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "rawdata"
            nested.mkdir()
            (root / "TTA-26-00727.zip").write_bytes(b"abc")
            (nested / "result.txt").write_text("ok", encoding="utf-8")

            scan = scan_folder(root)

            self.assertEqual(scan.file_count, 2)
            self.assertEqual(scan.directory_count, 1)
            self.assertEqual(scan.total_size_bytes, 5)
            self.assertEqual(
                [file.relative_path for file in scan.files],
                ["TTA-26-00727.zip", "rawdata/result.txt"],
            )

    def test_rule_cache_round_trip(self):
        payload = {
            "success": True,
            "rulebase_version": "20260619090000-abcdef123456",
            "engine_min_version": "0.1.0",
            "checksum": "sha256:abcdef",
            "rule_count": 1,
            "rules": [{"code": "artifact_01", "name": "계약서"}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = save_rule_cache(payload, Path(temp_dir))
            loaded = load_rule_cache(Path(temp_dir))

            self.assertTrue(summary.exists)
            self.assertTrue(loaded.exists)
            self.assertEqual(loaded.rulebase_version, payload["rulebase_version"])
            self.assertEqual(loaded.engine_min_version, "0.1.0")
            self.assertEqual(loaded.rule_count, 1)
            self.assertTrue(loaded.path.exists())
            self.assertEqual(load_rule_bundle(Path(temp_dir))["rulebase_version"], payload["rulebase_version"])

    def test_run_cached_rules_passes_required_file_rule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "TTA-26-00727 계약서.pdf").write_bytes(b"pdf")
            scan = scan_folder(root)
            bundle = {
                "rules": [
                    {
                        "code": "artifact_01",
                        "name": "계약서",
                        "rule_type": "required_artifact_file",
                        "config_json": {
                            "filename_keywords": ["계약서", "{project_number}"],
                            "extensions": [".pdf"],
                            "exact_count": 1,
                        },
                    }
                ]
            }

            summary = run_cached_rules(scan, bundle, "TTA-26-00727")

            self.assertEqual(summary.passed_count, 1)
            self.assertEqual(summary.results[0].status, PASS)

    def test_run_cached_rules_fails_missing_required_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scan = scan_folder(Path(temp_dir))
            bundle = {
                "rules": [
                    {
                        "code": "artifact_01",
                        "name": "계약서",
                        "rule_type": "required_artifact_file",
                        "config_json": {
                            "filename_keywords": ["계약서", "{project_number}"],
                            "extensions": [".pdf"],
                        },
                    }
                ]
            }

            summary = run_cached_rules(scan, bundle, "TTA-26-00727")

            self.assertEqual(summary.failed_count, 1)
            self.assertEqual(summary.results[0].status, FAIL)

    def test_run_cached_rules_marks_document_rule_unsupported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scan = scan_folder(Path(temp_dir))
            bundle = {
                "rules": [
                    {
                        "code": "artifact_02",
                        "name": "합의서",
                        "rule_type": "document_artifact_check",
                        "config_json": {},
                    }
                ]
            }

            summary = run_cached_rules(scan, bundle, "TTA-26-00727")

            self.assertEqual(summary.unsupported_count, 1)
            self.assertEqual(summary.results[0].status, UNSUPPORTED)

    def test_run_cached_rules_accepts_rawdata_zip_presence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "rawdata.zip").write_bytes(b"zip")
            scan = scan_folder(root)
            bundle = {
                "rules": [
                    {
                        "code": "artifact_10",
                        "name": "RawData",
                        "rule_type": "rawdata_folder_structure_check",
                        "config_json": {
                            "folder_checks": [
                                {"keyword": "성능", "failure_message": "성능 rawdata 확인 불가"}
                            ]
                        },
                    }
                ]
            }

            summary = run_cached_rules(scan, bundle, "TTA-26-00727")

            self.assertEqual(summary.passed_count, 1)
            self.assertEqual(summary.results[0].status, PASS)


if __name__ == "__main__":
    unittest.main()
