// 전역 변수
let currentData = [];
let isEditing = false;
let editingCell = null;
let selectedRows = new Set();

// DOM 요소
const tableBody = document.getElementById('tableBody');
const tableHeader = document.getElementById('tableHeader');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const totalCount = document.getElementById('totalCount');
const exportBtn = document.getElementById('exportBtn');
const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
const addRowBtn = document.getElementById('addRowBtn');
const selectedCount = document.getElementById('selectedCount');
const modal = document.getElementById('modal');
const modalTitle = document.getElementById('modalTitle');
const modalContent = document.getElementById('modalContent');
const closeModal = document.getElementById('closeModal');

// 테이블 스키마 정의
const tableSchema = {
    name: 'defects',
    fields: [
        { name: 'select', type: 'checkbox', label: '선택', editable: false },
        { name: 'test_env_os', type: 'select', label: '시험환경 OS', editable: true, 
          options: ['시험환경<BR/>모든 OS', '-'] },
        { name: 'defect_summary', type: 'textarea', label: '결함요약', editable: true },
        { name: 'defect_level', type: 'select', label: '결함정도', editable: true,
          options: ['H', 'M', 'L'] },
        { name: 'frequency', type: 'select', label: '발생빈도', editable: true,
          options: ['A', 'I'] },
        { name: 'quality_attribute', type: 'text', label: '품질특성', editable: true, defaultValue: '보안성' },
        { name: 'defect_description', type: 'textarea', label: '결함 설명', editable: true },
        { name: 'invicti_popup', type: 'popup', label: 'Invicti 분석', editable: false },
        { name: 'gpt_recommendation', type: 'popup', label: 'GPT 추천 수정 방안', editable: false }
    ]
};

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    loadTableData();
});

// 이벤트 리스너 초기화
function initializeEventListeners() {
    exportBtn.addEventListener('click', exportToExcel);
    deleteSelectedBtn.addEventListener('click', deleteSelectedRows);
    addRowBtn.addEventListener('click', addNewRow);
    closeModal.addEventListener('click', hideModal);
    
    // 모달 배경 클릭시 닫기
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            hideModal();
        }
    });
    
    // ESC 키로 모달 닫기
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (modal.classList.contains('hidden')) {
                cancelEdit();
            } else {
                hideModal();
            }
        }
    });
}

// 테이블 데이터 로드 (로컬 데이터)
function loadTableData() {
    showLoading(true);
    
    // 초기 샘플 데이터 (필요시)
    if (currentData.length === 0) {
        currentData = [
            {
                id: generateId(),
                test_env_os: '시험환경 모든 OS',
                defect_summary: '로그인 페이지에서 SQL 인젝션 취약점 발견',
                defect_level: 'H',
                frequency: 'A',
                quality_attribute: '보안성',
                defect_description: '사용자 입력값에 대한 검증이 부족하여\\nSQL 인젝션 공격이 가능함',
                invicti_analysis: '', // 추후 Invicti 분석 결과
                gpt_recommendation: '' // 추후 GPT 추천 방안
            },
            {
                id: generateId(),
                test_env_os: '/',
                defect_summary: 'XSS 취약점으로 인한 스크립트 실행 가능',
                defect_level: 'M',
                frequency: 'I',
                quality_attribute: '보안성',
                defect_description: '게시판 입력폼에서 스크립트 태그가\\n필터링되지 않아 XSS 공격 가능',
                invicti_analysis: '',
                gpt_recommendation: ''
            }
        ];
    }
    
    renderTable();
    updateTotalCount();
    updateSelectionUI();
    
    setTimeout(() => showLoading(false), 500);
}

