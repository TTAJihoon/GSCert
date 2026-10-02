"""산출물 폴더 탐색(ecm_folder_browser / ecm_folder_browser_api) 테스트. ECM 없이 가짜 폴더 트리와 실제 zip 구조로 검증한다."""

import io
import json
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from unittest import mock

from django.core import signing
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from main.test_kolas import _StreamResponse, _build_zip, _stream_zip
from main.views.review import ecm_folder_browser as fb
from main.views.review import ecm_zip_cache as zc
from main.views.review.ecm_folder_browser_api import browse, browse_download

PROJECT = "GS-C-25-0091"
OTHER_PROJECT = "GS-C-25-0092"


def _file(name, data):
    return {"fileName": name, "fileOID": f"oid-{name}", "storageFileID": f"sid-{name}", "fileSize": len(data)}


INNER_ZIP = _build_zip([("x/y.txt", b"inner y"), ("z.txt", b"inner z")])
ZIP_ENTRIES = [
    ("docs/a.txt", b"alpha"),
    ("docs/sub/b.txt", b"bravo"),
    ("img/c.png", b"\x89PNG fake"),
    ("empty/", b""),
    ("inner.zip", INNER_ZIP),
    ("__MACOSX/._a.txt", b"junk"),
    ("docs/._b.txt", b"junk"),
]
BIG_ZIP = _build_zip(ZIP_ENTRIES, compression=zipfile.ZIP_DEFLATED)
REPORT_DOCX = b"PK\x03\x04 report docx"
REPORT_PDF = b"%PDF-1.7 report"


class FakeBrowserEcm:
    """ECM 흉내: 폴더 트리, 파일 내용(blob), 열린 스트림 기록."""

    def __init__(self):
        self.blobs = {}
        self.tree = {}
        self.streams = []
        self.logins = 0

        def add_file(oid, name, data):
            meta = _file(name, data)
            self.blobs[meta["storageFileID"]] = data
            self.tree.setdefault(oid, {"folders": [], "files": []})["files"].append(meta)

        self.add_file = add_file
        self.tree["R"] = {"folders": [("4.시험", "T"), ("1.신청", "A")], "files": []}
        self.tree["T"] = {"folders": [("라.종료", "E"), ("가.계획", "P")], "files": []}
        self.tree["E"] = {"folders": [], "files": []}
        self.tree["A"] = {"folders": [], "files": []}
        self.tree["P"] = {"folders": [], "files": []}
        add_file("E", f"{PROJECT} 시험성적서.docx", REPORT_DOCX)
        add_file("E", f"{PROJECT} 시험성적서.pdf", REPORT_PDF)
        add_file("A", "신청서.pdf", b"%PDF application")
        add_file("R", "계약서.pdf", b"%PDF contract")
        add_file("R", "rawdata.zip", BIG_ZIP)
        add_file("R", "10번 메모.txt", b"memo ten")
        add_file("R", "2번 메모.txt", b"memo two")

    def login(self):
        self.logins += 1

    def find_full_project_folder(self, test_no, cert_date="", center_code=""):
        return {"oid": "R", "name": f"{test_no} 회사"} if test_no == PROJECT else None

    def folder_contents(self, oid):
        node = self.tree[oid]
        return {"folders": [{"name": n, "oid": o} for n, o in node["folders"]], "files": list(node["files"])}

    def walk_files(self, oid, _rel=None):
        rel = list(_rel or [])
        contents = self.folder_contents(oid)
        for meta in contents["files"]:
            yield rel, meta
        for folder in contents["folders"]:
            yield from self.walk_files(folder["oid"], rel + [folder["name"]])

    def blob_stream(self, meta):
        self.streams.append(meta["fileName"])
        return _StreamResponse(self.blobs[meta["storageFileID"]])


class BrowserTestCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        fb.reset_clients()
        # zip 임시 보관은 테스트마다 임시 폴더를 쓰고, 받기 작업은 호출 스레드에서 바로 실행한다(실제 서버 폴더를 건드리지 않음).
        # 점검 보관본(실제 공유 폴더)을 읽지 않도록 비워 둔다. 보관본 테스트는 임시 폴더로 따로 지정한다.
        archive_off = override_settings(AGENT_ARCHIVE_BASE_DIR="")
        archive_off.enable()
        self.addCleanup(archive_off.disable)
        self._cache_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cache_tmp.cleanup)
        self.cache_dir = Path(self._cache_tmp.name) / "zip_cache"
        override = override_settings(FOLDER_BROWSER_ZIP_CACHE_DIR=str(self.cache_dir))
        override.enable()
        self.addCleanup(override.disable)
        zc.zip_cache.reset()
        self.addCleanup(zc.zip_cache.reset)
        inline = mock.patch.object(zc, "RUN_INLINE", True)
        inline.start()
        self.addCleanup(inline.stop)
        self.ecm = FakeBrowserEcm()
        patcher = mock.patch.object(fb, "client_factory", lambda center: self.ecm)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(fb.reset_clients)
        self.addCleanup(cache.clear)

    def cached_files(self):
        return sorted(path.name for path in self.cache_dir.iterdir()) if self.cache_dir.exists() else []

    def root(self):
        return fb.list_location(PROJECT, center_hint="yeongnam", cert_date="2026-01-19")

    @staticmethod
    def by_name(listing):
        return {item["name"]: item for item in listing["items"]}

    def open_item(self, item):
        return fb.list_location(PROJECT, item["ref"])

    def download(self, ref):
        single = fb.describe_single_download(PROJECT, ref)
        self.assertIsNotNone(single)
        name, chunks = single
        return name, b"".join(chunks)

    @staticmethod
    def zip_of(chunks):
        return zipfile.ZipFile(io.BytesIO(b"".join(chunks)))


class ListingTests(BrowserTestCase):
    def test_root_lists_folders_first_then_files_in_natural_order_with_types(self):
        listing = self.root()

        self.assertEqual(listing["location"]["label"], f"{PROJECT} 회사")
        self.assertEqual(
            [(item["type"], item["name"]) for item in listing["items"]],
            [("folder", "1.신청"), ("folder", "4.시험"), ("file", "2번 메모.txt"), ("file", "10번 메모.txt"),
             ("zip", "rawdata.zip"), ("file", "계약서.pdf")],
        )

    def test_files_and_zip_carry_size_and_zip_has_separate_download_ref(self):
        items = self.by_name(self.root())

        self.assertEqual(items["계약서.pdf"]["size"], len(b"%PDF contract"))
        zip_item = items["rawdata.zip"]
        self.assertNotEqual(zip_item["ref"], zip_item["download_ref"])
        self.assertEqual(self.download(zip_item["download_ref"]), ("rawdata.zip", BIG_ZIP))
        self.assertNotIn("download_ref", items["계약서.pdf"])

    def test_opening_ecm_subfolders(self):
        t = self.open_item(self.by_name(self.root())["4.시험"])
        self.assertEqual([i["name"] for i in t["items"]], ["가.계획", "라.종료"])

        e = self.open_item(self.by_name(t)["라.종료"])
        self.assertEqual([i["name"] for i in e["items"]], [f"{PROJECT} 시험성적서.docx", f"{PROJECT} 시험성적서.pdf"])

    def test_missing_project_folder_is_404(self):
        with self.assertRaises(fb.BrowseError) as ctx:
            fb.list_location("GS-C-25-9999", center_hint="sangam")
        self.assertEqual(ctx.exception.status, 404)

    def test_clients_are_reused_between_requests(self):
        self.root()
        self.root()
        self.assertEqual(self.ecm.logins, 1)


