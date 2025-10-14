// history_ECM.js (WebSocket 버전)

document.addEventListener('DOMContentLoaded', function () {
    const loading = document.getElementById('loadingIndicator');

    function showLoading(message) {
        if (!loading) return;
        // 로딩 메시지를 동적으로 변경할 수 있도록 span 요소를 찾거나 생성합니다.
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

    // 페이지 로드 시 웹소켓 연결을 설정합니다.
    // 'ws://'는 http, 'wss://'는 https 환경에 맞춰 사용해야 합니다.
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

    // 서버로부터 메시지를 받았을 때 처리하는 핵심 로직
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
                const url = data.url;
                if (url && /^https?:\/\//i.test(url)) {
                    // 미리 열어둔 탭이 있다면 그 탭을 사용하고, 없다면 새로 엽니다.
                    if (window.previewWin && !window.previewWin.closed) {
                        window.previewWin.location.href = url;
                        try { window.previewWin.focus(); } catch (_) {}
                    } else {
                        window.open(url, '_blank');
                    }
                } else {
                    alert('작업은 완료되었으나 유효한 URL을 받지 못했습니다:\n' + url);
                }
                // 성공 후, 전역 변수로 관리하던 미리 열린 창 참조를 초기화합니다.
                window.previewWin = null; 
                break;

            case 'error':
                hideLoading();
                alert('작업 실패: ' + data.message);
                if (window.previewWin && !window.previewWin.closed) {
                    window.previewWin.close();
                }
                window.previewWin = null;
                break;
        }
    };


    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.download-btn');
        if (!btn) return;

        // 웹소켓 연결이 불안정한 경우 작업을 시작하지 않습니다.
        if (socket.readyState !== WebSocket.OPEN) {
            alert("서버와 연결이 불안정합니다. 잠시 후 다시 시도해주세요.");
            return;
        }

        const row = btn.closest('tr');
        const cells = row ? row.querySelectorAll('td') : null;
        if (!cells || cells.length < 3) {
            alert('행 구조가 예상과 다릅니다. (인증일자=1번째 칸, 시험번호=3번째 칸)');
            return;
        }

        const certDateRaw = (cells[0]?.textContent || '').trim();
        const testNo = (cells[2]?.textContent || '').trim();

        if (!testNo) return alert('시험번호를 찾을 수 없습니다.');
        if (!certDateRaw) return alert('인증일자를 찾을 수 없습니다.');
        
        // 팝업 차단 회피용: 사용자 클릭 시점에 새 탭을 미리 열어둡니다.
        // 전역 변수로 할당하여 onmessage 콜백에서도 접근할 수 있도록 합니다.
        try {
            window.previewWin = window.open('about:blank', '_blank');
        } catch (err) {
            console.warn("팝업이 차단되었을 수 있습니다.", err);
            window.previewWin = null;
        }

        // 서버로 작업을 시작하라는 메시지를 전송합니다.
        socket.send(JSON.stringify({
            '인증일자': certDateRaw,
            '시험번호': testNo
        }));
    });
});
