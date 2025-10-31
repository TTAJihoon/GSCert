(function (window, document) {
  const Table = (window.CheckReportTable = window.CheckReportTable || {});

  // 이모지/공백/대소문/괄호 등을 제거하고 표준 키로 정규화
  function normalizeSeverity(value) {
    if (!value) return '';
    // 1) 문자열화 후 트림
    let s = String(value).trim();
    // 2) 이모지/기호 제거 (사각형/색상 이모지 등)
    s = s.replace(/[\u{1F300}-\u{1FAFF}\u{FE0F}\u{200D}]/gu, '');
    // 3) 괄호 안 이모지/텍스트 방지용 트리밍
    s = s.replace(/[()]/g, '').trim();
    // 4) 전각 공백/다중 공백 제거
    s = s.replace(/\s+/g, '');
    // 5) 한글 소문자 개념 없음 → 그대로 비교
    return s;
  }

  // 표준화된 키 → CSS 클래스
  const severityMap = {
    '심각': 'severity-critical',
    '중요': 'severity-major',
    '보통': 'severity-medium',
    '경미': 'severity-minor'
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
    // ---------- 유틸 (함수 내부에 캡슐화) ----------
    function escapeHTML(s) {
      if (s == null) return '';
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    // 이모지/공백/괄호 제거 등으로 심각도 정규화
    function normalizeSeverity(value) {
      if (!value) return '';
      let s = String(value).trim();
      // 이모지/zero-width 등 제거
      s = s.replace(/[\u{1F300}-\u{1FAFF}\u{FE0F}\u{200D}]/gu, '');
      // 괄호 제거
      s = s.replace(/[()]/g, '').trim();
      // 전각/다중 공백 제거
      s = s.replace(/\s+/g, '');
      return s;
    }

    // 정규화된 키 → CSS 클래스
    const severityMap = {
      '심각': 'severity-critical',
      '중요': 'severity-major',
      '보통': 'severity-medium',
      '경미': 'severity-minor'
    };

    // ---------- 컬럼 정의 (제목/값 추출자) ----------
    // JSON 키가 프로젝트마다 조금씩 달 수 있어 안전한 대체 키 포함
    const columns = [
      {
        key: 'section',
        title: '구분(점검항목)',
        get: (r) => r.section ?? r.category ?? r.item ?? ''
      },
      {
        key: 'location',
        title: '위치(표/절/문장)',
        get: (r) => r.location ?? r.position ?? r.path ?? ''
      },
      {
        key: 'summary',
        title: '문제 요약',
        get: (r) => r.summary ?? r.issue ?? r.problem ?? ''
      },
      {
        key: 'evidence',
        title: '근거(원문 일부 인용)',
        get: (r) => r.evidence ?? r.quote ?? r.reference ?? ''
      },
      {
        key: 'fix',
        title: '권장 수정안',
        get: (r) => r.fix ?? r.recommendation ?? r.suggestion ?? ''
      }
    ];

    // ---------- 대상 테이블/섹션 탐색 ----------
    // 우선 id="checkreportTable"을 찾고, 없으면 첫 번째 table을 사용
    const table =
      document.getElementById('checkreportTable') ||
      document.querySelector('table');

    if (!table) {
      console.warn('[Table.render] 테이블 요소를 찾지 못했습니다.');
      return;
    }

    // thead/tbody 준비 (없으면 생성)
    let thead = table.querySelector('thead');
    let tbody = table.querySelector('tbody');
    if (!thead) {
      thead = document.createElement('thead');
      table.appendChild(thead);
    }
    if (!tbody) {
      tbody = document.createElement('tbody');
      table.appendChild(tbody);
    }

    // 기존 내용 초기화
    thead.innerHTML = '';
    tbody.innerHTML = '';

    // ---------- 헤더 렌더링 ----------
    const trHead = document.createElement('tr');
    for (const col of columns) {
      const th = document.createElement('th');
      th.textContent = col.title;
      trHead.appendChild(th);
    }
    thead.appendChild(trHead);

    // ---------- 데이터 렌더링 ----------
    const items = (result && Array.isArray(result.items)) ? result.items : [];

    for (const row of items) {
      const tr = document.createElement('tr');

      // 공통 행 클래스(후속 기능 대비)
      tr.classList.add('table-data-row');

      // 심각도 클래스 부여(행 단위)
      const sevKey = normalizeSeverity(row?.severity);
      const sevClass = severityMap[sevKey];
      if (sevClass) tr.classList.add(sevClass);

      // 셀 생성
      for (const col of columns) {
        const td = document.createElement('td');
        const raw = col.get(row);
        // 문자열/번호만 출력. 객체/배열이면 JSON 요약
        let text =
          (raw != null && (typeof raw === 'string' || typeof raw === 'number'))
            ? String(raw)
            : (raw == null ? '' : JSON.stringify(raw));
        td.innerHTML = escapeHTML(text);
        tr.appendChild(td);
      }

      tbody.appendChild(tr);
    }

    // ---------- (선택) 요약 카운트/빈 상태 처리 ----------
    // id="resultCount" 요소가 있다면 총 개수 출력
    const countEl = document.getElementById('resultCount');
    if (countEl) {
      countEl.textContent = String(items.length);
    }

    // 빈 데이터 시 안내 행 추가
    if (items.length === 0) {
      const trEmpty = document.createElement('tr');
      const tdEmpty = document.createElement('td');
      tdEmpty.colSpan = columns.length;
      tdEmpty.textContent = '표시할 항목이 없습니다.';
      trEmpty.appendChild(tdEmpty);
      tbody.appendChild(trEmpty);
    }
  };
})(window, document);
