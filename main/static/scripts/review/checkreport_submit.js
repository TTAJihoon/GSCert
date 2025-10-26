// GSCert/main/static/scripts/review/checkreport_submit.js
(function () {
  // === 실제 HTML id에 맞춤 ===
  const fileInput  = document.getElementById("fileInput");
  const submitBtn  = document.getElementById("btn-generate");
  const dropZone   = document.getElementById("dropArea") || document.body;
  const fileListEl = document.getElementById("fileList"); // optional

  // 상태 요소
  const loadingEl  = document.getElementById("loadingState");
  const emptyEl    = document.getElementById("emptyState");
  const tableEl    = document.getElementById("resultsTable");

  // 템플릿에서 아직 .html로 되어 있으면 런타임에서 교체
  try { if (fileInput && fileInput.accept !== ".docx,.pdf") fileInput.accept = ".docx,.pdf"; } catch (e) {}

  // MIME까지 확인하려면 true (지금은 확장자만 검사)
  const CHECK_MIME = false;

  // 내부 상태: 확장자별 1개만 유지
  const chosen = new Map(); // 'docx' | 'pdf' -> File

  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split("; ") : [];
    for (let i = 0; i < cookies.length; i++) {
      const parts = cookies[i].split("=");
      const key = decodeURIComponent(parts[0]);
      if (key === name) return decodeURIComponent(parts.slice(1).join("="));
    }
    return null;
  }
  const csrftoken = getCookie("csrftoken");

  function extOf(file) {
    const m = (file?.name || "").toLowerCase().match(/\.(\w+)$/);
    return m ? m[1] : "";
  }

  function mimeOk(file, ext) {
    if (!CHECK_MIME) return true;
    if (ext === "pdf")  return file.type === "application/pdf";
    if (ext === "docx")
      return file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    return false;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));
  }

  function showListVisible(hasItems) {
    if (!fileListEl) return;
    fileListEl.classList.toggle("hidden", !hasItems);
  }

  function renderList() {
    const docx = chosen.get("docx");
    const pdf  = chosen.get("pdf");

    const items = [];
    if (docx) items.push(`<li><i class="fa fa-file-word"></i> ${escapeHtml(docx.name)}</li>`);
    if (pdf)  items.push(`<li><i class="fa fa-file-pdf"></i> ${escapeHtml(pdf.name)}</li>`);

    if (fileListEl) {
      fileListEl.innerHTML = items.length
        ? `<ul class="upload-list">${items.join("")}</ul>`
        : `<div class="muted">docx 1개와 pdf 1개를 선택하세요.</div>`;
      showListVisible(true);
    } else {
      console.log("[checkreport] selected:", Object.fromEntries([...chosen].map(([k, f]) => [k, f?.name])));
    }
  }

  function acceptFiles(files) {
    let updated = false;
    for (const f of files || []) {
      if (!f) continue;
      const ext = extOf(f);
      if (ext !== "docx" && ext !== "pdf") continue;
      if (!mimeOk(f, ext)) {
        alert(`파일 형식(MIME)이 올바르지 않습니다: ${f.name}`);
        continue;
      }
      // 같은 확장자는 마지막 선택/드롭으로 교체
      chosen.set(ext, f);
      updated = true;
    }
    if (updated) renderList();
  }

  // ----- 클릭 선택 -----
  fileInput?.addEventListener("change", (e) => {
    acceptFiles(e.target.files);
  });

  // ----- 드래그/드롭 -----
  ;["dragenter", "dragover", "dragleave", "drop"].forEach((ev) => {
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });

  dropZone.addEventListener("dragover", () => {
    dropZone.classList?.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList?.remove("dragover");
  });
  dropZone.addEventListener("drop", (e) => {
    dropZone.classList?.remove("dragover");
    const files = e.dataTransfer?.files ? Array.from(e.dataTransfer.files) : [];
    acceptFiles(files);
  });

  // 드롭존 클릭 시 파일 선택창 열기(드롭존이 body면 클릭 생략)
  if (dropZone !== document.body) {
    dropZone.style.cursor = "pointer";
    dropZone.addEventListener("click", () => fileInput?.click());
  }

  // ===== 상태 토글 =====
  function showLoading() {
    loadingEl?.classList.remove("hidden");
    emptyEl?.classList.add("hidden");
    tableEl?.classList.add("hidden");
    window.CheckReportTable?.clear?.();
  }
  function showEmpty() {
    loadingEl?.classList.add("hidden");
    emptyEl?.classList.remove("hidden");
    tableEl?.classList.add("hidden");
  }
  function showTable() {
    loadingEl?.classList.add("hidden");
    emptyEl?.classList.add("hidden");
    tableEl?.classList.remove("hidden");
  }

  // ----- 제출 (/parse/) -----
  submitBtn?.addEventListener("click", async (e) => {
    e.preventDefault();

    const docx = chosen.get("docx");
    const pdf  = chosen.get("pdf");
    if (!docx || !pdf) {
      alert("반드시 docx 1개와 pdf 1개를 함께 올려 주세요.");
      return;
    }

    showLoading();

    try {
      const fd = new FormData();
      fd.append("docx", docx);
      fd.append("pdf",  pdf);

      const resp = await fetch("/parse/", {
        method: "POST",
        body: fd,
        headers: csrftoken ? { "X-CSRFToken": csrftoken } : {}
      });

      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        console.error("[/parse/] 실패", resp.status, t);
        alert(`서버 오류: ${resp.status}`);
        showEmpty();
        return;
      }

      const json = await resp.json();
      const hasData = window.CheckReportTable?.render?.(json) === true;

      if (hasData) {
        showTable();
      } else {
        showEmpty();
      }
    } catch (err) {
      console.error(err);
      alert("요청 중 오류가 발생했습니다.");
      showEmpty();
    }
  });

  // ===== 초기 상태 =====
  // 초기화면: loading 숨김, empty 표시, table 숨김
  loadingEl?.classList.add("hidden");
  emptyEl?.classList.remove("hidden");
  tableEl?.classList.add("hidden");

  // 초기: 파일 리스트 박스 보이도록
  showListVisible(true);
  renderList();
})();
