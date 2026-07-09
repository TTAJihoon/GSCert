// Null_check
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('queryForm');
    const clearButton = document.getElementById('clearSearchBtn');

    if (clearButton) {
        clearButton.addEventListener('click', function() {
            form.querySelectorAll('input').forEach(function(input) {
                const inputType = (input.getAttribute('type') || 'text').toLowerCase();
                if (inputType === 'hidden' || input.name === 'csrfmiddlewaretoken') {
                    return;
                }
                input.value = '';
            });
            if (typeof setYearsAgo === 'function') {
                setYearsAgo(10);
            }
            const firstInput = document.getElementById('gsnum');
            if (firstInput) firstInput.focus();
        });
    }

    form.addEventListener('submit', function(e) {
        const gsnum = document.getElementById('gsnum').value.trim();
        const project = document.getElementById('project').value.trim();
        const company = document.getElementById('company').value.trim();
        const product = document.getElementById('product').value.trim();
        const tester = document.getElementById('tester').value.trim();
        const comment = document.getElementById('comment').value.trim();

        if (!gsnum && !project && !company && !product && !tester && !comment) {
            e.preventDefault();
            alert('검색 조건을 입력해주세요');
            return false;
        }
    });

    initHistoryColumnFilter();
});

function initHistoryColumnFilter() {
    const tableBody = document.getElementById('resultsTableBody');
    const filterColumn = document.getElementById('historyFilterColumn');
    const filterValue = document.getElementById('historyFilterValue');
    const addButton = document.getElementById('historyFilterAddBtn');
    const resetButton = document.getElementById('historyFilterResetBtn');
    const chipContainer = document.getElementById('historyFilterChips');
    const resultsCount = document.getElementById('resultsCount');

    if (!tableBody || !filterColumn || !filterValue || !addButton || !resetButton || !chipContainer) {
        return;
    }

    const table = tableBody.closest('table');
    const rows = Array.from(tableBody.querySelectorAll('tr'));
    const totalCount = rows.length;
    const initialCountText = resultsCount ? resultsCount.textContent : '';
    let filters = [];
    let emptyRow = null;

    function normalize(value) {
        return (value || '').toString().trim().toLowerCase();
    }

    function getColumnLabel(columnIndex) {
        const option = filterColumn.querySelector(`option[value="${columnIndex}"]`);
        return option ? option.textContent.trim() : `컬럼 ${Number(columnIndex) + 1}`;
    }

    function removeEmptyRow() {
        if (emptyRow) {
            emptyRow.remove();
            emptyRow = null;
        }
    }

    function showEmptyRow() {
        if (emptyRow || !table) return;
        const columnCount = table.querySelectorAll('thead th').length || 1;
        emptyRow = document.createElement('tr');
        emptyRow.className = 'history-filter-empty-row';
        const cell = document.createElement('td');
        cell.colSpan = columnCount;
        cell.textContent = '적용한 컬럼 필터와 일치하는 결과가 없습니다.';
        emptyRow.appendChild(cell);
        tableBody.appendChild(emptyRow);
    }

    function renderChips() {
        chipContainer.innerHTML = '';
        filters.forEach(function(filter, index) {
            const chip = document.createElement('span');
            chip.className = 'history-filter-chip';

            const text = document.createElement('span');
            text.className = 'history-filter-chip-text';
            text.textContent = `${getColumnLabel(filter.column)}: ${filter.rawValue}`;

            const removeButton = document.createElement('button');
            removeButton.type = 'button';
            removeButton.className = 'history-filter-chip-remove';
            removeButton.setAttribute('aria-label', `${text.textContent} 필터 제거`);
            removeButton.textContent = '×';
            removeButton.addEventListener('click', function() {
                filters.splice(index, 1);
                applyFilters();
            });

            chip.appendChild(text);
            chip.appendChild(removeButton);
            chipContainer.appendChild(chip);
        });
    }

    function updateCount(visibleCount) {
        if (!resultsCount) return;
        if (!filters.length) {
            resultsCount.textContent = initialCountText || `🔍 총 ${totalCount}건의 검색 결과`;
            return;
        }
        resultsCount.textContent = `🔍 ${totalCount}건 중 ${visibleCount}건 표시 중`;
    }

    function applyFilters() {
        let visibleCount = 0;
        removeEmptyRow();

        rows.forEach(function(row) {
            const cells = row.querySelectorAll('td');
            const isVisible = filters.every(function(filter) {
                const cell = cells[filter.column];
                return normalize(cell ? cell.textContent : '').includes(filter.value);
            });
            row.style.display = isVisible ? '' : 'none';
            if (isVisible) visibleCount += 1;
        });

        if (filters.length && visibleCount === 0) {
            showEmptyRow();
        }
        renderChips();
        updateCount(visibleCount);
    }

    function addFilter() {
        const rawValue = filterValue.value.trim();
        if (!rawValue) {
            filterValue.focus();
            return;
        }

        filters.push({
            column: Number(filterColumn.value),
            rawValue: rawValue,
            value: normalize(rawValue)
        });
        filterValue.value = '';
        filterValue.focus();
        applyFilters();
    }

    addButton.addEventListener('click', addFilter);
    filterValue.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            addFilter();
        }
    });
    resetButton.addEventListener('click', function() {
        filters = [];
        filterValue.value = '';
        applyFilters();
    });
}