class ZipListingTests(BrowserTestCase):
    def zip_item(self):
        return self.by_name(self.root())["rawdata.zip"]

    def test_zip_root_shows_folders_and_files_without_junk(self):
        listing = self.open_item(self.zip_item())

        self.assertEqual(
            [(i["type"], i["name"]) for i in listing["items"]],
            [("zipdir", "docs"), ("zipdir", "empty"), ("zipdir", "img"), ("zip", "inner.zip")],
        )
        self.assertFalse(any("MACOSX" in i["name"] or i["name"].startswith("._") for i in listing["items"]))

    def test_navigating_into_zip_folders(self):
        root = self.open_item(self.zip_item())
        docs = self.open_item(self.by_name(root)["docs"])

        self.assertEqual([(i["type"], i["name"]) for i in docs["items"]], [("zipdir", "sub"), ("zipfile", "a.txt")])
        self.assertFalse(any(i["name"] == "._b.txt" for i in docs["items"]))
        sub = self.open_item(self.by_name(docs)["sub"])
        self.assertEqual([i["name"] for i in sub["items"]], ["b.txt"])

    def test_zip_is_streamed_only_once_for_listing_and_navigation(self):
        root = self.open_item(self.zip_item())
        self.open_item(self.by_name(root)["docs"])
        self.open_item(self.by_name(root)["img"])
        self.open_item(self.zip_item())

        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 1)

    def test_file_sizes_in_zip_are_known(self):
        docs = self.open_item(self.by_name(self.open_item(self.zip_item()))["docs"])

        self.assertEqual(self.by_name(docs)["a.txt"]["size"], len(b"alpha"))

    def test_nested_zip_is_opened_through_the_outer_zip(self):
        inner = self.by_name(self.open_item(self.zip_item()))["inner.zip"]
        self.assertEqual(inner["type"], "zip")

        listing = self.open_item(inner)

        self.assertEqual([(i["type"], i["name"]) for i in listing["items"]], [("zipdir", "x"), ("zipfile", "z.txt")])
        x = self.open_item(self.by_name(listing)["x"])
        self.assertEqual([i["name"] for i in x["items"]], ["y.txt"])

    def test_nested_zip_depth_is_limited(self):
        level3 = _build_zip([("level4.zip", _build_zip([("deep.txt", b"deep")])), ("three.txt", b"three")])
        level2 = _build_zip([("level3.zip", level3)])
        level1 = _build_zip([("level2.zip", level2)])
        self.ecm.add_file("R", "deep.zip", level1)

        zip_item = self.by_name(self.root())["deep.zip"]          # 1단계: ECM 의 zip
        l1 = self.open_item(zip_item)
        l2 = self.open_item(self.by_name(l1)["level2.zip"])        # 2단계
        l3_item = self.by_name(l2)["level3.zip"]                   # 3단계
        self.assertEqual(l3_item["type"], "zip")
        l3 = self.open_item(l3_item)
        l4 = self.by_name(l3)["level4.zip"]

        self.assertEqual(l4["type"], "zipfile")  # 3단계를 넘는 zip 은 더 열지 않고 파일로만 보여준다
        self.assertEqual(self.download(self.by_name(l3)["three.txt"]["ref"]), ("three.txt", b"three"))

    def test_zip_over_transfer_limit_is_rejected(self):
        with override_settings(FOLDER_BROWSER_ZIP_MAX_MB=0):
            with self.assertRaises(fb.BrowseError) as ctx:
                self.open_item(self.zip_item())
        self.assertEqual(ctx.exception.status, 413)

    def test_streaming_unsupported_zip_falls_back_to_temp_file_for_listing_and_download(self):
        unsupported = _stream_zip([("only/file.txt", b"stored data")], compression=zipfile.ZIP_STORED)
        self.ecm.add_file("R", "stored.zip", unsupported)

        item = self.by_name(self.root())["stored.zip"]
        listing = self.open_item(item)
        only = self.open_item(self.by_name(listing)["only"])
        name, data = self.download(self.by_name(only)["file.txt"]["ref"])

        self.assertEqual((name, data), ("file.txt", b"stored data"))

    def test_cp949_names_without_utf8_flag_are_shown_correctly(self):
        real = "한글폴더/시험성적서.docx"
        placeholder = "X" * len(real.encode("cp949"))
        raw = _build_zip([(placeholder, b"PK docx")]).replace(placeholder.encode(), real.encode("cp949"))
        self.ecm.add_file("R", "korean.zip", raw)

        listing = self.open_item(self.by_name(self.root())["korean.zip"])
        folder = self.open_item(self.by_name(listing)["한글폴더"])

        self.assertEqual([i["name"] for i in folder["items"]], ["시험성적서.docx"])

    def test_backslash_paths_are_treated_as_folders(self):
        legacy = _build_zip([("a\\b\\c.txt", b"legacy")])
        self.ecm.add_file("R", "legacy.zip", legacy)

        listing = self.open_item(self.by_name(self.root())["legacy.zip"])
        a = self.open_item(self.by_name(listing)["a"])
        b = self.open_item(self.by_name(a)["b"])
        self.assertEqual(self.download(self.by_name(b)["c.txt"]["ref"]), ("c.txt", b"legacy"))

    def test_encrypted_entries_are_shown_but_not_selectable(self):
        data = bytearray(_build_zip([("secret.txt", b"classified")], compression=zipfile.ZIP_STORED))
        data[6] |= 0x1  # 로컬 헤더의 암호화 비트
        index = bytes(data).index(b"PK\x01\x02")
        data[index + 8] |= 0x1  # 중앙 디렉터리 쪽도 맞춰 둔다
        self.ecm.add_file("R", "locked.zip", bytes(data))

        listing = self.open_item(self.by_name(self.root())["locked.zip"])
        secret = self.by_name(listing)["secret.txt"]

        self.assertTrue(secret["encrypted"])
        self.assertFalse(secret["selectable"])
        self.assertFalse(secret["downloadable"])


