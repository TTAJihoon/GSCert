(function () {
  const CELL_SELECTOR = '.cert-date-copy-cell';
  const DRAG_THRESHOLD = 4;
  let pointerState = null;
  let toastTimer = null;

  function selectedTextTouchesCell(cell) {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      return false;
    }
    return cell.contains(selection.anchorNode) || cell.contains(selection.focusNode);
  }

  function fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    if (!copied) throw new Error('copy command failed');
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch (error) {
        console.warn('클립보드 API 복사 실패, 대체 방식을 사용합니다.', error);
      }
    }
    fallbackCopy(text);
  }

  function showToast(message) {
    const toast = document.getElementById('historyCopyToast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.remove('hidden');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.add('hidden'), 1400);
  }

  function cellText(row, selector) {
    return row.querySelector(selector)?.textContent?.trim() || '-';
  }

  function firstLine(text) {
    return String(text || '-').split(/\r?\n/)[0].trim() || '-';
  }

  function buildProductCopyText(cell) {
    const row = cell.closest('tr');
    if (!row) return '';
    const wd = cellText(row, '.history-copy-wd');
    const testNumber = cellText(row, '.history-copy-test-number');
    const company = firstLine(cellText(row, '.history-copy-company'));
    const product = firstLine(cellText(row, '.history-copy-product'));
    const description = cellText(row, '.history-copy-description');
    return `${wd} WD / ${testNumber} / ${company}-${product} / ${description}`;
  }

  async function copyCellProduct(cell) {
    try {
      await copyText(buildProductCopyText(cell));
      showToast('제품 정보가 복사되었습니다.');
    } catch (error) {
      console.error('제품 정보 복사 실패:', error);
      showToast('제품 정보 복사에 실패했습니다.');
    }
  }

  document.addEventListener('pointerdown', event => {
    const cell = event.target.closest?.(CELL_SELECTOR);
    if (!cell || event.button !== 0) {
      pointerState = null;
      return;
    }
    pointerState = {
      cell,
      startX: event.clientX,
      startY: event.clientY,
      moved: false
    };
  });

  document.addEventListener('pointermove', event => {
    if (!pointerState || pointerState.moved) return;
    const distanceX = Math.abs(event.clientX - pointerState.startX);
    const distanceY = Math.abs(event.clientY - pointerState.startY);
    pointerState.moved = distanceX > DRAG_THRESHOLD || distanceY > DRAG_THRESHOLD;
  });

  document.addEventListener('click', event => {
    const cell = event.target.closest?.(CELL_SELECTOR);
    if (!cell) return;

    const wasDragged = pointerState?.cell === cell && pointerState.moved;
    pointerState = null;
    if (wasDragged || selectedTextTouchesCell(cell)) return;

    copyCellProduct(cell);
  });

  document.addEventListener('keydown', event => {
    const cell = event.target.closest?.(CELL_SELECTOR);
    if (!cell || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    copyCellProduct(cell);
  });
})();
