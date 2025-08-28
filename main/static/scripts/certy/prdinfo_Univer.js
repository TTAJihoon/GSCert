document.addEventListener('DOMContentLoaded', async () => {
  // 필수 UMD 존재 확인
  if (!window.UniverPresets || !window.UniverCore || !window.UniverPresetSheetsCore || !window.UniverPresetSheetsUI) {
    console.error('Univer UMD가 로드되지 않았습니다.');
    return;
  }
  if (!window.UniverSheetsXlsx && !window.UniverPresetSheetsXlsx) {
    console.error('XLSX 임포트 플러그인이 없습니다. (@univerjs/sheets-xlsx)');
    return;
  }

  const { createUniver } = window.UniverPresets;
  const hostEl = document.getElementById('app');

  // Univer 인스턴스 생성
  const univer = createUniver(hostEl, {
    theme: 'light',
    locales: [] // 필요시 ko-KR 로케일 주입
  });

  // XLSX 플러그인 인스턴스(빌드에 따라 네임스페이스가 다를 수 있어 둘 다 시도)
  const XlsxNS = window.UniverPresetSheetsXlsx || window.UniverSheetsXlsx;
  const xlsx = new XlsxNS.Xlsx(univer);

  // 서버에서 엑셀 다운로드 (이미 urls.py에 매핑된 엔드포인트)
  const res = await fetch('/source-excel/', { credentials: 'same-origin' });
  if (!res.ok) {
    console.error('엑셀 다운로드 실패:', res.status, await res.text().catch(()=> ''));
    return;
  }
  const blob = await res.blob();
  const file = new File(
    [blob],
    'prdinfo.xlsx',
    { type: blob.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
  );

  // ✅ 모든 시트/서식/병합/유효성 최대한 보존하여 로드
  if (typeof xlsx.open === 'function') {
    await xlsx.open({ file });
  } else if (typeof xlsx.import === 'function') {
    await xlsx.import({ file });
  } else {
    console.error('sheets-xlsx API(open/import) 미탑재 빌드입니다.');
  }
});
