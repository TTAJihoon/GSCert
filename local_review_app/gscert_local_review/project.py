from __future__ import annotations

import re
from pathlib import Path


PROJECT_NUMBER_PATTERN = re.compile(r"\b[A-Z]{2,5}-\d{2}-\d{5}\b", re.IGNORECASE)


def infer_project_number(folder: Path) -> str:
    candidates = []
    for text in [folder.name, *[child.name for child in folder.iterdir()]]:
        match = PROJECT_NUMBER_PATTERN.search(text)
        if match:
            candidates.append(match.group(0).upper())
    return candidates[0] if candidates else ""
