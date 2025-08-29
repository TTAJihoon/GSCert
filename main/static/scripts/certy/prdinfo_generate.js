document.addEventListener('DOMContentLoaded', function () {
  const form        = document.getElementById('queryForm');
  const fileInput   = document.getElementById('fileInput');
  const btnGenerate = document.getElementById('btn-generate');
  const loading     = document.getElementById('loadingContainer');

  // 업로드 검증: 각 그룹에서 최소 1개씩 포함
  const REQUIRED_GROUPS = [
    ['합의서'],            // 1번(.docx)
    ['성적서'],            // 2번(.docx)
    ['결함리포트', '결함'] // 3번(.xlsx)
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

  // 폼 기본 submit 방지(페이지 이동 X)
  form?.addEventListener('submit', (e) => e.preventDefault());

  // 클릭 → 서버 호출 → fillMap 반영
  btnGenerate?.addEventListener('click', async (e) => {
    e.preventDefault();

    // 1) 파일 검증(정확히 3개 + 그룹 충족)
    const files = Array.from(fileInput?.files || []);
    if (files.length !== 3) {
      alert('합의서, 성적서, 결함리포트를 모두 업로드해주세요(총 3개).');
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
      if (!data || !data.fillMap) throw new Error('서버 응답에 fillMap이 없습니다.');

      // 3) Luckysheet 셀 채우기
      if (window.PrdinfoFill?.apply) {
        await window.PrdinfoFill.apply(data.fillMap);
      } else {
        // (백업) 이 파일에 직접 구현된 간이 채움 로직
        await applyFillMapToLucky_Fallback(data.fillMap);
      }

      // (선택) data.gsNumber 로 파일명/화면 표시 등에 활용 가능
      console.log('GS Number:', data.gsNumber);

    } catch (err) {
      console.error(err);
      alert('생성 중 오류가 발생했습니다.\n' + err.message);
    } finally {
      hideLoading();
    }
  });

  // ───────────────── 백업용(모듈 미로드 시) ─────────────────
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

    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = files.find(s => s.name === sheetName) || files[0];
      if (!sheet) continue;

      if (typeof LS.setSheetActive === 'function' && typeof sheet.index === 'number') {
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
          const s = files.find(s => s.name === sheetName) || sheet;
          s.data = s.data || [];
          s.data[rc.r] = s.data[rc.r] || [];
          s.data[rc.r][rc.c] = { v: value, m: String(value) };
        }
      }
    }
    try { (window.luckysheet && window.luckysheet.refresh && window.luckysheet.refresh()); } catch (_) {}
  }
});
