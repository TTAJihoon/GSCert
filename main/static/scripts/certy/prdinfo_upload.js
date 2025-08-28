// static/scripts/certy/prdinfo_upload.js
document.addEventListener('DOMContentLoaded', function () {
  const fileInput   = document.getElementById('fileInput');
  const dropArea    = document.getElementById('dropArea');
  const fileListEl  = document.getElementById('fileList');

  const MAX_FILES   = 3;
  const ALLOWED_EXT = ['pdf', 'docx', 'xlsx'];

  // 현재 선택 파일을 우리가 관리 (중복·갯수·확장자 제어)
  let selectedFiles = [];

  const acceptExt = (f) => {
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    return ALLOWED_EXT.includes(ext);
  };
  const isDup = (a, b) => a.name===b.name && a.size===b.size && a.lastModified===b.lastModified;

  function syncInput() {
    const dt = new DataTransfer();
    selectedFiles.forEach(f => dt.items.add(f));
    fileInput.files = dt.files; // ✅ 서버 전송은 항상 file-input 경유
  }

  function renderList() {
    if (!fileListEl) return;
    if (!selectedFiles.length) {
      fileListEl.classList.add('hidden');
      fileListEl.innerHTML = '';
      return;
    }
    fileListEl.classList.remove('hidden');
    fileListEl.innerHTML = selectedFiles.map((f, i) => `
      <div class="file-item" data-index="${i}">
        <div class="file-name">${f.name}</div>
        <div class="remove-file" data-remove="${i}" title="제거">
          <i class="fas fa-times"></i>
        </div>
      </div>
    `).join('');
  }

  function addFiles(list) {
    for (const f of Array.from(list || [])) {
      if (!acceptExt(f)) {
        alert('업로드 가능한 확장자는 pdf, docx, xlsx 입니다.');
        continue;
      }
      if (selectedFiles.some(s => isDup(s, f))) continue;
      if (selectedFiles.length >= MAX_FILES) {
        alert('최대 3개까지 업로드할 수 있습니다.');
        break;
      }
      selectedFiles.push(f);
    }
    syncInput();
    renderList();
  }

  function removeAt(index) {
    selectedFiles.splice(index, 1);
    syncInput();
    renderList();
  }

  // 파일 제거(이벤트 위임)
  fileListEl?.addEventListener('click', (e) => {
    const rm = e.target.closest('[data-remove]');
    if (!rm) return;
    const idx = parseInt(rm.getAttribute('data-remove'), 10);
    if (!isNaN(idx)) removeAt(idx);
  });

  // 드래그앤드롭 + 클릭
  dropArea?.addEventListener('click', () => fileInput.click());
  dropArea?.addEventListener('dragover', (e) => { e.preventDefault(); dropArea.classList.add('active'); });
  dropArea?.addEventListener('dragleave', () => dropArea.classList.remove('active'));
  dropArea?.addEventListener('drop', (e) => {
    e.preventDefault();
    dropArea.classList.remove('active');
    addFiles(e.dataTransfer.files);
  });

  // 일반 파일 선택
  fileInput.addEventListener('change', (e) => addFiles(e.target.files));

  // (디버깅용) 전역 접근이 필요하면 아래 주석 해제
  // window.__prdinfo_upload__ = { getSelectedFiles: () => selectedFiles.slice() };
});
