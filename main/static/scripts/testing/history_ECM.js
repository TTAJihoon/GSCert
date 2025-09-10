document.addEventListener('DOMContentLoaded', function () {
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
  }

  const loading = document.getElementById('loadingIndicator');
  const POLL_MS = 1500;            // 상태 폴링 주기
  const POLL_TIMEOUT_MS = 2 * 60 * 1000; // 최대 대기 2분

  function showLoading() { loading && loading.classList.remove('hidden'); }
  function hideLoading() { loading && loading.classList.add('hidden'); }
  function openInNewTab(url) {
    if (!url) return;
    const w = window.open(url, '_blank', 'noopener,noreferrer');
    if (w) return; // 성공
    // 팝업 차단 폴백: 보이지 않는 앵커 클릭
    const a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => a.remove(), 0);
  }
  
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.download-btn');
    if (!btn) return;

    const row = btn.closest('tr');
    const cells = row ? row.querySelectorAll('td') : null;
    if (!cells || cells.length < 3) {
      alert('행 구조가 예상과 다릅니다. (인증일자=1번째 칸, 시험번호=3번째 칸)');
      return;
    }

    // ★ 1번째 칸(인증일자), 3번째 칸(시험번호)
    const certDateRaw = (cells[0]?.textContent || '').trim();  // 예: "2025.08.25"
    const testNo      = (cells[2]?.textContent || '').trim();  // 예: "GS-A-25-0099"

    if (!testNo) {
      alert('시험번호를 찾을 수 없습니다.');
      return;
    }
    if (!certDateRaw) {
      alert('인증일자를 찾을 수 없습니다.');
      return;
    }

    btn.disabled = true;
    showLoading();

    try {
      // ★ 시험번호 + 인증일자 함께 전달
      const payload = { "시험번호": testNo, "인증일자": certDateRaw };

      const res = await fetch('/api/run-job/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // start_job이 csrf_exempt라면 없어도 되지만, 있으면 더 안전
          'X-CSRFToken': getCookie('csrftoken') || ''
        },
        body: JSON.stringify(payload),
      });
      const j = await res.json();
      if (!res.ok || !j.jobId) throw new Error(j.error || '작업 생성 실패');

      const jobId = j.jobId;
      const startedAt = Date.now();

      const timer = setInterval(async () => {
        try {
          const r = await fetch(`/api/job/${jobId}/`);
          const s = await r.json();

          if (s.status === 'DONE') {
            console.log('복사된 문장:', s.final_link);
            openInNewTab(s.final_link);
          } else if (s.status === 'ERROR') {
            console.error('실패:', s.error);
            alert('실패: ' + (s.error || '오류가 발생했습니다.'));
          } else if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
            alert('처리가 지연되고 있습니다. 잠시 후 다시 시도해 주세요.');
          }
        } catch (err) {
          alert('상태 조회 실패: ' + err.message);
        } finally {
          clearInterval(timer);
        }
      }, POLL_MS);

    } catch (err) {
      alert('요청 실패: ' + err.message);
    } finally {
      btn.disabled = false;
      hideLoading();
    }
  });
});