// 테이블 렌더링
function renderTable() {
    // 헤더 렌더링
    renderTableHeader();
    
    // 바디 렌더링
    if (currentData.length === 0) {
        showEmptyState(true);
        return;
    }
    
    showEmptyState(false);
    
    tableBody.innerHTML = '';
    currentData.forEach((row, index) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50 transition-colors';
        
        // 각 필드에 대한 셀 생성
        tableSchema.fields.forEach(field => {
            const td = document.createElement('td');
            td.className = 'px-4 py-3 whitespace-nowrap text-sm';
            
            if (field.type === 'checkbox') {
                td.innerHTML = `
                    <input type="checkbox" class="row-checkbox" 
                           onchange="toggleRowSelection('${row.id}', this.checked)"
                           ${selectedRows.has(row.id) ? 'checked' : ''}>
                `;
            } else if (field.type === 'popup') {
                if (field.name === 'invicti_popup') {
                    td.innerHTML = `
                        <button onclick="showInvictiAnalysis('${row.id}')" 
                                class="inline-flex items-center px-3 py-1 bg-purple-100 text-purple-700 rounded-full hover:bg-purple-200 transition-colors text-xs font-medium">
                            <i class="fas fa-search mr-1"></i>
                            분석
                        </button>
                    `;
                } else if (field.name === 'gpt_recommendation') {
                    td.innerHTML = `
                        <button onclick="showGptRecommendation('${row.id}')" 
                                class="inline-flex items-center px-3 py-1 bg-green-100 text-green-700 rounded-full hover:bg-green-200 transition-colors text-xs font-medium">
                            <i class="fas fa-lightbulb mr-1"></i>
                            추천
                        </button>
                    `;
                }
            } else {
                const value = formatCellValue(row[field.name], field.type);
                
                if (field.editable) {
                    td.innerHTML = `
                        <div class="editable-cell p-2 rounded" 
                             onclick="startEdit(this, '${row.id}', '${field.name}', '${field.type}')"
                             data-original-value="${row[field.name] || ''}"
                             data-field-type="${field.type}">
                            <div class="table-cell-content">${value}</div>
                        </div>
                    `;
                } else {
                    td.innerHTML = `<div class="p-2"><div class="table-cell-content">${value}</div></div>`;
                }
            }
            
            tr.appendChild(td);
        });
        
        // 선택된 행 표시
        if (selectedRows.has(row.id)) {
            tr.classList.add('selected-row');
        }
        
        tableBody.appendChild(tr);
    });
}

// 테이블 헤더 렌더링
function renderTableHeader() {
    tableHeader.innerHTML = '';
    
    tableSchema.fields.forEach((field, index) => {
        const th = document.createElement('th');
        th.className = 'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-sky-50';
        
        if (field.type === 'checkbox') {
            th.innerHTML = `
                <input type="checkbox" class="row-checkbox" id="selectAll" 
                       onchange="toggleAllRows(this.checked)">
            `;
        } else {
            th.textContent = field.label;
        }
        
        tableHeader.appendChild(th);
    });
}

// 셀 값 포맷팅
function formatCellValue(value, type) {
    if (!value && value !== 0) return '<span class="text-gray-400">-</span>';
    
    switch (type) {
        case 'date':
            return new Date(value).toLocaleDateString('ko-KR');
        case 'number':
            return Number(value).toLocaleString();
        case 'textarea':
        case 'text':
            // 줄바꿈을 <br>로 변환
            return value.replace(/\n/g, '<br>');
        default:
            // 기본적으로도 줄바꿈 처리
            return value.replace(/\n/g, '<br>');
    }
}

