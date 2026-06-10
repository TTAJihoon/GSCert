(function () {
  const STORAGE_KEY = "historyTableColumnWidths";
  const DEFAULT_WIDTHS = [90, 80, 110, 200, 200, 170, 80, 100, 100, 110, 50, 100, 70, 70];
  const MIN_WIDTHS = [72, 72, 86, 120, 120, 120, 64, 86, 86, 80, 44, 76, 62, 62];

  function readWidths() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (!Array.isArray(parsed)) return DEFAULT_WIDTHS.slice();
      return DEFAULT_WIDTHS.map((width, index) => Number(parsed[index]) || width);
    } catch (error) {
      return DEFAULT_WIDTHS.slice();
    }
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

      const widths = readWidths();
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
