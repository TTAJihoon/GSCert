(function (window, document) {
  const Table = (window.CheckReportTable = window.CheckReportTable || {});

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

        const tdNo = document.createElement("td");
        tdNo.textContent = row.no ?? "";
        tr.appendChild(tdNo);

        const tdCat = document.createElement("td");
        tdCat.textContent = row.category ?? "";
        tr.appendChild(tdCat);

        const tdSev = document.createElement("td");
        tdSev.textContent = row.severity ?? "";
        tr.appendChild(tdSev);

        const tdLoc = document.createElement("td");
        tdLoc.textContent = row.location ?? "";
        tr.appendChild(tdLoc);

        const tdSum = document.createElement("td");
        tdSum.textContent = row.summary ?? "";
        tr.appendChild(tdSum);

        const tdEv = document.createElement("td");
        tdEv.textContent = row.evidence ?? "";
        tr.appendChild(tdEv);

        const tdRec = document.createElement("td");
        tdRec.textContent = row.recommendation ?? "";
        tr.appendChild(tdRec);

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
