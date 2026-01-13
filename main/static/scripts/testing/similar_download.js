// similar_ECM.js
// - .download-btn 클릭 시, 같은 카드(.similar-product)에서
//   '인증일자' 다음 <span>, '시험번호' 다음 <span> 값을 추출
// - WebSocket(/ws/run_job/)으로 {인증일자, 시험번호} 전송
// - success.url을 새 탭으로 오픈 (팝업 차단 최소화를 위해 "클릭 순간 빈탭" 방식 사용)
// - 로딩 UI: #loadingContainer(있으면) 사용, 없으면 #loadingIndicator(있으면) 사용
(function () {
  const WS_PATH = "/ws/run_job/"; // Channels routing과 일치(끝 슬래시 포함)

  // =========================
  // Loading UI helpers
  // =========================
  function setLoading(on) {
    const loadingContainer = document.getElementById("loadingContainer");
    if (loadingContainer) {
      if (on) loadingContainer.classList.remove("hidden");
      else loadingContainer.classList.add("hidden");
      return;
    }
    const loadingIndicator = document.getElementById("loadingIndicator");
    if (loadingIndicator) {
      if (on) loadingIndicator.classList.remove("hidden");
      else loadingIndicator.classList.add("hidden");
    }
  }

  function setLoadingText(text) {
    // similar.html엔 .loading-text가 있음
    const loadingContainer = document.getElementById("loadingContainer");
    if (loadingContainer) {
      const el = loadingContainer.querySelector(".loading-text");
      if (el) el.textContent = text;
      const desc = loadingContainer.querySelector(".loading-description");
      if (desc) desc.textContent = "ECM에서 문서 URL을 가져오는 중입니다.";
      return;
    }
    // history 페이지처럼 #loadingText가 있으면 활용
    const loadingText = document.getElementById("loadingText");
    if (loadingText) loadingText.innerHTML = String(text).replace(/\n/g, "<br>");
  }

  function setDefaultLoadingText() {
    setLoadingText("ECM 자동화 처리 중... 잠시만 기다려 주세요.");
  }

  // =========================
  // Extract: certDate / testNo from card(div)
  // 규칙:
  //  - '인증일자' 다음 <span> = certDate
  //  - '시험번호' 다음 <span> = testNo
  // =========================
  function extractParamsFromButton(btn) {
    const card = btn.closest(".similar-product") || btn.closest("div");
    if (!card) return { certDate: "", testNo: "" };

    const scope = card.querySelector(".product-tags") || card;

    const getNextSpanText = (label) => {
      const ps = Array.from(scope.querySelectorAll("p"));
      const p = ps.find(el => (el.textContent || "").trim() === label);
      if (!p) return "";

      // "다음 <span>"을 엄격히 따름 (사이에 다른 요소가 있으면 span 나올 때까지 스킵)
      let next = p.nextElementSibling;
      while (next && next.tagName !== "SPAN") next = next.nextElementSibling;
      return next ? (next.textContent || "").trim() : "";
    };

    const certDateRaw = getNextSpanText("인증일자");
    const testNoRaw = getNextSpanText("시험번호");

    // 서버는 yyyy.mm.dd / yyyy-mm-dd 둘 다 허용 (너 기존 tasks.py 기준)
    const certDate = (certDateRaw || "").replace(/[\/]/g, "-").trim();
    const testNo = (testNoRaw || "").trim();

    return { certDate, testNo };
  }

  // =========================
  // Queue text
  // =========================
  function buildQueueText(msg) {
    const ahead = Number.isFinite(msg.queue_ahead) ? msg.queue_ahead : null;
    const pos = Number.isFinite(msg.queue_position) ? msg.queue_position : (ahead != null ? ahead + 1 : null);
    const total = Number.isFinite(msg.queue_total) ? msg.queue_total : null;

    if (pos != null && total != null) return `대기중 (내 순번 ${pos}/${total})`;
    if (pos != null && ahead != null) return `대기중 (내 순번 ${pos} · 내 앞 ${ahead}명)`;
    if (ahead != null) return `대기중 (내 앞 ${ahead}명)`;
    return `대기중`;
  }

  // =========================
  // WebSocket runner
  // =========================
  function runJobOnce(payload, onProgress) {
    return new Promise((resolve, reject) => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${scheme}://${location.host}${WS_PATH}`;

      const ws = new WebSocket(wsUrl);
      let settled = false;

      const done = (fn, val) => {
        if (settled) return;
        settled = true;
        try { ws.close(); } catch (e) {}
        fn(val);
      };

      ws.onopen = () => {
        try {
          ws.send(JSON.stringify(payload));
        } catch (e) {
          done(reject, e);
        }
      };

      ws.onmessage = (e) => {
        const raw = String(e.data || "");

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

        if (msg.status === "hello") return;

        if (msg.status === "wait") {
          onProgress?.({
            phase: "wait",
            text: `${buildQueueText(msg)} · ECM 작업 큐에 등록 중...`,
            msg
          });
          return;
        }

        if (msg.status === "processing") {
          onProgress?.({
            phase: "processing",
            text: `실행중 · ECM 자동화 진행 중(폴더 이동/문서 선택/URL 복사)...`,
            msg
          });
          return;
        }

        if (msg.status === "success" && msg.url) {
          return done(resolve, msg);
        }

        if (msg.status === "error") {
          // 서버가 step/error_kind/screenshot도 주면 같이 활용 가능
          const detail = [];
          if (msg.step) detail.push(`S${msg.step}`);
          if (msg.error_kind) detail.push(msg.error_kind);
          if (msg.screenshot) detail.push(msg.screenshot);
          const suffix = detail.length ? ` (${detail.join(" | ")})` : "";
          return done(reject, new Error((msg.message || "작업 실패") + suffix));
        }
      };

      ws.onerror = () => done(reject, new Error("웹소켓 오류"));
      ws.onclose = () => { if (!settled) done(reject, new Error("연결이 종료되었습니다.")); };
    });
  }

  // =========================
  // Popup-safe open: "클릭 순간 빈 탭" -> 성공 시 그 탭을 URL로 이동
  // 그리고 원래 탭으로 포커스 복귀 시도(window.focus())
  // =========================
  function openBlankTabFromClick() {
    try {
      // noopener/noreferrer: 보안 + 일부 브라우저에서 팝업 차단 완화에 도움
      const w = window.open("about:blank", "_blank", "noopener,noreferrer");
      return w || null;
    } catch (e) {
      return null;
    }
  }

  function navigateOrOpen(url, blankTab) {
    if (blankTab && !blankTab.closed) {
      try {
        blankTab.location.href = url;
        // 원래 탭으로 돌아오려 "시도" (브라우저가 막을 수 있음)
        try { window.focus(); } catch (e) {}
        return;
      } catch (e) {
        // 실패하면 fallback으로 새 탭 오픈
      }
    }

    // fallback
    try {
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  }

  // =========================
  // Click handler (event delegation)
  // =========================
  document.addEventListener("click", (evt) => {
    const btn = evt.target.closest?.(".download-btn");
    if (!btn) return;

    evt.preventDefault();

    // ✅ 같은 카드에서 값 뽑기
    const { certDate, testNo } = extractParamsFromButton(btn);
    console.log("[similar_ECM] extracted:", { certDate, testNo });

    if (!certDate || !testNo) {
      alert("인증일자/시험번호를 찾지 못했습니다.");
      return;
    }

    // ✅ 클릭 순간 빈 탭(팝업 차단 회피)
    const blankTab = openBlankTabFromClick();

    // ✅ 로딩 시작
    setDefaultLoadingText();
    setLoading(true);

    // 버튼 연타 방지(선택)
    btn.disabled = true;
    btn.classList.add("opacity-50");
    btn.style.cursor = "not-allowed";

    const payload = { "인증일자": certDate, "시험번호": testNo };

    runJobOnce(payload, (p) => {
      setLoading(true);
      setLoadingText(p.text);
    })
      .then((msg) => {
        setLoading(false);
        const url = msg.url;

        // ✅ 성공: 빈탭 이동 or 새탭
        navigateOrOpen(url, blankTab);
      })
      .catch((err) => {
        setLoading(false);

        // 빈탭 열렸으면 닫기
        try { if (blankTab && !blankTab.closed) blankTab.close(); } catch (e) {}

        console.error(err);
        alert("작업 실패: " + (err?.message || String(err)));
      })
      .finally(() => {
        btn.disabled = false;
        btn.classList.remove("opacity-50");
        btn.style.cursor = "";
      });
  });
})();
