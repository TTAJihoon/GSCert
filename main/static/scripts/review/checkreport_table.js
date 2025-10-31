(function (window, document) {
  const Table = (window.CheckReportTable = window.CheckReportTable || {});

  // 표준화된 키 → CSS 클래스
  const severityMap = {
    '심각': '🟥 심각',
    '중요': '🟧 중요',
    '보통': '🟨 보통',
    '경미': '🟩 경미'
  };
  
  function qs(sel) { return document.querySelector(sel); }

  // 결과 JSON 스키마 (예시)
  // {
  //   "version": "1",
  //   "total": 3,
  //   "items": [
  //     {
  //       "no": 1,
  //       "category": "수식/산식",
  //       "severity": "심각",
  //       "location": "표 3-1, 2행",
  //       "summary": "X(%) 분모 누락",
  //       "evidence": "원문: ...",
  //       "recommendation": "분모에 n을 ... 정정"
  //     }
  //   ]
  // }

  Table.clear = function () {
    const tbody = qs("#tableBody");
    const count = qs("#totalCount");
    if (tbody) tbody.innerHTML = "";
    if (count) count.textContent = "0";
  };

  Table.render = function (result) {
    try {
      const items = Array.isArray(result?.items) ? result.items : [];
      const tbody = qs("#tableBody");
      const count = qs("#totalCount");
      const table = qs("#resultsTable");

      Table.clear();

      if (!tbody || !table) {
        console.warn("[checkreport_table] 테이블 요소를 찾을 수 없습니다.");
        return false;
      }

      if (count) count.textContent = String(items.length || 0);

      if (items.length === 0) {
        table.classList.add("hidden");
        return false;
      }

      const frag = document.createDocumentFragment();
      items.forEach(row => {
        const tr = document.createElement("tr");

        let sevClass = "";
        switch (row.severity) {
          case "심각": sevClass = "severity-critical";
            break;
          case "중요": sevClass = "severity-major";
            break;
          case "보통": sevClass = "severity-medium";
            break;
          case "경미": sevClass = "severity-minor";
            break;
          default:
            break;
        }
        if (sevClass) tr.classList.add(sevClass);

        const cells = [
          row.no ?? "",
          row.category ?? "",
          severityMap[row.severity] ?? "",
          row.location ?? "",
          row.summary ?? "",
          row.evidence ?? "",
          row.recommendation ?? ""
        ];

        for (let i = 0; i < cells.length; i++) {
          const td = document.createElement("td");
          const v = cells[i];
          td.textContent = (v == null) ? "" : String(v);
          tr.appendChild(td);
        }

        frag.appendChild(tr);
      });

      tbody.appendChild(frag);
      table.classList.remove("hidden");
      return true;
    } catch (e) {
      console.error("[checkreport_table] render 실패:", e);
      return false;
    }
  };
})(window, document);
