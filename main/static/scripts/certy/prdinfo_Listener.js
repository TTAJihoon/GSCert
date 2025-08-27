document.addEventListener('DOMContentLoaded', function () {
  const allowedExt = ["html"];
  const contentAuto = document.getElementById('content-auto');
  const inputSummary = document.getElementById('inputSummary');
  const summaryContent = document.getElementById('summaryContent');
  const resultsContent = document.getElementById('resultsContent');
  const manualInput = document.getElementById('manualInput');
  
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
      if (allowedExt.includes(e.target.files[0].name.split('.').at(-1).toLowerCase())) {
        uploadFile(e.target.files[0]);
      } else {
        alert('html 확장자만 업로드 가능합니다.');
        return;
      }
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
      if (allowedExt.includes(e.dataTransfer.files[0].name.split('.').at(-1).toLowerCase())) {
        uploadFile(e.dataTransfer.files[0]);
        const dt = new DataTransfer();
        dt.items.add(e.dataTransfer.files[0]);
        fileInput.files = dt.files;
      } else {
        alert('html 확장자만 업로드 가능합니다.');
        return;
      }
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
