(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  let modal, modalTitle, modalContent, closeModalBtn;

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
      <div class="invicti-report-popup" 
           style="max-height: 75vh; overflow-y: auto; padding: 5px; background-color: #f1f1f1; text-align: left;">
        ${content}
      </div>
    `;

    const modalDialog = modal.querySelector('.modal-content');
    if(modalDialog) {
        modalDialog.style.maxWidth = '80vw'; // 화면 너비의 80%
    }

    showModal();
  }

  function hideModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "auto";

    // [추가] 모달 너비 원상 복구
    const modalDialog = modal.querySelector('.modal-content');
    if(modalDialog) {
        modalDialog.style.maxWidth = ''; // 기본값으로 복원
    }
  }

  function showGptRecommendation(recordId) {
    const rec = App.state.currentData.find((r) => r.id === recordId);
    if (!rec) return;
    modalTitle.textContent = "GPT 추천 수정 방안";
    const content = rec.gpt_recommendation || "GPT의 추천 수정 방안을 받지 못했습니다.";
    modalContent.innerHTML = `
      <div class="space-y-4">
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
      </div>`;
    showModal();
  }

  // 공개 API
  App.popup.showModal = showModal;
  App.popup.hideModal = hideModal;
  App.popup.showRowDetails = showRowDetails;
  App.popup.showInvictiAnalysis = showInvictiAnalysis;
  App.popup.showGptRecommendation = showGptRecommendation;

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
