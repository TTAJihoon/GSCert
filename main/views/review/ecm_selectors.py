"""download-review 전용 CSS selector 상수."""

# --- 좌측 폴더 트리 ---
FOLDER_TREE = "#edm-folder"
LEFT_PANEL_MENU = "#edm-left-panel-menu"
FOLDER_PANEL_ACTIVE = (
    'div.edm-left-panel-menu-sub-item[submenu_type="Folder"]'
    '.ui-accordion-content-active'
)

# --- 로딩 오버레이 ---
SPLASHSCREEN = "#edmframe-contents .splashscreen"

# --- 문서 목록 ---
DOC_TABLE = "#main-list-document table.document-list-table"
DOC_ROWS = "#main-list-document tr.document-list-item"

# --- 전체 선택 체크박스 ---
SELECT_ALL_CHECKBOX = (
    "#main-list-document > table > thead > tr "
    "> th.document-list-header-checkbox > input[type=checkbox]"
)

# --- 고급 메뉴 ---
ADVANCED_MENU_BTN = "#menu-folder-list-drop"
CONTEXT_MENU = "#edm-main-context-menu"
DOWNLOAD_MENU_ITEM = '#edm-main-context-menu li[menuevent="saveDocumentsFileAll"]'
DOWNLOAD_MENU_FALLBACK = "#edm-main-context-menu > li:nth-child(10)"
