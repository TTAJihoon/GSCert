const SIMILAR_RESULT_STORAGE_KEY = 'similar_last_result_v1';

function escapeAttr(str) {
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

// data(=/summarize_document/ 응답 JSON)를 받아 요약/결과 영역의 HTML을 만든다.
// 최초 제출 시와, 새로고침 후 sessionStorage에서 복원할 때 모두 이 함수를 쓴다.
function renderSimilarResults(data, summaryContent, resultsContent) {
  const rerankWarning = data.rerank_error
    ? `<div class="rerank-warning">${data.rerank_error}</div>`
    : '';
  const summaryhtml = `${data.summary || '요약 없음'}${rerankWarning}`;
  const rows = Array.isArray(data.response) ? data.response : [];
  const resulthtml = rows.map(row => {
    const simVal = row.similarity;
    const simPercent = (typeof simVal === 'number' && !isNaN(simVal))
      ? (simVal * 100).toFixed(2)
      : 'N/A';
    const scoreLabel = typeof row.llm_score === 'number' ? 'AI 유사도' : '유사도';

    const copyCompany = row['회사명'] || '-';
    const copyProduct = row['제품'] || '-';
    const copyTestNo = row['시험번호'] || '-';
    const copyWd = (row['총WD'] || '-').toString();
    const copyDesc = row['제품설명'] || '-';
    const copyText = `${copyTestNo} ${copyCompany}-${copyProduct} ${copyWd}\n${copyDesc}`;

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
          <div>
            <table>
              <tr>
                <td class="copy-btn-cell">
                  <div class="copy-btn-wrap">
                    <button type="button" class="copy-btn" data-copy-text="${escapeAttr(copyText)}" aria-label="제품 정보 복사">
                      <i class="fas fa-copy"></i>
                    </button>
                    <span class="copy-btn-tooltip">제품 정보가 복사됩니다</span>
                  </div>
                </td>
                <td>
                  <div class="similarity-score" id="similarity-score">${scoreLabel} ${simPercent}%</div>
                </td>
                <td>
                  <button class="download-btn"><i class="fas fa-download"></i></button>
                </td>
              </tr>
            </table>
          </div>
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
  resultsContent.innerHTML = resulthtml;
}

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

  // 새로고침해도 직전 조회 결과가 유지되도록, sessionStorage에 저장해둔 마지막 결과를 복원한다.
  const savedResult = sessionStorage.getItem(SIMILAR_RESULT_STORAGE_KEY);
  if (savedResult) {
    try {
      renderSimilarResults(JSON.parse(savedResult), summaryContent, resultsContent);
    } catch (e) {
      console.error('저장된 유사 제품 조회 결과 복원 실패:', e);
      sessionStorage.removeItem(SIMILAR_RESULT_STORAGE_KEY);
    }
  }

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
      if (!response.ok) {
        const message = typeof data.response === 'string' ? data.response : '유사 제품 조회 중 오류가 발생했습니다.';
        throw new Error(message);
      }

console.log('similarities:', data.similarities);
console.log('response:', data.response);

      renderSimilarResults(data, summaryContent, resultsContent);

      try {
        sessionStorage.setItem(SIMILAR_RESULT_STORAGE_KEY, JSON.stringify(data));
      } catch (e) {
        console.error('유사 제품 조회 결과 저장 실패:', e);
      }
    } catch (err) {
      resultsContent.innerHTML = `<span style="color:red;">에러: ${err.message}</span>`;
    } finally {
      hideLoading();
    }
  });
});

document.addEventListener('click', (evt) => {
  const btn = evt.target.closest?.('.copy-btn');
  if (!btn) return;

  const text = btn.dataset.copyText || '';
  navigator.clipboard.writeText(text).then(() => {
    const tooltip = btn.parentElement.querySelector('.copy-btn-tooltip');
    if (!tooltip) return;
    const original = tooltip.textContent;
    tooltip.textContent = '복사되었습니다!';
    setTimeout(() => { tooltip.textContent = original; }, 1200);
  }).catch((err) => {
    console.error('클립보드 복사 실패:', err);
    alert('클립보드 복사에 실패했습니다.');
  });
});
