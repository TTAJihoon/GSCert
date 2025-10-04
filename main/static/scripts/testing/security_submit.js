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
    // [추가] FormData 객체 생성
    const fd = new FormData();
    files.forEach((f) => fd.append("file", f, f.name));

    // [추가] Django CSRF 토큰 가져오기
    const csrf = (document.querySelector('#queryForm input[name="csrfmiddlewaretoken"]') || {}).value
              || (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || "";

    showPageLoading(true);
    generateBtn?.setAttribute("disabled", "disabled");

    try {
      const res = await fetch(API_ENDPOINT, {
        method: "POST",
        // [수정] 헤더에서 불필요한 '...' 제거 및 표준 AJAX 헤더 추가
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest" 
        },
        body: fd, // 파일 데이터
      });

      if (!res.ok) {
        // 서버에서 온 에러 메시지를 포함하여 throw
        const errorText = await res.text();
        throw new Error(`서버 오류 (${res.status}): ${errorText}`);
      }
    
      const json = await res.json();
    
      if (json.error) {
        App.clearData();
        return App.showError(json.error);
      }
      
      const rows = Array.isArray(json?.rows) ? json.rows : [];
      
      if (!rows.length) {
        App.clearData(); // 데이터가 없을 경우 기존 테이블 초기화
        return App.showError("추출 가능한 결함 항목이 없습니다. 다른 리포트 파일을 사용해 보세요.");
      }
    
      if (json.css) {
        injectStyles(json.css);
      }

      rows.forEach((r) => { if (!r.id) r.id = App.generateId(); });
      App.setData(rows);
    
      App.showSuccess(`총 ${rows.length}개 항목을 반영했습니다.`);

    } catch (err) {
      console.error(err);
      App.showError(err.message || "자동 작성 중 오류가 발생했습니다.");
      App.clearData(); // 에러 발생 시 테이블 초기화
    } finally {
      showPageLoading(false);
      generateBtn?.removeAttribute("disabled");
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