class SingleDownloadTests(BrowserTestCase):
    def test_ecm_file_is_relayed_with_its_name(self):
        item = self.by_name(self.root())["계약서.pdf"]

        self.assertEqual(self.download(item["ref"]), ("계약서.pdf", b"%PDF contract"))

    def test_zip_entry_is_extracted_from_the_zip_without_other_entries(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        docs = self.open_item(self.by_name(self.open_item(zip_item))["docs"])

        name, data = self.download(self.by_name(docs)["a.txt"]["ref"])

        self.assertEqual((name, data), ("a.txt", b"alpha"))

    def test_entry_inside_nested_zip(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        inner = self.open_item(self.by_name(self.open_item(zip_item))["inner.zip"])

        name, data = self.download(self.by_name(inner)["z.txt"]["ref"])

        self.assertEqual((name, data), ("z.txt", b"inner z"))

    def test_nested_zip_can_be_downloaded_as_a_file(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        inner_item = self.by_name(self.open_item(zip_item))["inner.zip"]

        name, data = self.download(inner_item["download_ref"])

        self.assertEqual((name, data), ("inner.zip", INNER_ZIP))

    def test_folder_and_zip_open_refs_are_not_single_downloads(self):
        root = self.by_name(self.root())
        self.assertIsNone(fb.describe_single_download(PROJECT, root["4.시험"]["ref"]))
        self.assertIsNone(fb.describe_single_download(PROJECT, root["rawdata.zip"]["ref"]))

    def test_missing_entry_is_reported(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        docs = self.open_item(self.by_name(self.open_item(zip_item))["docs"])
        ref = self.by_name(docs)["a.txt"]["ref"]
        payload = signing.loads(ref, salt=fb.TOKEN_SALT)
        payload["name"] = "docs/not-there.txt"

        with self.assertRaises(fb.BrowseError) as ctx:
            self.download(fb.make_ref(payload))
        self.assertEqual(ctx.exception.status, 404)


class SelectionZipTests(BrowserTestCase):
    def names(self, refs):
        zf = self.zip_of(fb.iter_selection_zip(PROJECT, refs))
        self.assertIsNone(zf.testzip())
        return zf, sorted(zf.namelist())

    def test_ecm_folder_is_zipped_with_its_structure(self):
        folder = self.by_name(self.root())["4.시험"]

        zf, names = self.names([folder["ref"]])

        self.assertEqual(names, [f"4.시험/라.종료/{PROJECT} 시험성적서.docx", f"4.시험/라.종료/{PROJECT} 시험성적서.pdf"])
        self.assertEqual(zf.read(names[0]), REPORT_DOCX)

    def test_multiple_files_and_a_folder_in_one_zip(self):
        root = self.by_name(self.root())

        zf, names = self.names([root["계약서.pdf"]["ref"], root["1.신청"]["ref"], root["2번 메모.txt"]["ref"]])

        self.assertEqual(names, ["1.신청/신청서.pdf", "2번 메모.txt", "계약서.pdf"])

    def test_zip_folder_download_keeps_inner_structure_under_the_folder_name(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        docs = self.by_name(self.open_item(zip_item))["docs"]

        zf, names = self.names([docs["ref"]])

        self.assertEqual(names, ["docs/a.txt", "docs/sub/b.txt"])  # ._b.txt 같은 잡파일은 제외
        self.assertEqual(zf.read("docs/sub/b.txt"), b"bravo")

    def test_whole_zip_contents_are_zipped_under_the_zip_name(self):
        location = self.open_item(self.by_name(self.root())["rawdata.zip"])

        zf, names = self.names([location["location"]["ref"]])

        self.assertIn("rawdata/docs/a.txt", names)
        self.assertIn("rawdata/inner.zip", names)
        self.assertFalse(any("MACOSX" in name for name in names))

    def test_selected_entries_from_the_same_zip_are_read_in_one_pass(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        root = self.by_name(self.open_item(zip_item))
        docs = self.by_name(self.open_item(root["docs"]))
        img = self.by_name(self.open_item(root["img"]))
        before = self.ecm.streams.count("rawdata.zip")

        zf, names = self.names([docs["a.txt"]["ref"], img["c.png"]["ref"], root["inner.zip"]["download_ref"]])

        self.assertEqual(names, ["a.txt", "c.png", "inner.zip"])
        self.assertEqual(self.ecm.streams.count("rawdata.zip") - before, 0)  # 목록을 만들 때 받은 서버 사본에서 꺼낸다
        self.assertEqual(zf.read("inner.zip"), INNER_ZIP)

    def test_zip_download_ref_selects_the_raw_zip_file_not_its_contents(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]

        zf, names = self.names([zip_item["download_ref"]])

        self.assertEqual(names, ["rawdata.zip"])
        self.assertEqual(zf.read("rawdata.zip"), BIG_ZIP)

    def test_nested_zip_contents_can_be_selected(self):
        zip_item = self.by_name(self.root())["rawdata.zip"]
        inner = self.open_item(self.by_name(self.open_item(zip_item))["inner.zip"])

        zf, names = self.names([inner["location"]["ref"]])

        self.assertEqual(names, ["inner/x/y.txt", "inner/z.txt"])
        self.assertEqual(zf.read("inner/x/y.txt"), b"inner y")

    def test_duplicate_names_get_suffixes(self):
        root = self.by_name(self.root())
        folder_a = self.by_name(self.open_item(root["1.신청"]))["신청서.pdf"]

        zf, names = self.names([root["1.신청"]["ref"], folder_a["ref"], folder_a["ref"]])

        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3)

    def test_failure_of_one_item_is_reported_and_others_still_download(self):
        root = self.by_name(self.root())
        payload = signing.loads(root["계약서.pdf"]["ref"], salt=fb.TOKEN_SALT)
        payload["meta"]["s"] = "sid-does-not-exist"

        zf, names = self.names([fb.make_ref(payload), root["2번 메모.txt"]["ref"]])

        self.assertEqual(names, sorted(["_다운로드_오류.txt", "2번 메모.txt"]))  # 실패한 항목은 빈 파일로도 남지 않는다
        self.assertIn("계약서.pdf", zf.read("_다운로드_오류.txt").decode("utf-8-sig"))

    def test_selection_limit(self):
        root = self.by_name(self.root())
        with override_settings(FOLDER_BROWSER_MAX_SELECTION=2):
            with self.assertRaises(fb.BrowseError):
                list(fb.iter_selection_zip(PROJECT, [root["계약서.pdf"]["ref"]] * 3))

    def test_empty_selection(self):
        with self.assertRaises(fb.BrowseError):
            list(fb.iter_selection_zip(PROJECT, []))

    def test_unsupported_zip_selection_falls_back_to_temp_file(self):
        self.ecm.add_file("R", "stored.zip", _stream_zip([("only/file.txt", b"stored data")], compression=zipfile.ZIP_STORED))
        zip_item = self.by_name(self.root())["stored.zip"]
        location = self.open_item(zip_item)

        zf, names = self.names([location["location"]["ref"]])

        self.assertEqual(names, ["stored/only/file.txt"], zf.read("_다운로드_오류.txt").decode("utf-8-sig") if "_다운로드_오류.txt" in names else "")
        self.assertEqual(zf.read("stored/only/file.txt"), b"stored data")


class TokenSecurityTests(BrowserTestCase):
    def test_tampered_token_is_rejected(self):
        ref = self.by_name(self.root())["4.시험"]["ref"]
        tampered = ref[:-3] + ("abc" if not ref.endswith("abc") else "xyz")

        with self.assertRaises(fb.BrowseError):
            fb.list_location(PROJECT, tampered)

    def test_token_for_another_project_is_rejected(self):
        ref = self.by_name(self.root())["4.시험"]["ref"]

        with self.assertRaises(fb.BrowseError) as ctx:
            fb.list_location(OTHER_PROJECT, ref)
        self.assertIn("다른 프로젝트", ctx.exception.message)

    def test_forged_token_without_signature_is_rejected(self):
        forged = signing.b64_encode(json.dumps({"k": "folder", "c": "sangam", "p": PROJECT, "oid": "ROOT_OF_EVERYTHING"}).encode()).decode()

        with self.assertRaises(fb.BrowseError):
            fb.list_location(PROJECT, forged)

    def test_token_signed_with_another_salt_is_rejected(self):
        forged = signing.dumps({"k": "folder", "c": "sangam", "p": PROJECT, "oid": "X"}, salt="other-salt")

        with self.assertRaises(fb.BrowseError):
            fb.list_location(PROJECT, forged)

    def test_expired_token_is_rejected(self):
        ref = self.by_name(self.root())["4.시험"]["ref"]
        with mock.patch.object(fb, "TOKEN_MAX_AGE_SECONDS", -1):
            with self.assertRaises(fb.BrowseError) as ctx:
                fb.list_location(PROJECT, ref)
        self.assertIn("만료", ctx.exception.message)

    def test_file_token_cannot_be_opened_as_a_folder(self):
        ref = self.by_name(self.root())["계약서.pdf"]["ref"]

        with self.assertRaises(fb.BrowseError):
            fb.list_location(PROJECT, ref)


class ApiViewTests(BrowserTestCase):
    factory = RequestFactory()

    def get_json(self, path_project=PROJECT, **params):
        response = browse(self.factory.get(f"/api/projects/{path_project}/browse/", params), path_project)
        return response.status_code, json.loads(response.content)

    def test_browse_returns_success_json(self):
        status, payload = self.get_json(center="yeongnam", cert_date="2026-01-19")

        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["items"][0]["name"], "1.신청")
        self.assertEqual(payload["location"]["kind"], "folder")

    def test_browse_follows_ref(self):
        _status, root = self.get_json()
        folder = next(item for item in root["items"] if item["name"] == "4.시험")

        status, child = self.get_json(ref=folder["ref"])

        self.assertEqual(status, 200)
        self.assertEqual([i["name"] for i in child["items"]], ["가.계획", "라.종료"])

    def test_browse_errors_are_json_with_status(self):
        status, payload = self.get_json(path_project="GS-C-25-9999")
        self.assertEqual((status, payload["success"]), (404, False))

        status, payload = self.get_json(ref="garbage")
        self.assertEqual((status, payload["success"]), (400, False))

        status, payload = self.get_json(path_project="bad number")
        self.assertEqual(status, 400)

    def _download(self, method="get", refs=(), project=PROJECT):
        if method == "get":
            request = self.factory.get(f"/api/projects/{project}/browse/download/", {"ref": refs[0]} if refs else {})
        else:
            request = self.factory.post(f"/api/projects/{project}/browse/download/", {"ref": list(refs)})
            request._dont_enforce_csrf_checks = True
        return browse_download(request, project)

    def test_get_download_streams_a_single_file_as_attachment(self):
        item = self.by_name(self.get_json()[1])["계약서.pdf"]

        response = self._download("get", [item["ref"]])

        self.assertEqual(b"".join(response.streaming_content), b"%PDF contract")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(
            "filename*=UTF-8''%EA%B3%84%EC%95%BD%EC%84%9C.pdf",
            response["Content-Disposition"],
        )
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_get_download_of_a_folder_returns_a_zip(self):
        folder = self.by_name(self.get_json()[1])["1.신청"]

        response = self._download("get", [folder["ref"]])

        zf = self.zip_of(response.streaming_content)
        self.assertEqual(zf.namelist(), ["1.신청/신청서.pdf"])
        self.assertEqual(response["Content-Type"], "application/zip")

    def test_post_with_several_refs_returns_a_zip(self):
        items = self.by_name(self.get_json()[1])

        response = self._download("post", [items["계약서.pdf"]["ref"], items["2번 메모.txt"]["ref"]])

        self.assertEqual(sorted(self.zip_of(response.streaming_content).namelist()), ["2번 메모.txt", "계약서.pdf"])

    def test_post_with_one_file_ref_is_downloaded_as_the_file_itself(self):
        items = self.by_name(self.get_json()[1])

        response = self._download("post", [items["2번 메모.txt"]["ref"]])

        self.assertEqual(b"".join(response.streaming_content), b"memo two")

    def test_download_errors_come_back_as_a_text_attachment(self):
        for response in (self._download("get", ["garbage"]), self._download("post", []), self._download("get", [], project="bad number")):
            text = b"".join(response.streaming_content).decode("utf-8-sig")
            self.assertIn("다운로드 오류", text)
            self.assertIn("attachment", response["Content-Disposition"])

    def test_ecm_open_failure_before_the_first_byte_is_reported_instead_of_a_broken_download(self):
        item = self.by_name(self.get_json()[1])["계약서.pdf"]
        self.ecm.blob_stream = mock.Mock(side_effect=RuntimeError("ECM down"))

        response = self._download("get", [item["ref"]])

        self.assertIn("ECM down", b"".join(response.streaming_content).decode("utf-8-sig"))


# ---------------------------------------------------------------------------
# zip 임시 보관(받으면서 목록 + 사본), 미리 받기, 받는 중인 사본에서 꺼내기
# ---------------------------------------------------------------------------
import os as _os


class GatedResponse(_StreamResponse):
    """gate 가 열릴 때까지 gate_after 바이트에서 멈추는 ECM 응답(받는 중인 상태를 만든다)."""

    def __init__(self, data, gate_after, gate, step=4096):
        super().__init__(data)
        self.gate_after = gate_after
        self.gate = gate
        self.step = step
        self.reached = threading.Event()

    def iter_content(self, chunk_size=1024 * 1024):
        sent = 0
        for index in range(0, len(self._data), self.step):
            if sent >= self.gate_after and not self.gate.is_set():
                self.reached.set()
                self.gate.wait(15)
            piece = self._data[index:index + self.step]
            sent += len(piece)
            yield piece


def _random_zip(*names, size=200_000):
    return _build_zip([(name, _os.urandom(size)) for name in names], compression=zipfile.ZIP_STORED)


class SpoolBase(BrowserTestCase):
    def zip_item(self, name="rawdata.zip"):
        return self.by_name(self.root())[name]

    def zip_payload(self, item):
        return signing.loads(item["ref"], salt=fb.TOKEN_SALT)

    def wait_until(self, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False


class ListingCreatesLocalCopyTests(SpoolBase):
    def test_listing_a_zip_saves_a_server_copy_with_one_transfer(self):
        self.open_item(self.zip_item())

        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 1)
        files = self.cached_files()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith(".zip"))
        self.assertEqual((self.cache_dir / files[0]).read_bytes(), BIG_ZIP)

    def test_later_downloads_and_navigation_do_not_touch_ecm(self):
        root = self.by_name(self.open_item(self.zip_item()))
        docs = self.by_name(self.open_item(root["docs"]))
        streams_after_listing = len(self.ecm.streams)

        name, data = self.download(docs["a.txt"]["ref"])
        zf, names = SelectionZipTests.names(self, [docs["a.txt"]["ref"], root["inner.zip"]["download_ref"]])

        self.assertEqual((name, data), ("a.txt", b"alpha"))
        self.assertEqual(names, ["a.txt", "inner.zip"])
        self.assertEqual(len(self.ecm.streams), streams_after_listing)

    def test_nested_zip_is_read_from_the_server_copy(self):
        root = self.by_name(self.open_item(self.zip_item()))
        streams_after_listing = len(self.ecm.streams)

        inner = self.open_item(root["inner.zip"])
        name, data = self.download(self.by_name(inner)["z.txt"]["ref"])

        self.assertEqual((name, data), ("z.txt", b"inner z"))
        self.assertEqual(len(self.ecm.streams), streams_after_listing)

    def test_a_second_listing_after_the_list_cache_expires_still_uses_the_copy(self):
        item = self.zip_item()
        self.open_item(item)
        cache.clear()

        self.open_item(item)

        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 1)

    def test_progress_reports_complete_after_listing(self):
        item = self.zip_item()
        self.assertEqual(fb.zip_progress(PROJECT, item["ref"])["state"], "none")

        self.open_item(item)

        progress = fb.zip_progress(PROJECT, item["ref"])
        self.assertEqual((progress["state"], progress["percent"]), ("complete", 100))
        self.assertEqual(progress["written"], progress["total"])

    def test_progress_ignores_non_zip_and_nested_refs(self):
        folder = self.by_name(self.root())["4.시험"]
        self.assertEqual(fb.zip_progress(PROJECT, folder["ref"])["state"], "none")
        inner = self.by_name(self.open_item(self.zip_item()))["inner.zip"]
        self.assertEqual(fb.zip_progress(PROJECT, inner["ref"])["state"], "none")

    def test_disabled_cache_behaves_like_before_and_writes_nothing(self):
        with override_settings(FOLDER_BROWSER_ZIP_CACHE=False):
            root = self.by_name(self.open_item(self.zip_item()))
            docs = self.by_name(self.open_item(root["docs"]))
            self.download(docs["a.txt"]["ref"])

        self.assertEqual(self.cached_files(), [])
        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 2)  # 목록 1회 + 파일 1회


class SpoolRecoveryTests(SpoolBase):
    def test_copy_deleted_from_disk_is_downloaded_again_transparently(self):
        root = self.by_name(self.open_item(self.zip_item()))
        docs = self.by_name(self.open_item(root["docs"]))
        for path in self.cache_dir.iterdir():  # 매일 01시 초기화처럼 폴더를 비운다
            path.unlink()

        name, data = self.download(docs["a.txt"]["ref"])

        self.assertEqual((name, data), ("a.txt", b"alpha"))
        self.assertEqual(len(self.cached_files()), 1)  # 다음 요청을 위해 사본을 다시 만들어 둔다

    def test_truncated_copy_is_rejected_and_rebuilt(self):
        item = self.zip_item()
        self.open_item(item)
        copy = next(self.cache_dir.iterdir())
        copy.write_bytes(copy.read_bytes()[:100])
        cache.clear()

        listing = self.open_item(item)

        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 2)
        self.assertEqual((self.cache_dir / copy.name).read_bytes(), BIG_ZIP)
        self.assertIn("docs", [i["name"] for i in listing["items"]])

    def test_copy_left_from_before_a_restart_is_adopted_without_ecm(self):
        item = self.zip_item()
        self.open_item(item)
        zc.zip_cache.reset()  # 서버 재시작: 등록 정보는 사라지고 파일만 남는다
        cache.clear()

        listing = self.open_item(item)

        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 1)
        self.assertIn("inner.zip", [i["name"] for i in listing["items"]])

    def test_a_different_file_version_is_never_served_from_an_old_copy(self):
        self.open_item(self.zip_item())
        # ECM 에서 같은 이름의 파일이 새 버전(다른 ID·크기)으로 바뀐 상황
        newer = _build_zip([("new/only.txt", b"new version")])
        self.ecm.tree["R"]["files"] = [m for m in self.ecm.tree["R"]["files"] if m["fileName"] != "rawdata.zip"]
        self.ecm.add_file("R", "rawdata.zip", newer)
        cache.clear()

        listing = self.open_item(self.zip_item())

        self.assertEqual([i["name"] for i in listing["items"]], ["new"])

    def test_failed_download_is_reported_and_can_be_retried(self):
        real = self.ecm.blob_stream
        self.ecm.blob_stream = mock.Mock(side_effect=RuntimeError("ECM down"))
        item = self.zip_item()

        with self.assertRaises(fb.BrowseError):
            self.open_item(item)
        self.assertEqual(self.cached_files(), [])

        self.ecm.blob_stream = real
        listing = self.open_item(item)
        self.assertIn("docs", [i["name"] for i in listing["items"]])

    def test_truncated_transfer_is_not_kept_as_a_copy(self):
        class Short(_StreamResponse):
            def iter_content(self, chunk_size=0):
                yield self._data[: len(self._data) // 2]

        real = self.ecm.blob_stream
        self.ecm.blob_stream = lambda meta: Short(self.ecm.blobs[meta["storageFileID"]])
        with self.assertRaises(fb.BrowseError):
            self.open_item(self.zip_item())
        self.assertEqual(self.cached_files(), [])
        self.ecm.blob_stream = real

    def test_stored_with_descriptor_zip_is_saved_and_listed_from_the_finished_copy(self):
        unsupported = _stream_zip([("only/file.txt", b"stored data")], compression=zipfile.ZIP_STORED)
        self.ecm.add_file("R", "stored.zip", unsupported)

        listing = self.open_item(self.by_name(self.root())["stored.zip"])
        only = self.open_item(self.by_name(listing)["only"])

        self.assertEqual(self.download(self.by_name(only)["file.txt"]["ref"]), ("file.txt", b"stored data"))
        self.assertEqual(self.ecm.streams.count("stored.zip"), 1)


class SpoolLimitsTests(SpoolBase):
    def test_oldest_copy_is_evicted_when_the_size_limit_is_reached(self):
        self.ecm.add_file("R", "a.zip", _random_zip("a.bin"))
        self.ecm.add_file("R", "b.zip", _random_zip("b.bin"))
        limit_gb = 300_000 / 1024 ** 3  # 약 300KB: zip 두 개(각 약 200KB)는 함께 못 둔다

        with override_settings(FOLDER_BROWSER_ZIP_CACHE_MAX_GB=limit_gb):
            self.open_item(self.by_name(self.root())["a.zip"])
            first = self.cached_files()
            self.open_item(self.by_name(self.root())["b.zip"])

        self.assertEqual(len(first), 1)
        remaining = self.cached_files()
        self.assertEqual(len(remaining), 1)
        self.assertNotEqual(remaining, first)  # a 는 지워지고 b 만 남았다

    def test_zip_bigger_than_the_whole_limit_is_not_stored_but_still_opens(self):
        with override_settings(FOLDER_BROWSER_ZIP_CACHE_MAX_GB=100 / 1024 ** 3):
            listing = self.open_item(self.zip_item())

        self.assertIn("docs", [i["name"] for i in listing["items"]])
        self.assertEqual(self.cached_files(), [])

    def test_copy_in_use_is_not_evicted(self):
        self.ecm.add_file("R", "a.zip", _random_zip("a.bin"))
        self.ecm.add_file("R", "b.zip", _random_zip("b.bin"))
        limit_gb = 300_000 / 1024 ** 3
        with override_settings(FOLDER_BROWSER_ZIP_CACHE_MAX_GB=limit_gb):
            item_a = self.by_name(self.root())["a.zip"]
            self.open_item(item_a)
            job = zc.zip_cache.lookup("yeongnam", _file_meta(self.ecm, "a.zip"))
            with job.reading():
                self.open_item(self.by_name(self.root())["b.zip"])  # 공간이 없어도 a 는 읽는 중이라 지우지 못한다

        self.assertTrue(job.final_path.exists())

    def at(self, hour, minute, second=0):
        """오늘 날짜의 지정 시각(epoch 초). 정각 초기화 규칙 검증용."""
        today = time.localtime()
        return time.mktime((today.tm_year, today.tm_mon, today.tm_mday, hour, minute, second, 0, 0, -1))

    def test_expiry_is_the_next_hour_unless_received_in_the_last_five_minutes(self):
        self.assertEqual(zc.expires_at(self.at(2, 0), 300), self.at(3, 0))
        self.assertEqual(zc.expires_at(self.at(2, 30), 300), self.at(3, 0))
        self.assertEqual(zc.expires_at(self.at(2, 54, 59), 300), self.at(3, 0))
        self.assertEqual(zc.expires_at(self.at(2, 55), 300), self.at(4, 0))  # 정각 5분 전부터는 다음 정각까지 보관
        self.assertEqual(zc.expires_at(self.at(2, 59, 59), 300), self.at(4, 0))
        self.assertEqual(zc.expires_at(self.at(3, 0), 300), self.at(4, 0))

    def test_five_projects_received_between_2_and_2_30_are_all_deleted_at_3(self):
        for name in ("a.zip", "b.zip", "c.zip", "d.zip", "e.zip"):
            self.ecm.add_file("R", name, _random_zip(name + ".bin", size=1000))
            self.open_item(self.by_name(self.root())[name])
        self.assertEqual(len(self.cached_files()), 5)
        for job in zc.zip_cache._jobs.values():
            job.completed_at = self.at(2, 10)
        for path in self.cache_dir.iterdir():
            _os.utime(path, (self.at(2, 10), self.at(2, 10)))

        zc.zip_cache.sweep(self.at(2, 59, 59))
        self.assertEqual(len(self.cached_files()), 5)  # 정각 전에는 그대로
        zc.zip_cache.sweep(self.at(3, 0, 1))
        self.assertEqual(self.cached_files(), [])

    def test_copy_received_just_before_the_hour_survives_until_the_next_hour(self):
        self.open_item(self.zip_item())
        for job in zc.zip_cache._jobs.values():
            job.completed_at = self.at(2, 57)
        for path in self.cache_dir.iterdir():
            _os.utime(path, (self.at(2, 57), self.at(2, 57)))

        zc.zip_cache.sweep(self.at(3, 0, 1))
        self.assertEqual(len(self.cached_files()), 1)  # 3시 정각에는 남는다
        zc.zip_cache.sweep(self.at(3, 59))
        self.assertEqual(len(self.cached_files()), 1)
        zc.zip_cache.sweep(self.at(4, 0, 1))
        self.assertEqual(self.cached_files(), [])  # 다음 정각에 삭제

    def test_copy_being_read_is_not_deleted_at_the_hour(self):
        self.open_item(self.zip_item())
        job = next(iter(zc.zip_cache._jobs.values()))
        job.completed_at = self.at(2, 10)

        with job.reading():
            zc.zip_cache.sweep(self.at(3, 0, 1))
            self.assertEqual(len(self.cached_files()), 1)
        zc.zip_cache.sweep(self.at(3, 1))
        self.assertEqual(self.cached_files(), [])

    def test_untracked_copy_files_follow_the_same_hourly_rule_and_old_orphans_go(self):
        stale_part = self.cache_dir / "deadbeef.part"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        stale_part.write_bytes(b"orphan")
        old = self.at(0, 30)
        _os.utime(stale_part, (old, old))
        leftover = self.cache_dir / "feedface.zip"
        leftover.write_bytes(b"x")
        _os.utime(leftover, (self.at(2, 10), self.at(2, 10)))

        zc.zip_cache.sweep(self.at(3, 0, 1))

        self.assertEqual(self.cached_files(), [])

    def test_recent_copy_is_kept_by_the_sweep(self):
        self.open_item(self.zip_item())

        zc.zip_cache.sweep()

        self.assertEqual(len(self.cached_files()), 1)


def _file_meta(ecm, name):
    meta = next(m for m in ecm.tree["R"]["files"] if m["fileName"] == name)
    return {"fileName": meta["fileName"], "fileOID": meta["fileOID"], "storageFileID": meta["storageFileID"], "fileSize": meta["fileSize"]}


class PrefetchTests(SpoolBase):
    def test_opening_the_popup_prefetches_the_largest_root_zip_only(self):
        self.ecm.add_file("R", "huge.zip", _random_zip("h.bin", size=400_000))
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
            self.root()

        files = self.cached_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(self.ecm.streams, ["huge.zip"])  # rawdata.zip 은 더 작아서 미리 받지 않는다

    def test_listing_the_prefetched_zip_needs_no_new_transfer(self):
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
            root = self.root()
        listing = self.open_item(self.by_name(root)["rawdata.zip"])

        self.assertIn("docs", [i["name"] for i in listing["items"]])
        self.assertEqual(self.ecm.streams.count("rawdata.zip"), 1)

    def test_small_zips_are_not_prefetched_by_default(self):
        self.root()

        self.assertEqual(self.cached_files(), [])
        self.assertEqual(self.ecm.streams, [])

    def test_prefetch_can_be_switched_off(self):
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0, FOLDER_BROWSER_PREFETCH=False):
            self.root()

        self.assertEqual(self.ecm.streams, [])

    def test_only_the_root_listing_triggers_prefetch(self):
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
            root = self.root()
            streams = list(self.ecm.streams)
            self.open_item(self.by_name(root)["4.시험"])  # 하위 폴더 열기

        self.assertEqual(self.ecm.streams, streams)

    def test_prefetch_failure_never_breaks_the_root_listing(self):
        self.ecm.blob_stream = mock.Mock(side_effect=RuntimeError("ECM down"))
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
            listing = self.root()

        self.assertEqual(listing["items"][0]["name"], "1.신청")


