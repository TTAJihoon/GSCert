(() => {
  // Luckysheet 핸들
  const LS = () => (window.luckysheet || window.Luckysheet);

  // 시트명 정규화(공백 제거 + 소문자)
  function normName(s) {
    return String(s || "").replace(/\s+/g, "").toLowerCase();
  }

  // 시트 찾기 함수 (디버깅 로그 포함)
  function findSheet(files, targetName) {
    console.log(`[Debug] ===== 시트 찾기 시작 =====`);
    console.log(`[Debug] 찾으려는 시트 원본 이름: "${targetName}"`);

    const availableNames = files.map(f => f.name);
    console.log(`[Debug] 현재 사용 가능한 시트 목록:`, availableNames);

    const t = normName(targetName);
    console.log(`[Debug] 정규화된 타겟 이름: "${t}"`);

    let s = files.find(x => normName(x.name) === t);
    console.log(`[Debug] 1. 완전 일치 검색 결과:`, s ? s.name : '못 찾음');

    if (!s) {
      s = files.find(x => normName(x.name).includes(t));
      console.log(`[Debug] 2. 부분 일치 검색 결과:`, s ? s.name : '못 찾음');
    }
    
    if (!s) {
      s = files[0];
      console.log(`[Debug] 3. 기본값(첫 번째 시트) 선택:`, s ? s.name : '첫 번째 시트도 없음');
    }
    
    console.log(`[Debug] 최종 선택된 시트 객체:`, s);
    console.log(`[Debug] ========================`);
    return s;
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

  // 메인 적용 함수
  async function apply(fillMap) {
    const { api, files } = ensureLSReady();

    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = findSheet(files, sheetName);

      // ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 이 부분이 수정되었습니다 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
      // sheet.index 대신 sheet.order를 사용하여 시트 순서를 가져옵니다.
      const sheetOrder = sheet ? parseInt(sheet.order, 10) : NaN;
      if (isNaN(sheetOrder) || sheetOrder < 0) {
        console.warn(`[PrdinfoFill] 시트 "${sheetName}"를 찾을 수 없거나 유효한 order가 없습니다. (받은 값: ${sheet?.order})`);
        continue;
      }
      // ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

      // 유효한 order로 시트를 활성화합니다.
      api.setSheetActive(sheetOrder);
      await new Promise(resolve => setTimeout(resolve, 0));

      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;
        
        api.setCellValue(rc.r, rc.c, value);
      }
    }

    api.refresh();
  }

  // 전역 노출
  window.PrdinfoFill = { apply };
})();