// 편집 시작
function startEdit(element, recordId, fieldName, fieldType) {
    if (isEditing) return;
    
    isEditing = true;
    editingCell = { element, recordId, fieldName, fieldType };
    
    element.classList.add('editing');
    const originalValue = element.dataset.originalValue;
    
    let inputHtml;
    const record = currentData.find(r => r.id === recordId);
    const field = tableSchema.fields.find(f => f.name === fieldName);
    
    switch (fieldType) {
        case 'select':
            inputHtml = `
                <select class="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-sky-500 focus:border-transparent">
                    ${field.options.map(option => 
                        `<option value="${option}" ${originalValue === option ? 'selected' : ''}>${option}</option>`
                    ).join('')}
                </select>
            `;
            break;
        case 'textarea':
            inputHtml = `
                <textarea rows="3" class="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-sky-500 focus:border-transparent resize-none auto-resize">${originalValue || ''}</textarea>
            `;
            break;
        case 'date':
            const dateValue = originalValue ? new Date(originalValue).toISOString().split('T')[0] : '';
            inputHtml = `
                <input type="date" value="${dateValue}" 
                       class="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-sky-500 focus:border-transparent">
            `;
            break;
        case 'number':
            inputHtml = `
                <input type="number" value="${originalValue || ''}" 
                       class="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-sky-500 focus:border-transparent">
            `;
            break;
        case 'text':
            // 텍스트 필드도 textarea로 변경하여 여러 줄 입력 지원
            const textValue = (originalValue || '');
            inputHtml = `
                <textarea rows="2" class="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-sky-500 focus:border-transparent resize-none auto-resize" placeholder="Shift+Enter로 줄바꿈 가능">${textValue}</textarea>
            `;
            break;
        default:
            // 기본도 textarea로 설정
            const defaultValue = (originalValue || '');
            inputHtml = `
                <textarea rows="2" class="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-sky-500 focus:border-transparent resize-none auto-resize" placeholder="Shift+Enter로 줄바꿈 가능">${defaultValue}</textarea>
            `;
    }
    
    element.innerHTML = inputHtml;
    const input = element.querySelector('input, select, textarea');
    input.focus();
    
    // 키보드 이벤트 처리
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            if (e.shiftKey) {
                // Shift+Enter: 줄바꿈 (textarea에서만)
                if (input.tagName.toLowerCase() === 'textarea') {
                    // 기본 동작 허용 (줄바꿈)
                    return;
                }
            } else {
                // Enter만: 저장
                e.preventDefault();
                saveEdit();
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelEdit();
        }
    });
    
    // textarea의 경우 자동 크기 조절
    if (input.tagName.toLowerCase() === 'textarea') {
        input.addEventListener('input', autoResizeTextarea);
        autoResizeTextarea.call(input); // 초기 크기 설정
    }
    
    // 포커스 잃으면 저장
    input.addEventListener('blur', saveEdit);
}

// 편집 저장 (로컬 데이터)
function saveEdit() {
    if (!isEditing || !editingCell) return;
    
    const { element, recordId, fieldName, fieldType } = editingCell;
    const input = element.querySelector('input, select, textarea');
    const newValue = input.value;
    const originalValue = element.dataset.originalValue;
    
    // 값이 변경되지 않았으면 취소
    if (newValue === originalValue) {
        cancelEdit();
        return;
    }
    
    try {
        // 로컬 데이터 업데이트
        const record = currentData.find(r => r.id === recordId);
        if (record) {
            record[fieldName] = newValue;
        }
        
        // UI 업데이트
        element.dataset.originalValue = newValue;
        element.innerHTML = `<div class="table-cell-content">${formatCellValue(newValue, fieldType)}</div>`;
        element.classList.remove('editing');
        
        showSuccess('저장되었습니다.');
        
    } catch (error) {
        console.error('저장 오류:', error);
        showError('저장 중 오류가 발생했습니다.');
        cancelEdit();
    } finally {
        isEditing = false;
        editingCell = null;
    }
}

// 편집 취소
function cancelEdit() {
    if (!isEditing || !editingCell) return;
    
    const { element, fieldType } = editingCell;
    const originalValue = element.dataset.originalValue;
    
    element.innerHTML = `<div class="table-cell-content">${formatCellValue(originalValue, fieldType)}</div>`;
    element.classList.remove('editing');
    
    isEditing = false;
    editingCell = null;
}

// 행 선택 토글
function toggleRowSelection(recordId, isSelected) {
    const row = document.querySelector(`tr:has(input[onchange*="${recordId}"])`);
    
    if (isSelected) {
        selectedRows.add(recordId);
        row?.classList.add('selected-row');
    } else {
        selectedRows.delete(recordId);
        row?.classList.remove('selected-row');
    }
    
    updateSelectionUI();
}

