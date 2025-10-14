(() => {
  // Luckysheet 핸들
  const LS = () => (window.luckysheet || window.Luckysheet);

  // 시트명 정규화(공백 제거 + 소문자)
  function normName(s) {
    return String(s || "").replace(/\s+/g, "").toLowerCase();
  }

  // ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 이 부분이 수정되었습니다 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
  // 시트 찾기 함수에 디버깅 로그 추가
  function findSheet(files, targetName) {
    console.log(`[Debug] ===== 시트 찾기 시작 =====`);
    console.log(`[Debug] 찾으려는 시트 원본 이름: "${targetName}"`);

    // 현재 열려있는 모든 시트의 이름을 출력합니다.
    const availableNames = files.map(f => f.name);
    console.log(`[Debug] 현재 사용 가능한 시트 목록:`, availableNames);

    const t = normName(targetName);
    console.log(`[Debug] 정규화된 타겟 이름: "${t}"`);

    // 1. 이름이 완전히 일치하는 시트 찾기
    let s = files.find(x => normName(x.name) === t);
    console.log(`[Debug] 1. 완전 일치 검색 결과:`, s ? s.name : '못 찾음');

    // 2. 완전 일치하는 시트가 없으면, 이름에 타겟이 포함된 시트 찾기
    if (!s) {
      s = files.find(x => normName(x.name).includes(t));
      console.log(`[Debug] 2. 부분 일치 검색 결과:`, s ? s.name : '못 찾음');
    }
    
    // 3. 그래도 없으면 첫 번째 시트를 기본값으로 사용
    if (!s) {
      s = files[0];
      console.log(`[Debug] 3. 기본값(첫 번째 시트) 선택:`, s ? s.name : '첫 번째 시트도 없음');
    }
    
    console.log(`[Debug] 최종 선택된 시트 객체:`, s);
    console.log(`[Debug] ========================`);
    return s;
  }
  // ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

  // "A1" → { r: 0-based row, c: 0-based col }
  function a1ToRC(a1) {
    if (!a1 || typeof a1 !== "string") return null;
    const m = a1.trim().match(/^([A-Za-z]+)(\d+)$/);
    if (!m) return null;
    const [, colStr, rowStr] = m;
    let col = 0;
    for (let i = 0; i < colStr.length; i++) {
      col = col * 26 + (
