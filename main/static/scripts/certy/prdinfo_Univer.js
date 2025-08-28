document.addEventListener("DOMContentLoaded", async () => {
  // ===== Univer 플러그인 네임스페이스 추출 (UMD) =====
  const { Univer, LocaleType, mergeLocales, UniverInstanceType } = window.UniverCore;
  const { FUniver } = window.UniverCoreFacade;

  const { UniverRenderEnginePlugin } = window.UniverEngineRender;
  const { UniverFormulaEnginePlugin } = window.UniverEngineFormula;

  const { UniverUIPlugin } = window.UniverUi;
  const { UniverDocsPlugin } = window.UniverDocs;
  const { UniverDocsUIPlugin } = window.UniverDocsUi;

  const { UniverSheetsPlugin } = window.UniverSheets;
  const { UniverSheetsUIPlugin } = window.UniverSheetsUi;

  const { UniverSheetsFormulaPlugin } = window.UniverSheetsFormula;
  const { UniverSheetsFormulaUIPlugin } = window.UniverSheetsFormulaUi;

  const { UniverSheetsNumfmtPlugin } = window.UniverSheetsNumfmt;
  const { UniverSheetsNumfmtUIPlugin } = window.UniverSheetsNumfmtUi;

  // 데이터 유효성 (드롭다운/체크박스 등)
  const { UniverDataValidationPlugin } = window.UniverDataValidation;
  const { UniverSheetsDataValidationPlugin } = window.UniverSheetsDataValidation;
  const { UniverSheetsDataValidationUIPlugin } = window.UniverSheetsDataValidationUi;

  // ===== Univer 인스턴스 생성 =====
  const univer = new Univer({
    locale: LocaleType.EN_US,
    locales: {
      [LocaleType.EN_US]: mergeLocales(
        window.UniverDesignEnUS,
        window.UniverUiEnUS,
        window.UniverDocsUiEnUS,
        window.UniverSheetsEnUS,
        window.UniverSheetsUiEnUS,
        window.UniverSheetsFormulaUiEnUS,
        window.UniverSheetsNumfmtUiEnUS,
        window.UniverSheetsDataValidationUiEnUS
      ),
    },
  });

  // 필수 플러그인 등록
  univer.registerPlugin(UniverRenderEnginePlugin);
  univer.registerPlugin(UniverFormulaEnginePlugin);
  univer.registerPlugin(UniverUIPlugin, { container: "luckysheetContainer" });
  univer.registerPlugin(UniverDocsPlugin);
  univer.registerPlugin(UniverDocsUIPlugin);
  univer.registerPlugin(UniverSheetsPlugin);
  univer.registerPlugin(UniverSheetsUIPlugin);
  univer.registerPlugin(UniverSheetsFormulaPlugin);
  univer.registerPlugin(UniverSheetsFormulaUIPlugin);
  univer.registerPlugin(UniverSheetsNumfmtPlugin);
  univer.registerPlugin(UniverSheetsNumfmtUIPlugin);

  // 데이터 유효성 플러그인 등록 (서버 불필요, 드롭다운/체크박스 등)
  univer.registerPlugin(UniverDataValidationPlugin);
  univer.registerPlugin(UniverSheetsDataValidationPlugin);
  univer.registerPlugin(UniverSheetsDataValidationUIPlugin, { showEditOnDropdown: true });

  // 빈 시트(단위) 하나 생성 후 API 핸들러 획득
  univer.createUnit(UniverInstanceType.UNIVER_SHEET, {});
  const univerAPI = FUniver.newAPI(univer);

  // ===== 서버에서 원본 엑셀 가져오기 =====
  const url = "/source-excel/";
  let blob;
  try {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("엑셀 파일을 불러오지 못했습니다: " + res.status);
    blob = await res.blob();
  } catch (e) {
    console.error("엑셀 다운로드 실패:", e);
    alert("원본 엑셀을 불러오지 못했습니다.");
    return;
  }

  const file = new File([blob], "server.xlsx", {
    type: blob.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

  // ===== ① (권장) Univer Import API 경로 — 서버가 있을 때 =====
  // univerAPI.importXLSXToSnapshotAsync(file) 이 존재하면 사용
  // (문서: .xlsx -> Snapshot -> createWorkbook) 
  // https://docs.univer.ai/guides/sheets/features/import-export
  if (typeof univerAPI.importXLSXToSnapshotAsync === "function") {
    try {
      const snapshot = await univerAPI.importXLSXToSnapshotAsync(file); // 서버 필요
      univerAPI.createWorkbook(snapshot);
      // 필요 시: univerAPI.exportXLSXBySnapshotAsync(...) 등 (역시 서버 필요)
      // https://docs.univer.ai/guides/sheets/features/import-export
      
      return;
    } catch (e) {
      console.warn("Univer 서버 기반 Import 실패, SheetJS Fallback 시도:", e);
    }
  }
});
