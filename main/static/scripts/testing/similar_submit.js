document.addEventListener('DOMContentLoaded', function () {
  // fetch로 서버에서 응답을 받았다면
  const data = await response.json();  // data.response에 문장이 담겨있음
  
  // 결과 박스에 표시
  const resultContent = document.getElementById('resultsContent');
  resultContent.innerHTML = `<p>${data.response.replace(/\n/g, '<br>')}</p>`; // 줄바꿈 처리
});
