/**
 * prdinfo_download.js
 * - #btn-download 클릭 → Luckysheet에서 값 수집(줄바꿈 보존) → 서버 POST → XLSX 다운로드
 * - 대상 시트/셀:
 *   · '제품 정보 요청' 시트: B5~N5, B7~N7, B9, D9, F9, G9, H9, J9, L9
 *   · '결함정보' 시트: B4~O4
 * - 서버 파일은 덮어쓰지 않으며, 템플릿 사본에 값만 채워 응답(백엔드는 download_filled_prdinfo 뷰).
 */
(() => {
  "use strict";

  // ─────────────────────────────────────────────
  // 설정
  // ─────────────────────────────────────────────
  const ENDPOINT = "/download-filled/";
  const DOWNLOAD_NAME = "prdinfo_filled.xlsx";
  const SHEET_PRD = "제품 정보 요청";
  const SHEET_DEF = "결함정보";

  // ─────────────────────────────────────────────
  // Luckysheet 접근 & 시트 찾기
  // ─────────────────────────────────────────────
  const LS = () => window.luckysheet || window.Luckysheet || null;

  const norm = (s) =>
    String(s || "")
      .replace(/\u3000/g, " ") // 전각 공백 → 공백
      .replace(/\s+/g, " ")    // 다중 공백 축소
      .trim()
      .toLowerCase();

  const getSheets = () =>
    (LS()?.getAllSheets?.() ||
     (typeof $.luckysheet?.getLuckysheetfile === "function" && $.luckysheet.getLuckysheetfile()) ||
     window.luckysheetfile ||
     []);

  const findSheetEntry = (name) => {
    const want = norm(name);
    let files = getSheets();
    if (!Array.isArray(files)) files = [files].filter(Boolean);
    const entry = files.find(s => norm(s?.name ?? s?.title ?? "") === want) || null;
    if (!entry) {
      try {
        const names = files.map(s => s?.name ?? s?.title).filter(Boolean);
        console.warn("[prdinfo] 시트를 찾지 못했습니다. 현재 시트들:", names);
      } catch {}
    }
    return entry;
  };

  // ─────────────────────────────────────────────
  // 셀 주소/컬럼 변환 유틸
  // ─────────────────────────────────────────────
  const colToIndex = (col) => [...col].reduce((n, ch) => n * 26 + (ch.charCodeAt(0) - 64), 0); // "B"→2
  const idxToLetters = (c0) => { // 0-based → "A".."Z".."AA"
    let n = c0 + 1, s = "";
    while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = ((n - 1) / 26) | 0; }
    return s;
  };
  const addrToRC0 = (addr) => { // "B5" → {r0,c0} 0-based
    const m = /^([A-Z]+)(\d+)$/.exec(addr);
    if (!m) throw new Error("Invalid address: " + addr);
    return { r0: parseInt(m[2], 10) - 1, c0: colToIndex(m[1]) - 1 };
  };

  // ─────────────────────────────────────────────
  // 멀티라인/리치텍스트 안전 추출
  // ─────────────────────────────────────────────
  const htmlToText = (s) =>
    String(s ?? "")
      .replace(/&nbsp;/gi, " ")
      .replace(/&#10;|&#x0a;|&#13;|&#x0d;/gi, "\n") // 엔티티 개행
      .replace(/\r\n?/g, "\n")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p>/gi, "\n")
      .replace(/<\/(div|li|p)>/gi, "\n")
      .replace(/<[^>]+>/g, "");

  // 지정 시트의 data/celldata 에서만 셀 객체 조회(활성 시트/글로벌 API 영향 배제)
  const getCellObjStrict = (sheetEntry, r0, c0) => {
    let cell = sheetEntry?.data?.[r0]?.[c0] || null;
    if (!cell && Array.isArray(sheetEntry?.celldata)) {
      const hit = sheetEntry.celldata.find(e => e?.r === r0 && e?.c === c0);
      if (hit && hit.v) cell = hit.v;
    }
    return cell;
  };

  // 셀 텍스트 추출(줄바꿈 포함)
  const extractTextStrict = (cell) => {
    if (!cell) return "";

    // 1) 표시 문자열 m (HTML 가능)
    if (typeof cell.m === "string" && cell.m !== "") return htmlToText(cell.m);

    // 2) 리치 텍스트 ct.s
    if (Array.isArray(cell?.ct?.s)) {
      return htmlToText(cell.ct.s.map(r => r?.v ?? r?.text ?? "").join(""));
    }

    // 3) v 가 문자열
    if (typeof cell.v === "string") return htmlToText(cell.v);

    // 4) v.s / v.r
    if (Array.isArray(cell?.v?.s)) {
      return htmlToText(cell.v.s.map(r => r?.v ?? r?.text ?? "").join(""));
    }
    if (Array.isArray(cell?.v?.r)) {
      return htmlToText(cell.v.r.map(r => r?.v ?? r?.text ?? "").join(""));
    }

    // 5) 숫자/불리언
    if (typeof cell.v === "number" || typeof cell.v === "boolean") return String(cell.v);

    return "";
  };

  const readCellStrict = (sheetEntry, addr) => {
    const { r0, c0 } = addrToRC0(addr);
    const obj = getCellObjStrict(sheetEntry, r0, c0);
    let text = extractTextStrict(obj);
    if (text && text.includes("\\n")) text = text.replace(/\\n/g, "\n"); // 이스케이프 복원
    return text;
  };

  // 같은 행의 연속 범위(B..N 등)
  const readRowRangeStrict = (sheetEntry, row1, colStart, colEnd) => {
    const out = [];
    for (let c = colToIndex(colStart) - 1; c <= colToIndex(colEnd) - 1; c++) {
      out.push(readCellStrict(sheetEntry, `${idxToLetters(c)}${row1}`));
    }
    return out;
  };

  // ─────────────────────────────────────────────
  // CSRF & 다운로드
  // ─────────────────────────────────────────────
  const getCsrf = () =>
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    (document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/)?.[2] ?? "");

  const downloadBlob = async (res, filename) => {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  // ─────────────────────────────────────────────
  // 메인: 값 수집 → 서버 POST → 파일 다운로드
  // ─────────────────────────────────────────────
  async function onDownload(btn) {
    try {
      if (btn) { btn.disabled = true; btn.textContent = "생성 중…"; }

      const prd = findSheetEntry(SHEET_PRD);
      const def = findSheetEntry(SHEET_DEF);
      if (!prd || !def) { alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)"); return; }

      // 제품 정보 요청
      const prdinfo = {
        row_B5_N5: readRowRangeStrict(prd, 5, "B", "N"),
        row_B7_N7: readRowRangeStrict(prd, 7, "B", "N"),
        B9: readCellStrict(prd, "B9"),
        D9: readCellStrict(prd, "D9"),
        F9: readCellStrict(prd, "F9"),
        G9: readCellStrict(prd, "G9"),
        H9: readCellStrict(prd, "H9"),
        J9: readCellStrict(prd, "J9"),
        L9: readCellStrict(prd, "L9"),
      };

      // 결함정보 B4~O4
      const defect = { row_B4_O4: readRowRangeStrict(def, 4, "B", "O") };

      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
        body: JSON.stringify({ prdinfo, defect }),
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));

      await downloadBlob(res, DOWNLOAD_NAME);
    } catch (e) {
      console.error(e);
      alert(e.message || "다운로드 중 오류가 발생했습니다.");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "엑셀 다운로드"; }
    }
  }

  // ─────────────────────────────────────────────
  // 바인딩
  // ─────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("btn-download");
    if (!btn) {
      console.warn('[prdinfo] "#btn-download" 버튼을 찾지 못했습니다.');
      return;
    }
    btn.addEventListener("click", () => onDownload(btn), { passive: true });
  });
})();
