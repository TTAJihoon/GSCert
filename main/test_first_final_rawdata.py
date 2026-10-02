"""최초/최종형상RawData 규칙(image_screenshot_folder_date_check): 폴더 선택 순서와 최초·최종 이름 매칭."""

from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from gscert_review_core import engine

PROJECT = "GS-B-25-0137"
ROOT = "C:/dl/GS-B-25-0137"
PERIOD = ("2025-09-04", "2025-09-24")

CONFIG = {
    "artifact_column": "최초/최종형상RawData",
    "folder_keyword_chain": ["설계"],
    "fallback_folder_keywords": ["스크린샷", "형상"],
    "min_images_per_folder": 5,
    "required_candidate_folder_count": 2,
}


def _images(zip_chain, folder, count, day, prefix="a"):
    """zip_chain 안(없으면 일반 폴더)의 folder 아래 이미지 count 개. day 는 수정일."""
    files = []
    for index in range(count):
        name = f"{prefix}{index}.png"
        inner = f"{folder}/{name}" if folder else name
        path = "::".join([f"{ROOT}/{zip_chain[0]}", *zip_chain[1:], inner]) if zip_chain else f"{ROOT}/{inner}"
        files.append(engine.FileInfo(
            name=name, path=path, size=1, extension=".png",
            modified_at=datetime(2025, 9, day, 12, 0, 0),
        ))
    return files


def _doc(path, name="계획서.docx"):
    return engine.FileInfo(name=name, path=path, size=1, extension=".docx", modified_at=datetime(2025, 9, 5))


def _run(files, config=None):
    rule = SimpleNamespace(
        config_json={**CONFIG, **(config or {})}, target_file_pattern="", target_file_type="any", code="artifact_08",
        name="최초/최종형상RawData",
    )
    verify = SimpleNamespace(files=files)
    verify._inspection_files_cache = files
    context = engine.build_context(project_number=PROJECT, start_date=PERIOD[0], end_date=PERIOD[1])
    return engine._evaluate_image_screenshot_folder_date_check(rule, 8, SimpleNamespace(project_number=PROJECT), context, verify)


def _passed(result):
    return result.status == engine.DownloadReviewRuleStatus.PASS


