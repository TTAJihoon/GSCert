import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from gscert_review_core import engine


class CorruptDocxTests(SimpleTestCase):
    def _file(self, data):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "깨진.docx"
        path.write_bytes(data)
        return SimpleNamespace(path=str(path), name=path.name, extension=".docx")

    def test_docx_with_broken_central_directory_is_an_inspection_error_not_a_crash(self):
        broken = b"PK\x03\x04" + b"\x00" * 200 + b"PK\x05\x06" + b"\x00\x00\x00\x00\x01\x00\x01\x00\x10\x00\x00\x00\x99\x00\x00\x00\x00\x00"
        file_info = self._file(broken)

        for reader in (engine._docx_root, engine._docx_paragraphs, engine._docx_all_text):
            with self.subTest(reader=reader.__name__):
                with self.assertRaises(engine.DownloadReviewInspectionError):
                    reader(file_info)
