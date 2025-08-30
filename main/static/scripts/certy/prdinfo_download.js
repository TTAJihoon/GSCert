/**
 * Luckysheet 다줄(줄바꿈) 텍스트 완전 추출 디버그 코드
 * - #btn-download 클릭 → 지정 범위를 읽어 JSON을 콘솔에 출력
 * - 줄바꿈/리치텍스트/HTML 브레이크를 \n 로 보존
 */
(() => {
  "use strict";

  const SHEET_PRD = "제품 정보 요청";
  const SHEET_DEF = "결함정보";

  const LS = () => window.luckysheet || window.Luckysheet || null;

  // ── 유틸
  const norm = (s) =>
    String(s || "").replace(/\u3000/g, " ").replace(/\s+/g, " ").trim().toLowerCase();

  const getSheets = () =>
    (LS()?.getAllSheets?.() ||
     $.luckysheet?.getLuckysheetfile?.() ||
     window.luckysheetfile ||
     []);

  const findSheet = (name) => {
    const want = norm(name);
    let files = getSheets();
    if (!Array.isArray(files)) files = [files].filter(Boolean);
    const entry = files.find(s => norm(s?.name ?? s?.title ?? "") === want) || null;
    if (!entry) {
      const names = files.map(s => s?.name ?? s?.title).filter(Boolean);
      console.warn("[debug] 현재 시트들:", names);
    }
    return entry;
  };

  const colToIndex = (col) => [...col].reduce((n, ch) => n * 26 + (ch.charCodeAt(0) - 64), 0);
  const idxToLetters = (c0) => { let n=c0+1,s=""; while(n>0){ const r=(n-1)%26; s=String.fromCharCode(65+r)+s; n=((n-1)/26)|0; } return s; };
  const addrToRC0 = (addr) => { const m=/^([A-Z]+)(\d+)$/.exec(addr); if(!m) throw new Error("Invalid address: "+addr); return { r0:+m[2]-1, c0: colToIndex(m[1])-1 }; };

  // HTML/엔터티/줄바꿈 정규화: 줄바꿈을 \n 로 보존
  const htmlToText = (s) =>
    String(s ?? "")
      .replace(/&nbsp;/gi, " ")
      .replace(/&#10;|&#x0a;|&#13;|&#x0d;/gi, "\n")   // HTML 엔티티 개행
      .replace(/\r\n?/g, "\n")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p>/gi, "\n")
      .replace(/<\/(div|li|p)>/gi, "\n")
      .replace(/<[^>]+>/g, "");

  // 셀 오브젝트 획득(data 2D 우선, celldata 보조)
  const getCellObj = (sheetEntry, r0, c0) => {
    let cell = sheetEntry?.data?.[r0]?.[c0];
    if (!cell && Array.isArray(sheetEntry?.celldata)) {
      const hit = sheetEntry.celldata.find(e => e?.r === r0 && e?.c === c0);
      if (hit && hit.v) cell = hit.v;
    }
    return cell || null;
  };

  // 후보 텍스트 모두 수집 → 정규화 → 가장 긴 후보 선택
  const extractFullText = (cell, apiVal) => {
    const cand = [];

    // 1) 표시 문자열 m (HTML 가능)
    if (typeof cell?.m === "string") cand.push(htmlToText(cell.m));

    // 2) v 가 문자열
    if (typeof cell?.v === "string") cand.push(htmlToText(cell.v));

    // 3) 리치 텍스트 ct.s (런 배열)
    if (Array.isArray(cell?.ct?.s)) {
      cand.push(htmlToText(cell.ct.s.map(r => r?.v ?? r?.text ?? "").join("")));
    }

    // 4) v.s / v.r 형태
    if (Array.isArray(cell?.v?.s)) {
      cand.push(htmlToText(cell.v.s.map(r => r?.v ?? r?.text ?? "").join("")));
    }
    if (Array.isArray(cell?.v?.r)) {
      cand.push(htmlToText(cell.v.r.map(r => r?.v ?? r?.text ?? "").join("")));
    }

    // 5) 숫자/불리언 등
    if (typeof cell?.v === "number" || typeof cell?.v === "boolean") {
      cand.push(String(cell.v));
    }

    // 6) API 값 (종종 한 줄만 오지만 백업으로 포함)
    if (apiVal != null && apiVal !== "") cand.push(htmlToText(apiVal));

    // 최장 텍스트를 채택(잘림 방지)
    let best = "";
    for (const s of cand) if (String(s).length > best.length) best = String(s);

    // Luckysheet가 이스케이프한 \\n 이 들어오는 경우 한 번 더 복원
    best = best.replace(/\\n/g, "\n");

    return best;
  };

  // 셀 읽기(줄바꿈 보존)
  const readCell = (sheetEntry, addr) => {
    const { r0, c0 } = addrToRC0(addr);
    const sid = sheetEntry.index ?? sheetEntry.id ?? sheetEntry.sheetid ?? sheetEntry.sheetId;
    const obj = getCellObj(sheetEntry, r0, c0);
    const apiVal = LS()?.getCellValue?.(r0, c0, sid) ?? "";
    return extractFullText(obj, apiVal);
  };

  // 같은 행의 연속 범위(B..N 등)
  const readRowRange = (sheetEntry, row1, colStart, colEnd) => {
    const out = [];
    for (let c = colToIndex(colStart) - 1; c <= colToIndex(colEnd) - 1; c++) {
      out.push(readCell(sheetEntry, `${idxToLetters(c)}${row1}`));
    }
    return out;
  };

  // 버튼 클릭: 값 수집 → 콘솔 출력
  const onClick = () => {
    const prd = findSheet(SHEET_PRD);
    const def = findSheet(SHEET_DEF);
    if (!prd || !def) {
      alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)");
      return;
    }

    const prdinfo = {
      row_B5_N5: readRowRange(prd, 5, "B", "N"),
      row_B7_N7: readRowRange(prd, 7, "B", "N"),
      B9: readCell(prd, "B9"),
      D9: readCell(prd, "D9"),
      F9: readCell(prd, "F9"),
      G9: readCell(prd, "G9"),
      H9: readCell(prd, "H9"),
      J9: readCell(prd, "J9"),
      L9: readCell(prd, "L9"),
    };

    const defect = {
      row_B4_O4: readRowRange(def, 4, "B", "O"),
    };

    console.clear();
    console.log("=== prdinfo (제품 정보 요청) ===\n", JSON.stringify(prdinfo, null, 2));
    console.log("=== defect (결함정보) ===\n", JSON.stringify(defect, null, 2));

    // 전역 디버깅 핸들
    window.__PRDINFO__ = prdinfo;
    window.__DEFECT__  = defect;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("btn-download");
    if (!btn) { console.warn('[debug] "#btn-download" 버튼을 찾지 못했습니다.'); return; }
    btn.addEventListener("click", onClick, { passive: true });
  });
})();
