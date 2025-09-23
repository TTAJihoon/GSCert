(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.buttons = App.buttons || {};

  let exportBtn, deleteSelectedBtn, addRowBtn, selectedCountEl;

  // 선택 UI
  function updateSelectionUI() {
    const count = App.state.selectedRows.size;
    selectedCountEl && (selectedCountEl.textContent = count);
    if (deleteSelectedBtn) deleteSelectedBtn.disabled = count === 0;

    const selectAll = document.getElementById("selectAll");
    const totalCheckboxes = document.querySelectorAll('.row-checkbox[data-record-id]').length;
    if (selectAll) {
      if (count === 0) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
      } else if (count === totalCheckboxes && totalCheckboxes > 0) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
      } else {
        selectAll.checked = false;
        selectAll.indeterminate = true;
      }
    }
  }

  function addNewRow() {
    const rec = {
      id: App.generateId(),
      test_env_os: "시험환경<BR/>모든 OS",
      defect_summary: "",
      defect_level: "M",
      frequency: "A",
      quality_attribute: "보안성",
      defect_description: "",
      invicti_analysis: "",
      gpt_recommendation: "",
    };
    App.state.currentData.unshift(rec);
    App.renderTable();
    App.updateTotalCount();
    App.showSuccess("새 행이 추가되었습니다.");
  }

  function deleteSelectedRows() {
    const sel = App.state.selectedRows;
    if (sel.size === 0) return App.showError("삭제할 행을 선택해주세요.");
    if (!confirm(`선택된 ${sel.size}개의 행을 삭제하시겠습니까?`)) return;

    App.state.currentData = App.state.currentData.filter((row) => !sel.has(row.id));
    sel.clear();

    App.renderTable();
    App.updateTotalCount();
    updateSelectionUI();
    App.showSuccess("선택된 행이 삭제되었습니다.");
  }

  function exportToExcel() {
    if (!App.state.currentData.length) return App.showError("다운로드할 데이터가 없습니다.");
    try {
      const excelData = App.state.currentData.map((row) => ({
        "시험환경 OS": row.test_env_os || "",
        "결함요약": row.defect_summary || "",
        "결함정도": row.defect_level || "",
        "발생빈도": row.frequency || "",
        "품질특성": row.quality_attribute || "",
        "결함 설명": row.defect_description || "",
      }));
      const wb = XLSX.utils.book_new();
      const ws = XLSX.utils.json_to_sheet(excelData);
      ws["!cols"] = [{ wch: 20 }, { wch: 30 }, { wch: 10 }, { wch: 10 }, { wch: 12 }, { wch: 50 }];
      XLSX.utils.book_append_sheet(wb, ws, "결함목록");
      const fileName = `결함목록_${new Date().toISOString().split("T")[0]}.xlsx`;
      XLSX.writeFile(wb, fileName);
      App.showSuccess("엑셀 파일이 다운로드되었습니다.");
    } catch (err) {
      console.error("엑셀 다운로드 오류:", err);
      App.showError("엑셀 다운로드 중 오류가 발생했습니다.");
    }
  }

  // 공개 API
  App.buttons.updateSelectionUI = updateSelectionUI;
  App.buttons.addNewRow = addNewRow;
  App.buttons.deleteSelectedRows = deleteSelectedRows;
  App.buttons.exportToExcel = exportToExcel;

  document.addEventListener("DOMContentLoaded", () => {
    exportBtn = document.getElementById("exportBtn");
    deleteSelectedBtn = document.getElementById("deleteSelectedBtn");
    addRowBtn = document.getElementById("addRowBtn");
    selectedCountEl = document.getElementById("selectedCount");

    exportBtn && exportBtn.addEventListener("click", exportToExcel);
    deleteSelectedBtn && deleteSelectedBtn.addEventListener("click", deleteSelectedRows);
    addRowBtn && addRowBtn.addEventListener("click", addNewRow);

    updateSelectionUI();
  });
})(window);
