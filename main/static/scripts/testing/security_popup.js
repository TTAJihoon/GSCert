(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  function getDom() {
    return {
      modal: document.getElementById("modal"),
      modalTitle: document.getElementById("modalTitle"),
      modalContent: document.getElementById("modalContent"),
      closeBtn: document.getElementById("closeModal"),
      downloadBtn: document.getElementById("downloadHtmlBtn"),
    };
  }

  function open() {
    const { modal } = getDom();
    if (!modal) return;
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
  }

  function close() {
    const { modal } = getDom();
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
  }

  function findRowById(rowId) {
    const st = App.state || {};
    return (st.currentData || []).find((r) => r.id === rowId);
  }

  function buildDownloadHtml(snippetHtml) {
    // 페이지에 주입해 둔 원본 CSS(App.state.reportCss)를 함께 포함해서 다운로드
    const css = (App.state && App.state.reportCss) ? App.state.reportCss : "";
    return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Invicti 분석 스니펫</title>
<style>${css}</style>
</head>
<body>
${snippetHtml}
</body>
</html>`;
  }

  function download(filename, content) {
    const blob = new Blob([content], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.download = filename || "invicti_snippet.html";
    a.href = url;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // 공개 API: 테이블의 "Invicti 분석" 버튼이 호출
  async function showInvictiAnalysis(rowId) {
    const { modalTitle, modalContent, downloadBtn } = getDom();
    const row = findRowById(rowId);
    if (!row) return App.showError("해당 행을 찾을 수 없습니다.");

    // 제목과 내용 주입 (원본 스타일은 이미 App.state.reportCss로 페이지에 주입됨)
    modalTitle.textContent = row.invicti_report || "Invicti 분석";
    modalContent.innerHTML = row.invicti_analysis || "<p>표시할 내용이 없습니다.</p>";

    // 다운로드 버튼 핸들러
    if (downloadBtn) {
      downloadBtn.onclick = () => {
        const full = buildDownloadHtml(modalContent.innerHTML);
        // 파일명은 H2 텍스트(있으면) 기반으로 간단히 생성
        const safeName = (row.invicti_report || "invicti_snippet")
          .replace(/[\\/:*?"<>|]/g, "_")
          .slice(0, 80);
        download(`${safeName}.html`, full);
      };
    }

    open();
  }

  // 모달 공통 이벤트 바인딩
  document.addEventListener("DOMContentLoaded", () => {
    const { modal, closeBtn } = getDom();
    // 닫기
    closeBtn && closeBtn.addEventListener("click", close);
    // 배경 클릭 닫기
    modal && modal.addEventListener("click", (e) => {
      if (e.target.classList.contains("modal-backdrop")) close();
    });
    // ESC 닫기
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
  });

  App.popup.showInvictiAnalysis = showInvictiAnalysis;
})(window);
