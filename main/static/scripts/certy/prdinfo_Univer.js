document.addEventListener('DOMContentLoaded', async () => {
  // 1) 필수 전역 존재 확인 (Preset 모드 전역 네임스페이스)
  if (!window.UniverPresets || !window.UniverCore || !window.UniverPresetSheetsCore) {
    console.error('Univer UMD가 로드되지 않았습니다.');
    return;
  }

  // 2) UMD 전역에서 API 꺼내기 (0.5.x 이후 권장 분리)
  const { createUniver } = window.UniverPresets;
  const { LocaleType, mergeLocales } = window.UniverCore;
  const { UniverSheetsCorePreset } = window.UniverPresetSheetsCore;

  // (옵션) 데이터 검증 프리셋
  const hasDV = !!window.UniverPresetSheetsDataValidation;
  const { UniverSheetsDataValidationPreset } = window.UniverPresetSheetsDataValidation || {};

  // 3) 로케일 병합
  const locales = {};
  if (window.UniverPresetSheetsCoreEnUS) {
    locales[LocaleType.EN_US] = mergeLocales(
      window.UniverPresetSheetsCoreEnUS,
      window.UniverPresetSheetsDataValidationEnUS || {}
    );
  }

  // 4) Univer 앱 생성 (Preset 장착)
  const { univerAPI } = createUniver({
    locale: LocaleType.EN_US,
    locales,
    presets: [
      UniverSheetsCorePreset(),
      ...(hasDV ? [UniverSheetsDataValidationPreset({ showEditOnDropdown: true })] : []),
    ],
    // (선택) UI 컨테이너 지정은 Sheets Core 프리셋에서 자동 처리됩니다.
    container: 'app',
  });

  // 5) 빈 워크북 or 서버 엑셀 로드
  try {
    // 서버 엑셀을 바로 가져오고 싶다면 (지원되는 버전에서)
    if (typeof univerAPI.importXLSXToSnapshotAsync === 'function') {
      const snapshot = await univerAPI.importXLSXToSnapshotAsync('/source-excel/');
      univerAPI.createWorkbook(snapshot); // 교체 로드
    } else {
      console.warn('XLSX Import API가 노출되지 않았습니다. (구성/버전에 따라 다름)');
    }
  } catch (e) {
    console.error('엑셀 임포트 실패:', e);
  }
});
