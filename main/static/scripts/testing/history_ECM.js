document.addEventListener('DOMContentLoaded', function () {
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
  }

  const loading = document.getElementById('loadingIndicator');
  const POLL_MS = 1500;                 // 상태 폴링 주기
  const POLL_TIMEOUT_MS = 2 * 60 * 1000; // 최대 대기 2분
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function showLoading() { loading && loading.classList.remove('hidden'); }
  function hideLoading() { loading && loading.classList.add('hidden'); }

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

    if (!testNo)       return alert('시험번호를 찾을 수 없습니다.');
    if (!certDateRaw)  return alert('인증일자를 찾을 수 없습니다.');

    // 팝업 차단 회피용: 사용자 제스처 시점에 새 탭을 미리 열어둔다.
    let previewWin = null;
    try { previewWin = window.open('about:blank', '_blank'); } catch (_) {}

    btn.disabled = true;
    showLoading();

    try {
      // 서버에 시작 요청 (시험번호 + 인증일자 전달)
      const payload = { '시험번호': testNo, '인증일자': certDateRaw };

      const res = await fetch('/api/run-job/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || ''
        },
        body: JSON.stringify(payload),
      });
      const j = await res.json();
      if (!res.ok || !j.jobId) throw new Error(j.error || '작업 생성 실패');

      const jobId = j.jobId;
      const startedAt = Date.now();

      // 폴링: setInterval 대신 await 루프 → finally가 깔끔하게 동작
      while (true) {
        const r = await fetch(`/api/job/${jobId}/`);
        const s = await r.json();

        if (s.status === 'DONE') {
          const link = s.final_link || '';
          console.log('복사된 문장:', link);

          // URL이면 새 탭으로 열기, 아니면 alert로 본문 표시
          if (/^https?:\/\//i.test(link)) {
            if (previewWin && !previewWin.closed) {
              previewWin.location.href = link;
              try { previewWin.focus(); } catch (_) {}
            } else {
              window.open(link, '_blank');
            }
          } else {
            alert('완료!\n' + link);
            if (previewWin && !previewWin.closed) previewWin.close();
          }
          break;
        }

        if (s.status === 'ERROR') {
          throw new Error(s.error || '오류가 발생했습니다.');
        }

        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          throw new Error('처리가 지연되고 있습니다. 잠시 후 다시 시도해 주세요.');
        }

        await sleep(POLL_MS);
      }
    } catch (err) {
      console.error('실패:', err);
      alert('실패: ' + err.message);
      // 실패 시 미리 연 새 탭이 열려 있다면 닫기
      if (previewWin && !previewWin.closed) previewWin.close();
    } finally {
      btn.disabled = false;
      hideLoading();
    }
  });
});
