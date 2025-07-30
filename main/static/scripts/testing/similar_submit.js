document.addEventListener('DOMContentLoaded', function () {
  const actionButton = document.getElementById('actionButton'); // 제출 버튼
  const fileInput = document.getElementById('fileInput');       // 파일 input
  const manualInput = document.getElementById('manualInput');   // 수동입력 textarea
  const contentManual = document.getElementById('contentManual'); // 수동입력 탭 컨테이너
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

  actionButton.forEach(button => {
    button.addEventListener('click', async function (e) {
      print(submit);
      e.preventDefault();
      
      // 탭 상태 구분: 수동입력 탭이 "안 보이면" 자동입력(파일 탭)
      const isAutoTab = contentManual.classList.contains('hidden');

    // 유효성 검사
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

    // 로딩 표시
    showLoading();
    resultContent.innerHTML = "";

    try {
      const formData = new FormData();

      // 자동입력 탭이면 파일만, 수동입력 탭이면 텍스트만 body에 포함
      if (isAutoTab) {
        formData.append('fileType', 'functionList'); // 필요에 따라 수정
        formData.append('file', fileInput.files[0]);
        formData.append('manualInput', '');
      } else {
        formData.append('fileType', 'manual');
        formData.append('file', ''); // 파일 없음
        formData.append('manualInput', manualInput.value.trim());
      }

      const csrftoken = getCookie('csrftoken');
      const response = await fetch('/summarize_document/', {
        method: 'POST',
        body: formData,
        headers: {
          'X-CSRFToken': csrftoken
        }
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
});
