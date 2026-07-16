(function () {
  const STORAGE_KEY = "historyTableColumnWidths";
  const DEFAULT_WIDTHS = [90, 80, 110, 200, 200, 170, 80, 100, 100, 110, 50, 150, 90];
  const MIN_WIDTHS = [72, 72, 86, 120, 120, 120, 64, 86, 86, 80, 44, 100, 64];
  // '제품 개요'(col-overview) 컬럼: 저장된 커스텀 폭이 없는 첫 방문에 한해서만,
  // 그 순간 실제 남는 공간을 채우도록 초기값을 계산한다. 이후에는 다른 컬럼과 동일하게
  // 일반 숫자로 취급되어 자유롭게 리사이즈되고(100% 초과/스크롤도 가능) localStorage에 저장된다.
  const OVERVIEW_COLUMN_INDEX = 5;

  function readWidths(table) {
    let parsed = [];
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (Array.isArray(raw)) parsed = raw;
    } catch (error) {
      parsed = [];
    }

    const widths = DEFAULT_WIDTHS.map((width, index) => Number(parsed[index]) || width);

    if (!Number(parsed[OVERVIEW_COLUMN_INDEX])) {
      const otherWidthsSum = widths.reduce((sum, width, index) => (
        index === OVERVIEW_COLUMN_INDEX ? sum : sum + width
      ), 0);
      const container = table && (table.closest(".table-container") || table.closest(".scrollable-table-wrapper"));
      const availableWidth = (container && container.clientWidth) || window.innerWidth;
      widths[OVERVIEW_COLUMN_INDEX] = Math.max(
        MIN_WIDTHS[OVERVIEW_COLUMN_INDEX] || 120,
        availableWidth - otherWidthsSum
      );
    }

    return widths;
  }

  function writeWidths(widths) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(widths.map((width) => Math.round(width))));
    } catch (error) {
      // Keep resize working even when localStorage is unavailable.
    }
  }

  function applyWidths(table, widths) {
    const cols = Array.from(table.querySelectorAll("colgroup col"));
    cols.forEach((col, index) => {
      col.style.width = `${widths[index] || DEFAULT_WIDTHS[index] || 100}px`;
    });

    const tableWidth = widths.reduce((sum, width) => sum + width, 0);
    table.style.width = `${tableWidth}px`;
    table.style.minWidth = `${tableWidth}px`;

    const wrapper = table.closest(".scrollable-table-wrapper");
    if (wrapper) {
      wrapper.style.minWidth = `${tableWidth}px`;
    }
  }

  function startResize(event, table, widths, index, handle, eventNames) {
    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = widths[index];
    document.body.classList.add("history-column-resizing");
    table.classList.add("is-resizing");

    const onMove = (moveEvent) => {
      widths[index] = Math.max(MIN_WIDTHS[index] || 72, startWidth + moveEvent.clientX - startX);
      applyWidths(table, widths);
    };

    const onUp = () => {
      writeWidths(widths);
      document.body.classList.remove("history-column-resizing");
      table.classList.remove("is-resizing");
      document.removeEventListener(eventNames.move, onMove);
      document.removeEventListener(eventNames.up, onUp);
      if (eventNames.cancel) {
        document.removeEventListener(eventNames.cancel, onUp);
      }
      if (event.pointerId !== undefined && handle.releasePointerCapture) {
        try {
          handle.releasePointerCapture(event.pointerId);
        } catch (error) {
          // Pointer capture can already be released by the browser.
        }
      }
    };

    if (event.pointerId !== undefined && handle.setPointerCapture) {
      handle.setPointerCapture(event.pointerId);
    }
    document.addEventListener(eventNames.move, onMove);
    document.addEventListener(eventNames.up, onUp);
    if (eventNames.cancel) {
      document.addEventListener(eventNames.cancel, onUp);
    }
  }

  function initHistoryTableResize() {
    document.querySelectorAll(".results-table").forEach((table) => {
      if (table.dataset.resizableColumns === "true") return;

      const headers = Array.from(table.querySelectorAll("thead th"));
      const cols = Array.from(table.querySelectorAll("colgroup col"));
      if (!headers.length || headers.length !== cols.length) return;

      const widths = readWidths(table);
      applyWidths(table, widths);
      table.dataset.resizableColumns = "true";
      table.classList.add("resizable-results-table");

      headers.forEach((header, index) => {
        header.classList.add("resizable-results-header");

        const handle = document.createElement("span");
        handle.className = "history-column-resize-handle";
        handle.setAttribute("role", "separator");
        handle.setAttribute("aria-orientation", "vertical");
        handle.setAttribute("aria-label", "열 너비 조정");
        header.appendChild(handle);

        handle.addEventListener("pointerdown", (event) => {
          startResize(event, table, widths, index, handle, {
            move: "pointermove",
            up: "pointerup",
            cancel: "pointercancel"
          });
        });
        handle.addEventListener("mousedown", (event) => {
          startResize(event, table, widths, index, handle, {
            move: "mousemove",
            up: "mouseup"
          });
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", initHistoryTableResize);
})();
