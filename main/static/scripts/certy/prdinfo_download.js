(() => {
  "use strict";

  const ENDPOINT = "/certy/prdinfo/download-filled/";
  const FNAME = "prdinfo_filled.xlsx";
  const SHEET_PRD = "제품 정보 요청";
  const SHEET_DEF = "결함정보";

  // ── Luckysheet helpers
  const LS = () => window.luckysheet || window.Luckysheet;

  const getSheetId = (name) => {
    const files =
      (LS()?.getAllSheets?.() || $.luckysheet?.getLuckysheetfile?.() || window.luckysheetfile || []);
    const arr = Array.isArray(files) ? files : [files];
    const f = arr.find(s => (s?.name || s?.title) === name);
    return f ? (f.index ?? f.id ?? f.sheetid ?? f.sheetId) : null;
  };

  const colToIndex = (col) => { // "B" -> 2 (1-based)
    let n = 0; for (let ch of col) n = n * 26 + (ch.charCodeAt(0) - 64); return n;
  };

  const getRowValues = (sheetId, row1, colStart, colEnd) => {
    const r0 = row1 - 1, s = colToIndex(colStart) - 1, e = colToIndex(colEnd) - 1;
    const out = [];
    for (let c = s; c <= e; c++) out.push(LS().getCellValue(r0, c, sheetId) ?? "");
    return out;
  };

  const getCell = (sheetId, addr) => {
    const m = /^([A-Z]+)(\d+)$/.exec(addr);
    const r0 = (+m[2]) - 1, c0 = colToIndex(m[1]) - 1;
    return LS().getCellValue(r0, c0, sheetId) ?? "";
  };

  const getCsrf = () =>
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    (document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/)?.[2] ?? "");

  // ── Main
  async function onDownload(btn) {
    try {
      btn && (btn.disabled = true, btn.textContent = "생성 중…");

      const prdId = getSheetId(SHEET_PRD);
      const defId = getSheetId(SHEET_DEF);
      if (prdId == null || defId == null) {
        alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)");
        return;
      }

      // 제품 정보 요청
      const row_B5_N5 = getRowValues(prdId, 5, "B", "N");
      const row_B7_N7 = getRowValues(prdId, 7, "B", "N");
      const B9 = getCell(prdId, "B9"), D9 = getCell(prdId, "D9"), F9 = getCell(prdId, "F9");
      const G9 = getCell(prdId, "G9"), H9 = getCell(prdId, "H9");
      const J9 = getCell(prdId, "J9"), L9 = getCell(prdId, "L9");

      // 결함정보
      const row_B4_N4 = getRowValues(defId, 4, "B", "N");

      const payload = {
        prdinfo: { row_B5_N5, row_B7_N7, B9, D9, F9, G9, H9, J9, L9 },
        defect:  { row_B4_N4 }
      };

      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href: url, download: FNAME });
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e); alert(e.message || "다운로드 중 오류가 발생했습니다.");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "엑셀 다운로드"; }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("btn-download");
    if (btn) btn.addEventListener("click", () => onDownload(btn), { passive: true });
  });
})();
