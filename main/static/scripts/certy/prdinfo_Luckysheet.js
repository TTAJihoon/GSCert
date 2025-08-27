document.addEventListener("DOMContentLoaded", function () {
  // 1) 컨테이너 확인
  const containerId = "luckysheetContainer";
  const el = document.getElementById(containerId);
  if (!el) {
    console.error(`#${containerId} 컨테이너를 찾을 수 없습니다.`);
    return;
  }

  // 2) 전역 심볼 유연하게 선택 (UMD/Bundle 차이, CDN 빌드 차이 대비)
  const LS = window.luckysheet;
  if (!LS || typeof LS.create !== "function") {
    console.error("Luckysheet 라이브러리가 아직 전역에 없습니다.", {
      luckysheet: window.luckysheet
    });
    return;
  }

  luckysheet.create({
    container: "luckysheetContainer",
    title: "보안성 결과 임시 시트",
    lang: "en", // ko 리소스 별도 없으면 en 권장
    showinfobar: false,
    data: [{
      name: "Sheet1",
      index: "sheet1",
      status: 1,
      order: 0,
      row: 50,
      column: 20,
      celldata: [
        { r: 0, c: 0, v: { v: "Hello" } },
        { r: 0, c: 1, v: { v: 123, ct: { t: "n" } } },
        { r: 1, c: 0, v: { f: "=SUM(B1:B1)" } }
      ],
      config: {}
    }]
  });

  console.log("Luckysheet 초기화 완료");
});
