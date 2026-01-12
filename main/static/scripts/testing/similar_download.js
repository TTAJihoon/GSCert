document.addEventListener("click", (evt) => {
  const btn = evt.target.closest?.(".download-btn");
  if (!btn) return;

  evt.preventDefault();

  // 버튼이 속한 카드(해당 similar-product) 범위로 제한
  const card = btn.closest(".similar-product");
  if (!card) return;

  // 1) 카드 안의 <p>들 중에서 텍스트가 '시험번호'인 것을 찾기
  const labels = Array.from(card.querySelectorAll(".product-tags p"));
  const testLabel = labels.find(p => (p.textContent || "").trim() === "시험번호");
  if (!testLabel) {
    console.warn("시험번호 라벨을 찾지 못했습니다.");
    return;
  }

  // 2) 그 라벨 다음에 오는 span.product-tag가 시험번호 값
  const testSpan = testLabel.nextElementSibling;
  if (!testSpan || !testSpan.classList.contains("product-tag")) {
    console.warn("시험번호 값 span(product-tag)을 찾지 못했습니다.");
    return;
  }

  const testNo = (testSpan.textContent || "").trim();
  console.log("시험번호:", testNo);

  // 여기서 testNo를 가지고 WS 요청/다운로드 로직 호출하면 됨
  // runEcmJob({ 시험번호: testNo, ... })
});
