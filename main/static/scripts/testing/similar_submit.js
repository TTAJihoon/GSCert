const SIMILAR_RESULT_STORAGE_KEY = 'similar_last_result_v1';

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function htmlWithBreaks(value, fallback = '-') {
  const text = String(value ?? '').trim() || fallback;
  return escapeHtml(text).replace(/\n/g, '<br>');
}

// /summarize_document/ 검색 응답을 화면 및 sessionStorage 복원에 공통 사용한다.
function renderSimilarResults(data, summaryContent, resultsContent) {
  const summaries = Array.isArray(data.summary)
    ? data.summary
    : [data.summary].filter(Boolean);
  const summaryBody = summaries.length > 1
    ? `<ol class="selected-summary-list">${summaries.map(
      text => `<li>${escapeHtml(text)}</li>`
    ).join('')}</ol>`
    : escapeHtml(summaries[0] || '-');
  const rerankWarning = data.rerank_error
    ? `<div class="rerank-warning">${escapeHtml(data.rerank_error)}</div>`
    : '';
  const period = data.search_period || {};
  const periodHtml = period.start
    ? `<div class="search-period-summary">인증일자 ${escapeHtml(period.start)} ~ ${escapeHtml(period.end || '현재')}</div>`
    : '';
  const summaryHtml = `${periodHtml}${summaryBody}${rerankWarning}`;

  const rows = Array.isArray(data.response) ? data.response : [];
  const resultHtml = rows.map(row => {
    const simVal = row.similarity;
    const simPercent = (typeof simVal === 'number' && !isNaN(simVal))
      ? (simVal * 100).toFixed(2)
      : 'N/A';
    const scoreLabel = typeof row.llm_score === 'number' ? 'AI 평균 유사도' : '평균 유사도';

    const firstLine = val => String(val || '-').split('\n')[0].trim() || '-';
    const copyCompany = firstLine(row['회사명']);
    const copyProduct = firstLine(row['제품']);
    const copyTestNo = row['시험번호'] || '-';
    const copyWd = (row['총WD'] || '-').toString();
    const copyDesc = row['제품설명'] || '-';
    const copyText = `${copyWd} WD / ${copyTestNo} / ${copyCompany}-${copyProduct} / ${copyDesc}`;

    return `
      <div class="similar-product">
        <div class="product-header">
          <div class="product-title">
            <table class="company-product-table">
              <tbody>
                <tr>
                  <td class="company-cell">${htmlWithBreaks(row['회사명'])}</td>
                  <td class="separator-cell">-</td>
                  <td class="product-cell">${htmlWithBreaks(row['제품'])}</td>
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
                  <div class="similarity-score">${scoreLabel} ${simPercent}%</div>
                </td>
                <td>
                  <button class="download-btn"><i class="fas fa-download"></i></button>
                </td>
              </tr>
            </table>
          </div>
        </div>
        <div class="product-description">${htmlWithBreaks(row['제품설명'])}</div>
        <div class="product-tags">
          <p>인증일자</p><span class="product-tag">${htmlWithBreaks(row['인증일자'])}</span>
          <p>시험번호</p><span class="product-tag">${htmlWithBreaks(row['시험번호'])}</span>
          <p>WD</p><span class="product-tag wd-tag">${escapeHtml((row['총WD'] || '-').toString())}</span>
          <p>시험기간</p><span class="product-tag">${escapeHtml(row['시작일자'] || '-')}~${escapeHtml(row['종료일자'] || '-')}</span>
          <p>시험원</p><span class="product-tag">${htmlWithBreaks(row['시험원'])}</span>
        </div>
      </div>
    `;
  }).join('');

  summaryContent.innerHTML = summaryHtml;
  resultsContent.innerHTML = resultHtml || '<div class="result-placeholder">조회 결과가 없습니다.</div>';
}

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('queryForm');
  const fileInput = document.getElementById('fileInput');
  const manualInput = document.getElementById('manualInput');
  const contentManual = document.getElementById('content-manual');
  const loading = document.getElementById('loadingContainer');
  const loadingText = loading.querySelector('.loading-text');
  const loadingDescription = loading.querySelector('.loading-description');
  const summaryContent = document.getElementById('summaryContent');
  const resultsContent = document.getElementById('resultsContent');
  const resultsHeader = document.getElementById('resultsHeader');
  const inputSummary = document.getElementById('inputSummary');
  const resultsContainer = document.getElementById('resultsContainer');
  const selectionStep = document.getElementById('summarySelectionStep');
  const optionList = document.getElementById('summaryOptionList');
  const analysisReport = document.getElementById('analysisReport');
  const analysisMetrics = document.getElementById('analysisMetrics');
  const selectionError = document.getElementById('summarySelectionError');
  const selectionCancel = document.getElementById('summaryStepCancel');
  const selectionSearch = document.getElementById('summaryStepSearch');
  let preparedMode = '';

  const savedResult = sessionStorage.getItem(SIMILAR_RESULT_STORAGE_KEY);
  if (savedResult) {
    try {
      renderSimilarResults(JSON.parse(savedResult), summaryContent, resultsContent);
    } catch (error) {
      console.error('저장된 유사 제품 조회 결과 복원 실패:', error);
      sessionStorage.removeItem(SIMILAR_RESULT_STORAGE_KEY);
    }
  }

  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split(';') : [];
    for (const item of cookies) {
      const cookie = item.trim();
      if (cookie.startsWith(`${name}=`)) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return null;
  }

  function showLoading(title, description) {
    loadingText.textContent = title;
    loadingDescription.textContent = description;
    loading.classList.remove('hidden');
    selectionStep.classList.add('hidden');
    resultsContainer.classList.add('hidden');
  }

  function hideLoading() {
    loading.classList.add('hidden');
    resultsContainer.classList.remove('hidden');
  }

  async function postFormData(formData) {
    const response = await fetch('/summarize_document/', {
      method: 'POST',
      body: formData,
      headers: { 'X-CSRFToken': getCookie('csrftoken') }
    });
    const data = await response.json();
    if (!response.ok) {
      const message = typeof data.response === 'string'
        ? data.response
        : '유사 제품 조회 중 오류가 발생했습니다.';
      throw new Error(message);
    }
    return data;
  }

  function delay(milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds));
  }

  async function waitForAnalysis(jobId) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < 30 * 60 * 1000) {
      const statusForm = new FormData();
      statusForm.append('action', 'status');
      statusForm.append('jobId', jobId);
      const status = await postFormData(statusForm);
      loadingText.textContent = `문서 분석 중... ${status.progress || 0}%`;
      loadingDescription.textContent = status.progress_message || '제품 자료를 분석하고 있습니다.';
      if (status.status === 'completed') return status;
      if (status.status === 'failed') {
        throw new Error(status.response || '문서 분석에 실패했습니다.');
      }
      await delay(1200);
    }
    throw new Error('문서 분석 시간이 30분을 초과했습니다. 파일 크기와 형식을 확인해주세요.');
  }

  function closeSelectionStep() {
    selectionStep.classList.add('hidden');
    resultsContainer.classList.remove('hidden');
    selectionError.classList.add('hidden');
  }

  function openSelectionStep(data) {
    const defaults = new Set(data.default_selected_ids || []);
    preparedMode = data.mode || '';
    const fileReports = Array.isArray(data.file_reports) ? data.file_reports : [];
    const coverage = data.coverage || null;
    if (preparedMode === 'file' && coverage) {
      const metricItems = [
        ['파싱 문자', coverage.extracted_chars],
        ['전송 토큰', coverage.llm_input_tokens],
        ['응답 토큰', coverage.llm_output_tokens]
      ];
      analysisMetrics.innerHTML = metricItems.map(([label, value]) => `
        <div class="analysis-metric">
          <span>${label}</span>
          <strong>${Number(value || 0).toLocaleString()}</strong>
        </div>
      `).join('');
      analysisMetrics.classList.remove('hidden');
    } else {
      analysisMetrics.innerHTML = '';
      analysisMetrics.classList.add('hidden');
    }
    if (preparedMode === 'file' && (fileReports.length || coverage)) {
      const parsedCount = fileReports.filter(item => item.status === 'parsed').length;
      const failedCount = fileReports.length - parsedCount;
      const warnings = fileReports.flatMap(item => item.warnings || []);
      if (coverage?.truncated) {
        warnings.push('전체 텍스트는 추출했지만 토큰 안전 한도에 맞춰 관련도와 파일별 범위를 고려한 일부 블록을 LLM에 전달했습니다.');
      }
      analysisReport.innerHTML = `
        <div class="analysis-report-summary">
          <strong>${fileReports.length}개 파일 중 ${parsedCount}개 분석 완료</strong>
          ${failedCount ? `<span class="analysis-report-failed">${failedCount}개 실패</span>` : ''}
          ${coverage ? `<span>텍스트 블록 ${Number(coverage.selected_units || 0).toLocaleString()}개 반영</span>` : ''}
        </div>
        ${fileReports.map(item => `
          <div class="analysis-file-status ${item.status === 'failed' ? 'failed' : ''}">
            <i class="fas ${item.status === 'failed' ? 'fa-exclamation-circle' : 'fa-check-circle'}"></i>
            <span>${escapeHtml(item.name)}</span>
            <small>${item.status === 'failed'
              ? escapeHtml(item.error || '분석 실패')
              : `${Number(item.units || 0).toLocaleString()}개 블록`}</small>
          </div>
        `).join('')}
        ${warnings.length ? `<div class="analysis-warnings">${warnings.map(escapeHtml).join('<br>')}</div>` : ''}
      `;
      analysisReport.classList.remove('hidden');
    } else {
      analysisReport.innerHTML = '';
      analysisReport.classList.add('hidden');
    }
    optionList.innerHTML = (data.options || []).map((option, index) => {
      const checked = defaults.has(option.id) ? ' checked' : '';
      const label = option.is_original
        ? (preparedMode === 'file' ? '원본 추출 요약' : '원본 문장')
        : `추천 문장 ${index + 1}`;
      return `
        <label class="summary-option">
          <input type="checkbox" value="${escapeAttr(option.text)}"${checked}>
          <span class="summary-option-content">
            <span class="summary-option-label">${escapeHtml(label)}</span>
            <span class="summary-option-text">${escapeHtml(option.text)}</span>
          </span>
        </label>
      `;
    }).join('');
    selectionError.classList.add('hidden');
    resultsContainer.classList.add('hidden');
    selectionStep.classList.remove('hidden');
  }

  function getSearchPeriod(mode) {
    const prefix = mode === 'file' ? 'auto' : 'manual';
    return {
      start: document.getElementById(`${prefix}SearchStartDate`).value,
      end: document.getElementById(`${prefix}SearchEndDate`).value
    };
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    const isAutoTab = contentManual.classList.contains('hidden');
    const queuedFiles = typeof window.getSimilarUploadFiles === 'function'
      ? window.getSimilarUploadFiles()
      : Array.from(fileInput.files);
    if (isAutoTab && !queuedFiles.length) {
      alert('파일을 먼저 업로드해주세요.');
      return;
    }
    if (!isAutoTab && !manualInput.value.trim()) {
      alert('제품 설명을 입력해주세요.');
      return;
    }

    showLoading(
      '추천 문장 생성 중...',
      isAutoTab
        ? '업로드한 파일을 분석해 제품 개요 후보를 만들고 있습니다.'
        : '입력 문장과 유사한 제품 개요 후보를 만들고 있습니다.'
    );

    try {
      const formData = new FormData();
      if (isAutoTab) {
        formData.append('action', 'prepare_async');
        formData.append('fileType', 'functionList');
        queuedFiles.forEach(file => formData.append('file', file));
        formData.append('manualInput', '');
      } else {
        formData.append('action', 'prepare');
        formData.append('fileType', 'manual');
        formData.append('manualInput', manualInput.value.trim());
      }
      let data = await postFormData(formData);
      if (isAutoTab && data.job_id) {
        data = await waitForAnalysis(data.job_id);
      }
      loading.classList.add('hidden');
      openSelectionStep(data);
    } catch (error) {
      hideLoading();
      alert(error.message);
    }
  });

  selectionSearch.addEventListener('click', async function () {
    const selected = Array.from(
      optionList.querySelectorAll('input[type="checkbox"]:checked')
    ).map(input => input.value);
    if (!selected.length) {
      selectionError.textContent = '문장을 하나 이상 선택해주세요.';
      selectionError.classList.remove('hidden');
      return;
    }

    const searchPeriod = getSearchPeriod(preparedMode);
    if (!searchPeriod.start || (searchPeriod.end && searchPeriod.start > searchPeriod.end)) {
      selectionError.textContent = '인증일자 검색 기간을 올바르게 입력해주세요.';
      selectionError.classList.remove('hidden');
      return;
    }

    showLoading(
      '유사 제품 검색 중...',
      selected.length > 1
        ? `${selected.length}개 문장의 유사도를 계산하고 평균 순위를 만들고 있습니다.`
        : '선택한 문장으로 유사 제품을 검색하고 있습니다.'
    );

    try {
      const formData = new FormData();
      formData.append('action', 'search');
      formData.append('inputMode', preparedMode);
      formData.append('selectedSummaries', JSON.stringify(selected));
      formData.append('searchStartDate', searchPeriod.start);
      formData.append('searchEndDate', searchPeriod.end);
      const data = await postFormData(formData);
      renderSimilarResults(data, summaryContent, resultsContent);
      sessionStorage.setItem(SIMILAR_RESULT_STORAGE_KEY, JSON.stringify(data));
    } catch (error) {
      resultsContent.innerHTML = `<span style="color:red;">에러: ${escapeHtml(error.message)}</span>`;
    } finally {
      hideLoading();
    }
  });

  selectionCancel.addEventListener('click', closeSelectionStep);
});

