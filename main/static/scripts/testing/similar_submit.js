document.addEventListener('DOMContentLoaded', function () {  
  const form = document.getElementById('queryForm'); // 제출 폼
  const fileInput = document.getElementById('fileInput');       // 파일 input
  const manualInput = document.getElementById('manualInput');   // 수동입력 textarea
  const contentManual = document.getElementById('content-manual'); // 수동입력 탭 컨테이너
  const loading = document.getElementById('loadingContainer');
  const summaryContent = document.getElementById('summaryContent');
  const resultContent = document.getElementById('resultsContent');
  const resultHeader = document.getElementById('resultHeader');
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
    resultHeader.classList.add('hidden');
    inputSummary.classList.add('hidden');
  }
  function hideLoading() {
    loading.classList.add('hidden');
    resultHeader.classList.remove('hidden');
    inputSummary.classList.remove('hidden');
  }

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

console.log('similarities:', data.similarities);
console.log('response:', data.response);
      
      const summaryhtml = `${data.summary || '요약 없음'}`;
      const resulthtml = (data.response || []).map(row => {
        const simVal = row.similarity;
        const simPercent = (typeof simVal === 'number' && !isNaN(simVal))
          ? (simVal * 100).toFixed(2)
          : 'N/A';

        return `
          <div class="similar-product">
            <div class="product-header">
              <div class="product-title">
                <table class="company-product-table">
                  <tbody>
                    <tr>
                      <td class="company-cell">${(row['회사명'] || '-').replace(/\n/g, '<br>')}</td>
                      <td class="separator-cell">-</td>
                      <td class="product-cell">${(row['제품'] || '-').replace(/\n/g, '<br>')}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="similarity-score">유사도 ${simPercent}%</div>
            </div>
            <div class="product-description">
              ${(row['제품설명'] || '-').replace(/\n/g, '<br>')}
            </div>
            <div class="product-tags">
              <p>인증일자</p><span class="product-tag">${(row['인증일자'] || '-').replace(/\n/g, '<br>')}</span>
              <p>시험번호</p><span class="product-tag">${(row['시험번호'] || '-').replace(/\n/g, '<br>')}</span>
              <p>WD</p><span class="product-tag">${(row['총WD'] || '-').toString()}</span>
              <p>시험기간</p><span class="product-tag">${(row['시작일자'] || '-')}~${(row['종료일자'] || '-')}</span>
              <p>시험원</p><span class="product-tag">${(row['시험원'] || '-').replace(/\n/g, '<br>')}</span>
            </div>
          </div>
        `;
      }).join('');
      summaryContent.innerHTML = summaryhtml;
      resultContent.innerHTML = resulthtml;
    } catch (err) {
      resultContent.innerHTML = `<span style="color:red;">에러: ${err.message}</span>`;
    } finally {
      hideLoading();
    }
  });
});
