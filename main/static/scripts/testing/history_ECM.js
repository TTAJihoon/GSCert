document.querySelector('.download-btn').addEventListener('click', function() {
  // 버튼 클릭 시 링크를 띄우기까지 3초(3000ms)의 지연 시간을 설정합니다.
  const delayMilliseconds = 3000;
  const targetUrl = 'http://210.104.181.10:80/url/?key=4e45z1Pg8170auuG';

  console.log(`버튼이 클릭되었습니다. ${delayMilliseconds / 1000}초 후에 새 탭이 열립니다.`);

  const loading = document.getElementById("loadingIndicator");
  loading.classList.remove("hidden");
  
  // 3초 후에 실행될 함수를 setTimeout에 정의합니다.
  setTimeout(function() {
    // window.open(URL, windowName, [features])
    // windowName을 '_blank'로 설정하면 새 탭/창이 열립니다.
    // 추가 옵션(features)을 지정하지 않으면 기본 설정(같은 크기)으로 열립니다.
    window.open(targetUrl, '_blank');
    console.log(`링크가 새 탭에 열렸습니다: ${targetUrl}`);
    loading.classList.add("hidden");
  }, delayMilliseconds);
});
