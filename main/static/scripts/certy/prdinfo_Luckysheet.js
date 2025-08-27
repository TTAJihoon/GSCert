document.addEventListener("DOMContentLoaded", async function () {
  const containerId = "luckysheetContainer";
  const LS = window.luckysheet || window.Luckysheet; // 빌드마다 전역명이 다를 수 있어 양쪽 지원
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

  try {
    const url = "/source-excel/";
    
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("엑셀 파일을 불러오지 못했습니다: " + res.status);
    const blob = await res.blob();
    const file = new File([blob], "server.xlsx", { type: blob.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    
    await new Promise((resolve, reject) => {
      window.LuckyExcel.transformExcelToLucky(file, (exportJson) => {
        try {
          if (LS.destroy) LS.destroy();
          LS.create({
            container: containerId,
            lang: "en",
            showinfobar: false,
            title: (exportJson.info && exportJson.info.name) || "Workbook",
            userInfo: (exportJson.info && exportJson.info.creator) || "",
            data: exportJson.sheets
          });
          resolve();
        } catch (e) {
          reject(e);
        }
      }, (err) => reject(err));
    });
  } catch (e) {
    console.error("원본 엑셀 → Luckysheet 변환 실패:", e);
    alert("원본 파일을 표시하는 중 오류가 발생했습니다.");
  }
