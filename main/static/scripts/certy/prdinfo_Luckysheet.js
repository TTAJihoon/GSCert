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

  // 다운로드 파일명에 사용할 메타
  let workbookInfo = { name: "Workbook", creator: "" };

  try {
    const url = "/source-excel/";
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("엑셀 파일을 불러오지 못했습니다: " + res.status);
    const blob = await res.blob();
    const file = new File([blob], "server.xlsx", {
      type: blob.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });

    await new Promise((resolve, reject) => {
      window.LuckyExcel.transformExcelToLucky(
        file,
        (exportJson) => {
          try {
            workbookInfo = {
              name: (exportJson.info && exportJson.info.name) || "Workbook",
              creator: (exportJson.info && exportJson.info.creator) || ""
            };
            if (LS.destroy) LS.destroy();
            LS.create({
              container: containerId,
              lang: "en",
              showinfobar: false,
              title: workbookInfo.name,
              userInfo: workbookInfo.creator,
              data: exportJson.sheets
            });
            resolve();
          } catch (e) {
            reject(e);
          }
        },
        (err) => reject(err)
      );
    });
  } catch (e) {
    console.error("원본 엑셀 → Luckysheet 변환 실패:", e);
    alert("원본 파일을 표시하는 중 오류가 발생했습니다.");
    return;
  }

  // 다운로드: 현재 Luckysheet → .xlsx (파일명 = D5 + 접미사)
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

        // D5 값 읽기(0-index 기준 row=4, col=3). API와 파일구조 둘 다 시도.
        const d5Value = readCellD5(LS, 4, 3);
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

  // D5 값 읽기 유틸
  function readCellD5(LS, r, c) {
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

  // 파일명에 쓸 수 없는 문자 정리
  function sanitizeFilename(name) {
    const cleaned = String(name).replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, " ").trim();
    // Windows의 마지막 마침표/공백 금지 등 추가 방어
    return cleaned.replace(/[. ]+$/, "") || "Workbook";
  }
});
