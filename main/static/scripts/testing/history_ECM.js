// 요청별 WebSocket 버전
// - 버튼 클릭마다 WebSocket을 새로 열고(open→send→recv→close)
// - 'wait'/'processing' 수신 시 로딩 표시, 'success'/'error' 시 로딩 해제
// - 성공 시 그때 새 탭으로 URL 오픈
(function () {
  const WS_PATH = "/ws/run_job/"; // Channels routing과 일치(끝 슬래시 포함)

  // 헤더 자동 인식 실패 시 사용할 fallback 인덱스 (0부터)
  const FALLBACK_INDEX = {
    certDate: 0, // 인증일자
    testNo: 2    // 시험번호 (템플릿 상 3번째 열)
  };

  // 로딩 표시/해제
  function setLoading(on) {
    const el = document.getElementById("loadingIndicator");
    if (!el) return;
    if (on) el.classList.remove("hidden");
    else el.classList.add("hidden");
  }

  // 중복 새 탭 오픈 방지
  const openedOnce = new Set();

  // --- 유틸: 테이블 헤더에서 목표 열 인덱스 찾기 ---
  function findColumnIndexByHeader(tableEl, headerText) {
    const ths = tableEl.querySelectorAll("thead th");
    for (let i = 0; i < ths.length; i++) {
      const txt = (ths[i].textContent || "").trim();
      if (txt === headerText) return i;
    }
    return -1;
  }

  // --- 테이블 행에서 인증일자/시험번호 추출 ---
  function extractParamsFromButton(btn) {
    const tr = btn.closest("tr");
    if (!tr) return { certDate: "", testNo: "" };

    const table = tr.closest("table");
    if (!table) return { certDate: "", testNo: "" };

    let certIdx = findColumnIndexByHeader(table, "인증일자");
    let testIdx = findColumnIndexByHeader(table, "시험번호");

    if (certIdx < 0) certIdx = FALLBACK_INDEX.certDate;
    if (testIdx < 0) testIdx = FALLBACK_INDEX.testNo;

    const cells = Array.from(tr.querySelectorAll("td,th"));
    const certDate = cells[certIdx] ? (cells[certIdx].textContent || "").trim() : "";
    const testNo   = cells[testIdx] ? (cells[testIdx].textContent || "").trim() : "";

    // 서버는 yyyy.mm.dd / yyyy-mm-dd 둘 다 허용(tasks.py 패치 기준)
    const normCert = certDate.replace(/[\/]/g, "-").trim();
    const normTest = testNo.trim();

    return { certDate: normCert, testNo: normTest };
  }

  // --- 요청별 WebSocket 실행기 ---
  function runJobOnce(payload) {
    return new Promise((resolve, reject) => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const url = `${scheme}://${location.host}${WS_PATH}`;
      console.log("[WS] connect:", url);

      // 로딩 시작
      setLoading(true);

      const ws = new WebSocket(url);
      let settled = false;

      const done = (fn, val) => {
        if (!settled) {
          settled = true;
          setLoading(false);            // 로딩 해제 보장
          try { ws.close(); } catch (e) {}
          fn(val);
        }
      };

      ws.onopen = () => {
        try {
          const data = JSON.stringify(payload);
          console.log("[WS] send:", data);
          ws.send(data);
        } catch (e) {
          done(reject, e);
        }
      };

      ws.onmessage = (e) => {
        const raw = String(e.data || "");
        console.log("[WS] recv:", raw.slice(0, 200));

        if (raw.startsWith("<!DOCTYPE") || raw.startsWith("<html")) {
          return done(reject, new Error("서버가 HTML(오류 페이지)을 보냈습니다."));
        }
        let msg;
        try {
          msg = JSON.parse(raw);
        } catch (err) {
          return done(reject, new Error("서버 응답(JSON) 파싱 실패"));
        }

        if (msg.status === "wait" || msg.status === "processing") {
          // 로딩 유지
          setLoading(true);
          return;
        }
        if (msg.status === "success" && msg.url) {
          return done(resolve, msg.url);
        }
        if (msg.status === "error") {
          return done(reject, new Error(msg.message || "작업 실패"));
        }
        // 그 외는 무시하고 다음 메시지 대기
      };

      ws.onerror = () => done(reject, new Error("웹소켓 오류"));
      ws.onclose = () => { if (!settled) done(reject, new Error("연결이 종료되었습니다.")); };
    });
  }

  // --- 클릭 핸들러 (이벤트 위임) ---
  document.addEventListener("click", (evt) => {
    const btn = evt.target.closest?.(".download-btn");
    if (!btn) return;

    evt.preventDefault();
    const { certDate, testNo } = extractParamsFromButton(btn);
    console.log("extracted:", { certDate, testNo });

    if (!certDate || !testNo) {
      alert("인증일자/시험번호를 찾지 못했습니다.");
      return;
    }

    const payload = { "인증일자": certDate, "시험번호": testNo };

    runJobOnce(payload)
      .then((url) => {
        const key = `url:${url}`;
        if (!openedOnce.has(key)) {
          openedOnce.add(key);
          try {
            window.open(url, "_blank");
          } catch (err) {
            console.error("새 탭 열기 실패:", err);
            const a = document.createElement("a");
            a.href = url;
            a.target = "_blank";
            document.body.appendChild(a);
            a.click();
            a.remove();
          }
        }
      })
      .catch((err) => {
        console.error(err);
        alert("작업 실패: " + err.message);
      });
  });
})();
