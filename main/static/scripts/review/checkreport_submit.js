// GSCert/main/static/scripts/review/checkreport_submit.js
(function () {
  const fileInput  = document.getElementById("fileInput");
  const submitBtn  = document.getElementById("btn-generate");
  const dropZone   = document.getElementById("dropArea") || document.body;
  const fileListEl = document.getElementById("fileList"); // optional

  const loadingEl  = document.getElementById("loadingState");
  const emptyEl    = document.getElementById("emptyState");
  const tableEl    = document.getElementById("resultsTable");

  try { if (fileInput && fileInput.accept !== ".docx,.pdf") fileInput.accept = ".docx,.pdf"; } catch (e) {}

  const CHECK_MIME = false;
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
      chosen.set(ext, f); // 같은 확장자는 교체
      updated = true;
    }
    if (updated) renderList();
  }

  fileInput?.addEventListener("change", (e) => acceptFiles(e.target.files));

  ;["dragenter", "dragover", "dragleave", "drop"].forEach((ev) => {
    dropZone.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); });
  });
  dropZone.addEventListener("dragover", () => dropZone.classList?.add("dragover"));
  dropZone.addEventListener("dragleave", () => dropZone.classList?.remove("dragover"));
  dropZone.addEventListener("drop", (e) => {
    dropZone.classList?.remove("dragover");
    const files = e.dataTransfer?.files ? Array.from(e.dataTransfer.files) : [];
    acceptFiles(files);
  });
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

      // 디버그 헤더 → 서버가 gpt_input / gpt_request / gpt_response_meta를 에코
      const headers = {};
      if (csrftoken) headers["X-CSRFToken"] = csrftoken;
      headers["X-Debug-GPT"] = "1";

      const resp = await fetch("/parse/", { method: "POST", body: fd, headers });

      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        console.error("[/parse/] 실패", resp.status, t);
        alert(`서버 오류: ${resp.status}`);
        showEmpty();
        return;
      }

      const json = await resp.json();

      // === 개발자도구 Console에 '실제 GPT 요청 내용'까지 출력 ===
      if (json?._debug?.gpt_input || json?._debug?.gpt_request) {
        console.groupCollapsed("%c[CheckReport] GPT 디버그 정보", "color:#06b6d4;font-weight:bold");
        if (json._debug.gpt_input) {
          console.info("합쳐진 원본 입력 (combined):", json._debug.gpt_input);
        }
        if (json._debug.gpt_request) {
          console.info("OpenAI에 보낸 요청 전체 (messages/model/params):", json._debug.gpt_request);
        }
        if (json._debug.gpt_response_meta) {
          console.info("OpenAI 응답 메타(usage 등):", json._debug.gpt_response_meta);
        }
        console.groupEnd();
      }

      const hasData = window.CheckReportTable?.render?.(json) === true;
      if (hasData) showTable(); else showEmpty();
    } catch (err) {
      console.error(err);
      alert("요청 중 오류가 발생했습니다.");
      showEmpty();
    }
  });

  // ===== 초기 상태 =====
  loadingEl?.classList.add("hidden");
  emptyEl?.classList.remove("hidden");
  tableEl?.classList.add("hidden");

  showListVisible(true);
  renderList();
})();
