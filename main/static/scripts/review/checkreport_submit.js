// main/static/scripts/review/checkreport_submit.js
(function () {
  const fileInput  = document.getElementById("fileInput");
  const submitBtn  = document.getElementById("submitBtn");
  const dropZone   = document.getElementById("dropZone") || document.body;
  const fileListEl = document.getElementById("fileList"); // optional

  // (선택) MIME까지 확인하려면 true로
  const CHECK_MIME = false;

  // 내부 상태: 확장자별 1개만 유지
  const chosen = new Map(); // key: 'docx' | 'pdf', value: File

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

  function renderList() {
    if (!fileListEl) {
      console.log("[checkreport] selected:", Object.fromEntries([...chosen].map(([k, f]) => [k, f?.name])));
      return;
    }
    const items = [];
    for (const [k, f] of chosen) {
      if (f) items.push(`<li><strong>${k.toUpperCase()}</strong>: ${escapeHtml(f.name)} (${f.size} bytes)</li>`);
    }
    fileListEl.innerHTML = items.length ? `<ul class="upload-list">${items.join("")}</ul>` :
      `<div class="muted">docx 1개와 pdf 1개를 선택하세요.</div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));
  }

  function acceptFiles(files) {
    let updated = false;
    for (const f of files) {
      if (!f) continue;
      const ext = extOf(f);
      if (ext !== "docx" && ext !== "pdf") {
        // 무시(확장자 제한)
        continue;
      }
      if (!mimeOk(f, ext)) {
        alert(`파일 형식(MIME)이 올바르지 않습니다: ${f.name}`);
        continue;
      }
      // 같은 확장자면 교체(가장 마지막 드롭/선택이 우선)
      chosen.set(ext, f);
      updated = true;
    }
    if (updated) renderList();
  }

  // ----- 파일 입력(클릭) -----
  fileInput?.addEventListener("change", (e) => {
    acceptFiles(e.target.files || []);
    // 파일 입력창 자체 목록은 유지(재선택 가능)
  });

  // ----- 드래그앤드롭 -----
  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }
  ["dragenter","dragover","dragleave","drop"].forEach(evt => {
    dropZone.addEventListener(evt, preventDefaults, false);
  });

  dropZone.addEventListener("dragover", () => {
    dropZone.classList?.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList?.remove("dragover");
  });
  dropZone.addEventListener("drop", (e) => {
    dropZone.classList?.remove("dragover");
    const dt = e.dataTransfer;
    const files = dt?.files ? Array.from(dt.files) : [];
    acceptFiles(files);
  });

  // 드롭존 클릭 시 파일 선택창 열기(드롭존이 body인 경우엔 동작 안 함)
  if (dropZone !== document.body) {
    dropZone.style.cursor = "pointer";
    dropZone.addEventListener("click", () => fileInput?.click());
  }

  // ----- 제출 -----
  submitBtn?.addEventListener("click", async (e) => {
    e.preventDefault();

    const docx = chosen.get("docx");
    const pdf  = chosen.get("pdf");
    if (!docx || !pdf) {
      alert("반드시 docx 1개와 pdf 1개를 함께 올려 주세요.");
      return;
    }

    const fd = new FormData();
    // A안: 같은 키(file)로 두 개 전송 → 백엔드에서 확장자로 구분
    fd.append("file", docx);
    fd.append("file", pdf);

    try {
      const resp = await fetch("/parse/", {
        method: "POST",
        headers: { "X-CSRFToken": csrftoken },
        body: fd,
      });
      if (!resp.ok) {
        const err = await resp.text();
        console.error("Server error:", err);
        alert("서버 오류가 발생했습니다.");
        return;
      }
      const json = await resp.json();
      console.log("[checkreport] parser output:", json);
      // (원하면 요약 테이블도 표시 가능)
      // if (Array.isArray(json?.pages)) {
      //   console.table(json.pages.map((p, i) => ({
      //     page: i + 1,
      //     header: p.header?.length ?? 0,
      //     footer: p.footer?.length ?? 0,
      //     blocks: p.content?.length ?? 0,
      //   })));
      // }
    } catch (err) {
      console.error(err);
      alert("요청 중 오류가 발생했습니다.");
    }
  });

  // 초기 렌더
  renderList();
})();
