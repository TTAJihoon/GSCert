document.addEventListener('DOMContentLoaded', function () {
  const allowedExt = ["pdf", "doc", "docx", "xls", "xlsx", "hwp", "hwpx", "ppt", "pptx", "md"];
  const koreaTodayParts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(new Date());
  const koreaTodayByType = Object.fromEntries(
    koreaTodayParts.map(part => [part.type, part.value])
  );
  const koreaToday = `${koreaTodayByType.year}-${koreaTodayByType.month}-${koreaTodayByType.day}`;
  for (const inputId of ['autoSearchEndDate', 'manualSearchEndDate']) {
    const dateInput = document.getElementById(inputId);
    if (dateInput && !dateInput.value) {
      dateInput.value = koreaToday;
    }
  }
  // 탭 전환 기능
  const tabAuto = document.getElementById('tab-auto');
  const tabManual = document.getElementById('tab-manual');
  const contentAuto = document.getElementById('content-auto');
  const contentManual = document.getElementById('content-manual');
  const inputSummary = document.getElementById('inputSummary');
  const summaryContent = document.getElementById('summaryContent');
  const resultsContent = document.getElementById('resultsContent');
  const manualInput = document.getElementById('manualInput');
  
  tabAuto.addEventListener('click', () => {
    tabAuto.classList.add('active');
    tabManual.classList.remove('active');
    contentAuto.classList.remove('hidden');
    contentManual.classList.add('hidden');
  });
  
  tabManual.addEventListener('click', () => {
    tabManual.classList.add('active');
    tabAuto.classList.remove('active');
    contentManual.classList.remove('hidden');
    contentAuto.classList.add('hidden');
  });
  
  // 파일 업로드 기능
  const dropArea = document.getElementById('dropArea');
  const fileInput = document.getElementById('fileInput');
  const fileList = document.getElementById('fileList');
  let selectedFiles = [];
  window.getSimilarUploadFiles = () => selectedFiles.slice();
  
  dropArea.addEventListener('click', () => {
    fileInput.click();
  });
  
  fileInput.addEventListener('change', (e) => {
    addFiles(Array.from(e.target.files || []));
  });
  
  dropArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropArea.classList.add('active');
  });
  
  dropArea.addEventListener('dragleave', () => {
    dropArea.classList.remove('active');
  });
  
  dropArea.addEventListener('drop', (e) => {
    e.preventDefault();
    dropArea.classList.remove('active');
    
    addFiles(Array.from(e.dataTransfer.files || []));
  });

  fileList.addEventListener('click', (event) => {
    const removeButton = event.target.closest('[data-remove-file-index]');
    if (!removeButton) return;
    selectedFiles.splice(Number(removeButton.dataset.removeFileIndex), 1);
    renderFiles();
  });

  function addFiles(files) {
    const invalid = files.filter(file => {
      const extension = file.name.split('.').at(-1)?.toLowerCase();
      return !allowedExt.includes(extension);
    });
    if (invalid.length) {
      alert(`지원하지 않는 파일이 있습니다: ${invalid.map(file => file.name).join(', ')}\n지원 형식: pdf, doc(x), xls(x), hwp(x), ppt(x), md`);
    }
    const known = new Set(
      selectedFiles.map(file => `${file.name}|${file.size}|${file.lastModified}`)
    );
    files.filter(file => !invalid.includes(file)).forEach(file => {
      const key = `${file.name}|${file.size}|${file.lastModified}`;
      if (!known.has(key)) {
        selectedFiles.push(file);
        known.add(key);
      }
    });
    // 업로드 요청은 selectedFiles를 직접 사용한다. FileList는 브라우저별로
    // 생성/수정 지원이 달라 DataTransfer에 의존하지 않는다.
    fileInput.value = '';
    renderFiles();
  }

  function formatSize(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  }

  function renderFiles() {
    fileList.innerHTML = selectedFiles.map((file, index) => `
      <div class="file-item">
        <div class="file-name" title="${escapeAttr(file.name)}">
          <i class="far fa-file-alt"></i>
          <span>${escapeHtml(file.name)}</span>
          <small>${formatSize(file.size)}</small>
        </div>
        <button type="button" class="remove-file" data-remove-file-index="${index}" aria-label="${escapeAttr(file.name)} 제거">
          <i class="fas fa-times"></i>
        </button>
      </div>
    `).join('');
    fileList.classList.toggle('hidden', selectedFiles.length === 0);
    dropArea.classList.remove('hidden');
  }
});
