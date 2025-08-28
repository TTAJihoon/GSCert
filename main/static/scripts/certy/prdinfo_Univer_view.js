document.addEventListener('DOMContentLoaded', () => {
  (async function () {
    const GLOBAL = (window.PRDINFO ||= {});
    if (GLOBAL.ready) return; // 재실행 방지

    function waitForUniverUMD(timeoutMs = 5000) {
      const start = Date.now();
      return new Promise((resolve, reject) => {
        (function tick() {
          const hasPresets = !!window.UniverPresets?.createUniver;
          const hasUniver  = !!window.Univer?.createUniver; // 어떤 빌드는 여기 노출
          const XlsxNS     = window.UniverPresetSheetsXlsx || window.UniverSheetsXlsx;

          if ((hasPresets || hasUniver) && XlsxNS) {
            resolve({
              createUniver: (window.UniverPresets?.createUniver || window.Univer?.createUniver),
              XlsxNS,
            });
            return;
          }
          if (Date.now() - start > timeoutMs) {
            reject(new Error('Univer UMD를 찾지 못했습니다. (전역 심벌 미노출/로딩 실패)'));
            return;
          }
          setTimeout(tick, 50);
        })();
      });
    }

    GLOBAL.ready = (async () => {
      // 1) UMD 준비 대기
      const { createUniver, XlsxNS } = await waitForUniverUMD();

      // 2) 컨테이너
      const hostEl = document.getElementById('app');
      if (!hostEl) throw new Error('#app 컨테이너가 없습니다.');

      // 3) Univer/xlsx 생성(한 번만)
      const univer = createUniver(hostEl, { theme: 'light', locales: [] });
      const xlsx   = new XlsxNS.Xlsx(univer);

      // 4) 서버 엑셀 로드
      const res = await fetch('/source-excel/', { credentials: 'same-origin' });
      if (!res.ok) throw new Error('엑셀 다운로드 실패: ' + res.status);

      const blob = await res.blob();
      const file = new File([blob], 'prdinfo.xlsx', {
        type: blob.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });

      if (typeof xlsx.open === 'function')       await xlsx.open({ file });
      else if (typeof xlsx.import === 'function') await xlsx.import({ file });
      else console.error('sheets-xlsx API(open/import) 미탑재 빌드입니다.');

      // 5) 전역 공유
      GLOBAL.univer = univer;
      GLOBAL.xlsx   = xlsx;

      return GLOBAL;
    })().catch((err) => {
      console.error('[PRDINFO] init+view 실패:', err);
    });
  })();
});
