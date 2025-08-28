document.addEventListener('DOMContentLoaded', function () {
  const form         = document.getElementById('queryForm');
  const fileInput    = document.getElementById('fileInput');
  const btnGenerate  = document.getElementById('btn-generate');
  const loading      = document.getElementById('loadingContainer');

  const REQUIRED_GROUPS = [
    ['합의서'],            // 그룹1: '합의서' 포함
    ['성적서'],            // 그룹2: '성적서' 포함
    ['결함리포트', '결함'] // 그룹3: '결함리포트' 또는 '결함' 포함
  ];

  const showLoading = () => loading && loading.classList.remove('hidden');
  const hideLoading = () => loading && loading.classList.add('hidden');

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      for (const cookie of document.cookie.split(';')) {
        const c = cookie.trim();
        if (c.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(c.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // 기본 form submit은 사용하지 않음(AJAX만 사용)
  form?.addEventListener('submit', (e) => e.preventDefault());

  btnGenerate?.addEventListener('click', async (e) => {
    e.preventDefault();

    // 1) 클라이언트 검증: 파일 3개 & 각 그룹 충족
    const files = Array.from(fileInput.files || []);
    if (files.length !== 3) {
      alert('합의서, 성적서, 결함리포트를 모두 업로드하였는지 확인해주세요');
      return;
    }

    // 그룹 충족 체크
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
      alert('합의서, 성적서, 결함리포트를 모두 업로드하였는지 확인해주세요');
      return;
    }

    // 2) 서버 전송
    showLoading();
    try {
      const fd = new FormData();
      files.forEach(f => fd.append('file', f)); // 같은 key 'file'로 3개 전송
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
      if (!data.fillMap) throw new Error('fillMap이 비었습니다.');

      // 3) Luckysheet에 반영
      await applyFillMapToLucky(data.fillMap);
      // 필요 시 gsNumber(data.gsNumber) 등을 화면에 표시할 수 있음
    } catch (err) {
      console.error(err);
      alert('생성 중 오류가 발생했습니다.\n' + err.message);
    } finally {
      hideLoading();
    }
  });

  // ------------------ Luckysheet 반영 유틸 ------------------
  async function applyFillMapToLucky(fillMap) {
    const LS = window.luckysheet || window.Luckysheet;
    if (!LS || typeof LS.create !== 'function') throw new Error('Luckysheet 전역이 없습니다.');

    const files = (typeof LS.getluckysheetfile === 'function') ? LS.getluckysheetfile() : null;
    if (!files) throw new Error('Luckysheet 파일 정보를 가져올 수 없습니다.');

    const a1ToRC = (a1) => {
      const m = String(a1).match(/^([A-Z]+)(\d+)$/i);
      if (!m) return null;
      const colLetters = m[1].toUpperCase();
      let c = 0; for (let i=0;i<colLetters.length;i++) c = c*26 + (colLetters.charCodeAt(i)-64);
      const r = parseInt(m[2],10);
      return { r: r-1, c: c-1 }; // 0-based
    };

    for (const [sheetName, cells] of Object.entries(fillMap)) {
      const sheet = files.find(s => s.name === sheetName) || files[0];
      if (!sheet) continue;

      // 시트 활성화(선택사항)
      if (typeof LS.setSheetActive === 'function' && typeof sheet.index === 'number') {
        try { LS.setSheetActive(sheet.index); } catch(_) {}
      }

      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;

        // 표준 API 우선
        let ok = false;
        try {
          if (typeof LS.setCellValue === 'function') {
            LS.setCellValue(rc.r, rc.c, value); // 활성 시트 기준
            ok = true;
          }
        } catch (_) {}

        // Fallback: 데이터 직접 덮기
        if (!ok) {
          const s = files.find(s => s.name === sheetName) || sheet;
          s.data = s.data || [];
          s.data[rc.r] = s.data[rc.r] || [];
          s.data[rc.r][rc.c] = { v: value, m: String(value) };
        }
      }
    }

    // Fallback 수정이 있었다면 리프레시
    if (typeof luckysheet?.refresh === 'function') {
      try { luckysheet.refresh(); } catch (_) {}
    }
  }
});
