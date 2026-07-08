// similar_ECM.js
// - download-btn 클릭 → 문서 다운로드 방식(action:"document", scope 미지정=report):
//   분당 ECM 인증심의위원회 트리에서 해당 시험번호의 '시험성적서(Word)'만 받아
//   서버가 ZIP으로 묶어 반환(download_url) → 브라우저에서 ZIP 다운로드.
//   (history '문서 다운로드' 버튼과 동일 동작. 전체 문서가 필요하면 scope:"all")
// - similar 페이지는 "테이블"이 아니라 카드 DOM에서 인증일자/시험번호를 뽑는다.

(function () {
  const WS_PATH = "/ws/run_job/";

  // ===== 로딩 UI (similar.html 기준) =====
  function setLoading(on, title, desc) {
    // similar 페이지: #loadingContainer 사용
    const box = document.getElementById("loadingContainer");
    if (box) {
      if (on) box.classList.remove("hidden");
      else box.classList.add("hidden");

      const t = box.querySelector(".loading-text");
      const d = box.querySelector(".loading-description");
      if (t && title) t.textContent = title;
      if (d && desc) d.textContent = desc;
      return;
    }

    // (혹시 다른 페이지에서 재사용 시) history 페이지: #loadingIndicator/#loadingText
    const el = document.getElementById("loadingIndicator");
    if (el) {
      if (on) el.classList.remove("hidden");
      else el.classList.add("hidden");
    }
    const txt = document.getElementById("loadingText");
    if (txt && (title || desc)) {
      txt.innerHTML = `${title || ""}<br>${desc || ""}`;
    }
  }

  function buildQueueText(msg) {
    const ahead = Number.isFinite(msg.queue_ahead) ? msg.queue_ahead : null;
    const pos = Number.isFinite(msg.queue_position) ? msg.queue_position : (ahead != null ? ahead + 1 : null);
    const total = Number.isFinite(msg.queue_total) ? msg.queue_total : null;

    if (pos != null && total != null) return `대기중 (내 순번 ${pos}/${total})`;
    if (pos != null && ahead != null) return `대기중 (내 순번 ${pos} · 내 앞 ${ahead}명)`;
    if (ahead != null) return `대기중 (내 앞 ${ahead}명)`;
    return `대기중`;
  }

  // ===== DOM에서 값 추출 (카드 구조) =====
  function getTagValue(container, labelText) {
    // <p>시험번호</p><span class="product-tag">GS-A-...</span> 구조
    const ps = container.querySelectorAll(".product-tags p");
    for (const p of ps) {
      const key = (p.textContent || "").trim();
      if (key === labelText) {
        const next = p.nextElementSibling;
        if (next && next.tagName === "SPAN") {
          return (next.textContent || "").trim();
        }
      }
    }
    return "";
  }

  function extractParamsFromButton(btn) {
    const card = btn.closest(".similar-product") || btn.closest(".content-card") || document;
    const certDate = getTagValue(card, "인증일자");
    const testNo = getTagValue(card, "시험번호");

    // 서버는 yyyy.mm.dd / yyyy-mm-dd 둘 다 허용
    const normCert = (certDate || "").replace(/[\/]/g, "-").trim();
    const normTest = (testNo || "").trim();

    return { certDate: normCert, testNo: normTest };
  }

  // ===== WS 실행 =====
  function runJobOnce(payload, onProgress) {
    return new Promise((resolve, reject) => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${scheme}://${location.host}${WS_PATH}`;
      console.log("[WS] connect:", wsUrl);

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
            title: buildQueueText(msg),
            desc: "순차적으로 ECM 자동화 작업을 처리 중입니다. 잠시만 기다려 주세요..."
          });
          return;
        }

        if (msg.status === "processing") {
          onProgress?.({
            title: "실행중",
            desc: msg.message || "ECM 자동화 진행 중입니다..."
          });
          return;
        }

        if (msg.status === "success" && msg.download_url) {
          return done(resolve, msg.download_url);
        }

        if (msg.status === "error") {
          return done(reject, new Error(msg.message || "작업 실패"));
        }
      };

      ws.onerror = () => done(reject, new Error("웹소켓 오류"));
      ws.onclose = () => { if (!settled) done(reject, new Error("연결이 종료되었습니다.")); };
    });
  }

  // ===== 클릭 핸들러 =====
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

    setLoading(true, "문서 다운로드", "ECM에서 문서를 다운로드하는 중입니다...");

    // 문서 다운로드: scope 미지정 → 시험성적서(Word)만 받아 ZIP 링크 반환
    const payload = { "인증일자": certDate, "시험번호": testNo, "action": "document" };

    runJobOnce(payload, ({ title, desc }) => setLoading(true, title, desc))
      .then((downloadUrl) => {
        setLoading(false);
        // ZIP 첨부 다운로드 (새 탭 X)
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        a.remove();
      })
      .catch((err) => {
        setLoading(false);
        console.error(err);
        alert("문서 다운로드 실패: " + (err?.message || String(err)));
      });
  });
})();
