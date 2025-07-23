document.getElementById('queryForm').addEventListener('submit', function() {
  document.getElementById('loadingIndicator').style.display = 'block';
  document.querySelector('.main-content').style.display = 'none';
});

document.getElementById('queryForm').addEventListener('submit', function(e) {
    // 입력 필드 값을 가져옵니다.
    const gsnum = document.getElementById('gsnum').value.trim();
    const project = document.getElementById('project').value.trim();
    const company = document.getElementById('company').value.trim();
    const product = document.getElementById('product').value.trim();

    // 네 가지 필드가 모두 비어 있으면 알림창을 띄웁니다.
    if (!gsnum && !project && !company && !product) {
        e.preventDefault();  // 폼 제출 방지
        alert('검색 조건을 입력해주세요');
    }
});
