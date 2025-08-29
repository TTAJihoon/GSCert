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

  // 시트 data에 직접 기록(활성 시트/옵션 사용 안 함 → order 오류/머지 로그 방지)
  function setDataCell(sheet, r, c, value) {
    sheet.data = sheet.data || [];
    // 행 확장
    while (sheet.data.length <= r) sheet.data.push([]);
    // 열 확장
    sheet.data[r] = sheet.data[r] || [];
    while (sheet.data[r].length <= c) sheet.data[r].push(null);

    const isNumber = typeof value === "number" && isFinite(value);
    const v = isNumber ? value : String(value == null ? "" : value);
    sheet.data[r][c] = { v, m: String(v) };
  }

  // 메인 적용 함수
  async function apply(fillMap) {
    const { api, files } = ensureLSReady();

    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = findSheet(files, sheetName);
      if (!sheet) continue;

      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;
        setDataCell(sheet, rc.r, rc.c, value);
      }
    }

    try {
      // 데이터 직접 수정 후 화면 갱신
      const inst = LS();
      if (inst && typeof inst.refresh === "function") inst.refresh();
    } catch (_) {}
  }

  // 전역 노출
  window.PrdinfoFill = { apply };
})();
