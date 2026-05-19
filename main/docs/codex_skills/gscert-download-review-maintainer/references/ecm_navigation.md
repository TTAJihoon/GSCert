# ECM Navigation Reference

## Scope

Use this reference when the user asks to adjust or reason about ECM tree traversal, folder selection, document-list selection, or download target selection.

This skill guides Codex or another development agent while editing or testing the repository. It is not a runtime plugin inside the deployed Django app. End users will not type natural-language commands into the app for this workflow.

## Current Runtime Files

Primary files to inspect before changing behavior:

- `main/views/review/ecm_download.py`
- `main/views/review/ecm_selectors.py`
- `main/views/review/ecm_agent_popup.py`
- `main/views/review/ecm_download_review_worker.py`
- `main/docs/03_webpage1_automation.md`

## Known Tree Shape

Sangam:

```text
상암AX센터 > {year}년 시험서비스 > 01 GS인증시험(1등급) > project folder
```

Yeongnam:

```text
영남AX센터 > {year}년 시험서비스 > 01 GS인증시험(1등급) > project folder
```

Root occurrence rules:

- `상암AX센터` appears twice. The active root defaults to index `1`.
- `영남AX센터` appears once. The active root defaults to index `0`.
- Do not hard-code raw nth-child selectors when a label/attribute match is available.

## Prompt-To-Action Mapping

When a user phrase describes a path, convert it into an explicit navigation spec before editing code or running live tests.

Examples:

- "최상위 트리에서 2번째 아래에 있는 상암AX센터부터 시작"
  - `root_label = "상암AX센터"`
  - `root_occurrence_index = 1`
- "상암을 선택했을 때"
  - center `sangam`, root label `상암AX센터`, root index from `ECM_TREE_ROOT_INDEX`
- "영남을 선택했을 때"
  - center `yeongnam`, root label `영남AX센터`, root index from `ECM_TREE_ROOT_INDEX_YEONGNAM`
- "B가 포함된 이름의 폴더"
  - find a folder anchor whose visible text or `name` attribute contains `B`
- "2026년이 포함된 폴더"
  - find folder containing `2026년` or `{year}년 시험서비스`
- "GS인증시험 폴더"
  - prefer exact `01 GS인증시험(1등급)` unless the user intentionally gives a broader contains rule
- "프로젝트번호 폴더"
  - find project folder containing the DB `프로젝트번호`

Before acting on a vague phrase, normalize it into:

```text
root_label
root_occurrence_index
path_segments: exact/contains segment list
project_number
document_list_checkbox_selection
download_target
```

## Folder Traversal Rules

Use a consistent traversal strategy:

1. Locate `#edm-folder`.
2. Find the root folder by label and occurrence index.
3. Click or expand the root folder if needed.
4. For each path segment, wait for child nodes, then find by exact match first, contains match second.
5. Click the final project folder.
6. Wait for the document list to load before selecting checkboxes.

The user may only provide keywords. In that case, keep the code parameterized:

- label/exact text
- contains text
- occurrence index
- center code
- year
- project number

Avoid adding one-off selectors that only work for a single current DOM position.

## Document List Checkbox Selection

This means how the automation should tick checkboxes in the ECM document list after a project folder is clicked and before the download menu is opened.

It does not mean "document type" or "inspection rule target." It only describes the checkbox selection strategy on the ECM file list.

The current default flow ticks the header checkbox and selects all visible documents before download.

If the user says:

- "전체 선택": use the header select-all checkbox.
- "1개만 선택": select one eligible row checkbox, preferably the first visible file row after the project folder is loaded.
- "첫 번째만 선택": select the first visible file row checkbox.
- "B가 포함된 파일만 선택": select row checkboxes whose file name contains `B`.
- "확장자가 pdf인 파일만 선택": select row checkboxes whose file name or metadata indicates `.pdf`.
- "체크박스를 전체 선택하지 말고": do not click the header select-all checkbox.

Recommended implementation shape:

```text
DocumentSelectionSpec(
  mode="all|first|contains|extension|exact",
  value="optional search value",
  max_count=None|1|N
)
```

When changing document selection behavior, add or update tests where possible and update `main/docs/03_webpage1_automation.md`.

## Safety Rules

- Live ECM tests can affect the actual agent/download flow. Announce the specific center, root, project number, and selection mode before running a live test.
- If selecting fewer than all documents, make sure the download verification expectation matches the reduced selection.
- Do not expose internal absolute paths in user-facing results.
- Keep screenshots and stack traces in admin logs or local diagnostics only.

## Useful Questions To Resolve Ambiguity

Ask only if the prompt cannot be safely mapped:

- Which center: `상암` or `영남`?
- Which root occurrence when the same label appears more than once?
- Exact folder name or contains-match keyword?
- Select all document-list rows, first row only, or file-name/extension filter?
- Should this be a one-off live test or a reusable code path?

