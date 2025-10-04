(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  const API_ENDPOINT = "/security/invicti/parse/";

  let fileInput, dropArea, fileListEl, generateBtn, pageLoading;

  // ===== 허용 확장자 / 유틸 =====
  const ALLOWED_EXTS = [".html", ".htm"];
  const isHtmlFile = (name) => /\.html?$/i.test(name || "");
  const validateFiles = (files) => {
    const valid = [], invalid = [];
    (files || []).forEach((f) => (isHtmlFile(f.name) ? valid : invalid).push(f));
    return { valid, invalid };
  };
  const setFilesToInput = (files) => {
    if (!fileInput) return;
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    fileInput.files = dt.files;
  };
  const showPageLoading = (show) => {
    if (!pageLoading) return;
    pageLoading.classList.toggle("hidden", !show);
    document.body.style.overflow = show ? "hidden" : "auto";
  };
  const renderFileList = (files) => {
    if (!fileListEl) return;
    if (!files.length) {
      fileListEl.classList.add("hidden");
      fileListEl.innerHTML = "";
      return;
    }
    fileListEl.innerHTML = files
      .map((f) => `<div class="text-sm text-gray-700 py-1">
        <i class="fas fa-file-code mr-2"></i>${f.name}
        <span class="text-gray-400">(${(f.size / 1024).toFixed(1)} KB)</span>
      </div>`).join("");
    fileListEl.classList.remove("hidden");
  };

  // ===== 파일 선택창(클릭) — 가능하면 네이티브 제한 강제 =====
  async function pickFiles() {
    // 최신 크롬/엣지: 다른 확장자 아예 선택 불가 + 창 유지
    if (window.showOpenFilePicker) {
      try {
        const handles = await window.showOpenFilePicker({
          multiple: true,
          excludeAcceptAllOption: true,
          types: [{
            description: "HTML Files",
            accept: { "text/html": ALLOWED_EXTS }
          }],
        });
        const files = await Promise.all(handles.map((h) => h.getFile()));
        setFilesToInput(files);
        renderFileList(files);
        return;
      } catch (e) {
        // 사용자가 취소한 경우 등 — 조용히 무시
        return;
      }
    }
    // fallback
    fileInput?.click();
  }

  function injectStyles(css) {
    const styleId = 'invicti-dynamic-styles';
    let styleTag = document.getElementById(styleId);
    if (!styleTag) {
      styleTag = document.createElement('style');
      styleTag.id = styleId;
      document.head.appendChild(styleTag);
    }
    styleTag.textContent = css;
  }
  
  // ===== 서버 호출 (run_invicti_parse) =====
  async function requestInvictiParse(files) {
    // ... (FormData 및 csrf 설정 부분) ...
    showPageLoading(true);
    generateBtn?.setAttribute("disabled", "disabled");

    try {
      const res = await fetch(API_ENDPOINT, { /* ... */ });
      if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
    
      const json = await res.json(); // { css: "...", rows: [...] } 형태
    
      // ... (에러 처리) ...
      const rows = Array.isArray(json?.rows) ? json.rows : [];
      if (!rows.length) { /* ... */ }
    
      // [추가] CSS를 head에 동적으로 주입
      if (json.css) {
        injectStyles(json.css);
      }

      // [핵심] 각 row에 고유 ID 부여
      rows.forEach((r) => { if (!r.id) r.id = App.generateId(); });

      // [핵심] security_editable.js의 setData 함수를 호출하여 테이블 생성
      App.setData(rows);
    
      App.showSuccess(`총 ${rows.length}개 항목을 반영했습니다.`);
    } catch (err) {
      // ... (에러 처리) ...
    } finally {
      // ... (로딩 상태 해제) ...
    }
  }

  // ===== 초기 바인딩 =====
  document.addEventListener("DOMContentLoaded", () => {
    fileInput   = document.getElementById("fileInput");
    dropArea    = document.getElementById("dropArea");
    fileListEl  = document.getElementById("fileList");
    generateBtn = document.getElementById("btn-generate");
    pageLoading = document.getElementById("loadingContainer");

    // 클릭으로 파일 선택: 가능하면 showOpenFilePicker 사용
    dropArea?.addEventListener("click", pickFiles);

    // input으로 선택(모든 브라우저 공통 처리): 유효성 검사
    fileInput?.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      const { valid, invalid } = validateFiles(files);
      if (invalid.length) {
        alert("업로드 가능한 확장자가 아닙니다");
        // 잘못 선택된 경우: 초기화 + (가능하면) 즉시 다시 열어주기
        fileInput.value = "";
        // 같은 사용자 제스처 컨텍스트 내에서 재오픈하면 대개 허용됨
        setTimeout(() => pickFiles(), 0);
        return;
      }
      // 정상
      renderFileList(valid);
    });

    // 드래그&드롭: 유효성 검사 + 안내
    if (dropArea) {
      ["dragenter","dragover"].forEach((evt) =>
        dropArea.addEventListener(evt, (e) => {
          e.preventDefault(); e.stopPropagation();
          dropArea.classList.add("ring","ring-sky-300");
        })
      );
      ["dragleave","drop"].forEach((evt) =>
        dropArea.addEventListener(evt, (e) => {
          e.preventDefault(); e.stopPropagation();
          dropArea.classList.remove("ring","ring-sky-300");
        })
      );
      dropArea.addEventListener("drop", (e) => {
        const files = Array.from(e.dataTransfer.files || []);
        const { valid, invalid } = validateFiles(files);
        if (invalid.length) {
          alert("업로드 가능한 확장자가 아닙니다");
        }
        if (valid.length) {
          setFilesToInput(valid);
          renderFileList(valid);
        }
      });
    }

    // 자동 작성 실행
    generateBtn?.addEventListener("click", async () => {
      const files = Array.from(fileInput?.files || []);
      const { valid, invalid } = validateFiles(files);
      if (invalid.length || !valid.length) {
        alert("업로드 가능한 확장자가 아닙니다");
        return;
      }
      await requestInvictiParse(valid);
    });
  });
})(window);
