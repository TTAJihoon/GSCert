(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  const API_ENDPOINT = "/security/invicti/parse/";

  App.dom = App.dom || {};

  let currentFiles = [];
  const ALLOWED_EXTS = [".html", ".htm"];
  const isHtmlFile = (name) => /\.html?$/i.test(name || "");
  
  const validateFiles = (files) => {
    const valid = [], invalid = [];
    (files || []).forEach((f) => (isHtmlFile(f.name) ? valid : invalid).push(f));
    return { valid, invalid };
  };

  const setFilesToInput = (files) => {
    if (!App.dom.fileInput) return;
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    App.dom.fileInput.files = dt.files;
  };

  const showPageLoading = (show) => {
    const pageLoading = document.getElementById("loadingContainer");
    if (!pageLoading) return;
    pageLoading.classList.toggle("hidden", !show);
    document.body.style.overflow = show ? "hidden" : "auto";
  };

  function renderFileList() {
    const { fileListEl } = App.dom;
    if (!fileListEl) return;

    if (currentFiles.length === 0) {
      fileListEl.innerHTML = "";
      fileListEl.classList.add("hidden");
    } else {
      fileListEl.innerHTML = currentFiles
        .map((f) => `
          <div class="file-item flex justify-between items-center text-sm text-gray-700 py-1 px-2 mb-1 rounded bg-gray-100">
            <span>
              <i class="fas fa-file-code mr-2 text-gray-500"></i>${f.name}
              <span class="text-gray-400">(${(f.size / 1024).toFixed(1)} KB)</span>
            </span>
            <button type="button" class="file-remove-btn text-red-500 hover:text-red-700" data-filename="${f.name}" title="파일 제거">
              <i class="fas fa-times"></i>
            </button>
          </div>`
        ).join("");
      fileListEl.classList.remove("hidden");
    }
  }

  function removeFile(fileName) {
    currentFiles = currentFiles.filter(f => f.name !== fileName);
    updateFileInput();
    renderFileList();
  }

  function addFiles(newFiles) {
    const validFiles = validateFiles(newFiles).valid;
    if (newFiles.length !== validFiles.length) {
      alert("HTML 파일(.html, .htm)만 업로드할 수 있습니다.");
    }
    
    validFiles.forEach(file => {
      // 중복 파일 체크 (파일 이름 기준)
      if (!currentFiles.some(f => f.name === file.name)) {
        currentFiles.push(file);
      }
    });
    
    updateFileInput();
    renderFileList();
  }
  
  function updateFileUI(files) {
    const { fileListEl, dropArea } = App.dom;
    if (!fileListEl || !dropArea) return;

    dropArea.classList.remove("hidden");

    if (files.length === 0) {
      fileListEl.innerHTML = "";
      fileListEl.classList.add("hidden");
    } else {
      fileListEl.innerHTML = files
        .map((f) => `
          <div class="file-item flex justify-between items-center text-sm text-gray-700 py-1 px-2 rounded bg-gray-100">
            <span>
              <i class="fas fa-file-code mr-2 text-gray-500"></i>${f.name}
              <span class="text-gray-400">(${(f.size / 1024).toFixed(1)} KB)</span>
            </span>
            <button type="button" class="file-remove-btn text-red-500 hover:text-red-700" data-filename="${f.name}" title="파일 제거">
              <i class="fas fa-times"></i>
            </button>
          </div>`
        ).join("");
      fileListEl.classList.remove("hidden");
    }
  }
  
  function removeFile(fileName) {
    const currentFiles = Array.from(App.dom.fileInput.files);
    const newFiles = currentFiles.filter(f => f.name !== fileName);
    setFilesToInput(newFiles);
    updateFileUI(newFiles);
  }

  async function pickFiles() {
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
        updateFileUI(files);
        return;
      } catch (e) { return; }
    }
    App.dom.fileInput?.click();
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
  
  async function requestInvictiParse(files) {
    const fd = new FormData();
    files.forEach((f) => fd.append("file", f, f.name));
    const csrf = (document.querySelector('#queryForm input[name="csrfmiddlewaretoken"]') || {}).value
              || (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || "";

    showPageLoading(true);
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
    
      if (json.error) {
        App.clearData();
        return App.showError(json.error);
      }
      
      const rows = Array.isArray(json?.rows) ? json.rows : [];
      if (!rows.length) {
        App.clearData();
        return App.showError("추출 가능한 결함 항목이 없습니다.");
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
      App.clearData();
    } finally {
      showPageLoading(false);
      App.dom.generateBtn?.removeAttribute("disabled");
      App.dom.loadingState?.classList.add("hidden");
    }
  }

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
    
    App.dom.fileListEl?.addEventListener('click', (e) => {
        const removeBtn = e.target.closest('.file-remove-btn');
        if (removeBtn) {
            removeFile(removeBtn.dataset.filename);
        }
    });

    App.dom.dropArea?.addEventListener("click", pickFiles);

    App.dom.fileInput?.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      const { valid, invalid } = validateFiles(files);
      if (invalid.length) {
        alert("업로드 가능한 확장자가 아닙니다");
        e.target.value = "";
        updateFileUI([]);
        return;
      }
      updateFileUI(valid);
    });

    if (App.dom.dropArea) {
      ["dragenter","dragover"].forEach((evt) =>
        App.dom.dropArea.addEventListener(evt, (e) => {
          e.preventDefault(); e.stopPropagation();
          App.dom.dropArea.classList.add("ring","ring-sky-300");
        })
      );
      ["dragleave","drop"].forEach((evt) =>
        App.dom.dropArea.addEventListener(evt, (e) => {
          e.preventDefault(); e.stopPropagation();
          App.dom.dropArea.classList.remove("ring","ring-sky-300");
        })
      );
      
      App.dom.dropArea.addEventListener("drop", (e) => {
        const files = Array.from(e.dataTransfer.files || []);
        const { valid, invalid } = validateFiles(files);
        if (invalid.length) {
          alert("업로드 가능한 확장자가 아닙니다");
        }
        if (valid.length) {
          setFilesToInput(valid);
          updateFileUI(valid);
        }
      });
    }

    App.dom.generateBtn?.addEventListener("click", async () => {
      const files = Array.from(App.dom.fileInput?.files || []);
      if (!files.length) {
        alert("분석할 HTML 파일을 업로드해주세요.");
        return;
      }
      await requestInvictiParse(files);
    });
  });
})(window);
