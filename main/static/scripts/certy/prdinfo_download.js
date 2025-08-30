/**
 * 최소·새출발 버전
 * - #btn-download 클릭 → Luckysheet에서 지정 범위 값만 읽어 JSON으로 콘솔 출력
 * - 서버 통신/엑셀 생성 없음 (디버그용)
 */
(() => {
  "use strict";

  // 시트명
  const SHEET_PRD = "제품 정보 요청";
  const SHEET_DEF = "결함정보";

  // Luckysheet 핸들
  const LS = () => window.luckysheet || window.Luckysheet || null;

  // 공백/대소문자/전각 공백까지 정규화
  const norm = (s) =>
    String(s || "")
      .replace(/\u3000/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  // 시트 목록 획득 (빌드차 방어)
  const getSheets = () =>
    (LS()?.getAllSheets?.() ||
     $.luckysheet?.getLuckysheetfile?.() ||
     window.luckysheetfile ||
     []);

  // 시트 이름으로 파일엔트리 찾기
  const findSheet = (name) => {
    const want = norm(name);
    let files = getSheets();
    if (!Array.isArray(files)) files = [files].filter(Boolean);
    const entry = files.find(s => norm(s?.name ?? s?.title ?? "") === want) || null;

    if (!entry) {
      try {
        const names = files.map(s => s?.name ?? s?.title).filter(Boolean);
        console.warn("[debug] 현재 시트들:", names);
      } catch {}
    }
    return entry;
  };

  // "B" -> 2 (1-based)
  const colToIndex = (col) => [...col].reduce((n, ch) => n * 26 + (ch.charCodeAt(0) - 64), 0);

  // "B5" -> {r0, c0} (0-based)
  const addrToRC0 = (addr) => {
    const m = /^([A-Z]+)(\d+)$/.exec(addr);
    if (!m) throw new Error("Invalid address: " + addr);
    return { r0: parseInt(m[2], 10) - 1, c0: colToIndex(m[1]) - 1 };
  };

  // Luckysheet가 줄바꿈/리치텍스트를 담는 형식을 \n로 정규화
  const normalizeMultiline = (v) =>
    (v == null ? "" : String(v))
      .replace(/\r\n?/g, "\n")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p>/gi, "\n")
      .replace(/<\/?[^>]+>/g, "");

  // 셀 1개 읽기: grid raw 우선, 없으면 API로 보조
  const readCell = (sheetEntry, addr) => {
    const { r0, c0 } = addrToRC0(addr);
    const id = sheetEntry.index ?? sheetEntry.id ?? sheetEntry.sheetid ?? sheetEntry.sheetId;
    const grid = sheetEntry?.data;
    const cell = grid?.[r0]?.[c0];

    let raw = "";
    if (cell && (cell.v != null || cell.m != null)) {
      // m(표시 문자열) 우선, 없으면 v
      raw = (typeof cell.m === "string" && cell.m !== "") ? cell.m : cell.v;
    } else {
      raw = LS()?.getCellValue?.(r0, c0, id) ?? "";
    }
    return normalizeMultiline(raw);
  };

  // 같은 행의 연속 범위 읽기: B..N 같은 식
  const readRowRange = (sheetEntry, row1, colStart, colEnd) => {
    const out = [];
    const r0 = row1 - 1;
    for (let c = colToIndex(colStart) - 1; c <= colToIndex(colEnd) - 1; c++) {
      const addr = colName(c) + row1;
      out.push(readCell(sheetEntry, addr));
    }
    return out;
  };

  // 0-based column index -> "A".."Z".. "AA"
  const colName = (c0) => {
    let n = c0 + 1, s = "";
    while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = ((n - 1) / 26) | 0; }
    return s;
  };

  // 클릭 핸들러: JSON으로 콘솔에 출력
  const onClick = () => {
    const prd = findSheet(SHEET_PRD);
    const def = findSheet(SHEET_DEF);

    if (!prd || !def) {
      alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)");
      return;
    }

    // ── 제품 정보 요청
    const prdinfo = {
      row_B5_N5: readRowRange(prd, 5, "B", "N"), // B5~N5
      row_B7_N7: readRowRange(prd, 7, "B", "N"), // B7~N7
      B9: readCell(prd, "B9"),
      D9: readCell(prd, "D9"),
      F9: readCell(prd, "F9"),
      G9: readCell(prd, "G9"),
      H9: readCell(prd, "H9"),
      J9: readCell(prd, "J9"),
      L9: readCell(prd, "L9"),
    };

    // ── 결함정보 (요청: B4~O4)
    const defect = {
      row_B4_O4: readRowRange(def, 4, "B", "O"),
    };

    // 콘솔 출력 (JSON 확인)
    console.log("=== prdinfo (제품 정보 요청) ===");
    console.log(JSON.stringify(prdinfo, null, 2));
    console.log("=== defect (결함정보) ===");
    console.log(JSON.stringify(defect, null, 2));

    // 편의: 전역에서도 확인 가능하게 노출
    window.__PRDINFO__ = prdinfo;
    window.__DEFECT__  = defect;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("btn-download");
    if (!btn) {
      console.warn('[debug] 버튼 "#btn-download"를 찾지 못했습니다.');
      return;
    }
    btn.addEventListener("click", onClick, { passive: true });
  });
})();
