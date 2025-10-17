(function () {
  const WS_PATH = "/ws/run_job/"; // Channels routing과 일치 (끝 슬래시 포함)

  // 헤더 자동 인식 실패 시 사용할 fallback 인덱스 (0부터)
  const FALLBACK_INDEX = {
    certDate: 0, // 인증일자
    testNo: 2    // 시험번호 (템플릿에서 3번째 열)
  };

  // 중복 새 탭 오픈 방지
  const openedOnce = new Set();

  // ------------------------------------------------------------------
  // WebSocket 연결
  // ------------------------------------------------------------------
  let socket = null;
  let socketReady = false;
  let pendingSends = [];

  function wsUrl() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const u = `${scheme}://${location.host}${WS_PATH}`;
    console.log("[WS] 연결 시도:", u);
    return u;
  }

  function connectWS() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    socket = new WebSocket(wsUrl());

    socket.addEventListener("open", () => {
      console.log("[WS] open");
      socketReady = true;
      if (pendingSends.length) {
        for (const payload of pendingSends.splice(0)) {
          try { socket.send(payload); } catch (e) { console.error("[WS] send 실패:", e); }
        }
      }
    });

    socket.addEventListener("close", () => {
      console.warn("[WS] close");
      socketReady = false;
      setTimeout(connectWS, 1000);
    });

    socket.addEventListener("error", (e) => {
      console.error("[WS] error:", e);
    });

    socket.addEventListener("message", onWSMessage);
  }

  function sendWS(obj) {
    const payload = JSON.stringify(obj);
    console.log("[WS] send:", payload);
    if (socketReady && socket && socket.readyState === WebSocket.OPEN) {
      try { socket.send(payload); } catch (e) { console.error("[WS] send 실패:", e); }
    } else {
      console.warn("[WS] 아직 미연결, 큐잉");
      pendingSends.push(payload);
      connectWS();
    }
  }

  function onWSMessage(e) {
    const raw = typeof e.data === "string" ? e.data : "";
    console.log("[WS] recv:", raw.slice(0, 200));

    // HTML(오류 페이지) 방어
    if (raw.startsWith("<!DOCTYPE") || raw.startsWith("<html")) {
      console.error("[WS] HTML 수신 (404/500 가능). preview:", raw.slice(0, 160));
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

    switch (msg.status) {
      case "wait":
      case "processing":
        console.log("[WS]", msg.status, msg.message || "");
        break;
      case "success":
        if (msg.url) {
          const key = `url:${msg.url}`;
          if (!openedOnce.has(key)) {
            openedOnce.add(key);
            try {
              window.open(msg.url, "_blank");
            } catch (err) {
              console.error("새 탭 열기 실패:", err);
              // fallback: a 태그 클릭
              const a = document.createElement("a");
              a.href = msg.url;
              a.target = "_blank";
              document.body.appendChild(a);
              a.click();
              a.remove();
            }
          }
        } else {
          console.warn("[WS] success인데 url 없음:", msg);
        }
        break;
      case "error":
        alert("작업 실패: " + (msg.message || "알 수 없는 오류"));
        break;
      default:
        console.warn("[WS] unknown status:", msg);
    }
  }

  connectWS();

  // ------------------------------------------------------------------
  // 테이블에서 인증일자/시험번호 추출
  // ------------------------------------------------------------------

  // 헤더에서 목표 열 인덱스를 찾아주는 유틸 (못 찾으면 -1)
  function findColumnIndexByHeader(tableEl, headerText) {
    const ths = tableEl.querySelectorAll("thead th");
    for (let i = 0; i < ths.length; i++) {
      const txt = (ths[i].textContent || "").trim();
      if (txt === headerText) return i;
    }
    return -1;
  }

  function extractParamsFromButton(btn) {
    // 같은 행
    const tr = btn.closest("tr");
    if (!tr) return { certDate: "", testNo: "" };

    // 표 요소
    const table = tr.closest("table");
    if (!table) return { certDate: "", testNo: "" };

    // 헤더 기준으로 인덱스 탐색
    let certIdx = findColumnIndexByHeader(table, "인증일자");
    let testIdx = findColumnIndexByHeader(table, "시험번호");

    // 못 찾으면 fallback
    if (certIdx < 0) certIdx = FALLBACK_INDEX.certDate;
    if (testIdx < 0) testIdx = FALLBACK_INDEX.testNo;

    const cells = Array.from(tr.querySelectorAll("td,th"));
    const certDate = cells[certIdx] ? (cells[certIdx].textContent || "").trim() : "";
    const testNo   = cells[testIdx] ? (cells[testIdx].textContent || "").trim() : "";

    // 서버는 '인증일자'에 yyyy.mm.dd 또는 yyyy-mm-dd 허용(tasks.py 패치 가정)
    const normCert = certDate.replace(/[\/]/g, "-").trim();
    const normTest = testNo.trim();

    return { certDate: normCert, testNo: normTest };
  }

  // ------------------------------------------------------------------
  // 클릭 이벤트 (이벤트 위임)
  // ------------------------------------------------------------------
  document.addEventListener("click", function (evt) {
    const btn = evt.target.closest && evt.target.closest(".download-btn");
    if (!btn) return;

    evt.preventDefault();
    console.log("click .download-btn");

    const { certDate, testNo } = extractParamsFromButton(btn);
    console.log("extracted:", { certDate, testNo });

    if (!certDate || !testNo) {
      alert("인증일자/시험번호를 찾지 못했습니다.\n테이블 헤더/열 구성을 확인해주세요.");
      return;
    }

    // 서버가 기대하는 키 이름에 맞춰 전송(한국어 키)
    sendWS({ "인증일자": certDate, "시험번호": testNo });
  });
})();
