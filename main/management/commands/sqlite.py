import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.utils.xlsx_to_sqlite import convert_xlsx_to_sqlite


class Command(BaseCommand):
    help = "reference.xlsx 파일을 SQLite DB로 변환하고 기준 데이터 변경분을 Git에 반영합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "xlsx_path",
            type=str,
            nargs="?",
            default="main/data/reference.xlsx",
            help="입력 XLSX 파일 경로 (기본: main/data/reference.xlsx)",
        )
        parser.add_argument(
            "db_path",
            type=str,
            nargs="?",
            default="main/data/reference.db",
            help="출력 SQLite DB 파일 경로 (기본: main/data/reference.db)",
        )
        parser.add_argument(
            "--table-name",
            default="sw_data",
            help="SQLite에 생성할 테이블명 (기본: sw_data)",
        )
        parser.add_argument(
            "--commit-message",
            default="data: update reference database",
            help="Git 커밋 메시지",
        )
        parser.add_argument(
            "--remote",
            default="origin",
            help="push할 Git remote 이름 (기본: origin)",
        )
        parser.add_argument(
            "--branch",
            default="",
            help="push할 Git 브랜치명. 비우면 현재 브랜치를 사용합니다.",
        )
        parser.add_argument(
            "--no-git-sync",
            action="store_true",
            help="DB 생성 후 Git commit/push를 수행하지 않습니다.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        xlsx_path = _resolve_path(base_dir, options["xlsx_path"])
        db_path = _resolve_path(base_dir, options["db_path"])

        self.stdout.write(f"▶ XLSX 파일: {xlsx_path}")
        self.stdout.write(f"▶ SQLite DB: {db_path}")

        convert_xlsx_to_sqlite(str(xlsx_path), str(db_path), table_name=options["table_name"])

        if options["no_git_sync"]:
            self.stdout.write("▶ Git 동기화 생략 (--no-git-sync)")
            return

        sync_reference_data_to_git(
            repo_dir=base_dir,
            paths=[xlsx_path, db_path],
            commit_message=options["commit_message"],
            remote=options["remote"],
            branch=options["branch"],
            stdout=self.stdout,
        )


def _resolve_path(base_dir, value):
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _run_git(repo_dir, args, *, check=True):
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise CommandError(f"git {' '.join(args)} 실패: {message}")
    return completed


def _relative_to_repo(repo_dir, path):
    try:
        return str(path.resolve().relative_to(repo_dir.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise CommandError(f"Git에 반영할 파일이 저장소 밖에 있습니다: {path}") from exc


def _current_branch(repo_dir):
    completed = _run_git(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = completed.stdout.strip()
    if not branch or branch == "HEAD":
        raise CommandError("현재 Git 브랜치를 확인할 수 없습니다. --branch 값을 지정하세요.")
    return branch


def sync_reference_data_to_git(repo_dir, paths, commit_message, remote, branch, stdout):
    repo_dir = repo_dir.resolve()
    rel_paths = [_relative_to_repo(repo_dir, path) for path in paths]

    staged_before = _run_git(repo_dir, ["diff", "--cached", "--name-only"]).stdout.splitlines()
    unrelated_staged = [path for path in staged_before if path not in rel_paths]
    if unrelated_staged:
        joined = ", ".join(unrelated_staged)
        raise CommandError(f"기준 데이터 외 staged 변경이 있어 자동 커밋을 중단합니다: {joined}")

    _run_git(repo_dir, ["add", "--", *rel_paths])

    diff = _run_git(repo_dir, ["diff", "--cached", "--quiet", "--", *rel_paths], check=False)
    if diff.returncode == 0:
        stdout.write("▶ Git 반영할 기준 데이터 변경 없음")
        return
    if diff.returncode not in (0, 1):
        raise CommandError("Git staged diff 확인 중 오류가 발생했습니다.")

    _run_git(repo_dir, ["commit", "-m", commit_message, "--", *rel_paths])
    target_branch = branch or _current_branch(repo_dir)
    _run_git(repo_dir, ["push", remote, f"HEAD:{target_branch}"])
    stdout.write(f"[OK] Git push 완료: {remote}/{target_branch}")