// 전체 행 선택/해제
function toggleAllRows(selectAll) {
    const checkboxes = document.querySelectorAll('.row-checkbox:not(#selectAll)');
    
    checkboxes.forEach(checkbox => {
        const recordId = checkbox.getAttribute('onchange').match(/'([^']+)'/)[1];
        checkbox.checked = selectAll;
        toggleRowSelection(recordId, selectAll);
    });
}

// 선택된 행 삭제 (로컬 데이터)
function deleteSelectedRows() {
    if (selectedRows.size === 0) {
        showError('삭제할 행을 선택해주세요.');
        return;
    }
    
    if (!confirm(`선택된 ${selectedRows.size}개의 행을 삭제하시겠습니까?`)) {
        return;
    }
    
    try {
        // 로컬 데이터에서 선택된 행들 제거
        currentData = currentData.filter(row => !selectedRows.has(row.id));
        
        selectedRows.clear();
        showSuccess('선택된 행이 삭제되었습니다.');
        renderTable();
        updateTotalCount();
        updateSelectionUI();
        
    } catch (error) {
        console.error('삭제 오류:', error);
        showError('삭제 중 오류가 발생했습니다.');
    }
}

// 선택 UI 업데이트
function updateSelectionUI() {
    const count = selectedRows.size;
    selectedCount.textContent = count;
    deleteSelectedBtn.disabled = count === 0;
    
    // 전체 선택 체크박스 상태 업데이트
    const selectAllCheckbox = document.getElementById('selectAll');
    const totalCheckboxes = document.querySelectorAll('.row-checkbox:not(#selectAll)').length;
    
    if (selectAllCheckbox) {
        if (count === 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        } else if (count === totalCheckboxes) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        }
    }
}

// 행 상세 정보 표시
function showRowDetails(recordId) {
    const record = currentData.find(r => r.id === recordId);
    if (!record) return;
    
    modalTitle.textContent = `결함 상세 정보`;
    
    const detailsHtml = `
        <div class="space-y-3">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700">시험환경 OS</label>
                    <p class="mt-1 text-sm text-gray-900">${record.test_env_os || '-'}</p>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700">결함정도</label>
                    <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getDefectLevelBadgeClass(record.defect_level)}">
                        ${record.defect_level || '-'}
                    </span>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700">발생빈도</label>
                    <p class="mt-1 text-sm text-gray-900">${record.frequency || '-'}</p>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700">품질특성</label>
                    <p class="mt-1 text-sm text-gray-900">${record.quality_attribute || '-'}</p>
                </div>
                <div class="col-span-2">
                    <label class="block text-sm font-medium text-gray-700">Invicti 보고서</label>
                    <p class="mt-1 text-sm text-gray-900">${record.invicti_report || '-'}</p>
                </div>
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700">결함요약</label>
                <p class="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded">${record.defect_summary || '-'}</p>
            </div>
            ${record.defect_description ? `
                <div>
                    <label class="block text-sm font-medium text-gray-700">결함 설명</label>
                    <div class="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded">${formatCellValue(record.defect_description, 'textarea')}</div>
                </div>
            ` : ''}
        </div>
    `;
    
    modalContent.innerHTML = detailsHtml;
    showModal();
}

// 결함정도별 배지 클래스
function getDefectLevelBadgeClass(level) {
    switch (level) {
        case 'H':
            return 'bg-red-100 text-red-800';
        case 'M':
            return 'bg-yellow-100 text-yellow-800';
        case 'L':
            return 'bg-green-100 text-green-800';
        default:
            return 'bg-gray-100 text-gray-800';
    }
}

