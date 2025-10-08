(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  let modal, modalTitle, modalContent, closeModalBtn;

  function rebindPopupEvents() {
    if (!modalContent) return;

    // 1. '대책 보기/숨기기' 같은 토글 버튼 기능 재설정
    const toggleLabels = modalContent.querySelectorAll('.more-detail-input + label');
    toggleLabels.forEach(label => {
      label.addEventListener('click', (e) => {
        e.preventDefault(); // 기본 동작 방지
        const input = label.previousElementSibling;
        if (input && input.type === 'checkbox') {
          input.checked = !input.checked;
          // ARIA 속성 업데이트
          input.setAttribute('aria-expanded', input.checked);
        }
      });
    });
    
    // 2. 취약점 상세 내용(URL 목록) 토글 기능 재설정
    const vulnUrlToggles = modalContent.querySelectorAll('.vuln-url[style*="cursor: pointer"]');
    vulnUrlToggles.forEach(toggle => {
      toggle.addEventListener('click', (e) => {
        e.preventDefault();
        const input = toggle.parentElement.querySelector('.vuln-input');
        if (input && input.type === 'checkbox') {
          input.checked = !input.checked;
        }
      });
    });
  }
  
  function downloadInvictiHtml(recordId) {
    const rec = App.state.currentData.find((r) => r.id === recordId);
    if (!rec || !rec.invicti_analysis) {
      alert("다운로드할 HTML 콘텐츠가 없습니다.");
      return;
    }

    const cssStyles = App.state.reportCss || '';
    const htmlBody = rec.invicti_analysis;
    const reportTitle = rec.invicti_report || 'Invicti Report';

    const fullHtmlContent = `
      <!DOCTYPE html>
      <html lang="ko">
      <head>
        <meta charset="UTF-8">
        <title>${reportTitle}</title>
        <style>
          ${cssStyles}
        </style>
      </head>
      <body>
        ${htmlBody}
      </body>
      </html>
    `;

    const sanitizedTitle = reportTitle.replace(/[\\/:*?"<>|]/g, '').trim();
    const fileName = `${sanitizedTitle}.html`;

    const blob = new Blob([fullHtmlContent], { type: 'text/html;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = fileName;
    
    document.body.appendChild(link);
    link.click();
    
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }
  
  function getDefectLevelBadgeClass(level) {
    switch (level) {
      case "H": return "bg-red-100 text-red-800";
      case "M": return "bg-yellow-100 text-yellow-800";
      case "L": return "bg-green-100 text-green-800";
      default:  return "bg-gray-100 text-gray-800";
    }
  }

  function showModal() {
    if (!modal) return;
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function hideModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "auto";
    
    const modalDialog = modal.querySelector('.modal-content');
    if(modalDialog) {
        modalDialog.style.maxWidth = ''; // 모달 너비 기본값으로 복원
    }
  }

  function showRowDetails(recordId) {
    const rec = App.state.currentData.find((r) => r.id === recordId);
    if (!rec) return;
    modalTitle.textContent = "결함 상세 정보";
    modalContent.innerHTML = `
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700">시험환경 OS</label>
            <p class="mt-1 text-sm text-gray-900">${rec.test_env_os || "-"}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">결함정도</label>
            <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getDefectLevelBadgeClass(rec.defect_level)}">
              ${rec.defect_level || "-"}
            </span>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">발생빈도</label>
            <p class="mt-1 text-sm text-gray-900">${rec.frequency || "-"}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">품질특성</label>
            <p class="mt-1 text-sm text-gray-900">${rec.quality_attribute || "-"}</p>
          </div>
          <div class="col-span-2">
            <label class="block text-sm font-medium text-gray-700">Invicti 보고서</label>
            <p class="mt-1 text-sm text-gray-900">${rec.invicti_report || "-"}</p>
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">결함요약</label>
          <p class="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded">${rec.defect_summary || "-"}</p>
        </div>
        ${
          rec.defect_description
            ? `<div>
                 <label class="block text-sm font-medium text-gray-700">결함 설명</label>
                 <div class="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded">
                   ${App.formatCellValue(rec.defect_description, "textarea")}
                 </div>
               </div>`
            : ""
        }
      </div>`;
    showModal();
  }

  function showInvictiAnalysis(recordId) {
    const rec = App.state.currentData.find((r) => r.id === recordId);
    if (!rec) return;

    modalTitle.textContent = "Invicti 원본 보고서 상세 내용";
    const content = rec.invicti_analysis || "<p>상세 보고서 내용을 불러오지 못했습니다.</p>";
    
    modalContent.innerHTML = `
      <div class="text-right mb-2 border-b pb-2">
        <button onclick="SecurityApp.popup.downloadInvictiHtml('${rec.id}')" class="inline-flex items-center px-3 py-1 bg-blue-500 text-white rounded text-xs font-medium hover:bg-blue-600 transition-colors">
          <i class="fas fa-download mr-1"></i> HTML 다운로드
        </button>
      </div>
      <div class="invicti-report-popup" style="max-height: 70vh; overflow-y: auto; text-align: left;">
        ${content}
      </div>
    `;
    
    const modalDialog = modal.querySelector('.modal-content');
    if(modalDialog) {
        modalDialog.style.maxWidth = '80vw';
    }

    showModal();
    rebindPopupEvents();
  }

  function showGptRecommendation(recordId, isLoading = false) {
    const rec = App.state.currentData.find((r) => r.id === recordId);
    if (!rec) return;

    modalTitle.textContent = "GPT 추천 수정 방안";

    let contentHtml;

    // [핵심 수정] isLoading이 true일 때 표시할 UI 변경
    if (isLoading) {
      // 로딩 중일 때 표시할 UI
      contentHtml = `
          <div class="text-center py-8">
              <i class="fas fa-spinner fa-spin text-4xl text-blue-500"></i>
              <p class="mt-4 text-gray-600">GPT가 답변을 생성 중입니다...</p>
          </div>
      `;
    } else {
      // 결과를 받았을 때 표시할 UI
      const content = rec.gpt_recommendation || "GPT의 추천 수정 방안을 받지 못했습니다.";
      contentHtml = `
          <div class="space-y-4 text-left">
              <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                  <div class="flex items-center mb-2">
                      <i class="fas fa-robot text-green-600 mr-2"></i>
                      <span class="font-medium text-green-800">AI 추천 수정 방안</span>
                  </div>
                  <div class="text-sm text-gray-700 whitespace-pre-line leading-relaxed">${content}</div>
              </div>
              <div class="bg-gray-50 rounded-lg p-3">
                  <div class="text-xs text-gray-500">
                      <strong>결함 요약:</strong> ${rec.defect_summary || "-"}<br>
                      <strong>발생 빈도:</strong> ${rec.frequency || "-"}<br>
                      <strong>시험 환경:</strong> ${rec.test_env_os || "-"}
                  </div>
              </div>
          </div>
      `;
    }
    
    modalContent.innerHTML = contentHtml;
    showModal();
  }

  // 공개 API
  App.popup.showModal = showModal;
  App.popup.hideModal = hideModal;
  App.popup.showRowDetails = showRowDetails;
  App.popup.showInvictiAnalysis = showInvictiAnalysis;
  App.popup.showGptRecommendation = showGptRecommendation;
  App.popup.downloadInvictiHtml = downloadInvictiHtml;

  document.addEventListener("DOMContentLoaded", () => {
    modal = document.getElementById("modal");
    modalTitle = document.getElementById("modalTitle");
    modalContent = document.getElementById("modalContent");
    closeModalBtn = document.getElementById("closeModal");

    closeModalBtn && closeModalBtn.addEventListener("click", hideModal);
    // 배경 클릭 닫기 (backdrop 요소에 클래스가 있을 경우)
    modal && modal.addEventListener("click", (e) => {
      if (e.target.classList.contains("modal-backdrop")) hideModal();
      if (e.target === modal) hideModal(); // 안전망
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal && !modal.classList.contains("hidden")) hideModal();
    });
  });
})(window);
