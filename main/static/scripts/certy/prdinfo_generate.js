document.addEventListener('DOMContentLoaded', function () {
  const form        = document.getElementById('queryForm');
  const fileInput   = document.getElementById('fileInput');
  const btnGenerate = document.getElementById('btn-generate');
  const loading     = document.getElementById('loadingContainer');

  const REQUIRED_GROUPS = [
    ['합의서'],
    ['성적서'],
    ['결함리포트', '결함']
  ];

  const showLoading = () => loading && loading.classList.remove('hidden');
  const hideLoading = () => loading && loading.classList.add('hidden');

  function getCookie(name) {
    if (!document.cookie) return null;
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return null;
  }

  // '사전 입력 사항' 탭의 데이터를 읽어 fillMap 형식으로 반환하는 함수
  function getPreInputData() {
    const sheetName = '제품 정보 요청';
    const fillData = {};

    // Helper: ID로 엘리먼트 값 가져오기
    const getValue = (id, defaultValue = '') => document.getElementById(id)?.value || defaultValue;

    // 1. SW 분류 (E5)
    fillData['E5'] = getValue('swClassification', '-');

    // 2. 시험원 (L5) - 수정됨
    fillData['L5'] = getValue('tester', '-');

    // 3. 클라우드 환경 구성 (B9, D9)
    if (document.getElementById('cloud_yes')?.checked) {
      fillData['B9'] = 'O';
      fillData['D9'] = getValue('testEnvironment', '-');
    } else {
      fillData['B9'] = 'X';
      fillData['D9'] = '-';
    }

    // 4. SaaS형 제품 (F9)
    fillData['F9'] = document.getElementById('saas_yes')?.checked ? 'O' : 'X';

    // 5. 재계약 여부 (I5) - UI 동작에 맞춰 로직 수정
    if (document.getElementById('recontract_yes')?.checked) { // 'O'가 선택된 경우
      const recontractNum = getValue('recontractNumber');
      fillData['I5'] = recontractNum ? `${recontractNum} 재계약` : '재계약';
    } else { // 'X'가 선택된 경우
      fillData['I5'] = '-';
    }

    // 6. 재인증 구분 (G9, H9)
    const reCertType = getValue('reCertType');
    if (reCertType === '해당사항 없음') {
      fillData['G9'] = '해당사항 없음';
      fillData['H9'] = '-';
    } else {
      fillData['G9'] = reCertType;
      fillData['H9'] = getValue('reCertResultText', '-');
    }

    // 7. 보안성 시험 면제 여부 (J9, L9)
    if (document.getElementById('security_yes')?.checked) {
      fillData['J9'] = 'O';
      const security1 = getValue('security1', '-');
      const security2 = getValue('security2', '-');
      const security3 = getValue('security3', '-');
      fillData['L9'] = `- 보안 인증 종류: ${security1}\n- 인증번호: ${security2}\n- 인증일: ${security3}`;
    } else {
      fillData['J9'] = 'X';
      fillData['L9'] = '-';
    }

    return { [sheetName]: fillData };
  }

  async function doGenerate() {
    const files = Array.from(fileInput?.files || []);
    if (files.length !== 3) {
      alert('합의서, 성적서, 결함리포트(또는 결함)를 모두 업로드해주세요(총 3개).');
      return;
    }

    const coverage = REQUIRED_GROUPS.map(() => false);
    for (const f of files) {
      const name = (f.name || '').toLowerCase();
      REQUIRED_GROUPS.forEach((group, idx) => {
        if (coverage[idx]) return;
        for (const kw of group) {
          if (name.includes(kw.toLowerCase())) { coverage[idx] = true; break; }
        }
      });
    }
    if (!coverage.every(Boolean)) {
      alert('파일명이 ‘합의서 / 성적서 / 결함리포트(또는 결함)’를 각각 포함해야 합니다.');
      return;
    }

    if (!window.PrdinfoFill || typeof window.PrdinfoFill.apply !== 'function') {
      alert('시트 채우기 모듈(prdinfo_fill_cells.js)이 로드되지 않았습니다.');
      throw new Error('PrdinfoFill.apply not found');
    }

    showLoading();
    try {
      const fd = new FormData();
      files.forEach(f => fd.append('file', f));
      const csrftoken = getCookie('csrftoken');

      const resp = await fetch('/generate_prdinfo/', {
        method: 'POST',
        body: fd,
        headers: { 'X-CSRFToken': csrftoken }
      });
      if (!resp.ok) {
        const t = await resp.text().catch(()=> '');
        throw new Error(`서버 오류: ${resp.status} ${t}`);
      }

      const data = await resp.json();
      console.log('[DEBUG] list1:', data.list1);
      console.log('[DEBUG] list2:', data.list2);
      console.log('[DEBUG] list3:', data.list3);
      console.log('[DEBUG] fillMap from Server:', data.fillMap);

      if (!data || !data.fillMap) {
        throw new Error('서버 응답에 fillMap이 없습니다.');
      }
      
      const preInputFillMap = getPreInputData();
      console.log('[DEBUG] fillMap from Pre-Input:', preInputFillMap);

      const finalFillMap = data.fillMap;
      const sheetName = '제품 정보 요청';

      if (!finalFillMap[sheetName]) {
        finalFillMap[sheetName] = {};
      }
      Object.assign(finalFillMap[sheetName], preInputFillMap[sheetName]);
      
      console.log('[DEBUG] Final Merged fillMap:', finalFillMap);

      await window.PrdinfoFill.apply(finalFillMap);

      const resultTab = document.querySelector('.main-tab[data-tab="resultSheet"]');
      if (resultTab) {
        resultTab.click();
      }

      console.log('GS Number:', data.gsNumber);
    } catch (err) {
      console.error(err);
      alert('생성 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : err));
    } finally {
      hideLoading();
    }
  }

  form?.addEventListener('submit', (e) => { e.preventDefault(); doGenerate(); });
  btnGenerate?.addEventListener('click', (e) => { e.preventDefault(); doGenerate(); });
});
