(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  const API_ENDPOINT = "/security/invicti/parse/";

  App.dom = App.dom || {};
  let currentFiles = [];

  // ===== 유틸리티 함수 =====
  const ALLOWED_EXTS = ["html", "htm"];
  const isHtmlFile = (fileName) => {
    const ext = (fileName.split('.').pop() || '').toLowerCase();
    return ALLOWED_EXTS.includes(ext);
  };

  const isDuplicate = (file) => {
    return currentFiles.some(existingFile => 
      existingFile.name === file.name &&
      existingFile.size === file.size &&
      existingFile.lastModified === file.lastModified
    );
  };

  // `currentFiles` 배열의 내용을 실제 <input type="file">에 동기화하는 함수
  function syncFileInput() {
    if (!App.dom.fileInput) return;
    const dataTransfer = new DataTransfer();
    currentFiles.forEach(file => dataTransfer.items.add(file));
    App.dom.fileInput.files = dataTransfer.files;
  }

  // `currentFiles` 배열을 기반으로 화면에 파일 목록을 그리는 함수
  function renderFileList() {
    const { fileListEl } = App.dom;
    if (!fileListEl) return;

    if (currentFiles.length === 0) {
      fileListEl.innerHTML = "";
      fileListEl.classList.add("hidden");
    } else {
      fileListEl.innerHTML = currentFiles.map(file => `
        <div class="file-item flex justify-between items-center text-sm text-gray-700 py-1 px-2 mb-1 rounded bg-gray-100">
          <span>
            <i class="fas fa-file-code mr-2 text-gray-500"></i>${file.name}
            <span class="text-gray-400">(${(file.size / 1024).toFixed(1)} KB)</span>
          </span>
          <button type="button" class="file-remove-btn text-red-500 hover:text-red-700" data-filename="${file.name}" title="파일 제거">
            <i class="fas fa-times"></i>
          </button>
        </div>`
      ).join("");
      fileListEl.classList.remove("hidden");
    }
  }

  // 새로운 파일을 `currentFiles` 배열에 추가하는 함수
  function addFiles(filesToAdd) {
    const newFiles = Array.from(filesToAdd || []);

    newFiles.forEach(file => {
      if (!isHtmlFile(file.name)) {
        alert(`'${file.name}' 파일은 허용되지 않는 확장자입니다.\n(.html, .htm 파일만 가능)`);
        return; // 다음 파일로 넘어감
      }
      if (isDuplicate(file)) {
        return; // 중복 파일은 추가하지 않음
      }
      currentFiles.push(file);
    });

    syncFileInput();
    renderFileList();
  }

  // 파일을 `currentFiles` 배열에서 제거하는 함수
  function removeFile(fileName) {
    currentFiles = currentFiles.filter(file => file.name !== fileName);
    syncFileInput();
    renderFileList();
  }
  
  // 스타일 주입 및 서버 요청 함수 (기존과 동일)
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
  
  async function requestInvictiParse(files) {
    const fd = new FormData();
    files.forEach((f) => fd.append("file", f, f.name));
    const csrf = (document.querySelector('#queryForm input[name="csrfmiddlewaretoken"]') || {}).value
              || (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || "";

    App.dom.generateBtn?.setAttribute("disabled", "disabled");
    App.dom.loadingState?.classList.remove("hidden");
    App.dom.emptyState?.classList.add("hidden");
    if (App.dom.tableBody) App.dom.tableBody.style.display = 'none';

    try {
      const res = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
        body: fd,
      });
      if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
      
      const json = await res.json();
      
      if (json.error) { App.clearData(); return App.showError(json.error); }
      const rows = Array.isArray(json?.rows) ? json.rows : [];
      if (!rows.length) { App.clearData(); return App.showError("추출 가능한 결함 항목이 없습니다."); }
      
      if (json.css) {
        App.state = App.state || {};
        App.state.reportCss = json.css;
        injectStyles(json.css);
      }

      rows.forEach((r) => { if (!r.id) r.id = App.generateId(); });
      App.setData(rows);
      
      App.showSuccess(`총 ${rows.length}개 항목을 반영했습니다.`);
    } catch (err) {
      console.error(err);
      App.showError(err.message || "자동 작성 중 오류가 발생했습니다.");
      App.clearData();
    } finally {
      App.dom.generateBtn?.removeAttribute("disabled");
      App.dom.loadingState?.classList.add("hidden");
    }
  }

  // ===== 페이지 로드 후 이벤트 바인딩 =====
  document.addEventListener("DOMContentLoaded", () => {
    Object.assign(App.dom, {
      fileInput:    document.getElementById("fileInput"),
      dropArea:     document.getElementById("dropArea"),
      fileListEl:   document.getElementById("fileList"),
      generateBtn:  document.getElementById("btn-generate"),
      loadingState: document.getElementById("loadingState"),
      emptyState:   document.getElementById("emptyState"),
      tableBody:    document.getElementById("tableBody")
    });
    
    // 파일 삭제 버튼 이벤트 (이벤트 위임)
    App.dom.fileListEl?.addEventListener('click', (e) => {
        const removeBtn = e.target.closest('.file-remove-btn');
        if (removeBtn) {
            removeFile(removeBtn.dataset.filename);
        }
    });

    // 클릭해서 파일 선택
    App.dom.dropArea?.addEventListener("click", () => App.dom.fileInput?.click());

    // 파일 선택창에서 파일 선택 시
    App.dom.fileInput?.addEventListener("change", (e) => {
      addFiles(e.target.files);
      e.target.value = ""; // 동일한 파일을 다시 선택할 수 있도록 초기화
    });

    // 드래그 앤 드롭 이벤트
    if (App.dom.dropArea) {
      ["dragenter", "dragover"].forEach(eventName => {
        App.dom.dropArea.addEventListener(eventName, (e) => {
          e.preventDefault();
          App.dom.dropArea.classList.add("ring", "ring-sky-300");
        });
      });
      ["dragleave", "drop"].forEach(eventName => {
        App.dom.dropArea.addEventListener(eventName, (e) => {
          e.preventDefault();
          App.dom.dropArea.classList.remove("ring", "ring-sky-300");
        });
      });
      App.dom.dropArea.addEventListener("drop", (e) => {
        addFiles(e.dataTransfer.files);
      });
    }

    // '자동 작성' 버튼 클릭 이벤트
    App.dom.generateBtn?.addEventListener("click", async () => {
      if (currentFiles.length === 0) {
        alert("분석할 HTML 파일을 업로드해주세요.");
        return;
      }
      await requestInvictiParse(currentFiles);
    });
  });
})(window);
