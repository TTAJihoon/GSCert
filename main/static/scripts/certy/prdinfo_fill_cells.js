(() => {
  // Luckysheet 핸들
  const LS = () => (window.luckysheet || window.Luckysheet);

  // 시트명 정규화(공백 제거 + 소문자)
  function normName(s) {
    return String(s || "").replace(/\s+/g, "").toLowerCase();
  }

  // 시트 찾기(정규화 완전일치 → 부분일치 → 첫 시트)
  function findSheet(files, targetName) {
    const t = normName(targetName);
    let s = files.find(x => normName(x.name) === t);
    if (s) return s;
    s = files.find(x => normName(x.name).includes(t));
    return s || files[0];
  }

  // "A1" → { r: 0-based row, c: 0-based col }
  function a1ToRC(a1) {
    if (!a1 || typeof a1 !== "string") return null;
    const m = a1.trim().match(/^([A-Za-z]+)(\d+)$/);
    if (!m) return null;
    const [, colStr, rowStr] = m;
    let col = 0;
    for (let i = 0; i < colStr.length; i++) {
      col = col * 26 + (colStr.charCodeAt(i) & 31);
    }
    return { r: parseInt(rowStr, 10) - 1, c: col - 1 };
  }

  // Luckysheet 준비 확인
  function ensureLSReady() {
    const api = LS();
    if (!api) throw new Error("Luckysheet 전역이 없습니다.");
    const files = (typeof api.getluckysheetfile === "function")
      ? api.getluckysheetfile()
      : null;
    if (!files || !files.length) throw new Error("Luckysheet 파일이 없습니다.");
    return { api, files };
  }

  // fillMap 적용
  async function apply(fillMap) {
    const { api, files } = ensureLSReady();
    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = findSheet(files, sheetName);
      if (!sheet) continue;

      // 문자열 index도 허용
      if (typeof api.setSheetActive === "function" && sheet.index) {
        try { api.setSheetActive(sheet.index); } catch (_) {}
      }

      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;

        let ok = false;
        try {
          if (typeof api.setCellValue === "function") {
            api.setCellValue(rc.r, rc.c, value);
            ok = true;
          }
        } catch (_) {}

        // API 실패 시 파일 데이터 직접 쓰기
        if (!ok) {
          const s = findSheet(files, sheetName);
          s.data = s.data || [];
          s.data[rc.r] = s.data[rc.r] || [];
          s.data[rc.r][rc.c] = { v: value, m: String(value) };
        }
      }
    }

    try {
      if (LS() && LS().refresh) LS().refresh();
    } catch (_) {}
  }

  window.PrdinfoFill = { apply };
})();
