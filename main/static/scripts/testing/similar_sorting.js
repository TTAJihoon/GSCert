document.addEventListener('DOMContentLoaded', () => {
  const resultsContent = document.getElementById('resultsContent');
  const btnDate = document.getElementById('sortByDateBtn');
  const btnSim = document.getElementById('sortBySimilarityBtn');

  // 정렬 상태 토글 저장용
  let dateAsc = true;
  let simAsc = true;

  // 날짜 문자열을 Date 객체로 변환하는 함수 (시작일자 기준)
  function parseStartDate(productElem) {
    const pTags = productElem.querySelectorAll('.product-tags > p');
    let startDateStr = null;

    for (const p of pTags) {
      if (p.textContent.trim() === '시험기간') {
        if (p.nextElementSibling && p.nextElementSibling.textContent) {
          const periodText = p.nextElementSibling.textContent.trim();
          startDateStr = periodText.split('~')[0];
        }
        break;
      }
    }

    if (!startDateStr) {
      return new Date(0);  // 기본값 (1970-01-01)
    }

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
