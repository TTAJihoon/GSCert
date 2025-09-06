// prdinfo_generate.js  (fallback 제거 버전)
document.addEventListener('DOMContentLoaded', function () {
  const form        = document.getElementById('queryForm');
  const fileInput   = document.getElementById('fileInput');
  const btnGenerate = document.getElementById('btn-generate');
  const loading     = document.getElementById('loadingContainer');

  // 업로드 파일 검증: 합의서 / 성적서 / 결함리포트(또는 결함)
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

  async function doGenerate() {
    const files = Array.from(fileInput?.files || []);
    if (files.length !== 3) {
      alert('합의서, 성적서, 결함리포트(또는 결함)를 모두 업로드해주세요(총 3개).');
      return;
    }

    // 파일명에 필수 키워드가 들어있는지 확인
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

    // Luckysheet 채우기 모듈 필수 (폴백 없음)
    if (!window.PrdinfoFill || typeof window.PrdinfoFill.apply !== 'function') {
      alert('시트 채우기 모듈(prdinfo_fill_cells.js)이 로드되지 않았습니다.');
      throw new Error('PrdinfoFill.apply not found');
    }

    showLoading();
    try {
      const fd = new FormData();
      files.forEach(f => fd.append('file', f));
      const csrftoken = getCookie('csrftoken');

      // Django 뷰로 전송
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
      console.log('[DEBUG] fillMap:', data.fillMap);

      if (!data || !data.fillMap) {
        throw new Error('서버 응답에 fillMap이 없습니다.');
      }

      // Luckysheet에 값 채우기 (폴백 없이 이 경로만 사용)
      await window.PrdinfoFill.apply(data.fillMap);

      console.log('GS Number:', data.gsNumber);
    } catch (err) {
      console.error(err);
      alert('생성 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : err));
    } finally {
      hideLoading();
    }
  }

  // 원본 흐름 유지: submit 막고 공용 실행 함수로 통일
  form?.addEventListener('submit', (e) => { e.preventDefault(); doGenerate(); });
  btnGenerate?.addEventListener('click', (e) => { e.preventDefault(); doGenerate(); });
});