class FirstFinalRawdataTests(SimpleTestCase):
    def test_rawdata_zip_with_first_and_final_image_zips_passes_even_when_design_folder_has_no_images(self):
        # GS-B-25-0137: root 의 raw data.zip 안에 최초/패치 후 이미지 zip, 프로젝트 zip 의 '나.설계' 에는 문서만 있다.
        files = [_doc(f"{ROOT}/프로젝트.zip::4.시험/나.설계/환경구성도.docx", "환경구성도.docx")]
        for platform in ("Android", "iOS"):
            files += _images(["raw data.zip", "최초 제품형상 이미지.zip"], f"패치 전 스크린샷/{platform}", 6, 5, platform)
            files += _images(["raw data.zip", "패치 후 제품영상 이미지.zip"], f"패치 후 스크린샷/{platform}", 6, 24, platform)

        result = _run(files)

        self.assertTrue(_passed(result), (result.message, result.raw_detail))
        self.assertTrue(result.raw_detail["used_rawdata_scope"])
        self.assertEqual(sorted(item["image_count"] for item in result.raw_detail["selected_candidate_folders"]), [12, 12])

    def test_root_rawdata_is_tried_first_then_the_design_folder(self):
        design = _images([], "4.시험/나.설계/최초형상", 5, 5) + _images([], "4.시험/나.설계/최종형상", 5, 24)
        rawdata = _images(["rawdata.zip"], "최초형상", 5, 6, "r") + _images(["rawdata.zip"], "최종형상", 5, 23, "r")

        result = _run(design + rawdata)

        self.assertTrue(_passed(result))
        self.assertTrue(result.raw_detail["used_rawdata_scope"])
        self.assertTrue(all("rawdata" in item["folder"] or "형상" in item["folder"]
                            for item in result.raw_detail["selected_candidate_folders"]))

    def test_without_rawdata_the_design_folder_is_used_as_before(self):
        files = _images([], "4.시험/나.설계/최초형상", 5, 5) + _images([], "4.시험/나.설계/최종형상", 5, 24)

        result = _run(files)

        self.assertTrue(_passed(result))
        self.assertFalse(result.raw_detail["used_rawdata_scope"])

    def test_rawdata_without_usable_images_falls_back_to_the_design_folder(self):
        files = _images([], "4.시험/나.설계/최초형상", 5, 5) + _images([], "4.시험/나.설계/최종형상", 5, 24)
        files.append(engine.FileInfo(name="메모.txt", path=f"{ROOT}/rawdata.zip::메모.txt", extension=".txt"))

        result = _run(files)

        self.assertTrue(_passed(result))
        self.assertFalse(result.raw_detail["used_rawdata_scope"])

    def test_design_folder_without_images_falls_through_to_screenshot_or_form_folders(self):
        files = [_doc(f"{ROOT}/4.시험/나.설계/설계서.docx", "설계서.docx")]
        files += _images([], "형상/최초형상", 5, 5) + _images([], "형상/최종형상", 5, 24)

        result = _run(files)

        self.assertTrue(_passed(result), (result.message, result.raw_detail))

    def test_images_outside_the_test_period_still_fail_with_the_dates(self):
        files = _images(["raw data.zip", "최초 제품형상 이미지.zip"], "패치 전 스크린샷/iOS", 5, 1, "x")
        files += _images(["raw data.zip", "패치 후 제품영상 이미지.zip"], "패치 후 스크린샷/iOS", 5, 24, "y")

        result = _run(files)

        self.assertFalse(_passed(result))
        self.assertEqual(result.raw_detail["out_of_range_date_counts"], {"2025.09.01.": 5})

    def test_final_images_are_date_checked_too_not_only_the_first_form(self):
        files = _images(["raw data.zip", "최초 제품형상 이미지.zip"], "패치 전 스크린샷/iOS", 5, 5, "x")
        files += _images(["raw data.zip", "패치 후 제품영상 이미지.zip"], "패치 후 스크린샷/iOS", 5, 30, "y")

        result = _run(files)

        self.assertFalse(_passed(result))
        self.assertEqual(result.raw_detail["out_of_range_date_counts"], {"2025.09.30.": 5})

    def test_unrelated_screenshot_folder_is_not_picked_as_a_form_folder(self):
        files = _images(["rawdata.zip", "결함리포트 스크린샷.zip"], "결함 스크린샷", 6, 16, "d")
        files += _images(["rawdata.zip", "최초 제품형상 이미지.zip"], "패치 전 스크린샷", 5, 5, "f")
        files += _images(["rawdata.zip", "패치 후 제품영상 이미지.zip"], "패치 후 스크린샷", 5, 24, "g")

        result = _run(files)

        self.assertTrue(_passed(result))
        folders = [item["folder"] for item in result.raw_detail["selected_candidate_folders"]]
        self.assertFalse([folder for folder in folders if "결함" in folder])

    def test_name_that_contains_both_first_and_final_cannot_decide_so_structure_is_used(self):
        files = _images([], "형상/최초,최종 구분/A", 5, 5) + _images([], "형상/최초,최종 구분/B", 5, 24)

        result = _run(files)

        self.assertTrue(_passed(result))  # 구조(같은 부모 아래 형제 2개)로 통과
        self.assertEqual(len(result.raw_detail["selected_candidate_folders"]), 2)

    def test_custom_first_and_final_keywords_from_the_rule_config(self):
        files = _images(["rawdata.zip", "알파 버전.zip"], "스크린샷", 5, 5, "p") + _images(["rawdata.zip", "베타 버전.zip"], "스크린샷", 5, 24, "q")

        default_result = _run(files)
        custom_result = _run(files, {"first_form_keywords": ["알파"], "final_form_keywords": ["베타"]})

        # 기본 키워드로는 이름으로 구분되지 않고, 두 zip 의 안쪽 폴더 이름이 같아 구조로도 후보 2개가 안 나온다.
        self.assertFalse(_passed(default_result))
        self.assertTrue(_passed(custom_result))
        self.assertEqual(sorted(item["image_count"] for item in custom_result.raw_detail["selected_candidate_folders"]), [5, 5])

    def test_nothing_found_keeps_the_original_failure_message(self):
        files = [_doc(f"{ROOT}/4.시험/나.설계/설계서.docx", "설계서.docx")]

        result = _run(files)

        self.assertFalse(_passed(result))
        self.assertEqual(result.message, "제품 스크린샷 폴더를 찾을 수 없음")
        self.assertEqual(result.actual, "후보 폴더 0개")

    def test_no_design_and_no_screenshot_folder_reports_the_missing_folder(self):
        files = [_doc(f"{ROOT}/기타/문서.docx", "문서.docx")]

        result = _run(files)

        self.assertFalse(_passed(result))
        self.assertEqual(result.message, "rawdata 폴더를 찾을 수 없습니다")
