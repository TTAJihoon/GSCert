document.addEventListener('DOMContentLoaded', async () => {
  // (생략) Univer/XLSX 로딩 및 /source-excel/에서 open/import 까지 마친 상태라고 가정
  // univer, xlsx 인스턴스가 아래처럼 존재한다고 가정합니다.
  const { createUniver } = window.UniverPresets;
  const hostEl = document.getElementById('app');
  const univer = createUniver(hostEl, { theme: 'light' });

  // XLSX 플러그인
  const XlsxNS = window.UniverPresetSheetsXlsx || window.UniverSheetsXlsx;
  const xlsx = new XlsxNS.Xlsx(univer);

  // 서버 원본 로드 (이미 구현해 두신 코드와 동일)
  const res = await fetch('/source-excel/', { credentials: 'same-origin' });
  const blob = await res.blob();
  const file = new File([blob], 'prdinfo.xlsx', {
    type: blob.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  });
  if (typeof xlsx.open === 'function') await xlsx.open({ file });
  else if (typeof xlsx.import === 'function') await xlsx.import({ file });

  // ====== ▼▼▼ 여기부터 "현재 상태 그대로 다운로드" 구현 ▼▼▼ ======
  const btn = document.getElementById('btn-download');

  // 공통: Blob을 파일로 저장하는 헬퍼
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
    const ts = new Date().toISOString().slice(0,19).replace(/[:T]/g,'-'); // 2025-08-28-10-30-00
    const fileName = `prdinfo-${ts}.xlsx`;

    try {
      // 1) 가장 쉬운 경로: 플러그인의 내보내기 함수가 있는 경우
      if (typeof xlsx.export === 'function') {
        // 일부 빌드는 자동으로 다운로드까지 처리합니다.
        await xlsx.export({ fileName }); // 내부에서 a[download]까지 수행되는 경우가 많음
        return;
      }

      // 2) Blob 반환형 내보내기(빌드마다 이름이 다를 수 있으니 후보들을 순차 시도)
      const exportCandidates = ['save', 'saveAs', 'toXlsx', 'exportAsBlob', 'download']; 
      for (const m of exportCandidates) {
        if (typeof xlsx[m] === 'function') {
          const out = await xlsx[m]({ fileName });
          // 일부는 Blob을, 일부는 ArrayBuffer/Uint8Array를 반환할 수 있음
          let blobOut = out instanceof Blob ? out : new Blob([out], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          });
          saveBlobToFile(blobOut, fileName);
          return;
        }
      }

      // 3) 최후 수단: 스냅샷(JSON)으로라도 내려받기 (사용자 편집 상태 보존은 가능하나 xlsx가 아닌 json)
      // ※ 필요 시 SheetJS를 함께 로드해 스냅샷→XLSX 변환도 가능(원하시면 코드 드릴게요).
      if (typeof univer.getActiveWorkbook === 'function') {
        const wb = univer.getActiveWorkbook();
        const snapshot = wb?.getSnapshot ? wb.getSnapshot() : null;
        if (snapshot) {
          const jsonBlob = new Blob([JSON.stringify(snapshot)], { type: 'application/json' });
          saveBlobToFile(jsonBlob, `prdinfo-${ts}.json`);
          alert('현재 빌드에서 XLSX 내보내기 API를 찾지 못해 JSON 스냅샷으로 저장했습니다.');
          return;
        }
      }

      console.error('XLSX 내보내기 API를 찾지 못했습니다.');
      alert('죄송합니다. 이 UMD 번들에는 XLSX 내보내기 API가 노출되지 않습니다.');
    } catch (err) {
      console.error('내보내기 실패:', err);
      alert('다운로드 중 오류가 발생했습니다.');
    }
  });
  // ====== ▲▲▲ 내보내기 구현 끝 ▲▲▲ ======
});
