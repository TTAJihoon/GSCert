(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});

  // 전역 상태 (초기 데이터 없음)
  App.state = App.state || {
    currentData: [],
    selectedRows: new Set(),
    isEditing: false,
    editingCell: null,
  };

  App.dom = App.dom || {};

  // 테이블 스키마 (필요 컬럼만)
  App.schema = App.schema || {
    name: "defects",
    fields: [
      { name: "select", type: "checkbox", label: "선택", editable: false, width: "35px" },
      { name: "test_env_os", type: "select", label: "시험환경 OS", editable: true, options: ["시험환경<BR/>모든 OS", "-"], width: "95px" },
      { name: "defect_summary", type: "textarea", label: "결함요약", editable: true, width: "135px" },
      { name: "defect_level", type: "select", label: "결함정도", editable: true, options: ["H", "M", "L"], width: "75px" },
      { name: "frequency", type: "select", label: "발생빈도", editable: true, options: ["A", "I"], width: "75px" },
      { name: "quality_attribute", type: "text", label: "품질특성", editable: true, defaultValue: "보안성", width: "75px" },
      { name: "defect_description", type: "textarea", label: "결함 설명", editable: true, width: "400px" },
      { name: "invicti_popup", type: "popup", label: "Invicti 분석", editable: false, width: "150px" },
      { name: "gpt_recommendation", type: "popup", label: "GPT 추천 수정 방안", editable: false, width: "150px" },
    ],
  };

  // ===== 유틸/공통 UI =====
  function formatCellValue(value, type) {
    if (!value && value !== 0) return '<span class="text-gray-400">-</span>';
    switch (type) {
      case "date": return new Date(value).toLocaleDateString("ko-KR");
      case "number": return Number(value).toLocaleString();
      default: return String(value).replace(/\n/g, "<br>");
    }
  }
  function showEmptyState(show) {
    if (!App.dom.emptyState || !App.dom.tableBody) return;
    App.dom.emptyState.classList.toggle("hidden", !show);
    App.dom.tableBody.style.display = show ? "none" : "table-row-group";
  }
  function showToast(message, type) {
    const el = document.createElement("div");
    el.className = `fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg text-white transition-all ${type === "success" ? "bg-green-500" : "bg-red-500"}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add("opacity-0", "translate-x-full"), 3000);
    setTimeout(() => el.remove(), 3500);
  }
  function showSuccess(msg){ showToast(msg, "success"); }
  function showError(msg){ showToast(msg, "error"); }
  function updateTotalCount(){ App.dom.totalCount && (App.dom.totalCount.textContent = App.state.currentData.length); }
  function generateId(){ return "row_" + Date.now() + "_" + Math.random().toString(36).slice(2, 9); }

  // ===== 렌더링 =====
  function renderTableHeader() {
    const { fields } = App.schema;
    App.dom.tableHeader.innerHTML = "";
    fields.forEach((field) => {
      const th = document.createElement("th");
      th.className = "px-4 py-3 text-center font14 text-gray-500 uppercase tracking-wider bg-sky-50";
      
      if (field.width) {
        th.style.width = field.width;
      }

      th.innerHTML = (field.type === "checkbox")
        ? `<input type="checkbox" id="selectAll" class="row-checkbox" onchange="SecurityApp.editable.toggleAllRows(this.checked)">`
        : field.label;
      App.dom.tableHeader.appendChild(th);
    });
  }

  function renderTable() {
    renderTableHeader(); // 이 함수를 호출하기 위해 바로 위에 정의되어 있어야 합니다.
    const data = App.state.currentData;
    if (!data || data.length === 0) { showEmptyState(true); App.dom.tableBody.innerHTML = ""; return; }
    showEmptyState(false);
    App.dom.tableBody.innerHTML = "";

    data.forEach((row) => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-gray-50 transition-colors";
      tr.dataset.rowId = row.id;

      App.schema.fields.forEach((field) => {
        const td = document.createElement("td");
        td.className = "px-4 py-3 text-sm text-gray-800 align-top text-center";

        if (field.name === 'defect_description') {
          td.classList.remove('text-center');
          td.classList.add('text-left');
        }

        if (field.type === "checkbox") {
          td.innerHTML = `
            <input type="checkbox" class="row-checkbox" data-record-id="${row.id}"
                   onchange="SecurityApp.editable.toggleRowSelection(this.dataset.recordId, this.checked)"
                   ${App.state.selectedRows.has(row.id) ? "checked" : ""}>`;
        } else if (field.type === "popup") {
          td.innerHTML = (field.name === "invicti_popup")
            ? `<button onclick="SecurityApp.popup.showInvictiAnalysis('${row.id}')" class="inline-flex items-center px-3 py-1 bg-purple-100 text-purple-700 rounded-full hover:bg-purple-200 text-xs font-medium"><i class="fas fa-search mr-1"></i>분석</button>`
            : `<button onclick="SecurityApp.gpt.getGptRecommendation('${row.id}')" class="inline-flex items-center px-3 py-1 bg-green-100 text-green-700 rounded-full hover:bg-green-200 text-xs font-medium"><i class="fas fa-lightbulb mr-1"></i>추천</button>`;
        } else {
          const value = formatCellValue(row[field.name], field.type);
          if (field.editable) {
            td.innerHTML = `
              <div class="editable-cell p-2 rounded" data-original-value="${row[field.name] || ""}" data-field-type="${field.type}"
                   onclick="SecurityApp.editable.startEdit(this, '${row.id}', '${field.name}', '${field.type}')">
                <div class="table-cell-content">${value}</div>
              </div>`;
          } else {
            td.innerHTML = `<div class="p-2"><div class="table-cell-content">${value}</div></div>`;
          }
        }
        tr.appendChild(td);
      });

      if (App.state.selectedRows.has(row.id)) tr.classList.add("selected-row");
      App.dom.tableBody.appendChild(tr);
    });

    App.buttons && App.buttons.updateSelectionUI && App.buttons.updateSelectionUI();
  }

  // ===== 편집 =====
  function autoResizeTextarea(){ this.style.height = "auto"; this.style.height = Math.min(this.scrollHeight, 150) + "px"; }
  function startEdit(element, recordId, fieldName, fieldType) {
    if (App.state.isEditing) return;
    App.state.isEditing = true;
    App.state.editingCell = { element, recordId, fieldName, fieldType };

    element.classList.add("editing");
    const originalValue = element.dataset.originalValue;
    const field = App.schema.fields.find((f) => f.name === fieldName);
    let inputHtml = "";

    switch (fieldType) {
      case "select":
        inputHtml = `<select class="w-full px-2 py-1 border rounded focus:ring-2 focus:ring-sky-500">
          ${field.options.map(opt => `<option value="${opt}" ${originalValue === opt ? "selected" : ""}>${opt}</option>`).join("")}
        </select>`;
        break;
      case "textarea":
        inputHtml = `<textarea rows="3" class="w-full px-2 py-1 border rounded focus:ring-2 focus:ring-sky-500 resize-none auto-resize">${originalValue || ""}</textarea>`;
        break;
      default:
        inputHtml = `<textarea rows="2" class="w-full px-2 py-1 border rounded focus:ring-2 focus:ring-sky-500 resize-none auto-resize">${originalValue || ""}</textarea>`;
    }

    element.innerHTML = inputHtml;
    const input = element.querySelector("input, select, textarea");
    input.focus();
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { if (e.shiftKey && input.tagName.toLowerCase() === "textarea") return; e.preventDefault(); saveEdit(); }
      else if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
    });
    if (input.tagName.toLowerCase() === "textarea") { input.addEventListener("input", autoResizeTextarea); autoResizeTextarea.call(input); }
    input.addEventListener("blur", saveEdit);
  }

  function saveEdit() {
    const st = App.state;
    if (!st.isEditing || !st.editingCell) return;
    const { element, recordId, fieldName, fieldType } = st.editingCell;
    const input = element.querySelector("input, select, textarea");
    const newValue = input.value;
    const originalValue = element.dataset.originalValue;

    if (newValue === originalValue) return cancelEdit();
    const rec = st.currentData.find((r) => r.id === recordId);
    if (rec) rec[fieldName] = newValue;

    element.dataset.originalValue = newValue;
    element.innerHTML = `<div class="table-cell-content">${formatCellValue(newValue, fieldType)}</div>`;
    element.classList.remove("editing");
    st.isEditing = false; st.editingCell = null;
    showSuccess("저장되었습니다.");
  }

  function cancelEdit() {
    const st = App.state;
    if (!st.isEditing || !st.editingCell) return;
    const { element, fieldType } = st.editingCell;
    const originalValue = element.dataset.originalValue;
    element.innerHTML = `<div class="table-cell-content">${formatCellValue(originalValue, fieldType)}</div>`;
    element.classList.remove("editing");
    st.isEditing = false; st.editingCell = null;
  }

  // ===== 선택(체크박스) =====
  function toggleRowSelection(recordId, isSelected) {
    const rowEl = document.querySelector(`tr[data-row-id="${recordId}"]`);
    if (isSelected) { App.state.selectedRows.add(recordId); rowEl && rowEl.classList.add("selected-row"); }
    else { App.state.selectedRows.delete(recordId); rowEl && rowEl.classList.remove("selected-row"); }
    App.buttons && App.buttons.updateSelectionUI && App.buttons.updateSelectionUI();
  }
  function toggleAllRows(selectAll) {
    document.querySelectorAll('.row-checkbox[data-record-id]').forEach((cb) => {
      cb.checked = selectAll; toggleRowSelection(cb.dataset.recordId, selectAll);
    });
  }

  // ===== 데이터 주입 API (업로드 파싱 결과를 여기로 넣음) =====
  function setData(rows) {
    App.state.currentData = Array.isArray(rows) ? rows : [];
    App.state.selectedRows.clear();
    renderTable();
    updateTotalCount();
  }
  function clearData() {
    setData([]);
  }

  // 공개 API
  App.formatCellValue = formatCellValue;
  App.showEmptyState = showEmptyState;
  App.showSuccess = showSuccess;
  App.showError = showError;
  App.updateTotalCount = updateTotalCount;
  App.generateId = generateId;
  App.renderTable = renderTable;
  App.setData = setData;
  App.clearData = clearData;

  App.editable = { startEdit, saveEdit, cancelEdit, autoResizeTextarea, toggleRowSelection, toggleAllRows };

  // 초기화
  document.addEventListener("DOMContentLoaded", () => {
    App.dom = {
      tableBody: document.getElementById("tableBody"),
      tableHeader: document.getElementById("tableHeader"),
      loadingState: document.getElementById("loadingState"),
      emptyState: document.getElementById("emptyState"),
      totalCount: document.getElementById("totalCount"),
    };
    App.dom.loadingState && App.dom.loadingState.classList.add("hidden");
    renderTable();
    updateTotalCount();
  });
})(window);
