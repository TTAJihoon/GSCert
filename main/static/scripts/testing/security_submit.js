(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  // 필요시 바꿔 써 주세요 (Django URL 패턴 맞춰서)
  const API_ENDPOINT = "/security/invicti/parse/"; 

  let fileInput, dropArea, fileListEl, generateBtn, pageLoading, csrfInput;

  // ===== 공용: 페이지 로딩 토글 =====
  function showPageLoading(show) {
    if (!pageLoading) return;
    pageLoading.classList.toggle("hidden", !show);
    document.body.style.overflow = show ? "hidden" : "auto";
  }

  // ===== 파일 필터/목록 =====
  function filterSupportedFiles(fileList) {
    // UI 문구가 HTML 업로드 기준이라 .html/.htm만 허용
    return Array.from(fileList || []).filter((f) => /\.html?$/i.test(f.name));
  }
  function renderFileList(files) {
    if (!fileListEl) return;
    if (!files.length) {
      fileListEl.classList.add("hidden");
      fileListEl.innerHTML = "";
      return;
    }
    const items = files
      .map(
        (f) =>
          `<div class="text-sm text-gray-700 py-1">
             <i class="fas fa-file-code mr-2"></i>${f.name}
             <span class="text-gray-400">(${(f.size / 1024).toFixed(1)} KB)</span>
           </div>`
      )
      .join("");
    fileListEl.innerHTML = items;
    fileListEl.classList.remove("hidden");
  }

  // ===== CSRF 토큰 =====
  function getCsrfToken() {
    // form 안의 {% csrf_token %} 우선
    const input = document.querySelector('#queryForm input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;

    // fallback: cookie에서 추출
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  // ===== 서버 호출 (run_invicti_parse() 백엔드) =====
  async function requestInvictiParse(files) {
    if (!files || !files.length) {
      App.showError("HTML 파일을 업로드해주세요.");
      return;
    }
    const fd = new FormData();
    // Django: request.FILES.getlist('file')로 받기 쉽게 같은 키로 반복 추가
    files.forEach((f) => fd.append("file", f, f.name));

    const csrf = getCsrfToken();
    const headers = { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" };

    showPageLoading(true);
    generateBtn?.setAttribute("disabled", "disabled");

    try {
      const res = await fetch(API_ENDPOINT, { method: "POST", headers, body: fd, credentials: "same-origin" });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`서버 오류 (${res.status}) ${text || ""}`.trim());
      }
      const json = await res.json();

      // 기대 포맷: { rows: [...] } 또는 [...]
      const rows = Array.isArray(json) ? json : Array.isArray(json?.rows) ? json.rows : [];
      if (!rows.length) {
        App.clearData();
        App.showError("추출 가능한 항목이 없습니다. 리포트/분석 결과를 확인해주세요.");
        return;
      }

      // id 누락 시 클라이언트에서 보강
      rows.forEach((r) => { if (!r.id) r.id = App.generateId(); });
      App.setData(rows);
      App.showSuccess(`총 ${rows.length}개 항목을 반영했습니다.`);
    } catch (err) {
      console.error(err);
      App.showError("자동 작성 중 오류가 발생했습니다.");
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

    // 파일 선택
    fileInput && fileInput.addEventListener("change", (e) => {
      const files = filterSupportedFiles(e.target.files);
      renderFileList(files);
    });

    // 드래그&드롭
    if (dropArea) {
      ["dragenter", "dragover"].forEach((evt) =>
        dropArea.addEventListener(evt, (e) => {
          e.preventDefault(); e.stopPropagation();
          dropArea.classList.add("ring", "ring-sky-300");
        })
      );
      ["dragleave", "drop"].forEach((evt) =>
        dropArea.addEventListener(evt, (e) => {
          e.preventDefault(); e.stopPropagation();
          dropArea.classList.remove("ring", "ring-sky-300");
        })
      );
      dropArea.addEventListener("drop", (e) => {
        const files = filterSupportedFiles(e.dataTransfer.files);
        renderFileList(files);
        // 파일 인풋과 동기화(선택 사항)
        if (fileInput) {
          const dt = new DataTransfer();
          files.forEach((f) => dt.items.add(f));
          fileInput.files = dt.files;
        }
      });
      dropArea.addEventListener("click", () => fileInput && fileInput.click());
    }

    // 자동 작성 실행 (서버 호출만 수행)
    generateBtn &&
      generateBtn.addEventListener("click", async () => {
        const files = filterSupportedFiles(fileInput?.files || []);
        await requestInvictiParse(files);
      });
  });
})(window);