class InFlightDownloadTests(SpoolBase):
    """받는 중인 상태(백그라운드 스레드 + 멈춘 ECM 응답)에서의 동작."""

    def setUp(self):
        super().setUp()
        self.gate = threading.Event()
        self.addCleanup(self._drain_background)
        self.addCleanup(self.gate.set)
        self.responses = []
        real = self.ecm.blob_stream
        data = _build_zip([("first.txt", b"alpha" * 10), ("big.bin", _os.urandom(300_000))], compression=zipfile.ZIP_STORED)
        self.big = data
        self.ecm.add_file("R", "gated.zip", data)

        def blob_stream(meta):
            if meta["fileName"] != "gated.zip":
                return real(meta)
            self.ecm.streams.append(meta["fileName"])
            if not self.responses:  # 첫 요청(백그라운드 받기)만 멈춘다. 이후 요청은 정상 응답.
                response = GatedResponse(self.ecm.blobs[meta["storageFileID"]], 8192, self.gate)
            else:
                response = _StreamResponse(self.ecm.blobs[meta["storageFileID"]])
            self.responses.append(response)
            return response

        self.ecm.blob_stream = blob_stream
        background = mock.patch.object(zc, "RUN_INLINE", False)
        background.start()
        self.addCleanup(background.stop)

    def _drain_background(self):
        # 임시 폴더를 지우기 전에 백그라운드 받기가 끝나 파일 핸들을 놓을 때까지 기다린다(Windows).
        self.wait_until(lambda: all(j.state != zc.RUNNING for j in list(zc.zip_cache._jobs.values())), 10)

    def start_prefetch(self):
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
            root = self.root()
        self.assertTrue(self.wait_until(lambda: self.responses and self.responses[0].reached.is_set()))
        item = self.by_name(root)["gated.zip"]
        job = zc.zip_cache.lookup("yeongnam", _file_meta(self.ecm, "gated.zip"))
        self.assertEqual(job.state, zc.RUNNING)
        return item, job

    def entry_ref(self, item, name):
        return fb.make_ref({**self.zip_payload(item), "k": "zfile", "name": name})

    def test_entry_requested_while_downloading_is_served_from_ecm_without_disturbing_the_copy(self):
        item, job = self.start_prefetch()

        name, data = self.download(self.entry_ref(item, "first.txt"))

        self.assertEqual((name, data), ("first.txt", b"alpha" * 10))
        self.assertEqual(self.ecm.streams.count("gated.zip"), 2)  # 받는 중에는 원래 방식(ECM 직접)으로 보낸다
        self.assertEqual(job.state, zc.RUNNING)

    def test_entry_not_received_yet_falls_back_to_ecm_direct(self):
        item, job = self.start_prefetch()

        name, data = self.download(self.entry_ref(item, "big.bin"))

        self.assertEqual(name, "big.bin")
        self.assertEqual(len(data), 300_000)
        self.assertEqual(self.ecm.streams.count("gated.zip"), 2)  # 원래 방식: ECM 에서 직접 받아 그 항목만 보냄
        self.assertEqual(job.state, zc.RUNNING)

    def test_listing_waits_for_the_running_download_instead_of_starting_another(self):
        item, job = self.start_prefetch()
        result = {}

        def list_it():
            result["listing"] = self.open_item(item)

        thread = threading.Thread(target=list_it)
        thread.start()
        time.sleep(0.2)
        self.assertTrue(thread.is_alive())  # 받는 중이라 대기
        self.assertEqual(fb.zip_progress(PROJECT, item["ref"])["state"], "running")
        progress = fb.zip_progress(PROJECT, item["ref"])
        self.assertLess(progress["percent"], 100)

        self.gate.set()
        thread.join(10)

        self.assertFalse(thread.is_alive())
        self.assertEqual([i["name"] for i in result["listing"]["items"]], ["big.bin", "first.txt"])
        self.assertEqual(self.ecm.streams.count("gated.zip"), 1)
        self.assertEqual(job.state, zc.COMPLETE)

    def test_two_requests_for_the_same_zip_share_one_transfer(self):
        item, job = self.start_prefetch()
        payload = self.zip_payload(item)

        again = zc.zip_cache.ensure("yeongnam", fb._meta_from_token(payload["meta"]), fb._spool_zip, 10 ** 9)

        self.assertIs(again, job)
        self.assertEqual(self.ecm.streams.count("gated.zip"), 1)

    def test_entry_is_available_from_the_finished_copy_after_the_download_completes(self):
        item, job = self.start_prefetch()
        self.gate.set()
        self.assertEqual(job.wait(10), zc.COMPLETE)

        name, data = self.download(self.entry_ref(item, "big.bin"))

        self.assertEqual(len(data), 300_000)
        self.assertEqual(self.ecm.streams.count("gated.zip"), 1)
        self.assertEqual((self.cache_dir / f"{job.key}.zip").read_bytes(), self.big)


