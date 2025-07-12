function setYearsAgo(years) {
  const endDateInput = document.getElementById('end_date');
  const startDateInput = document.getElementById('start_date');
  
  const today = new Date();
  
  const pastDate = new Date(today.getFullYear() - years, today.getMonth(), today.getDate());

  // 날짜 포맷을 yyyy-mm-dd로 맞춤
  const formatDate = (date) => {
    let month = '' + (date.getMonth() + 1);
    let day = '' + date.getDate();
    const year = date.getFullYear();

    if (month.length < 2) month = '0' + month;
    if (day.length < 2) day = '0' + day;

    return [year, month, day].join('-');
  };

  // 시작 날짜를 버튼 클릭 시점으로부터 N년 전 날짜로 설정
  startDateInput.value = formatDate(pastDate);
  
  // 종료 날짜는 오늘 날짜로 자동 설정
  endDateInput.value = formatDate(today);
}
