(() => {
  "use strict";

  const ENDPOINT = "/certy/prdinfo/download-filled/";
  const FNAME    = "prdinfo_filled.xlsx";
  const SHEET_PRD = "제품 정보 요청";
  const SHEET_DEF = "결함정보";

  // ── Luckysheet 접근
  const LS = () => window.luckysheet || window.Luckysheet;

  // ── 도우미
  const norm = (s) =>
    String(s || "")
      .replace(/\u3000/g, " ") // 전각 공백 → 일반 공백
      .replace(/\s+/g, " ")    // 다중 공백 축소
      .trim()
      .toLowerCase();

  const getSheets = () =>
    (LS()?.getAllSheets?.() ||
     $.luckysheet?.getLuckysheetfile?.() ||
     window.luckysheetfile || []);

  const findSheet = (name) => {
    const want = norm(name);
    let files = getSheets();
    if (!Array.isArray(files)) files = [files].filter(Boolean);
    return files.find(s => norm(s?.name ?? s?.title ?? "") === want) || null;
  };

  const colToIndex = (col) => [...col].reduce((n, ch) => n * 26 + (ch.charCodeAt(0) - 64), 0);
  const idxToLetters = (n) => { let s=""; while(n>0){ const r=(n-1)%26; s=String.fromCharCode(65+r)+s; n=(n-1)/26|0; } return s; };

  const normalizeMultiline = (v) =>
    (v == null ? "" : String(v))
      .replace(/\r\n?/g, "\n")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p>/gi, "\n")
      .replace(/<div>/gi, "\n")
      .replace(/<\/?[^>]+>/g, ""); // 남은 HTML 제거

  // raw grid 우선 → API 보조로 값 읽기 (줄바꿈 보존)
  const readCell = (sheet, addr) => {
    const m = /^([A-Z]+)(\d+)$/.exec(addr);
    if (!m) return "";
    const r0 = (+m[2]) - 1;
    const c0 = colToIndex(m[1]) - 1;

    const grid = sheet?.data;
    const cell = grid?.[r0]?.[c0];
    let raw = "";
    if (cell && (cell.v != null || cell.m != null)) {
      raw = (typeof cell.v === "string") ? cell.v : (cell.m ?? cell.v ?? "");
    } else {
      raw = LS()?.getCellValue?.(r0, c0, sheet.index ?? sheet.id ?? sheet.sheetid ?? sheet.sheetId) ?? "";
    }
    return normalizeMultiline(raw);
  };

  // 같은 행의 B..N 읽기
  const readRow = (sheet, row1, c1, c2) => {
    const out = [];
    for (let j = colToIndex(c1); j <= colToIndex(c2); j++) {
      out.push(readCell(sheet, `${idxToLetters(j)}${row1}`));
    }
    return out;
  };

  const getCsrf = () =>
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    (document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/)?.[2] ?? "");

  // ── 메인
  async function onDownload(btn) {
    try {
      if (btn) { btn.disabled = true; btn.textContent = "생성 중…"; }

      const prd = findSheet(SHEET_PRD);
      const def = findSheet(SHEET_DEF);
      if (!prd || !def) {
        alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)");
        return;
      }

      // 제품 정보 요청
      const row_B5_N5 = readRow(prd, 5, "B", "N");
      const row_B7_N7 = readRow(prd, 7, "B", "N");
      const B9 = readCell(prd, "B9");
      const D9 = readCell(prd, "D9");
      const F9 = readCell(prd, "F9");
      const G9 = readCell(prd, "G9");
      const H9 = readCell(prd, "H9");
      const J9 = readCell(prd, "J9");
      const L9 = readCell(prd, "L9");

      // 결함정보
      const row_B4_N4 = readRow(def, 4, "B", "N");

      const payload = {
        prdinfo: { row_B5_N5, row_B7_N7, B9, D9, F9, G9, H9, J9, L9 },
        defect : { row_B4_N4 }
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
      console.error(e);
      alert(e.message || "다운로드 중 오류가 발생했습니다.");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "다운로드"; }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("btn-download");
    if (btn) btn.addEventListener("click", () => onDownload(btn), { passive: true });
  });
})();
