(function (window, document) {
  const Table = (window.CheckReportTable = window.CheckReportTable || {});

  // 표준화된 키 → CSS 클래스
  const severityMap = {
    '심각': { label: '🟥 심각', css: 'severity-critical' },
    '중요': { label: '🟧 중요', css: 'severity-major' },
    '보통': { label: '🟨 보통', css: 'severity-medium' },
    '경미': { label: '🟩 경미', css: 'severity-minor' }
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

        // row.severity (예: '심각')를 사용하여 맵에서 정보를 가져옵니다.
        const severityInfo = severityMap[row.severity];
      
        // 유효성 검사 및 CSS 클래스 적용
        if (severityInfo && severityInfo.css) {
          tr.classList.add(severityInfo.css);
        }

        const cells = [
          row.no ?? "",
          row.category ?? "",
          severityInfo ? severityInfo.label : row.severity ?? "",
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
