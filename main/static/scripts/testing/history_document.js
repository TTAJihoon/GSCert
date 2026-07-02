// 시험 이력 조회 '문서' 버튼: ECM 문서 전체를 서버 report 폴더로 다운로드한 뒤
// ZIP 링크(download_url)로 사용자 브라우저에 내려받게 한다.
// - 서버가 report\<시험번호> 폴더에 파일이 있으면 ECM 접속 없이 즉시 링크를 반환(캐시).
// - 프로토콜은 ECM 버튼과 동일한 /ws/run_job/ 을 쓰되 action:"document" 로 구분.
(function () {
  const WS_PATH = "/ws/run_job/";
  const FALLBACK_INDEX = { certDate: 0, testNo: 2 };

  function setLoading(on) {
    const el = document.getElementById("loadingIndicator");
    if (!el) return;
    if (on) el.classList.remove("hidden");
    else el.classList.add("hidden");
  }
  function setLoadingText(html) {
    const el = document.getElementById("loadingText");
    if (el) el.innerHTML = html;
  }

  function findColumnIndexByHeader(tableEl, headerText) {
    const ths = tableEl.querySelectorAll("thead th");
    for (let i = 0; i < ths.length; i++) {
      if ((ths[i].textContent || "").trim() === headerText) return i;
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
    const testNo = cells[testIdx] ? (cells[testIdx].textContent || "").trim() : "";
    return { certDate: certDate.replace(/[\/]/g, "-").trim(), testNo: testNo.trim() };
  }

  function triggerDownload(url) {
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function runDocumentJob(payload) {
    return new Promise((resolve, reject) => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${location.host}${WS_PATH}`);
      let settled = false;

      setLoadingText("ECM에서 문서를 다운로드하는 중입니다. 잠시만 기다려 주세요...<br>오류 발생 시, 다시 요청해주세요.");
      setLoading(true);

      const done = (fn, val) => {
        if (settled) return;
        settled = true;
        setLoading(false);
        try { ws.close(); } catch (e) {}
        fn(val);
      };

      ws.onopen = () => ws.send(JSON.stringify(payload));

      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch (_) { return done(reject, new Error("서버 응답(JSON) 파싱 실패")); }
        if (msg.status === "hello") return;
        if (msg.status === "wait" || msg.status === "processing") {
          if (msg.message) setLoadingText(msg.message);
          return;
        }
        if (msg.status === "success" && msg.download_url) return done(resolve, msg.download_url);
        if (msg.status === "error") return done(reject, new Error(msg.message || "문서 다운로드 실패"));
      };

      ws.onerror = () => done(reject, new Error("웹소켓 오류"));
      ws.onclose = () => { if (!settled) done(reject, new Error("연결이 종료되었습니다.")); };
    });
  }

  document.addEventListener("click", (evt) => {
    const btn = evt.target.closest?.(".document-download-btn");
    if (!btn) return;
    evt.preventDefault();

    const { certDate, testNo } = extractParamsFromButton(btn);
    if (!certDate || !testNo) {
      alert("인증일자/시험번호를 찾지 못했습니다.");
      return;
    }

    runDocumentJob({ "인증일자": certDate, "시험번호": testNo, "action": "document" })
      .then((downloadUrl) => triggerDownload(downloadUrl))
      .catch((err) => {
        console.error(err);
        alert("문서 다운로드 실패: " + (err?.message || String(err)));
      });
  });
})();
