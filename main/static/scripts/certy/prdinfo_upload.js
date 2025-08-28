// static/scripts/certy/prdinfo_upload.js
document.addEventListener('DOMContentLoaded', function () {
  const fileInput   = document.getElementById('fileInput');
  const dropArea    = document.getElementById('dropArea');
  const fileListEl  = document.getElementById('fileList');

  const MAX_FILES   = 3;
  const ALLOWED_EXT = ['pdf', 'docx', 'xlsx'];
  let selectedFiles = [];

  const acceptExt = (f) => (f.name.split('.').pop() || '').toLowerCase() && ALLOWED_EXT.includes((f.name.split('.').pop() || '').toLowerCase());
  const isDup = (a, b) => a.name===b.name && a.size===b.size && a.lastModified===b.lastModified;

  function syncInput() {
    const dt = new DataTransfer();
    selectedFiles.forEach(f => dt.items.add(f));
    fileInput.files = dt.files; // 서버 전송은 항상 file-input 경유
  }
  function renderList() {
    if (!selectedFiles.length) {
      fileListEl.classList.add('hidden'); fileListEl.innerHTML = ''; return;
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
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      if (!ALLOWED_EXT.includes(ext)) { alert('업로드 가능한 확장자는 pdf, docx, xlsx 입니다.'); continue; }
      if (selectedFiles.some(s => isDup(s, f))) continue;
      if (selectedFiles.length >= MAX_FILES) { alert('최대 3개까지 업로드할 수 있습니다.'); break; }
      selectedFiles.push(f);
    }
    syncInput(); renderList();
  }
  function removeAt(index) { selectedFiles.splice(index, 1); syncInput(); renderList(); }

  fileListEl?.addEventListener('click', (e) => {
    const rm = e.target.closest('[data-remove]');
    if (!rm) return;
    const idx = parseInt(rm.getAttribute('data-remove'), 10);
    if (!isNaN(idx)) removeAt(idx);
  });

  dropArea?.addEventListener('click', () => fileInput.click());
  dropArea?.addEventListener('dragover', (e) => { e.preventDefault(); dropArea.classList.add('active'); });
  dropArea?.addEventListener('dragleave', () => dropArea.classList.remove('active'));
  dropArea?.addEventListener('drop', (e) => {
    e.preventDefault(); dropArea.classList.remove('active');
    addFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', (e) => addFiles(e.target.files));
});