document.addEventListener('DOMContentLoaded', function () {
  const tooltip = document.getElementById('copyTooltipLayer');
  let activeButton = null;
  let copiedTimer = null;

  function positionTooltip(button) {
    const rect = button.getBoundingClientRect();
    tooltip.style.left = `${rect.left + rect.width / 2}px`;
    tooltip.style.top = `${rect.top}px`;
  }

  function showTooltip(button) {
    activeButton = button;
    tooltip.textContent = '제품 정보가 복사됩니다';
    positionTooltip(button);
    tooltip.classList.remove('hidden');
  }

  function hideTooltip(button) {
    if (activeButton !== button) return;
    activeButton = null;
    tooltip.classList.add('hidden');
  }

  document.addEventListener('mouseover', event => {
    const button = event.target.closest?.('.copy-btn');
    if (button) showTooltip(button);
  });
  document.addEventListener('mouseout', event => {
    const button = event.target.closest?.('.copy-btn');
    if (button && !button.contains(event.relatedTarget)) hideTooltip(button);
  });
  document.addEventListener('scroll', () => {
    if (activeButton) positionTooltip(activeButton);
  }, true);
  window.addEventListener('resize', () => {
    if (activeButton) positionTooltip(activeButton);
  });

  document.addEventListener('click', event => {
    const button = event.target.closest?.('.copy-btn');
    if (!button) return;

    navigator.clipboard.writeText(button.dataset.copyText || '').then(() => {
      activeButton = button;
      positionTooltip(button);
      tooltip.textContent = '복사되었습니다!';
      tooltip.classList.remove('hidden');
      clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => hideTooltip(button), 1200);
    }).catch(error => {
      console.error('클립보드 복사 실패:', error);
      alert('클립보드 복사에 실패했습니다.');
    });
  });
});
