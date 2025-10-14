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

  async function apply(fillMap) {
    const { api, files } = ensureLSReady();

    // API는 보통 활성 시트에 대해 동작하므로, 시트별로 순회하며 작업합니다.
    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = findSheet(files, sheetName);
      // 시트를 찾고, 활성화에 필요한 'index' 속성이 있는지 확인합니다.
      if (!sheet || typeof sheet.index === 'undefined') {
        console.warn(`[PrdinfoFill] 시트 "${sheetName}"를 찾을 수 없거나 index가 없습니다.`);
        continue;
      }

      // 값을 입력할 시트를 활성화합니다.
      // 이 작업은 비동기일 수 있으므로 약간의 지연을 줍니다.
      api.setSheetActive(sheet.index);
      await new Promise(resolve => setTimeout(resolve, 0));

      // 해당 시트의 모든 셀에 대해 공식 API를 사용하여 값을 설정합니다.
      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;
        
        // 공식 API: setCellValue(행, 열, 값)
        // 이 함수는 값 설정뿐만 아니라 필요한 모든 내부 상태를 안전하게 업데이트합니다.
        api.setCellValue(rc.r, rc.c, value);
      }
    }

    // 모든 값 입력 후, 최종적으로 한 번 화면을 새로고침하여 모든 변경사항을 반영합니다.
    api.refresh();
  }

  // 전역 노출
  window.PrdinfoFill = { apply };
})();
