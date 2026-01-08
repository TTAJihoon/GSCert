// 요청별 WebSocket 버전 (메시지 수신 때마다 loadingIndicator 문구 실시간 갱신)
// - 버튼 클릭마다 WebSocket을 새로 열고(open→send→recv→close)
// - wait/processing 동안 로딩 표시 + 큐 정보 표시(가능한 경우)
// - success/error 시 로딩 해제 + 연결 close
(function () {
  const WS_PATH = "/ws/run_job/"; // Channels routing과 일치(끝 슬래시 포함)

  const FALLBACK_INDEX = {
    certDate: 0, // 인증일자
    testNo: 2    // 시험번호
  };

  // 로딩 표시/해제
  function setLoading(on) {
    const el = document.getElementById("loadingIndicator");
    if (!el) return;
    if (on) el.classList.remove("hidden");
    else el.classList.add("hidden");
  }

  // 로딩 문구 갱신(HTML의 <span id="loadingText">를 사용)
  function setLoadingText(html) {
    const el = document.getElementById("loadingText");
    if (!el) return;
    el.innerHTML = html;
  }

  // 기본 문구
  function setDefaultLoadingText() {
    setLoadingText(
      `순차적으로 시험성적서 다운로드가 가능한 ECM 페이지가 열립니다. 잠시만 기다려 주세요...<br>` +
      `오류 발생 시, 다시 요청해주세요.`
    );
  }

  // 중복 새 탭 오픈 방지
  const openedOnce = new Set();

  function findColumnIndexByHeader(tableEl, headerText) {
    const ths = tableEl.querySelectorAll("thead th");
    for (let i = 0; i < ths.length; i++) {
      const txt = (ths[i].textContent || "").trim();
      if (txt === headerText) return i;
    }
    return -1;
  }

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

    // 서버는 yyyy.mm.dd / yyyy-mm-dd 둘 다 허용(tasks.py 기준)
    const normCert = certDate.replace(/[\/]/g, "-").trim();
    const normTest = testNo.trim();

    return { certDate: normCert, testNo: normTest };
  }

  function buildQueueText(msg) {
    // 서버가 아래 필드를 보내면 최대한 활용
    // - queue_ahead: 내 앞 대기 수
    // - queue_position: 내 순번(대략)
    // - queue_total: (있으면) 대기열 총 크기(대략)
    const ahead = Number.isFinite(msg.queue_ahead) ? msg.queue_ahead : null;
    const pos = Number.isFinite(msg.queue_position) ? msg.queue_position : (ahead != null ? ahead + 1 : null);
    const total = Number.isFinite(msg.queue_total) ? msg.queue_total : null;

    if (pos != null && total != null) return `대기중 (내 순번 ${pos}/${total})`;
    if (pos != null && ahead != null) return `대기중 (내 순번 ${pos} · 내 앞 ${ahead}명)`;
    if (ahead != null) return `대기중 (내 앞 ${ahead}명)`;
    return `대기중`;
  }

  function runJobOnce(payload) {
    return new Promise((resolve, reject) => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const url = `${scheme}://${location.host}${WS_PATH}`;
      console.log("[WS] connect:", url);

      // 로딩 시작
      setDefaultLoadingText();
      setLoading(true);

      const ws = new WebSocket(url);
      let settled = false;

      const done = (fn, val) => {
        if (settled) return;
        settled = true;
        setLoading(false);
        try { ws.close(); } catch (e) {}
        fn(val);
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
        console.log("[WS] recv:", raw.slice(0, 300));

        // HTML 오류 페이지 방지
        if (raw.startsWith("<!DOCTYPE") || raw.startsWith("<html")) {
          return done(reject, new Error("서버가 HTML(오류 페이지)을 보냈습니다."));
        }

        let msg;
        try {
          msg = JSON.parse(raw);
        } catch (err) {
          return done(reject, new Error("서버 응답(JSON) 파싱 실패"));
        }

        // hello는 UI에 굳이 반영하지 않음
        if (msg.status === "hello") return;

        if (msg.status === "wait") {
          setLoading(true);
          const qtxt = buildQueueText(msg);
          setLoadingText(
            `${qtxt}<br>` +
            `순차적으로 ECM 자동화 작업을 처리 중입니다. 잠시만 기다려 주세요...`
          );
          return;
        }

        if (msg.status === "processing") {
          setLoading(true);
          setLoadingText(
            `실행중 (ECM 자동화 진행)<br>` +
            `브라우저가 폴더 이동/문서 선택/URL 복사를 수행 중입니다...`
          );
          return;
        }

        if (msg.status === "success" && msg.url) {
          return done(resolve, msg.url);
        }

        if (msg.status === "error") {
          return done(reject, new Error(msg.message || "작업 실패"));
        }

        // 그 외 메시지는 무시하고 계속 대기
      };

      ws.onerror = () => done(reject, new Error("웹소켓 오류"));
      ws.onclose = () => { if (!settled) done(reject, new Error("연결이 종료되었습니다.")); };
    });
  }

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
        if (openedOnce.has(key)) return;
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
      })
      .catch((err) => {
        console.error(err);
        alert("작업 실패: " + (err?.message || String(err)));
      });
  });
})();
