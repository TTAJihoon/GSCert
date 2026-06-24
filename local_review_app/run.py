from __future__ import annotations

import sys

from gscert_local_review.app import main


def _self_check() -> int:
    import fitz  # noqa: F401
    import openpyxl  # noqa: F401
    import xlrd.compdoc  # noqa: F401
    from lxml import etree  # noqa: F401

    from gscert_review_core import engine

    context = engine.build_context(project_number="SELF-CHECK")
    result = engine.evaluate_rules([], context, [])
    return 0 if result == [] else 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        raise SystemExit(_self_check())
    raise SystemExit(main())
