document.addEventListener("DOMContentLoaded", function () {
  // UMD 전역 확인
  if (!window.Luckysheet || typeof window.Luckysheet.create !== "function") {
    console.error("Luckysheet 라이브러리가 로드되지 않았거나 create가 없습니다.", window.Luckysheet);
    return;
  }

  // 컨테이너 존재 확인
  const el = document.getElementById("luckysheetContainer");
  if (!el) {
    console.error("#luckysheetContainer를 찾을 수 없습니다.");
    return;
  }

  window.luckysheet.create({
    container: "luckysheetContainer",
    title: "보안성 결과 임시 시트",
    lang: "en", // ko 리소스 별도 없으면 en 권장
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