// 모달 표시
function showModal() {
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

// 모달 숨기기
function hideModal() {
    modal.classList.add('hidden');
    document.body.style.overflow = 'auto';
}

// 엑셀 다운로드
function exportToExcel() {
    if (currentData.length === 0) {
        showError('다운로드할 데이터가 없습니다.');
        return;
    }
    
    try {
        // 엑셀용 데이터 준비 (줄바꿈 유지, Invicti 보고서 열 제외)
        const excelData = currentData.map(row => ({
            '시험환경 OS': row.test_env_os || '',
            '결함요약': row.defect_summary || '',
            '결함정도': row.defect_level || '',
            '발생빈도': row.frequency || '',
            '품질특성': row.quality_attribute || '',
            '결함 설명': row.defect_description || ''
        }));
        
        // 워크북 생성
        const wb = XLSX.utils.book_new();
        const ws = XLSX.utils.json_to_sheet(excelData);
        
        // 컬럼 너비 설정
        const colWidths = [
            { wch: 20 }, // 시험환경 OS
            { wch: 30 }, // 결함요약
            { wch: 10 }, // 결함정도
            { wch: 10 }, // 발생빈도
            { wch: 12 }, // 품질특성
            { wch: 50 }  // 결함 설명
        ];
        ws['!cols'] = colWidths;
        
        // 셀 스타일 설정 (가운데 정렬 및 줄바꿈 처리)
        const range = XLSX.utils.decode_range(ws['!ref']);
        
        for (let R = range.s.r; R <= range.e.r; ++R) {
            for (let C = range.s.c; C <= range.e.c; ++C) {
                const cellAddress = XLSX.utils.encode_cell({ r: R, c: C });
                if (!ws[cellAddress]) continue;
                
                // 결함 설명 열(5번째, 인덱스 5)은 왼쪽 정렬, 나머지는 가운데 정렬
                const alignment = C === 5 ? { horizontal: 'left', vertical: 'top', wrapText: true } 
                                         : { horizontal: 'center', vertical: 'center', wrapText: true };
                
                ws[cellAddress].s = {
                    alignment: alignment,
                    font: { name: '맑은 고딕', size: 10 }
                };
                
                // 헤더 스타일
                if (R === 0) {
                    ws[cellAddress].s.font = { name: '맑은 고딕', size: 11, bold: true };
                    ws[cellAddress].s.fill = { fgColor: { rgb: 'E0F2FE' } };
                    ws[cellAddress].s.alignment.horizontal = 'center';
                }
            }
        }
        
        // 행 높이 설정 (줄바꿈 내용을 위해)
        const rowHeights = [];
        for (let R = 0; R <= range.e.r; ++R) {
            rowHeights[R] = { hpt: R === 0 ? 25 : 35 }; // 헤더는 25, 데이터는 35 (줄바꿈 고려)
        }
        ws['!rows'] = rowHeights;
        
        XLSX.utils.book_append_sheet(wb, ws, '결함목록');
        
        // 파일 다운로드
        const fileName = `결함목록_${new Date().toISOString().split('T')[0]}.xlsx`;
        XLSX.writeFile(wb, fileName);
        
        showSuccess('엑셀 파일이 다운로드되었습니다.');
        
    } catch (error) {
        console.error('엑셀 다운로드 오류:', error);
        showError('엑셀 다운로드 중 오류가 발생했습니다.');
    }
}

// 페이지 변경
function changePage(page) {
    if (page < 1 || page > totalPages) return;
    loadTableData(page);
}



// 로딩 상태 표시
function showLoading(show) {
    loadingState.style.display = show ? 'block' : 'none';
    tableBody.style.display = show ? 'none' : 'table-row-group';
}

// 빈 상태 표시
function showEmptyState(show) {
    emptyState.style.display = show ? 'block' : 'none';
    tableBody.style.display = show ? 'none' : 'table-row-group';
}

// 성공 메시지 표시
function showSuccess(message) {
    showToast(message, 'success');
}

// 오류 메시지 표시
function showError(message) {
    showToast(message, 'error');
}

// 토스트 메시지 표시
function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg text-white transition-all transform translate-x-0 ${
        type === 'success' ? 'bg-green-500' : 'bg-red-500'
    }`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    // 애니메이션
    setTimeout(() => toast.classList.add('opacity-0', 'translate-x-full'), 3000);
    setTimeout(() => document.body.removeChild(toast), 3500);
}

// ID 생성 함수
function generateId() {
    return 'row_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// 새 행 추가 (로컬 데이터)
function addNewRow() {
    const newRecord = {
        id: generateId(),
        test_env_os: '시험환경<BR/>모든 OS',
        defect_summary: '',
        defect_level: 'M',
        frequency: 'A',
        quality_attribute: '보안성',
        defect_description: '',
        invicti_analysis: '',
        gpt_recommendation: ''
    };
    
    currentData.unshift(newRecord); // 맨 위에 추가
    renderTable();
    updateTotalCount();
    showSuccess('새 행이 추가되었습니다.');
}

// 총 개수 업데이트
function updateTotalCount() {
    totalCount.textContent = currentData.length;
}

// 페이지 관련 함수들 제거 (페이지네이션 불필요)
function changePage() {
    // 페이지네이션 불필요
}

// Invicti 분석 결과 팝업
function showInvictiAnalysis(recordId) {
    const record = currentData.find(r => r.id === recordId);
    if (!record) return;
    
    modalTitle.textContent = `Invicti 보안 분석 결과`;
    
    const analysisContent = record.invicti_analysis || "Invicti 보고서 분석에 실패하였습니다.";
    
    const detailsHtml = `
        <div class="space-y-4">
            <div class="bg-purple-50 border border-purple-200 rounded-lg p-4">
                <div class="flex items-center mb-2">
                    <i class="fas fa-shield-alt text-purple-600 mr-2"></i>
                    <span class="font-medium text-purple-800">보안 분석 리포트</span>
                </div>
                <div class="text-sm text-gray-700 whitespace-pre-line leading-relaxed">
                    ${analysisContent}
                </div>
            </div>
            <div class="bg-gray-50 rounded-lg p-3">
                <div class="text-xs text-gray-500">
                    <strong>결함 정도:</strong> ${record.defect_level || '-'}<br>
                    <strong>품질 특성:</strong> ${record.quality_attribute || '-'}<br>
                    <strong>시험 환경:</strong> ${record.test_env_os || '-'}
                </div>
            </div>
        </div>
    `;
    
    modalContent.innerHTML = detailsHtml;
    showModal();
}

// GPT 추천 수정 방안 팝업
function showGptRecommendation(recordId) {
    const record = currentData.find(r => r.id === recordId);
    if (!record) return;
    
    modalTitle.textContent = `GPT 추천 수정 방안`;
    
    const recommendationContent = record.gpt_recommendation || "GPT의 추천 수정 방안을 받지 못했습니다.";
    
    const detailsHtml = `
        <div class="space-y-4">
            <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                <div class="flex items-center mb-2">
                    <i class="fas fa-robot text-green-600 mr-2"></i>
                    <span class="font-medium text-green-800">AI 추천 수정 방안</span>
                </div>
                <div class="text-sm text-gray-700 whitespace-pre-line leading-relaxed">
                    ${recommendationContent}
                </div>
            </div>
            <div class="bg-gray-50 rounded-lg p-3">
                <div class="text-xs text-gray-500">
                    <strong>결함 요약:</strong> ${record.defect_summary || '-'}<br>
                    <strong>발생 빈도:</strong> ${record.frequency || '-'}<br>
                    <strong>시험 환경:</strong> ${record.test_env_os || '-'}
                </div>
            </div>
        </div>
    `;
    
    modalContent.innerHTML = detailsHtml;
    showModal();
}

// textarea 자동 크기 조절 함수
function autoResizeTextarea() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 150) + 'px'; // 최대 150px로 제한
}

// 전역 함수로 등록 (HTML에서 호출 가능)
window.showRowDetails = showRowDetails;
window.showInvictiAnalysis = showInvictiAnalysis;
window.showGptRecommendation = showGptRecommendation;
window.toggleRowSelection = toggleRowSelection;
window.toggleAllRows = toggleAllRows;
