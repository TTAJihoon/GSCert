document.addEventListener('DOMContentLoaded', async () => {
  try {
    const GLOBAL = await window.PRDINFO?.ready;
    if (!GLOBAL?.xlsx) throw new Error('XLSX 플러그인이 초기화되지 않았습니다.');

    const btn = document.getElementById('btn-download');
    if (!btn) return; // 버튼이 없으면 조용히 종료

    function saveBlobToFile(blob, fileName) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }

    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const ts = new Date().toISOString().slice(0,19).replace(/[:T]/g,'-');
      const fileName = `prdinfo-${ts}.xlsx`;

      // 1) 내보내기 API 후보군
      if (typeof GLOBAL.xlsx.export === 'function') {
        await GLOBAL.xlsx.export({ fileName });
        return;
      }
      const candidates = ['save', 'saveAs', 'toXlsx', 'exportAsBlob', 'download'];
      for (const m of candidates) {
        if (typeof GLOBAL.xlsx[m] === 'function') {
          const out = await GLOBAL.xlsx[m]({ fileName });
          const blobOut = out instanceof Blob ? out : new Blob([out], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          });
          saveBlobToFile(blobOut, fileName);
          return;
        }
      }

      // 2) 최후 수단: 스냅샷 JSON 저장 (원하시면 SheetJS 경로 추가 가능)
      const wb = GLOBAL.univer?.getActiveWorkbook?.();
      const snapshot = wb?.getSnapshot?.();
      if (snapshot) {
        saveBlobToFile(
          new Blob([JSON.stringify(snapshot)], { type: 'application/json' }),
          `prdinfo-${ts}.json`
        );
        alert('이 번들은 XLSX 내보내기 API가 없어 JSON 스냅샷으로 저장했습니다.');
        return;
      }
      alert('이 번들에는 XLSX 내보내기 API가 노출되지 않습니다.');
    });
  } catch (e) {
    console.error('[PRDINFO] download 바인딩 실패:', e);
  }
});
