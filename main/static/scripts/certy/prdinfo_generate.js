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

  // 공용 실행 함수: 폼 submit/버튼 click 모두 이 함수만 호출
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
      console.log('[DEBUG] fillMap:', data.fillMap);

      if (!data || !data.fillMap) throw new Error('서버 응답에 fillMap이 없습니다.');

      if (window.PrdinfoFill?.apply) {
        await window.PrdinfoFill.apply(data.fillMap);
      } else {
        await applyFillMapToLucky_Fallback(data.fillMap);
      }

      console.log('GS Number:', data.gsNumber);
    } catch (err) {
      console.error(err);
      alert('생성 중 오류가 발생했습니다.\n' + err.message);
    } finally {
      hideLoading();
    }
  }

  // 원본 흐름 유지: submit은 막고, 실행은 doGenerate로 통일
  form?.addEventListener('submit', (e) => { e.preventDefault(); doGenerate(); });
  btnGenerate?.addEventListener('click', (e) => { e.preventDefault(); doGenerate(); });

  // ───────────────── 백업용(모듈 누락 시) ─────────────────
  async function applyFillMapToLucky_Fallback(fillMap) {
    const LS = window.luckysheet || window.Luckysheet;
    if (!LS || typeof LS.create !== 'function') throw new Error('Luckysheet 전역이 없습니다.');
    const files = (typeof LS.getluckysheetfile === 'function') ? LS.getluckysheetfile() : null;
    if (!files) throw new Error('Luckysheet 파일 정보를 가져올 수 없습니다.');

    const a1ToRC = (a1) => {
      const m = String(a1).match(/^([A-Z]+)(\d+)$/i);
      if (!m) return null;
      const colLetters = m[1].toUpperCase();
      let c = 0; for (let i = 0; i < colLetters.length; i++) c = c * 26 + (colLetters.charCodeAt(i) - 64);
      const r = parseInt(m[2], 10);
      return { r: r - 1, c: c - 1 };
    };

    // 시트명 정규화(공백 제거+소문자)로 안정적으로 찾기
    const normName = s => String(s || '').replace(/\s+/g, '').toLowerCase();
    const findSheet = (target) => {
      const t = normName(target);
      return files.find(s => normName(s.name) === t)
          || files.find(s => normName(s.name).includes(t))
          || files[0];
    };

    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = findSheet(sheetName);
      if (!sheet) continue;

      // 문자열 index도 허용
      if (typeof LS.setSheetActive === 'function' && sheet.index) {
        try { LS.setSheetActive(sheet.index); } catch(_) {}
      }

      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;

        let ok = false;
        try {
          if (typeof LS.setCellValue === 'function') {
            LS.setCellValue(rc.r, rc.c, value);
            ok = true;
          }
        } catch (_) {}

        if (!ok) {
          const s = findSheet(sheetName);
          s.data = s.data || [];
          s.data[rc.r] = s.data[rc.r] || [];
          s.data[rc.r][rc.c] = { v: value, m: String(value) };
        }
      }
    }
    try { (window.luckysheet && window.luckysheet.refresh && window.luckysheet.refresh()); } catch (_) {}
  }
});
