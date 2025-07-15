function updateFormState() {
  const historyRadio = document.getElementById('history');
  const isHistory = historyRadio.checked;

  // 입력창 활성화/비활성화 처리
  document.getElementById('company').disabled = !isHistory;
  document.getElementById('product').disabled = !isHistory;
  
  // 배경색 변경 처리
  document.getElementById('company-group').style.opacity = isHistory ? "1" : "0.5";
  document.getElementById('product-group').style.opacity = isHistory ? "1" : "0.5";
}

// 라디오 버튼 변경 시 이벤트 처리
document.getElementById('history').addEventListener('change', updateFormState);
document.getElementById('similar').addEventListener('change', updateFormState);
