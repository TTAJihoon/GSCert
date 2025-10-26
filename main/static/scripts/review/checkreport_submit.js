(function () {
  const fileInput = document.getElementById("fileInput");
  const submitBtn = document.getElementById("submitBtn");

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
    const m = file.name.toLowerCase().match(/\.(\w+)$/);
    return m ? m[1] : "";
  }

  submitBtn?.addEventListener("click", async (e) => {
    e.preventDefault();

    const files = Array.from(fileInput?.files || []);
    if (files.length !== 2) {
      alert("docx 1개 + pdf 1개, 총 2개를 선택해 주세요.");
      return;
    }

    let docxCount = 0, pdfCount = 0;
    for (const f of files) {
      const ext = extOf(f);
      if (ext === "docx") docxCount++;
      else if (ext === "pdf") pdfCount++;
    }
    if (docxCount !== 1 || pdfCount !== 1) {
      alert("반드시 docx 1개와 pdf 1개를 함께 올려 주세요.");
      return;
    }

    const fd = new FormData();
    // A안: 모두 'file' 키로 전송 (백엔드에서 확장자로 구분)
    files.forEach(f => fd.append("file", f));

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
      // 2번 합의: 파서 결과를 '그대로' 반환 → 그대로 콘솔에 표시
      console.log("[checkreport] parser output:", json);

      // (옵션) pages 요약 한 줄 보고 싶다면 아래 주석을 해제
      // if (json && Array.isArray(json.pages)) {
      //   console.table(json.pages.map((p, idx) => ({
      //     page: idx + 1,
      //     header: p.header?.length ?? 0,
      //     footer: p.footer?.length ?? 0,
      //     blocks: p.content?.length ?? 0,
      //   })));
      // }
    } catch (e) {
      console.error(e);
      alert("요청 중 오류가 발생했습니다.");
    }
  });
})();
