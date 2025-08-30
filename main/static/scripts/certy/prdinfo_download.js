(function () {
  function getCsrfToken() {
    const el = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return el ? el.value : '';
  }

  // Luckysheet에서 시트ID 찾기 (시트 이름으로)
  function getSheetIdByName(name) {
    const info = luckysheet.getAllSheets();
    const found = info.find(s => s.name === name);
    return found ? found.id : null;
  }

  // 지정 범위의 값을 2차원 배열로 획득(B..N, row 고정)
  function getRowValues(sheetId, row1based, colStartLetter, colEndLetter) {
    const startColIdx = letterToIndex(colStartLetter); // 1-based
    const endColIdx   = letterToIndex(colEndLetter);   // 1-based
    const r = row1based - 1; // luckysheet는 0-based

    const arr = [];
    for (let c = startColIdx - 1; c <= endColIdx - 1; c++) {
      arr.push(luckysheet.getCellValue(r, c, sheetId) ?? "");
    }
    return arr;
  }

  // 단일 셀 값
  function getCell(sheetId, addr) {
    const { r, c } = addrToRC(addr); // 1-based
    return luckysheet.getCellValue(r - 1, c - 1, sheetId) ?? "";
  }

  // "B5" -> {r:5, c:2}
  function addrToRC(addr) {
    const m = /^([A-Z]+)(\d+)$/.exec(addr);
    const col = m[1];
    const row = parseInt(m[2], 10);
    return { r: row, c: letterToIndex(col) };
  }

  // "B" -> 2 (1-based)
  function letterToIndex(letters) {
    let n = 0;
    for (let i = 0; i < letters.length; i++) {
      n = n * 26 + (letters.charCodeAt(i) - 64);
    }
    return n;
  }

  async function onDownload() {
    const prdSheetId = getSheetIdByName("제품 정보 요청");
    const defSheetId = getSheetIdByName("결함정보");
    if (!prdSheetId || !defSheetId) {
      alert("시트를 찾을 수 없습니다. (제품 정보 요청 / 결함정보)");
      return;
    }

    // ── 제품 정보 요청
    const row_B5_N5 = getRowValues(prdSheetId, 5, "B", "N"); // 13개
    const row_B7_N7 = getRowValues(prdSheetId, 7, "B", "N"); // 13개

    const B9 = getCell(prdSheetId, "B9");
    const D9 = getCell(prdSheetId, "D9");
    const F9 = getCell(prdSheetId, "F9");
    const G9 = getCell(prdSheetId, "G9");
    const H9 = getCell(prdSheetId, "H9");
    const J9 = getCell(prdSheetId, "J9");
    const L9 = getCell(prdSheetId, "L9");

    // ── 결함정보
    const row_B4_N4 = getRowValues(defSheetId, 4, "B", "N"); // 13개

    const payload = {
      prdinfo: {
        row_B5_N5,
        row_B7_N7,
        B9, D9, F9, G9, H9, J9, L9
      },
      defect: {
        row_B4_N4
      }
    };

    const csrf = getCsrfToken();

    const res = await fetch("/certy/prdinfo/download-filled/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      alert("다운로드 생성 실패: " + (txt || res.status));
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "prdinfo_filled.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("btn-download");
    if (btn) btn.addEventListener("click", onDownload);
  });
})();
