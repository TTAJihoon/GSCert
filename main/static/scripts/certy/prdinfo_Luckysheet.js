// static/scripts/certy/prdinfo_Luckysheet.js
document.addEventListener("DOMContentLoaded", function () {
  const containerId = "luckysheetContainer";
  const containerSel = "#" + containerId;
  const LS = window.luckysheet || window.Luckysheet;

  // ---- 의존성 체크 ----
  if (!LS || typeof LS.create !== "function") {
    console.error("Luckysheet 전역이 없습니다.", { luckysheet: window.luckysheet, Luckysheet: window.Luckysheet });
    return;
  }
  if (!window.LuckyExcel) {
    console.error("LuckyExcel이 로드되지 않았습니다.");
    return;
  }
  if (!window.XLSX) {
    console.error("SheetJS(XLSX)가 로드되지 않았습니다.");
    return;
  }

  let workbookInfo = { name: "Workbook", creator: "" };
  let initialized = false; // Luckysheet 초기화 여부

  // ---- 결과 시트 탭을 열 때 초기화 ----
  bindTabInit();

  // ---- 다운로드 버튼 ----
  const $btnDownload = document.getElementById("btn-download");
  if ($btnDownload) {
    $btnDownload.addEventListener("click", async (ev) => {
      ev.preventDefault();
      try {
        if (!initialized) {
          // 결과 시트 탭을 열지 않은 상태에서 다운로드를 누른 경우: 초기화
          await initLuckysheetWhenVisible();
        }

        const sheets =
          typeof LS.getAllSheets === "function"
            ? LS.getAllSheets()
            : typeof LS.getluckysheetfile === "function"
            ? LS.getluckysheetfile()
            : null;

        if (!sheets || !sheets.length) {
          alert("내보낼 시트가 없습니다.");
          return;
        }

        const d5Value = readCellD5(LS); // D5 = (r=4,c=3)
        const safeName = sanitizeFilename(d5Value || workbookInfo.name || "Workbook");

        const luckyFile = {
          info: { name: safeName, creator: workbookInfo.creator },
          sheets
        };

        const filename = `${safeName}_제품_정보_요청_첨부_v12.0.xlsx`;
        window.LuckyExcel.transformLuckyToExcel(luckyFile, filename);
      } catch (err) {
        console.error("엑셀 내보내기 실패:", err);
        alert("다운로드 중 오류가 발생했습니다.");
      }
    });
  }

  // ====== 함수들 ======

  // 탭 클릭 시 '결과 시트' 활성화되면 초기화
  function bindTabInit() {
    const tabs = document.querySelectorAll(".main-tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", async () => {
        const target = tab.getAttribute("data-tab");
        if (target === "resultSheet") {
          await initLuckysheetWhenVisible();
        }
      });
    });

    // 혹시 사용자가 탭을 클릭하지 않고 바로 결과 영역을 보여주는 경우를 대비해,
    // 결과 컨테이너가 보이는 순간에도 한 번 더 시도
    const resultContent = document.getElementById("resultSheetContent");
    if (resultContent) {
      const obs = new MutationObserver(async () => {
        if (isVisible(resultContent) && !initialized) {
          await initLuckysheetWhenVisible();
        }
      });
      obs.observe(resultContent, { attributes: true, attributeFilter: ["class", "style"] });
    }
  }

  // 결과 시트 컨테이너가 보이는 시점에 초기화
  async function initLuckysheetWhenVisible() {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error("Luckysheet 컨테이너를 찾을 수 없습니다:", containerId);
      return;
    }
    if (!isVisible(container)) {
      // 보이지 않으면 잠시 뒤 재시도
      await wait(60);
      if (!isVisible(container)) return; // 탭이 아직 안 열림
    }
    if (initialized) {
      // 이미 초기화됐다면 리사이즈만
      safeResize();
      return;
    }

    // 서버 XLSX → LuckyJSON 변환 후 생성
    const exportJson = await fetchLuckyFromServer("/source-excel/");
    if (!exportJson) {
      alert("원본 파일을 표시하는 중 오류가 발생했습니다.");
      return;
    }

    workbookInfo = {
      name: (exportJson.info && exportJson.info.name) || "Workbook",
      creator: (exportJson.info && exportJson.info.creator) || ""
    };

    if (LS.destroy) { try { LS.destroy(); } catch (_) {} }

    LS.create({
      container: containerId, // 또는 document.getElementById(containerId)
      lang: "en",
      showinfobar: false,
      title: workbookInfo.name,
      userInfo: workbookInfo.creator,
      data: exportJson.sheets
    });

    initialized = true;

    // 가로 스크롤 가능한 툴바 활성화
    setupToolbarHorizontalScroll(containerSel);

    // 숨김 상태였다가 보인 직후 레이아웃 보정
    requestAnimationFrame(safeResize);
  }

  async function fetchLuckyFromServer(url) {
    try {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) throw new Error("엑셀 파일을 불러오지 못했습니다: " + res.status);

      const blob = await res.blob();
      const file = new File([blob], "server.xlsx", {
        type: blob.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      });

      const exportJson = await new Promise((resolve, reject) => {
        window.LuckyExcel.transformExcelToLucky(
          file,
          (json) => (json && Array.isArray(json.sheets) ? resolve(json) : reject(new Error("변환 결과가 비어있습니다."))),
          (err) => reject(err)
        );
      });

      return exportJson;
    } catch (e) {
      console.error("원본 엑셀 → Luckysheet 변환 실패:", e);
      return null;
    }
  }

  function readCellD5(LS) {
    const r = 4, c = 3;
    try {
      if (typeof LS.getCellValue === "function") {
        const v = LS.getCellValue(r, c);
        return (v == null ? "" : String(v)).trim();
      }
    } catch (_) {}
    try {
      const files = LS.getluckysheetfile ? LS.getluckysheetfile() : null;
      const active = files && files.find((s) => s.status === 1) || files?.[0];
      const cell = active?.data?.[r]?.[c];
      const v = (cell && (cell.m ?? cell.v)) ?? "";
      return String(v).trim();
    } catch (_) {}
    return "";
  }

  function sanitizeFilename(name) {
    const cleaned = String(name).replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, " ").trim();
    return cleaned.replace(/[. ]+$/, "") || "Workbook";
  }

  function safeResize() {
    try { LS.resize && LS.resize(); } catch (_) {}
  }

  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // -------- Luckysheet 툴바 가로 스크롤 세팅 --------
  function setupToolbarHorizontalScroll(containerSelector) {
    const MAX_TRY = 6; // DOM 붙는 타이밍 대비
    let tries = 0;

    const tryBind = () => {
      const el = findToolbar(containerSelector);
      if (!el) {
        if (++tries < MAX_TRY) return setTimeout(tryBind, 80);
        return;
      }
      // 필수 스타일(가로 스크롤/줄바꿈 방지) 강제
      Object.assign(el.style, {
        overflowX: "auto",
        overflowY: "hidden",
        whiteSpace: "nowrap"
      });
      // 자식들이 줄바꿈 없이 가로로만 늘어나도록
      Array.from(el.children).forEach((ch) => { ch.style.flex = "0 0 auto"; });

      // 휠 세로 → 가로 스크롤(넘칠 때만)
      const onWheel = (e) => {
        const canScrollX = el.scrollWidth > el.clientWidth;
        if (canScrollX && Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
          el.scrollLeft += e.deltaY;
          e.preventDefault();
        }
      };
      el.addEventListener("wheel", onWheel, { passive: false });

      // 리사이즈 시에도 스타일 유효화
      window.addEventListener("resize", () => {
        Object.assign(el.style, {
          overflowX: "auto",
          overflowY: "hidden",
          whiteSpace: "nowrap"
        });
      });
    };

    requestAnimationFrame(tryBind);
  }

  function findToolbar(containerSelector) {
    // 컨테이너 내부 우선 검색
    const candidatesInContainer = [
      `${containerSelector} .luckysheet-toolbar`,
      `${containerSelector} #luckysheet-toolbar`,
      `${containerSelector} .luckysheet-wa-toolbar`
    ];
    for (const q of candidatesInContainer) {
      const el = document.querySelector(q);
      if (el) return el;
    }
    // 전역 폴백(버전에 따라 바깥에 렌더되는 경우 대비)
    const globalFallback = [
      ".luckysheet-toolbar",
      "#luckysheet-toolbar",
      ".luckysheet-wa-toolbar"
    ];
    for (const q of globalFallback) {
      const el = document.querySelector(q);
      if (el) return el;
    }
    return null;
  }
});
