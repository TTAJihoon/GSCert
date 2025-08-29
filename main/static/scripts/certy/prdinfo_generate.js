(() => {
  // =========================
  // 유틸
  // =========================
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, evt, fn) => el && el.addEventListener(evt, fn);

  const normName = s => String(s || "").replace(/\s+/g, "").toLowerCase();

  function a1ToRC(a1) {
    if (!a1 || typeof a1 !== "string") return null;
    const m = a1.trim().match(/^([A-Za-z]+)(\d+)$/);
    if (!m) return null;
    const [, colStr, rowStr] = m;
    let col = 0;
    for (let i = 0; i < colStr.length; i++) col = col * 26 + (colStr.charCodeAt(i) & 31);
    return { r: parseInt(rowStr, 10) - 1, c: col - 1 };
  }

  function findSheet(files, target) {
    const t = normName(target);
    return files.find(s => normName(s.name) === t)
        || files.find(s => normName(s.name).includes(t))
        || files[0];
  }

  // CSRF (Django)
  function getCSRFToken() {
    const meta = qs('meta[name="csrf-token"], meta[name="csrfmiddlewaretoken"]');
    if (meta && meta.content) return meta.content;
    const input = qs('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  // 출력/로그
  function setText(idOrEl, text) {
    const el = typeof idOrEl === "string" ? qs(idOrEl) : idOrEl;
    if (el) el.textContent = typeof text === "string" ? text : JSON.stringify(text, null, 2);
  }
  function appendLine(idOrEl, line) {
    const el = typeof idOrEl === "string" ? qs(idOrEl) : idOrEl;
    if (!el) return;
    el.textContent += (el.textContent ? "\n" : "") + line;
  }

  // =========================
  // Luckysheet 적용기 (정식 + 폴백)
  // =========================
  async function applyFillMapToLucky(fillMap) {
    // 정식 경로: 별도 파일에서 주입된 PrdinfoFill.apply 가 있으면 그것 사용
    if (window.PrdinfoFill && typeof window.PrdinfoFill.apply === "function") {
      return window.PrdinfoFill.apply(fillMap);
    }
    // 폴백
    return applyFillMapToLucky_Fallback(fillMap);
  }

  async function applyFillMapToLucky_Fallback(fillMap) {
    const LS = window.luckysheet || window.Luckysheet;
    if (!LS || typeof LS.create !== "function") {
      throw new Error("Luckysheet 전역이 없습니다.");
    }
    const files = (typeof LS.getluckysheetfile === "function") ? LS.getluckysheetfile() : null;
    if (!files || !files.length) throw new Error("Luckysheet 파일 정보를 가져올 수 없습니다.");

    for (const [sheetName, cells] of Object.entries(fillMap || {})) {
      const sheet = findSheet(files, sheetName);
      if (!sheet) continue;

      if (typeof LS.setSheetActive === "function" && sheet.index) {
        try { LS.setSheetActive(sheet.index); } catch (_) {}
      }

      for (const [addr, value] of Object.entries(cells || {})) {
        const rc = a1ToRC(addr);
        if (!rc) continue;

        let ok = false;
        try {
          if (typeof LS.setCellValue === "function") {
            LS.setCellValue(rc.r, rc.c, value);
            ok = true;
          }
        } catch (_) {}

        if (!ok) {
          const s = findSheet(files, sheetName);
          s.data = s.data || [];
          s.data[rc.r] = s.data[rc.r] || [];
          s.data[rc.r][rc.c] = { v: value, m: String(value) };
        }
      }
    }
    try { (window.luckysheet && window.luckysheet.refresh && window.luckysheet.refresh()); } catch (_) {}
  }

  // =========================
  // 서버 호출
  // =========================
  async function postGenerate(form) {
    const endpoint = form.getAttribute("action") || form.dataset.endpoint || "/generate_prdinfo";
    const fd = new FormData(form);
    const headers = { "X-CSRFToken": getCSRFToken() };

    const resp = await fetch(endpoint, { method: "POST", body: fd, headers });
    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      throw new Error(`서버 오류 ${resp.status}: ${txt || resp.statusText}`);
    }
    return resp.json();
  }

  // =========================
  // 이벤트 바인딩
  // =========================
  function bindUI() {
    const form = qs("#prdinfo-form") || qs('form[data-prdinfo]');
    const fileInput = qs("#prdinfo-files") || (form && form.querySelector('input[type="file"][name="file"]'));
    const btnGenerate = qs("#btn-generate") || (form && form.querySelector('[type="submit"]'));
    const btnApply = qs("#btn-apply-to-lucky");
    const outArea = qs("#prdinfo-output");
    const dbgArea = qs("#prdinfo-debug");
    const fileListArea = qs("#file-list");

    // 파일 선택 미리보기
    on(fileInput, "change", () => {
      if (!fileListArea) return;
      const names = (fileInput.files ? Array.from(fileInput.files) : []).map(f => f.name);
      fileListArea.textContent = names.join("\n");
    });

    // 폼 제출(생성)
    on(form, "submit", async (e) => {
      e.preventDefault();
      setText(outArea, "요청 중...");
      setText(dbgArea, "");

      try {
        const json = await postGenerate(form);
        // 응답 표시
        setText(outArea, json);

        // Luckysheet에 적용
        if (json && json.fillMap) {
          appendLine(dbgArea, "[INFO] fillMap 적용 시작");
          await applyFillMapToLucky(json.fillMap);
          appendLine(dbgArea, "[INFO] fillMap 적용 완료");
        } else {
          appendLine(dbgArea, "[WARN] fillMap이 비어 있습니다.");
        }
      } catch (err) {
        setText(dbgArea, `[ERROR] ${err && err.message ? err.message : err}`);
        setText(outArea, "실패");
      }
    });

    // 별도 버튼으로 수동 적용(옵션)
    on(btnApply, "click", async () => {
      const txt = outArea && outArea.textContent;
      if (!txt) return appendLine(dbgArea, "[WARN] 적용할 응답이 없습니다.");
      let parsed = null;
      try { parsed = JSON.parse(txt); } catch (_) {}
      const fillMap = parsed && parsed.fillMap;
      if (!fillMap) return appendLine(dbgArea, "[WARN] fillMap이 없습니다.");
      appendLine(dbgArea, "[INFO] 수동 fillMap 적용 시작");
      try {
        await applyFillMapToLucky(fillMap);
        appendLine(dbgArea, "[INFO] 수동 적용 완료");
      } catch (e) {
        appendLine(dbgArea, `[ERROR] 수동 적용 실패: ${e && e.message ? e.message : e}`);
      }
    });
  }

  // =========================
  // 초기화
  // =========================
  function ready(fn) {
    if (document.readyState === "complete" || document.readyState === "interactive") {
      setTimeout(fn, 0);
    } else {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    }
  }

  ready(bindUI);

  // 전역 노출(테스트/디버그용)
  window.PrdinfoGenerate = {
    applyFillMapToLucky,
    applyFillMapToLucky_Fallback,
  };
})();