class ProgressApiTests(SpoolBase):
    def test_progress_view(self):
        from main.views.review.ecm_folder_browser_api import browse_progress

        item = self.zip_item()
        factory = RequestFactory()

        none = json.loads(browse_progress(factory.get("/p", {"ref": item["ref"]}), PROJECT).content)
        self.open_item(item)
        done = json.loads(browse_progress(factory.get("/p", {"ref": item["ref"]}), PROJECT).content)
        missing = browse_progress(factory.get("/p"), PROJECT)
        bad = browse_progress(factory.get("/p", {"ref": "garbage"}), PROJECT)

        self.assertEqual((none["success"], none["state"]), (True, "none"))
        self.assertEqual((done["state"], done["percent"]), ("complete", 100))
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(bad.status_code, 400)


# ---------------------------------------------------------------------------
# 팝업을 닫으면 받던 zip 정리(85% 미만) / 보는 팝업이 남아 있으면 유지 / 우선순위 대기열
# ---------------------------------------------------------------------------
class CancelOnCloseTests(SpoolBase):
    """ECM 응답을 멈춰 둔 채(받는 중) 팝업 세션 id 로 열고 닫는다."""

    def setUp(self):
        super().setUp()
        self.gate = threading.Event()
        self.addCleanup(self._drain)
        self.addCleanup(self.gate.set)
        self.responses = []
        real = self.ecm.blob_stream
        self.payload = _build_zip([("a.bin", _os.urandom(400_000))], compression=zipfile.ZIP_STORED)
        self.ecm.add_file("R", "slow.zip", self.payload)
        self.gate_after = 8192

        def blob_stream(meta):
            if meta["fileName"] != "slow.zip":
                return real(meta)
            self.ecm.streams.append(meta["fileName"])
            response = GatedResponse(self.ecm.blobs[meta["storageFileID"]], self.gate_after, self.gate)
            self.responses.append(response)
            return response

        self.ecm.blob_stream = blob_stream
        background = mock.patch.object(zc, "RUN_INLINE", False)
        background.start()
        self.addCleanup(background.stop)
        self.cache = zc.zip_cache

    def _drain(self):
        self.wait_until(lambda: all(j.state != zc.RUNNING or not j.started for j in list(self.cache._jobs.values())), 10)

    def open_root(self, sid):
        with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
            return fb.list_location(PROJECT, center_hint="yeongnam", cert_date="2026-07-13", sid=sid)

    def job(self):
        return self.cache.lookup("yeongnam", _file_meta(self.ecm, "slow.zip"))

    def wait_receiving(self, index=0):
        self.assertTrue(self.wait_until(lambda: len(self.responses) > index and self.responses[index].reached.is_set()))

    def test_closing_the_popup_cancels_a_download_under_85_percent_and_removes_the_file(self):
        self.open_root("sidAAAAAAAA")
        self.wait_receiving()
        job = self.job()

        self.cache.release("sidAAAAAAAA")

        self.assertEqual(job.state, zc.CANCELED)
        self.assertIsNone(self.job())  # 새 요청은 새 작업으로 시작한다
        self.gate.set()
        self.assertTrue(self.wait_until(lambda: self.cached_files() == []))

    def test_download_stops_at_the_next_chunk_so_the_worker_is_freed(self):
        self.open_root("sidAAAAAAAA")
        self.wait_receiving()
        job = self.job()
        written = job.written

        self.cache.release("sidAAAAAAAA")
        self.gate.set()

        self.assertTrue(self.wait_until(lambda: self.cached_files() == []))
        self.assertLess(job.written, job.total)  # 끝까지 받지 않았다
        self.assertLessEqual(job.written, written + 2 * 1024 * 1024)

    def test_another_popup_still_watching_keeps_the_download(self):
        self.open_root("sidAAAAAAAA")
        self.open_root("sidBBBBBBBB")
        self.wait_receiving()
        job = self.job()

        self.cache.release("sidAAAAAAAA")
        self.assertEqual(job.state, zc.RUNNING)  # B 가 보고 있다
        self.cache.release("sidBBBBBBBB")
        self.assertEqual(job.state, zc.CANCELED)
        self.gate.set()

    def test_download_at_85_percent_or_more_continues_after_the_popup_closes(self):
        self.gate_after = int(len(self.payload) * 0.9)
        self.open_root("sidAAAAAAAA")
        self.wait_receiving()
        job = self.job()

        self.cache.release("sidAAAAAAAA")
        self.assertEqual(job.state, zc.RUNNING)
        self.gate.set()

        self.assertEqual(job.wait(10), zc.COMPLETE)
        self.assertEqual(len([n for n in self.cached_files() if n.endswith(".zip")]), 1)

    def test_request_without_a_session_id_is_never_cancelled(self):
        self.open_root("")
        self.wait_receiving()
        job = self.job()

        self.cache.release("sidAAAAAAAA")
        with self.cache._lock:
            self.cache._expire_leases_locked(time.monotonic() + 1000)

        self.assertEqual(job.state, zc.RUNNING)
        self.gate.set()

    def test_lost_popup_is_detected_by_missing_beats_but_beats_keep_it_alive(self):
        self.open_root("sidAAAAAAAA")
        self.wait_receiving()
        job = self.job()

        with self.cache._lock:
            self.cache._expire_leases_locked(time.monotonic() + zc.LEASE_SECONDS - 1)
        self.assertEqual(job.state, zc.RUNNING)

        self.cache.watch("sidAAAAAAAA")
        with self.cache._lock:
            self.cache._expire_leases_locked(time.monotonic() + zc.LEASE_SECONDS - 1)
        self.assertEqual(job.state, zc.RUNNING)  # 방금 신호가 있었다

        with self.cache._lock:
            self.cache._expire_leases_locked(time.monotonic() + zc.LEASE_SECONDS + 1)
        self.assertEqual(job.state, zc.CANCELED)
        self.gate.set()

    def test_listing_request_waiting_on_a_cancelled_zip_gets_a_clear_error(self):
        root = self.open_root("sidAAAAAAAA")
        self.wait_receiving()
        item = self.by_name(root)["slow.zip"]
        result = {}

        def list_it():
            try:
                fb.list_location(PROJECT, item["ref"], sid="sidAAAAAAAA")
            except fb.BrowseError as exc:
                result["error"] = exc

        thread = threading.Thread(target=list_it)
        thread.start()
        time.sleep(0.2)
        self.cache.release("sidAAAAAAAA")
        thread.join(5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result["error"].status, 409)
        self.gate.set()

    def test_reopening_after_cancel_starts_a_fresh_download(self):
        self.open_root("sidAAAAAAAA")
        self.wait_receiving()
        self.cache.release("sidAAAAAAAA")
        self.gate.set()
        self.wait_until(lambda: self.cached_files() == [])
        self.gate.clear()

        self.open_root("sidCCCCCCCC")
        self.wait_receiving(1)

        self.assertEqual(self.ecm.streams.count("slow.zip"), 2)
        self.cache.release("sidCCCCCCCC")
        self.gate.set()


