import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from main.views.review.ecm_download_verify import verify_downloaded_files
from main.views.review.ecm_llm_review import (
    LlmReviewDocumentContext,
    LlmReviewRuleContext,
    build_llm_review_payload,
    file_context_from_verify_file,
)
from main.views.review.ecm_reference_db import ReferenceDbError, get_projects_by_numbers


class Command(BaseCommand):
    help = "Build a provider-neutral LLM review prompt payload for manual Claude/GPT/Gemini testing."

    def add_arguments(self, parser):
        parser.add_argument("--project-number", required=True)
        parser.add_argument("--download-dir", required=True)
        parser.add_argument("--center", default="sangam")
        parser.add_argument("--rule-code", default="manual_llm_rule")
        parser.add_argument("--rule-name", default="LLM 수동 점검")
        parser.add_argument("--rule-prompt", default="")
        parser.add_argument("--rule-prompt-file", default="")
        parser.add_argument("--artifact-column", default="")
        parser.add_argument("--expected", default="")
        parser.add_argument("--provider-hint", default="manual-claude")
        parser.add_argument("--context-file", action="append", default=[])
        parser.add_argument("--output", default="")

    def handle(self, *args, **options):
        project_number = options["project_number"].strip()
        download_dir = Path(options["download_dir"]).expanduser()
        if not project_number:
            raise CommandError("--project-number is required.")
        if not download_dir.is_dir():
            raise CommandError(f"Download directory does not exist: {download_dir}")

        prompt = self._resolve_rule_prompt(options)
        if not prompt:
            prompt = (
                "제공된 프로젝트 정보, 파일 목록, 문서 추출 내용을 기준으로 이 산출물이 "
                "점검 기준을 만족하는지 판단하세요. 근거가 부족하면 warning으로 응답하세요."
            )

        verify_result = verify_downloaded_files(str(download_dir), project_number)
        files = [
            file_context_from_verify_file(file_info, project_number)
            for file_info in verify_result.files
        ]
        project = self._load_project_context(project_number, options["center"])
        project["download_verify"] = {
            "success": verify_result.success,
            "file_count": verify_result.file_count,
            "total_size": verify_result.total_size,
            "warnings": verify_result.warnings,
            "error_message": verify_result.error_message,
        }

        payload = build_llm_review_payload(
            project=project,
            rule=LlmReviewRuleContext(
                code=options["rule_code"].strip(),
                name=options["rule_name"].strip(),
                prompt=prompt,
                artifact_column=options["artifact_column"].strip(),
                expected=options["expected"].strip(),
            ),
            files=files,
            document_contexts=self._load_document_contexts(options["context_file"]),
            provider_hint=options["provider_hint"].strip() or "manual-claude",
        ).to_dict()
        output_text = json.dumps(payload, ensure_ascii=False, indent=2)

        output_path = options["output"].strip()
        if output_path:
            Path(output_path).write_text(output_text + "\n", encoding="utf-8")
            self.stdout.write(f"LLM review prompt written: {output_path}")
        else:
            self.stdout.write(output_text)

    def _resolve_rule_prompt(self, options):
        prompt_file = options["rule_prompt_file"].strip()
        if prompt_file:
            return Path(prompt_file).read_text(encoding="utf-8").strip()
        return options["rule_prompt"].strip()

    def _load_project_context(self, project_number, center):
        project = {
            "project_number": project_number,
            "center_code": center,
        }
        try:
            row = get_projects_by_numbers([project_number], center_code=center)[0]
        except (ReferenceDbError, IndexError) as exc:
            project["reference_lookup"] = {"found": False, "error": str(exc)}
            return project

        if not row:
            project["reference_lookup"] = {"found": False, "error": "project not found"}
            return project
        project.update(row)
        project["reference_lookup"] = {"found": True}
        return project

    def _load_document_contexts(self, context_files):
        contexts = []
        for index, raw_path in enumerate(context_files, start=1):
            path = Path(raw_path).expanduser()
            if not path.is_file():
                raise CommandError(f"Context file does not exist: {path}")
            contexts.append(
                LlmReviewDocumentContext(
                    file_name=path.name,
                    content_type="text/plain",
                    text=path.read_text(encoding="utf-8"),
                    chunk_index=index,
                )
            )
        return contexts
