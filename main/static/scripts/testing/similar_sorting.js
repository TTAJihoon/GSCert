document.addEventListener('DOMContentLoaded', () => {
  const resultsContent = document.getElementById('resultsContent');
  const btnDate = document.getElementById('sortByDateBtn');
  const btnSim = document.getElementById('sortBySimilarityBtn');

  // 정렬 상태 토글 저장용
  let dateAsc = true;
  let simAsc = true;

  // 날짜 문자열을 Date 객체로 변환하는 함수 (시작일자 기준)
  function parseStartDate(productElem) {
    // 시험기간 텍스트 예시: "2023-01-01~2023-12-31"
    const periodText = productElem.querySelector('.product-tags p:nth-child(4)').nextElementSibling.textContent.trim();
    // 대략 “시작일자~종료일자” 구조라 가정하고 ~로 분리
    const startDateStr = periodText.split('~')[0];
    return new Date(startDateStr);
  }

  // 유사도 숫자 가져오는 함수 (%. 숫자만)
  function parseSimilarity(productElem) {
    const simText = productElem.querySelector('.similarity-score').textContent.trim(); // 예: "유사도 78.23%"
    const match = simText.match(/([\d.]+)%/);
    return match ? parseFloat(match[1]) : 0;
  }

  // 정렬 후 다시 DOM에 붙이기
  function sortProducts(compareFn) {
    const products = Array.from(resultsContent.querySelectorAll('.similar-product'));
    products.sort(compareFn);
    products.forEach(p => resultsContent.appendChild(p));
  }

  // 날짜 정렬 버튼 클릭 이벤트
  btnDate.addEventListener('click', () => {
    sortProducts((a, b) => {
      const dateA = parseStartDate(a);
      const dateB = parseStartDate(b);
      return dateAsc ? dateA - dateB : dateB - dateA;
    });
    dateAsc = !dateAsc;  // 토글
  });

  // 유사도 정렬 버튼 클릭 이벤트
  btnSim.addEventListener('click', () => {
    sortProducts((a, b) => {
      const simA = parseSimilarity(a);
      const simB = parseSimilarity(b);
      return simAsc ? simA - simB : simB - simA;
    });
    simAsc = !simAsc;  // 토글
  });
});
