def css_attr_eq(attr: str, value: str) -> str:
    v = (value or "").replace('"', '\\"')
    return f'[{attr}="{v}"]'


# ===== DOM Selectors (ECM 화면) =====

DOC_ROOT = "#main-list-document"
DOC_TABLE = f"{DOC_ROOT} table.document-list-table"
DOC_ROW_ALL = f"{DOC_ROOT} tr.document-list-item"
DOC_CLICK_SPAN_IN_ROW = 'span[events="document-list-viewDocument-click"]'

LEFT_PANEL_MENU = "#edm-left-panel-menu"
FOLDER_PANEL_ACTIVE = (
    'div.edm-left-panel-menu-sub-item[submenu_type="Folder"].ui-accordion-content-active'
)
FOLDER_TREE = "#edm-folder"  # jstree container

# 파일 목록 (문서 상세/속성 영역)
FILE_ROW = "tr.prop-view-file-list-item"

# URL 복사 버튼
URL_COPY_BTN = "div#prop-view-document-btn-url-copy"
