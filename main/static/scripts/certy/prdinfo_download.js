/**
 * strict_reader.js
 * - #btn-download → Luckysheet 지정 범위를 "해당 시트 data/celldata"에서만 읽음
 * - 줄바꿈 보존(\n), 서버 통신 없음(콘솔 디버그용)
 */
(() => {
  "use strict";

  const SHEET_PRD = "제품 정보 요청";
  const SHEET_DEF = "결함정보";

  // ── 헬퍼
  const LS = () => window.luckysheet || window.Luckysheet || null;

  const norm = (s) =>
    String(s || "")
      .replace(/\u3000/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  const getSheets = () =>
    (LS()?.getAllSheets?.() ||
     $.luckysheet?.getLuckysheetfile?.() ||
     window.luckysheetfile || []);

  const findSheetEntry = (name) => {
    const want = norm(name);
    let files = getSheets();
    if (!Array.isArray(files)) files = [files].filter(Boolean);
    const entry = files.find(s => norm(s?.name ?? s?.title ?? "") === want) || null;
    if (!entry) {
      const names = files.map(s => s?.name ?? s?.title).filter(Boolean);
      console.warn("[strict_reader] 시트를 찾지 못함. 현재 시트들:", names);
    }
    return entry;
  };

  const colToIndex = (col) => [...col].reduce((n, ch) => n * 26 + (ch.charCodeAt(0) - 64), 0);
  const idxToLetters = (c0) => { let n=c0+1,s=""; while(n>0){ const r=(n-1)%26; s=String.fromCharCode(65+r)+s; n=((n-1)/26)|0; } return s; };

  const addrToRC0 = (addr) => {
    const m = /^([A-Z]+)(\d+)$/.exec(addr);
    if (!m) throw new Error("Invalid address: " + addr);
    return { r0: parseInt(m[2], 10) - 1, c0: colToIndex(m[1]) - 1 };
  };

  // HTML/엔티티 → \n 정규화 (줄바꿈 보존)
  const htmlToText = (s) =>
    String(s ?? "")
      .replace(/&nbsp;/gi, " ")
      .replace(/&#10;|&#x0a;|&#13;|&#x0d;/gi, "\n")
      .replace(/\r\n?/g, "\n")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p>/gi, "\n")
      .replace(/<\/(div|li|p)>/gi, "\n")
      .replace(/<[^>]+>/g, "");

  // 지정 시트의 data/celldata 에서만 셀 객체 조회
  const getCellObjStrict = (sheetEntry, r0, c0) => {
    let cell = sheetEntry?.data?.[r0]?.[c0] || null;
    if (!cell && Array.isArray(sheetEntry?.celldata)) {
      const hit = sheetEntry.celldata.find(e => e?.r === r0 && e?.c === c0);
      if (hit && hit.v) cell = hit.v;
    }
    return cell;
  };

  // 셀 텍스트 추출(줄바꿈 포함) — 절대 다른 시트 API에 의존하지 않음
  const extractTextStrict = (cell) => {
    if (!cell) return "";

    // 1) 표시 문자열 m
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
    // Luckysheet가 \\n 으로 이스케이프한 경우 복원
    if (text && text.includes("\\n")) text = text.replace(/\\n/g, "\n");
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

  // 클릭 → 수집 → 콘솔
  const onClick = () => {
    const prd = findSheetEntry(SHEET_PRD);
    const def = findSheetEntry(SHEET_DEF);
    if (!prd || !def) {
      alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)");
      return;
    }

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

    const defect = {
      row_B4_O4: readRowRangeStrict(def, 4, "B", "O"),
    };

    console.clear();
    console.log("=== prdinfo (제품 정보 요청) ===\n", JSON.stringify(prdinfo, null, 2));
    console.log("=== defect (결함정보) ===\n", JSON.stringify(defect, null, 2));

    // 전역 확인용
    window.__PRDINFO__ = prdinfo;
    window.__DEFECT__  = defect;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("btn-download");
    if (!btn) { console.warn('[strict_reader] "#btn-download" 버튼 없음'); return; }
    btn.addEventListener("click", onClick, { passive: true });
  });
})();
