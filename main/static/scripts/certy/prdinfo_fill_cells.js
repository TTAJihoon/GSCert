(() => {
  const LS = () => (window.luckysheet || window.Luckysheet);

  function a1ToRC(a1) {
    const m = String(a1).match(/^([A-Z]+)(\d+)$/i);
    if (!m) return null;
    const colLetters = m[1].toUpperCase();
    let c = 0;
    for (let i = 0; i < colLetters.length; i++) c = c * 26 + (colLetters.charCodeAt(i) - 64);
    const r = parseInt(m[2], 10);
    return { r: r - 1, c: c - 1 };
  }

  function ensureLSReady() {
    const api = LS();
    if (!api || typeof api.create !== "function") {
      throw new Error("Luckysheet 전역이 없습니다.");
    }
    const files = (typeof api.getluckysheetfile === "function") ? api.getluckysheetfile() : null;
    if (!files || !Array.isArray(files) || files.length === 0) {
      throw new Error("Luckysheet 파일 정보를 가져올 수 없습니다.");
    }
    return { api, files };
  }

  async function apply(fillMap) {
    const { api, files } = ensureLSReady();

    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = files.find(s => s.name === sheetName) || files[0];
      if (!sheet) continue;

      if (typeof api.setSheetActive === "function" && typeof sheet.index === "number") {
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

        if (!ok) {
          const s = files.find(s => s.name === sheetName) || sheet;
          s.data = s.data || [];
          s.data[rc.r] = s.data[rc.r] || [];
          s.data[rc.r][rc.c] = { v: value, m: String(value) };
        }
      }
    }

    try { (window.luckysheet && window.luckysheet.refresh && window.luckysheet.refresh()); } catch (_) {}
  }

  window.PrdinfoFill = { apply };
})();
