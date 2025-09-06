// static/scripts/certy/prdinfo_Luckysheet.js
document.addEventListener("DOMContentLoaded", async function () {
  const containerId = "luckysheetContainer";
  const LS = window.luckysheet || window.Luckysheet;

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

  // 서버 원본 XLSX → LuckyJSON → 렌더
  try {
    const res = await fetch("/source-excel/", { credentials: "same-origin" });
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

    workbookInfo = {
      name: (exportJson.info && exportJson.info.name) || "Workbook",
      creator: (exportJson.info && exportJson.info.creator) || ""
    };

    if (LS.destroy) { try { LS.destroy(); } catch (_) {} }

    // 휠(세로 스크롤)을 가로 스크롤로 전환 – 마우스로 좌우도 편하게 움직이게
  function enableToolbarHScroll(container = '#luckysheet') {
    const candidates = [
      `${container} .luckysheet-toolbar`,
      `${container} #luckysheet-toolbar`,
      `${container} .luckysheet-wa-toolbar`
    ];
    const el = candidates.map(q => document.querySelector(q)).find(Boolean);
    if (!el) return;

    el.addEventListener('wheel', (e) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        el.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    }, { passive: false });
  }
    
    LS.create({
      container: containerId, // 또는 document.getElementById(containerId)
      lang: "en",
      showinfobar: false,
      title: workbookInfo.name,
      userInfo: workbookInfo.creator,
      data: exportJson.sheets
    });

    requestAnimationFrame(() => enableToolbarHScroll('#luckysheet'));
  } catch (e) {
    console.error("원본 엑셀 → Luckysheet 변환 실패:", e);
    alert("원본 파일을 표시하는 중 오류가 발생했습니다.");
    return;
  }

  // 다운로드: 현재 Luckysheet → .xlsx (파일명 = D5 값 + 접미사)
  const $btn = document.getElementById("btn-download");
  if ($btn) {
    $btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      try {
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
});
