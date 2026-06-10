import unittest

from playwright_job.ecm import committee_target_child_folders


class CommitteeDownloadTests(unittest.TestCase):
    def test_target_child_folders_excludes_first_and_last(self) -> None:
        names = [
            "G4B 온라인 발급",
            "가. GS-C-22-086",
            "나. GS-C-22-094",
            "다. GS-C-22-095",
            "하허. 내부 처리",
        ]

        self.assertEqual(
            committee_target_child_folders(names),
            [
                "가. GS-C-22-086",
                "나. GS-C-22-094",
                "다. GS-C-22-095",
            ],
        )

    def test_target_child_folders_ignores_blank_names(self) -> None:
        names = ["", "G4B 온라인 발급", "가. GS-C-22-086", "하허"]

        self.assertEqual(committee_target_child_folders(names), ["가. GS-C-22-086"])

    def test_target_child_folders_returns_empty_for_short_lists(self) -> None:
        self.assertEqual(committee_target_child_folders(["G4B 온라인 발급", "하허"]), [])


if __name__ == "__main__":
    unittest.main()
