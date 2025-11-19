document.addEventListener('DOMContentLoaded', function () {  
  const form = document.getElementById('queryForm'); // 제출 폼
  const fileInput = document.getElementById('fileInput');       // 파일 input
  const manualInput = document.getElementById('manualInput');   // 수동입력 textarea
  const contentManual = document.getElementById('content-manual'); // 수동입력 탭 컨테이너
  const loading = document.getElementById('loadingContainer');
  const summaryContent = document.getElementById('summaryContent');
  const resultsContent = document.getElementById('resultsContent');
  const resultsHeader = document.getElementById('resultsHeader');
  const inputSummary = document.getElementById('inputSummary');

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
  
  function showLoading() {
    loading.classList.remove('hidden');
    resultsHeader.classList.add('hidden');
    inputSummary.classList.add('hidden');
    resultsContent.classList.add('hidden');
  }
  function hideLoading() {
    loading.classList.add('hidden');
    resultsHeader.classList.remove('hidden');
    inputSummary.classList.remove('hidden');
    resultsContent.classList.remove('hidden');
  }

  form.addEventListener('submit', function(e) {
    e.preventDefault()
    showLoading();

    try {
      setTimeout(function() {
        const summaryhtml = `홈페이지 및 문서 정보를 기반으로 자연어 대화로 안내하고 할루시네이션 없는 정확한 정보를 제공하는 AI 챗봇 시스템`;
        const resulthtml = `
        `;
        summaryContent.innerHTML = summaryhtml;
        resultsContent.innerHTML = resulthtml;
      }
    } catch (err) {
      resultsContent.innerHTML = `<span style="color:red;">에러: ${err.message}</span>`;
    } finally {
      hideLoading();
    }
  }, 3000);
});
