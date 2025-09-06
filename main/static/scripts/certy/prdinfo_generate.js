// prdinfo_generate.js  (재인증 팝업 게이팅 + 추가 셀 입력)
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

  // ─────────────────────────────────────────────────────────
  // 재인증 팝업(라디오 선택) - 선택 시 resolve(값), 취소 시 resolve(null)
  // ─────────────────────────────────────────────────────────
  function showReCertModal() {
    return new Promise((resolve) => {
      const id = 'recert-modal';
      const old = document.getElementById(id);
      if (old) old.remove();

      const wrap = document.createElement('div');
      wrap.id = id;
      wrap.style.position = 'fixed';
      wrap.style.inset = '0';
      wrap.style.background = 'rgba(0,0,0,0.4)';
      wrap.style.display = 'flex';
      wrap.style.alignItems = 'center';
      wrap.style.justifyContent = 'center';
      wrap.style.zIndex = '9999';

      wrap.innerHTML = `
        <div style="background:#fff; padding:20px; border-radius:10px; width: 360px; box-shadow:0 10px 30px rgba(0,0,0,0.2)">
          <h3 style="margin:0 0 10px; font-size:18px;">재인증 유형 선택</h3>
          <p style="margin:0 0 14px; color:#666; font-size:13px;">다음 단계로 진행하려면 유형을 선택하세요.</p>
          <div style="display:grid; gap:8px; font-size:14px;">
            <label><input type="radio" name="rc" value="간소화 재인증(품질 개선)"> 간소화 재인증(품질 개선)</label>
            <label><input type="radio" name="rc" value="간소화 재인증(부분 변경)"> 간소화 재인증(부분 변경)</label>
            <label><input type="radio" name="rc" value="중요 변경 재인증"> 중요 변경 재인증</label>
          </div>
          <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:16px;">
            <button id="rc-cancel" style="padding:8px 12px;">취소</button>
            <button id="rc-ok" style="padding:8px 12px; background:#2563eb; color:#fff; border-radius:6px;">확인</button>
          </div>
        </div>
      `;
      document.body.appendChild(wrap);

      const onClose = (val) => { wrap.remove(); resolve(val); };
      wrap.querySelector('#rc-cancel').addEventListener('click', () => onClose(null));
      wrap.querySelector('#rc-ok').addEventListener('click', () => {
        const sel = wrap.querySelector('input[name="rc"]:checked');
        if (!sel) { alert('하나를 선택해주세요.'); return; }
        onClose(sel.value);
      });
    });
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
      console.log('[DEBUG] fillMap:', data.fillMap);
      console.log('[DEBUG] reCertText:', data.reCertText);
      console.log('[DEBUG] secOmitText:', data.secOmitText);
      console.log('[DEBUG] aiSuggest:', data.aiSuggest);

      if (!data || !data.fillMap) {
        throw new Error('서버 응답에 fillMap이 없습니다.');
      }

      // 베이스 시트명(첫 엔트리) 추정
      const firstSheetName = Object.keys(data.fillMap)[0] || 'Sheet1';

      // ─────────────────────────────────────────────────────
      // (1) 재인증 게이팅 + G9/H9
      // ─────────────────────────────────────────────────────
      let extraCells1 = {};
      if ((data.reCertText || "-") !== "-") {
        // 팝업에서 선택 완료 전에는 다음 단계로 넘어가지 않음
        const sel = await showReCertModal();
        if (!sel) {
          alert('재인증 유형 선택이 취소되었습니다.');
          return; // 게이트
        }
        extraCells1["G9"] = sel;          // 1-8
        extraCells1["H9"] = data.reCertText; // 1-9
      } else {
        // 신규인증 또는 정보 없음
        extraCells1["G9"] = "X";          // 1-10
        extraCells1["H9"] = "-";          // 1-10
      }

      // ─────────────────────────────────────────────────────
      // (2) 보안성 생략 여부 + J9/L9
      // ─────────────────────────────────────────────────────
      let extraCells2 = {};
      if ((data.secOmitText || "-") === "-") {
        extraCells2["J9"] = "X";  // 2-5
        extraCells2["L9"] = "-";  // 2-5
      } else {
        extraCells2["J9"] = "O";              // 2-6
        extraCells2["L9"] = data.secOmitText; // 2-6
      }

      // ─────────────────────────────────────────────────────
      // (3) AI 추천 SW/키워드 + E5/N7
      // ─────────────────────────────────────────────────────
      let extraCells3 = {};
      const ai = data.aiSuggest || {};
      if (ai && (ai.SW || ai.keyword1 || ai.keyword2)) {
        if (ai.SW) extraCells3["E5"] = ai.SW;
        const kw = [ai.keyword1, ai.keyword2].filter(Boolean).join(", ");
        if (kw) extraCells3["N7"] = kw;
      }

      // ─────────────────────────────────────────────────────
      // Luckysheet 쓰기: 우선 베이스 fillMap, 이어서 추가 셀들 배치
      // (재인증 유형을 이미 선택 완료했으므로 이제 채움)
      // ─────────────────────────────────────────────────────
      await window.PrdinfoFill.apply(data.fillMap);
      await window.PrdinfoFill.apply({ [firstSheetName]: extraCells1 });
      await window.PrdinfoFill.apply({ [firstSheetName]: extraCells2 });
      await window.PrdinfoFill.apply({ [firstSheetName]: extraCells3 });

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
