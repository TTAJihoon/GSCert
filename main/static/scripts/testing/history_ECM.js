document.addEventListener('DOMContentLoaded', function () {
    const loading = document.getElementById('loadingIndicator');

    function showLoading(message) {
        if (!loading) return;
        let messageSpan = loading.querySelector('span');
        if (!messageSpan) {
            messageSpan = document.createElement('span');
            loading.appendChild(messageSpan);
        }
        messageSpan.innerHTML = message.replace(/\n/g, '<br>');
        loading.classList.remove('hidden');
    }

    function hideLoading() {
        if (loading) loading.classList.add('hidden');
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/run_job/`);

    socket.onopen = function(e) {
        console.log("WebSocket 연결이 성공적으로 열렸습니다.");
    };

    socket.onclose = function(e) {
        console.error("WebSocket 연결이 닫혔습니다. 사유:", e.reason);
        alert("서버와의 실시간 연결이 끊어졌습니다. 페이지를 새로고침 해주세요.");
    };

    socket.onerror = function(e) {
        console.error("WebSocket 오류 발생:", e);
        alert("서버와 통신 중 오류가 발생했습니다.");
    };

    // 서버로부터 메시지를 받았을 때 처리하는 로직
    socket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        console.log("서버로부터 메시지 수신:", data);

        switch (data.status) {
            case 'wait':
            case 'processing':
                showLoading(data.message);
                break;
            
            case 'success':
                hideLoading();
                // 모든 작업이 완료된 후, 여기서 새 탭 열기를 시도합니다.
                // 이 부분은 브라우저 팝업 차단기에 의해 막힐 수 있습니다.
                try {
                    window.open(data.url, '_blank');
                } catch (err) {
                    console.error("새 탭 열기 실패:", err);
                    alert("새 탭을 여는 데 실패했습니다. 브라우저의 팝업 차단 설정을 확인해주세요.");
                }
                break;

            case 'error':
                hideLoading();
                alert('작업 실패: ' + data.message);
                break;
        }
    };

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.download-btn');
        if (!btn) return;

        if (socket.readyState !== WebSocket.OPEN) {
            alert("서버와 연결이 불안정합니다. 잠시 후 다시 시도해주세요.");
            return;
        }

        const row = btn.closest('tr');
        const cells = row.querySelectorAll('td');
        const certDateRaw = (cells[0]?.textContent || '').trim();
        const testNo = (cells[2]?.textContent || '').trim();

        if (!testNo || !certDateRaw) {
            alert('시험번호 또는 인증일자를 찾을 수 없습니다.');
            return;
        }
        
        // 클릭 시 더 이상 새 탭을 미리 열지 않습니다.
        // 로딩 UI만 표시하고 서버에 메시지를 보냅니다.
        showLoading("서버에 작업을 요청하는 중입니다...");
        socket.send(JSON.stringify({
            '인증일자': certDateRaw,
            '시험번호': testNo
        }));
    });
});
