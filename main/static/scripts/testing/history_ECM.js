(function () {
  const WS_PATH = "/ws/run_job/"; // Channels routing과 일치해야 함 (끝 슬래시 포함)
  const TABLE_FALLBACK = {
    enabled: true,         // 버튼 data-*가 없을 때만 사용
    certDateCellIndex: 0,  // 인증일자가 들어있는 셀의 인덱스 (0부터)
    testNoCellIndex: 1     // 시험번호가 들어있는 셀의 인덱스 (0부터)
  };

  // 중복 새 탭 오픈 방지 (서버가 같은 url을 두 번 보낼 때)
  const openedOnce = new Set();

  // 간단한 로딩 토스트 (원하면 교체/제거 가능)
  let loadingCount = 0;
  function showLoading(msg) {
    loadingCount++;
    if (msg) console.log("[WS] " + msg);
  }
  function hideLoading() {
    loadingCount = Math.max(0, loadingCount - 1);
  }

  // ---- WebSocket 연결/재연결 ---------------------------------------------
  let socket = null;
  let socketReady = false;
  let pendingSends = []; // 연결 전 큐잉

  function wsUrl() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${location.host}${WS_PATH}`;
    // 프록시/서브패스가 있으면 필요한 만큼 앞에 prefix를 추가하세요.
  }

  function connectWS() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    socket = new WebSocket(wsUrl());

    socket.addEventListener("open", () => {
      socketReady = true;
      // 보류 중인 전송들을 flush
      if (pendingSends.length) {
        for (const payload of pendingSends) {
          try { socket.send(payload); } catch (e) { console.error("WS send failed:", e); }
        }
        pendingSends = [];
      }
    });

    socket.addEventListener("close", () => {
      socketReady = false;
      // 재연결 (간단 backoff)
      setTimeout(connectWS, 1000);
    });

    socket.addEventListener("error", (e) => {
      console.error("[WS] error:", e);
    });

    socket.addEventListener("message", onWSMessage);
  }

  function sendWS(obj) {
    const payload = JSON.stringify(obj);
    if (socketReady && socket && socket.readyState === WebSocket.OPEN) {
      try { socket.send(payload); } catch (e) { console.error("WS send failed:", e); }
    } else {
      pendingSends.push(payload);
      connectWS();
    }
  }

  function onWSMessage(e) {
    const raw = typeof e.data === "string" ? e.data : "";
    // HTML(오류 페이지) 방어
    if (raw.startsWith("<!DOCTYPE") || raw.startsWith("<html")) {
      console.error("[WS] HTML 수신 (아마 404/500). preview:", raw.slice(0, 160));
      alert("서버에서 JSON 대신 HTML을 보냈습니다. (오류 가능) 관리자 로그를 확인해주세요.");
      return;
    }

    let msg;
    try {
      msg = JSON.parse(raw);
    } catch (err) {
      console.error("[WS] JSON 파싱 실패:", err, "payload:", raw.slice(0, 160));
      alert("서버 응답(JSON) 파싱 실패. 로그를 확인해주세요.");
      return;
    }

    // 상태 처리
    switch (msg.status) {
      case "wait":
      case "processing":
        showLoading(msg.message || "처리 중...");
        break;

      case "success":
        hideLoading();
        if (msg.url) {
          const key = `url:${msg.url}`;
          if (!openedOnce.has(key)) {
            openedOnce.add(key);
            try {
              window.open(msg.url, "_blank");
            } catch (err) {
              console.error("새 탭 열기 실패:", err);
              // fallback a 태그
              const a = document.createElement("a");
              a.href = msg.url;
              a.target = "_blank";
              document.body.appendChild(a);
              a.click();
              a.remove();
            }
          }
        } else {
          console.warn("[WS] success인데 url이 없습니다:", msg);
        }
        break;

      case "error":
        hideLoading();
        alert("작업 실패: " + (msg.message || "알 수 없는 오류"));
        break;

      default:
        console.warn("[WS] 알 수 없는 status:", msg.status, msg);
    }
  }

  // 첫 진입 시 연결 시도
  connectWS();

  // ---- 버튼 클릭 -> 데이터 추출 -> WS 전송 -------------------------------

  // 버튼에서 인증일자/시험번호를 추출
  function extractParamsFromButton(btn) {
    // 1) data-* 우선
    let certDate = btn.dataset.certDate || btn.getAttribute("data-cert-date");
    let testNo   = btn.dataset.testNo   || btn.getAttribute("data-test-no");

    // 2) fallback: 같은 행의 셀에서 텍스트 추출
    if ((!certDate || !testNo) && TABLE_FALLBACK.enabled) {
      const tr = btn.closest("tr");
      if (tr) {
        const cells = Array.from(tr.querySelectorAll("td,th"));
        if (!certDate && cells[TABLE_FALLBACK.certDateCellIndex]) {
          certDate = cells[TABLE_FALLBACK.certDateCellIndex].textContent.trim();
        }
        if (!testNo && cells[TABLE_FALLBACK.testNoCellIndex]) {
          testNo = cells[TABLE_FALLBACK.testNoCellIndex].textContent.trim();
        }
      }
    }

    // 3) 마지막 정리
    // 서버는 '인증일자'에 yyyy.mm.dd 또는 yyyy-mm-dd를 기대 (tasks에서 둘 다 허용하도록 패치함)
    if (certDate) certDate = certDate.replace(/[\/]/g, "-").trim();
    if (testNo)   testNo   = testNo.trim();

    return { certDate, testNo };
  }

  // 모든 download-btn에 클릭 핸들러 바인딩 (동적 추가 대응: 이벤트 위임 사용)
  document.addEventListener("click", function (evt) {
    const btn = evt.target.closest && evt.target.closest(".download-btn");
    if (!btn) return;

    evt.preventDefault();

    const { certDate, testNo } = extractParamsFromButton(btn);

    if (!certDate || !testNo) {
      alert("인증일자 또는 시험번호를 찾지 못했습니다.\n버튼에 data-cert-date/data-test-no를 넣거나, TABLE_FALLBACK 인덱스를 맞춰주세요.");
      return;
    }

    // 서버가 기대하는 키 이름에 맞춰 전송(한국어 키)
    const payload = {
      "인증일자": certDate,
      "시험번호": testNo
    };

    sendWS(payload);
  });
})();
