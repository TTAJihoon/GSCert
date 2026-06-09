import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.utils.xlsx_to_sqlite import convert_xlsx_to_sqlite


class Command(BaseCommand):
    help = "Convert reference.xlsx to SQLite and optionally sync reference data to Git."

    def add_arguments(self, parser):
        parser.add_argument(
            "xlsx_path",
            type=str,
            nargs="?",
            default="main/data/reference.xlsx",
            help="Input XLSX path. Default: main/data/reference.xlsx",
        )
        parser.add_argument(
            "db_path",
            type=str,
            nargs="?",
            default="main/data/reference.db",
            help="Output SQLite DB path. Default: main/data/reference.db",
        )
        parser.add_argument(
            "--table-name",
            default="sw_data",
            help="SQLite table name. Default: sw_data",
        )
        parser.add_argument(
            "--commit-message",
            default="data: update reference database",
            help="Git commit message.",
        )
        parser.add_argument(
            "--remote",
            default="origin",
            help="Git remote name to push to. Default: origin",
        )
        parser.add_argument(
            "--branch",
            default="",
            help="Git branch name to push to. Empty value uses current branch.",
        )
        parser.add_argument(
            "--no-git-sync",
            action="store_true",
            help="Skip Git commit/push after DB generation.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate SQLite DB even when contents match the existing DB.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        xlsx_path = _resolve_path(base_dir, options["xlsx_path"])
        db_path = _resolve_path(base_dir, options["db_path"])

        self.stdout.write(f"XLSX path: {xlsx_path}")
        self.stdout.write(f"SQLite DB path: {db_path}")

        convert_xlsx_to_sqlite(
            str(xlsx_path),
            str(db_path),
            table_name=options["table_name"],
            force=options["force"],
        )

        if options["no_git_sync"]:
            self.stdout.write("Git sync skipped (--no-git-sync)")
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
        raise CommandError(f"git {' '.join(args)} failed: {message}")
    return completed


def _relative_to_repo(repo_dir, path):
    try:
        return str(path.resolve().relative_to(repo_dir.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise CommandError(f"Path is outside the repository and cannot be synced to Git: {path}") from exc


def _current_branch(repo_dir):
    completed = _run_git(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = completed.stdout.strip()
    if not branch or branch == "HEAD":
        raise CommandError("Cannot determine the current Git branch. Provide --branch.")
    return branch


def sync_reference_data_to_git(repo_dir, paths, commit_message, remote, branch, stdout):
    repo_dir = repo_dir.resolve()
    rel_paths = [_relative_to_repo(repo_dir, path) for path in paths]

    staged_before = _run_git(repo_dir, ["diff", "--cached", "--name-only"]).stdout.splitlines()
    unrelated_staged = [path for path in staged_before if path not in rel_paths]
    if unrelated_staged:
        joined = ", ".join(unrelated_staged)
        raise CommandError(f"Unrelated staged changes exist, aborting automatic commit: {joined}")

    _run_git(repo_dir, ["add", "--", *rel_paths])

    diff = _run_git(repo_dir, ["diff", "--cached", "--quiet", "--", *rel_paths], check=False)
    if diff.returncode == 0:
        stdout.write("No reference data changes to sync to Git")
        return
    if diff.returncode not in (0, 1):
        raise CommandError("Failed to inspect Git staged diff.")

    _run_git(repo_dir, ["commit", "-m", commit_message, "--", *rel_paths])
    target_branch = branch or _current_branch(repo_dir)
    _run_git(repo_dir, ["push", remote, f"HEAD:{target_branch}"])
    stdout.write(f"[OK] Git push complete: {remote}/{target_branch}")