class SchedulerTests(SpoolBase):
    """대기열: 보는 사람이 사라진 대기 작업은 시작하지 않고, 사용자가 직접 연 zip 이 앞서 받는다."""

    def setUp(self):
        super().setUp()
        background = mock.patch.object(zc, "RUN_INLINE", False)
        background.start()
        self.addCleanup(background.stop)
        override = override_settings(FOLDER_BROWSER_PREFETCH_WORKERS=1)
        override.enable()
        self.addCleanup(override.disable)
        self.cache = zc.ZipCache()
        self.release = threading.Event()
        self.addCleanup(self._drain)
        self.addCleanup(self.release.set)
        self.ran = []

    def _drain(self):
        self.wait_until(lambda: all(j.state != zc.RUNNING for j in list(self.cache._jobs.values())), 10)

    def meta(self, name):
        return {"fileName": name, "fileOID": name, "storageFileID": name, "fileSize": 1000}

    def target(self, job):
        self.ran.append(job.meta["fileName"])
        if job.meta["fileName"] == "blocker":
            self.release.wait(10)
        job.written = job.total
        job.part_path.write_bytes(b"x" * 1000)
        _os.replace(job.part_path, job.final_path)

    def ensure(self, name, **kwargs):
        return self.cache.ensure("c", self.meta(name), self.target, 10 ** 9, **kwargs)

    def start_blocker(self):
        job = self.ensure("blocker", sid="blockersid1")
        self.assertTrue(self.wait_until(lambda: "blocker" in self.ran))
        return job

    def test_queued_prefetch_whose_popup_closed_never_starts(self):
        self.start_blocker()
        stale = self.ensure("stale", sid="sidAAAAAAAA", priority=1)
        wanted = self.ensure("wanted", sid="sidBBBBBBBB", priority=1)

        self.cache.release("sidAAAAAAAA")
        self.assertEqual(stale.state, zc.CANCELED)
        self.release.set()

        self.assertEqual(wanted.wait(5), zc.COMPLETE)
        self.assertNotIn("stale", self.ran)

    def test_zip_the_user_opened_jumps_ahead_of_queued_prefetches(self):
        self.start_blocker()
        self.ensure("first_prefetch", sid="sidAAAAAAAA", priority=1)
        self.ensure("second_prefetch", sid="sidBBBBBBBB", priority=1)
        opened = self.ensure("second_prefetch", sid="sidBBBBBBBB", priority=0)  # 사용자가 직접 열었다
        self.release.set()

        self.assertEqual(opened.wait(5), zc.COMPLETE)
        self.assertTrue(self.wait_until(lambda: "first_prefetch" in self.ran))
        self.assertLess(self.ran.index("second_prefetch"), self.ran.index("first_prefetch"))

    def test_sibling_background_copies_run_after_user_requests(self):
        self.start_blocker()
        self.ensure("later_copy", priority=2)
        self.ensure("prefetch", sid="sidAAAAAAAA", priority=1)
        self.release.set()

        self.assertTrue(self.wait_until(lambda: len(self.ran) == 3))
        self.assertEqual(self.ran, ["blocker", "prefetch", "later_copy"])


