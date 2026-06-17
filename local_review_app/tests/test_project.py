import tempfile
import unittest
from pathlib import Path

from gscert_local_review.project import infer_project_number
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
            self.assertEqual(scan.total_size_bytes, 5)
            self.assertEqual(
                [file.relative_path for file in scan.files],
                ["TTA-26-00727.zip", "rawdata/result.txt"],
            )


if __name__ == "__main__":
    unittest.main()
