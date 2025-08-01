document.addEventListener('DOMContentLoaded', function () {  
  const form = document.getElementById('queryForm'); // 제출 폼
  const fileInput = document.getElementById('fileInput');       // 파일 input
  const manualInput = document.getElementById('manualInput');   // 수동입력 textarea
  const contentManual = document.getElementById('content-Manual'); // 수동입력 탭 컨테이너
  const loading = document.getElementById('loadingContainer');
  const resultContent = document.getElementById('resultsContent');

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        // Does this cookie string begin with the name we want?
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  
  function showLoading() { loading.classList.remove('hidden'); }
  function hideLoading() { loading.classList.add('hidden'); }

  form.addEventListener('submit', async function(e) {
    console.log('폼 제출 이벤트 발생!');
    e.preventDefault();  // <<<<< form submit 완벽 차단!
    const isAutoTab = contentManual.classList.contains('hidden');
    if (isAutoTab) {
      if (!fileInput.files.length) {
        alert('파일을 먼저 업로드해주세요.');
        return;
      }
    } else {
      if (!manualInput.value.trim()) {
        alert('제품 설명을 입력해주세요.');
        return;
      }
    }

    showLoading();
    resultContent.innerHTML = "";

    try {
      const formData = new FormData();
      if (isAutoTab) {
        formData.append('fileType', 'functionList');
        formData.append('file', fileInput.files[0]);
        formData.append('manualInput', '');
      } else {
        formData.append('fileType', 'manual');
        formData.append('file', '');
        formData.append('manualInput', manualInput.value.trim());
      }
      const csrftoken = getCookie('csrftoken');
      const response = await fetch('/summarize_document/', {
        method: 'POST',
        body: formData,
        headers: { 'X-CSRFToken': csrftoken }
      });

      const data = await response.json();
      resultContent.innerHTML = `<p>${(data.response || '결과 없음').replace(/\n/g, '<br>')}</p>`;
    } catch (err) {
      resultContent.innerHTML = `<span style="color:red;">에러: ${err.message}</span>`;
    } finally {
      hideLoading();
    }
  });
});