class WatchApiTests(SpoolBase):
    def post(self, project, **data):
        from main.views.review.ecm_folder_browser_api import browse_watch

        return browse_watch(RequestFactory().post("/watch", data), project)

    def test_beat_and_close_are_accepted_and_bad_input_is_rejected(self):
        self.assertEqual(self.post(PROJECT, sid="sidAAAAAAAA", action="beat").status_code, 200)
        self.assertEqual(self.post(PROJECT, sid="sidAAAAAAAA", action="close").status_code, 200)
        self.assertEqual(self.post(PROJECT, sid="short", action="close").status_code, 400)
        self.assertEqual(self.post(PROJECT, sid="sidAAAAAAAA", action="nope").status_code, 400)
        self.assertEqual(self.post(PROJECT, action="close").status_code, 400)

    def test_close_signal_releases_the_zip_the_popup_was_watching(self):
        with mock.patch.object(zc, "RUN_INLINE", False):
            with override_settings(FOLDER_BROWSER_PREFETCH_MIN_MB=0):
                gate = threading.Event()
                self.addCleanup(gate.set)
                responses = []

                def blob_stream(meta):
                    responses.append(GatedResponse(self.ecm.blobs[meta["storageFileID"]], 0, gate))
                    return responses[-1]

                self.ecm.blob_stream = blob_stream
                request = RequestFactory().get(
                    "/b", {"sid": "sidAAAAAAAA", "center": "yeongnam", "cert_date": "2026-07-13"},
                )
                self.assertEqual(browse(request, PROJECT).status_code, 200)
                job = zc.zip_cache.lookup("yeongnam", _file_meta(self.ecm, "rawdata.zip"))
                self.assertTrue(self.wait_until(lambda: responses and responses[0].reached.is_set()))

                self.post(PROJECT, sid="sidAAAAAAAA", action="close")

                self.assertEqual(job.state, zc.CANCELED)
                gate.set()
                self.wait_until(lambda: self.cached_files() == [])


# ---------------------------------------------------------------------------
# 점검 보관본(AGENT_ARCHIVE_BASE_DIR)에서 읽기 / 보관 폴더 통째 교체
# ---------------------------------------------------------------------------
from types import SimpleNamespace as _NS

from main.views.review import ecm_archive
from main.views.review import ecm_download_review_worker as worker


class ArchiveBase(BrowserTestCase):
    def setUp(self):
        super().setUp()
        self._archive_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._archive_tmp.cleanup)
        self.archive_base = Path(self._archive_tmp.name)
        override = override_settings(AGENT_ARCHIVE_BASE_DIR=str(self.archive_base))
        override.enable()
        self.addCleanup(override.disable)
        self.project_dir = self.archive_base / PROJECT
        self.inner = _build_zip([("z.txt", b"inner z")])
        self.outer = _stream_zip([
            ("docs/a.txt", b"alpha"),
            ("docs/b.txt", b"beta"),
            ("img/c.png", b"png-data"),
            ("inner.zip", self.inner),
        ])
        self.write("1.신청/신청서.docx", b"application")
        self.write("4.시험/라.종료/성적서.pdf", b"%PDF report")
        self.write("rawdata.zip", self.outer)
        self.write(ecm_archive.MARKER_NAME, json.dumps({"archived_at": "2026-10-01 17:01:54"}).encode("utf-8"))

    def write(self, rel, data):
        path = self.project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def root_archive(self, **kwargs):
        return fb.list_location(PROJECT, center_hint="yeongnam", cert_date="2026-01-19", **kwargs)


