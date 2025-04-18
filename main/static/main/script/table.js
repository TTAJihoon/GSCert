function onlyOne(checkbox) {
  const checkboxes = document.getElementsByName('queryType');
  checkboxes.forEach(cb => {
    if (cb !== checkbox) cb.checked = false;
  });
}

function handleSearch() {
  const queryType = document.querySelector('input[name="queryType"]:checked')?.value || '';
  const company = document.querySelector('input[placeholder*="회사명"]').value;
  const product = document.querySelector('input[placeholder*="제품명"]').value;
  const startDate = document.querySelectorAll('input[type="date"]')[0].value;
  const endDate = document.querySelectorAll('input[type="date"]')[1].value;
  const description = document.querySelector('input[placeholder*="설명"]').value;

  const resultArea = document.getElementById('result-area');
  resultArea.innerHTML = `
    <table class="info-table">
      <thead>
        <tr>
          <th>회사명</th>
          <th>인증일자</th>
          <th>인증번호</th>
          <th>시험번호</th>
          <th>시험WD</th>
          <th colspan="3">관련 문서 다운로드</th>
        </tr>
        <tr>
          <th colspan="2">제품명</th>
          <th colspan="3">제품 개요</th>
        </tr>
        <tr>
          <th>분류</th>
          <th>재계약 여부</th>
          <th>간소화 여부</th>
          <th>수수료</th>
          <th colspan="3">***</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>${company}</td>
          <td>${startDate}</td>
          <td>예: 2025-1234</td>
          <td>예: 시험-5678</td>
          <td>WD-3</td>
          <td colspan="3" rowspan="3">
            <div class="document-icons">
              <img src="/static/main/images/doc-word.png" alt="결과서" title="결과서">
              <img src="/static/main/images/doc-excel1.png" alt="기능리스트" title="기능리스트">
              <img src="/static/main/images/doc-excel2.png" alt="결합리포트" title="결합리포트">
            </div>
          </td>
        </tr>
        <tr>
          <td colspan="2">${product}</td>
          <td colspan="3">${description}</td>
        </tr>
        <tr>
          <td>${queryType}</td>
          <td>아니오</td>
          <td>예</td>
          <td>무료</td>
        </tr>
      </tbody>
    </table>
  `;
}
