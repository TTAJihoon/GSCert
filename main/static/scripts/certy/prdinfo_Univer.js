document.addEventListener('DOMContentLoaded', async () => {
  // 필수 전역 체크
  if (!window.UniverPresets || !window.UniverCore || !window.UniverPresetSheetsCore) {
    console.error('Univer UMD가 로드되지 않았습니다.');
    return;
  }

  // UMD 전역에서 API 꺼내기
  const { createUniver } = window.UniverPresets;
  const { LocaleType, mergeLocales } = window.UniverCore;
  const { UniverSheetsCorePreset } = window.UniverPresetSheetsCore;

  // (선택) 데이터 검증 프리셋 - 드롭다운 등
  const hasDV = !!window.UniverPresetSheetsDataValidation;
  const { UniverSheetsDataValidationPreset } = window.UniverPresetSheetsDataValidation || {};

  // 로케일(영문 예시). 필요 시 ko-KR로 교체 가능
  const locales = {};
  if (window.UniverPresetSheetsCoreEnUS) {
    locales[LocaleType.EN_US] = mergeLocales(
      window.UniverPresetSheetsCoreEnUS,
      window.UniverPresetSheetsDataValidationEnUS || {}
    );
  }

  // Univer 앱 만들기
  const { univerAPI } = createUniver({
    locale: LocaleType.EN_US,
    locales,
    // 프리셋 장착 (시트 코어 + 데이터 검증 UI)
    presets: [
      UniverSheetsCorePreset(),
      ...(hasDV ? [UniverSheetsDataValidationPreset({ showEditOnDropdown: true })] : []),
    ],
  });
  
  try {
    if (typeof univerAPI.importXLSXToSnapshotAsync === 'function') {
      const snapshot = await univerAPI.importXLSXToSnapshotAsync('/source-excel/');
      univerAPI.createWorkbook(snapshot); // 서버 엑셀 로드
    } else {
      console.warn('XLSX Import API가 제공되지 않습니다. (Univer Pro 서버 필요)');
    }
  } catch (e) {
    console.error('엑셀 임포트 실패:', e);
  }
});
