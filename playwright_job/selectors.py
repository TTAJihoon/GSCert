# ---- Left tree / layout ----
LEFT_PANEL_MENU = "#edm-left-panel-menu"
FOLDER_PANEL_ACTIVE = (
    'div.edm-left-panel-menu-sub-item[submenu_type="Folder"].ui-accordion-content-active'
)
FOLDER_TREE = "#edm-folder"

# 로딩 오버레이(있을 때도/없을 때도 안전하게 hidden 대기 가능)
SPLASHSCREEN = "#edmframe-contents .splashscreen"

# 상단 타이틀(현재 선택된 폴더명 표시)
CONTENT_TITLE_TEXT = "#main-list-menu .contents-title-text span"

# ---- Document list (center) ----
DOC_ROOT = "#main-list-document"
DOC_TABLE = f"{DOC_ROOT} table.document-list-table"
DOC_ROW_ALL = f"{DOC_ROOT} tr.document-list-item"
DOC_CLICK_SPAN_IN_ROW = 'span[events="document-list-viewDocument-click"]'

# ---- File list / URL copy (properties pane) ----
FILE_ROW = "tr.prop-view-file-list-item"
URL_COPY_BTN = "div#prop-view-document-btn-url-copy"