class ArchiveListingTests(ArchiveBase):
    def test_root_comes_from_the_archive_without_touching_ecm(self):
        listing = self.root_archive()

        self.assertEqual(listing["location"]["center"], "archive")
        self.assertEqual(listing["source"], {"kind": "archive", "archived_at": "2026-10-01 17:01:54"})
        self.assertEqual([i["name"] for i in listing["items"]], ["1.신청", "4.시험", "rawdata.zip"])
        self.assertEqual(self.ecm.streams, [])
        self.assertEqual(self.cached_files(), [])  # 서버 임시 보관·미리 받기는 쓰지 않는다

    def test_marker_file_is_hidden_from_listings(self):
        names = [i["name"] for i in self.root_archive()["items"]]

        self.assertNotIn(ecm_archive.MARKER_NAME, names)

    def test_archive_without_marker_still_works_and_reports_no_time(self):
        (self.project_dir / ecm_archive.MARKER_NAME).unlink()

        listing = self.root_archive()

        self.assertEqual(listing["source"], {"kind": "archive", "archived_at": ""})

    def test_navigating_folders_and_files_in_the_archive(self):
        root = self.by_name(self.root_archive())
        exam = self.by_name(self.open_item(root["4.시험"]))
        end = self.by_name(self.open_item(exam["라.종료"]))

        self.assertEqual(self.download(end["성적서.pdf"]["ref"]), ("성적서.pdf", b"%PDF report"))
        self.assertEqual(self.ecm.streams, [])

    def test_zip_listing_and_entry_download_read_the_archive_directly(self):
        root = self.by_name(self.root_archive())
        zip_level = self.open_item(root["rawdata.zip"])
        docs = self.by_name(self.open_item(self.by_name(zip_level)["docs"]))

        self.assertEqual(sorted(self.by_name(zip_level)), ["docs", "img", "inner.zip"])
        self.assertEqual(self.download(docs["a.txt"]["ref"]), ("a.txt", b"alpha"))
        self.assertEqual(self.ecm.streams, [])
        self.assertEqual(self.cached_files(), [])

    def test_nested_zip_inside_an_archived_zip(self):
        root = self.by_name(self.root_archive())
        zip_level = self.by_name(self.open_item(root["rawdata.zip"]))
        inner = self.by_name(self.open_item(zip_level["inner.zip"]))

        self.assertEqual(self.download(inner["z.txt"]["ref"]), ("z.txt", b"inner z"))

    def test_zip_file_itself_downloads_from_the_archive(self):
        root = self.by_name(self.root_archive())

        name, data = self.download(root["rawdata.zip"]["download_ref"])

        self.assertEqual((name, data), ("rawdata.zip", self.outer))

    def test_selection_zip_from_archive_folder_zip_entries_and_files(self):
        root = self.by_name(self.root_archive())
        zip_level = self.by_name(self.open_item(root["rawdata.zip"]))
        docs_dir = zip_level["docs"]

        zf, names = SelectionZipTests.names(self, [root["1.신청"]["ref"], docs_dir["ref"], root["rawdata.zip"]["download_ref"]])

        self.assertEqual(names, ["1.신청/신청서.docx", "docs/a.txt", "docs/b.txt", "rawdata.zip"])
        self.assertEqual(zf.read("docs/b.txt"), b"beta")
        self.assertEqual(self.ecm.streams, [])

    def test_whole_project_root_zip_from_the_archive(self):
        location = self.root_archive()["location"]

        zf, names = SelectionZipTests.names(self, [location["ref"]])

        self.assertIn(f"{PROJECT}/1.신청/신청서.docx".replace(PROJECT, location["label"]), names)
        self.assertFalse([n for n in names if ecm_archive.MARKER_NAME in n])

    def test_replaced_archive_zip_is_listed_again_instead_of_a_stale_cached_list(self):
        root = self.by_name(self.root_archive())
        before = self.open_item(root["rawdata.zip"])
        self.assertIn("docs", [i["name"] for i in before["items"]])

        replaced = self.write("rawdata.zip", _stream_zip([("new/only.txt", b"x" * 5), ("pad.txt", b"y" * 5)]))
        stat = replaced.stat()
        _os.utime(replaced, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        root = self.by_name(self.root_archive())
        after = self.open_item(root["rawdata.zip"])

        self.assertEqual(sorted(i["name"] for i in after["items"]), ["new", "pad.txt"])


class ArchiveFallbackTests(ArchiveBase):
    def test_ecm_is_used_when_there_is_no_archive_for_the_project(self):
        import shutil

        shutil.rmtree(self.project_dir)

        listing = self.root_archive()

        self.assertEqual(listing["location"]["center"], "yeongnam")
        self.assertEqual(listing["source"]["kind"], "ecm")
        self.assertFalse(listing["source"]["archive_available"])

    def test_archive_folder_with_nothing_but_the_marker_counts_as_missing(self):
        import shutil

        shutil.rmtree(self.project_dir)
        self.write(ecm_archive.MARKER_NAME, b"{}")

        self.assertEqual(self.root_archive()["location"]["center"], "yeongnam")

    def test_ecm_latest_can_be_chosen_even_when_an_archive_exists(self):
        listing = self.root_archive(source="ecm")

        self.assertEqual(listing["location"]["center"], "yeongnam")
        self.assertEqual(listing["source"], {"kind": "ecm", "archive_available": True})

    def test_unreadable_archive_base_falls_back_to_ecm(self):
        with override_settings(AGENT_ARCHIVE_BASE_DIR=str(self.archive_base / "missing" / "share")):
            listing = self.root_archive()

        self.assertEqual(listing["location"]["center"], "yeongnam")

    def test_archive_disabled_by_empty_setting(self):
        with override_settings(AGENT_ARCHIVE_BASE_DIR=""):
            self.assertEqual(self.root_archive()["location"]["center"], "yeongnam")

    def test_archive_refs_do_not_open_under_another_project(self):
        ref = self.root_archive()["location"]["ref"]

        with self.assertRaises(fb.BrowseError):
            fb.list_location("GS-C-25-0999", ref)


class ArchivePathSafetyTests(ArchiveBase):
    def archive_client(self):
        return ecm_archive.ArchiveClient(PROJECT)

    def test_parent_directory_absolute_and_hidden_paths_are_refused(self):
        client = self.archive_client()
        for bad in ("../secret.txt", "4.시험/../../x", "C:/Windows/win.ini", "..", f"{ecm_archive.MARKER_NAME}"):
            with self.subTest(path=bad):
                with self.assertRaises(ecm_archive.ArchiveError):
                    client.resolve(bad)

    def test_blob_and_folder_listing_cannot_leave_the_project_archive(self):
        outside = self.archive_base / "OTHER-PROJECT"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        client = self.archive_client()

        with self.assertRaises(ecm_archive.ArchiveError):
            client.blob_stream({"storageFileID": "../OTHER-PROJECT/secret.txt"})
        with self.assertRaises(ecm_archive.ArchiveError):
            client.folder_contents("../OTHER-PROJECT")

    def test_project_number_with_path_characters_has_no_archive(self):
        for bad in ("..", "a/b", "a\\b", ""):
            with self.subTest(project=bad):
                self.assertIsNone(ecm_archive.project_dir(bad))


class ArchiveReplaceTests(SimpleTestCase):
    """워커: 점검할 때마다 보관 폴더를 통째로 교체한다(합치지 않는다)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.archive = root / "archive"
        self.archive.mkdir()
        self.download = root / "download" / PROJECT
        self.download.mkdir(parents=True)
        override = override_settings(AGENT_ARCHIVE_BASE_DIR=str(self.archive))
        override.enable()
        self.addCleanup(override.disable)
        log = mock.patch.object(worker, "DownloadReviewLog")
        self.log = log.start()
        self.addCleanup(log.stop)
        self.job = _NS(id="job-1")
        self.project = _NS(project_number=PROJECT)

    def archived(self):
        folder = self.archive / PROJECT
        return sorted(str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*") if p.is_file())

    def run_archive(self):
        worker._archive_download_dir_safely(self.job, self.project, str(self.download))

    def test_old_archive_content_is_removed_and_replaced_by_the_new_download(self):
        old = self.archive / PROJECT
        (old / "삭제된폴더").mkdir(parents=True)
        (old / "삭제된폴더" / "옛파일.txt").write_text("stale")
        (old / "공통.txt").write_text("old version")
        (self.download / "공통.txt").write_text("new version")
        (self.download / "신규.txt").write_text("new")

        self.run_archive()

        self.assertEqual(self.archived(), [ecm_archive.MARKER_NAME, "공통.txt", "신규.txt"])
        self.assertEqual((old / "공통.txt").read_text(), "new version")
        self.assertFalse((old / "삭제된폴더").exists())

    def test_marker_records_when_the_archive_was_made(self):
        (self.download / "a.txt").write_text("a")

        self.run_archive()

        with override_settings(AGENT_ARCHIVE_BASE_DIR=str(self.archive)):
            self.assertRegex(ecm_archive.archived_at(PROJECT), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_no_temporary_folder_is_left_behind(self):
        (self.download / "a.txt").write_text("a")

        self.run_archive()

        self.assertEqual(sorted(p.name for p in self.archive.iterdir()), [PROJECT])

    def test_first_archive_for_a_project_without_a_previous_one(self):
        (self.download / "sub").mkdir()
        (self.download / "sub" / "a.txt").write_text("a")

        self.run_archive()

        self.assertEqual(self.archived(), [ecm_archive.MARKER_NAME, "sub/a.txt"])

    def test_failed_copy_removes_the_old_archive_so_stale_content_is_never_shown(self):
        old = self.archive / PROJECT
        old.mkdir()
        (old / "옛파일.txt").write_text("stale")
        (self.download / "a.txt").write_text("a")

        with mock.patch.object(worker.shutil, "copytree", side_effect=OSError("share down")):
            self.run_archive()

        self.assertFalse(old.exists())
        self.assertEqual(sorted(p.name for p in self.archive.iterdir()), [])
        self.assertEqual(self.log.objects.create.call_args.kwargs["event_code"], "archive_failed")

    def test_nothing_happens_when_archiving_is_not_configured(self):
        with override_settings(AGENT_ARCHIVE_BASE_DIR=""):
            self.run_archive()

        self.assertEqual(list(self.archive.iterdir()), [])
