document.addEventListener('DOMContentLoaded', function () {
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
  const fileName = document.getElementById('fileName');
  const removeFile = document.getElementById('removeFile');
  
  dropArea.addEventListener('click', () => {
    fileInput.click();
  });
  
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
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
    
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });
  
  removeFile.addEventListener('click', () => {
    fileList.classList.add('hidden');
    dropArea.classList.remove('hidden');
    fileInput.value = '';
  });
  
  function uploadFile(file) {
    fileName.textContent = file.name;
    fileList.classList.remove('hidden');
    dropArea.classList.add('hidden');
    
    // 업로드된 파일 이름을 요약 영역에 표시
    summaryContent.textContent = file.name;
  }
});
