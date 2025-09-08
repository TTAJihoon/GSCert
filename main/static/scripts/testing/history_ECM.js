document.addEventListener('DOMContentLoaded', function () {
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.download-btn');
    if (!btn) return;

    const row = btn.closest('tr');
    const cells = row.querySelectorAll('td');
    const testNo = (cells[2]?.textContent || "").trim();  // ★ 3번째 칸 = 시험번호

    if (!testNo) return alert("시험번호를 찾을 수 없습니다.");

    btn.disabled = true;

    try {
      const res = await fetch('/api/run-job/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ "시험번호": testNo }),
      });
      const j = await res.json();
      if (!j.jobId) throw new Error(j.error || '작업 생성 실패');

      const jobId = j.jobId;
      const timer = setInterval(async () => {
        const r = await fetch(`/api/job/${jobId}/`);
        const s = await r.json();
        if (s.status === 'DONE') {
          clearInterval(timer);
          btn.disabled = false;
          // 복사된 문장을 바로 보여주거나 새 탭으로 열기
          console.log('복사된 문장:', s.final_link);
          alert('완료!\n' + s.final_link);
        } else if (s.status === 'ERROR') {
          clearInterval(timer);
          btn.disabled = false;
          alert('실패: ' + (s.error || '원인 불명'));
        }
      }, 1500);

    } catch (err) {
      btn.disabled = false;
      alert('요청 실패: ' + err.message);
    }
  });
});
