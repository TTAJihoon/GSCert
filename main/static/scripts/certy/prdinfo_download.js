document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btn-download');
  if (!btn) return;

  // ── ExcelJS 로더 ─────────────────────────────
  function ensureExcelJS() {
    if (window.ExcelJS) return Promise.resolve();
    return new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js';
      s.onload = () => res();
      s.onerror = () => rej(new Error('ExcelJS 로드 실패'));
      document.head.appendChild(s);
    });
  }

  // ── 유틸: Luckysheet → ExcelJS 변환 보조 ─────
  const pxToWidth = px => Math.max(1, Math.round((px || 64) / 7)); // 대략적 환산
  const pxToPt    = px => (px || 19) * 0.75; // 96dpi→pt
  const safeName  = (() => {
    return (name, used) => {
      let n = String(name || 'Sheet').replace(/[\\/?*\[\]:]/g, '_').slice(0, 31);
      if (!n) n = 'Sheet';
      const base = n; let i = 1;
      while (used.has(n)) { const suf = '_' + (i++); n = base.slice(0, 31 - suf.length) + suf; }
      used.add(n); return n;
    };
  })();

  function getLS() {
    return window.luckysheet || window.Luckysheet;
  }

  function normName(s){ return String(s||'').replace(/\s+/g,'').toLowerCase(); }

  // Luckysheet cell → {value, style} 매핑
  function applyCellValue(ws, r1, c1, cell) {
    if (!cell) return;
    const excelCell = ws.getCell(r1, c1);

    // 값
    let v = (cell.v !== undefined) ? cell.v
          : (cell.m !== undefined) ? cell.m
          : "";
    // 타입/포맷 (ct: { t, fa })
    if (cell.ct && cell.ct.t) {
      const t = cell.ct.t; // 'n'(number), 's'(string), 'b'(bool), 'd'(date) 등
      if (t === 'n') {
        const num = Number(v);
        if (Number.isFinite(num)) v = num;
      } else if (t === 'b') {
        v = Boolean(v);
      } else if (t === 'd') {
        // Luckysheet 날짜는 실수/문자 혼재 가능 → 기본은 문자열 취급
        // 필요 시 시리얼 변환 로직 추가 가능
      }
      if (cell.ct.fa) {
        excelCell.numFmt = cell.ct.fa; // 숫자/날짜 포맷
      }
    }
    excelCell.value = v;

    // 정렬 (ht, vt), 줄바꿈(tb)
    const align = {};
    if (cell.ht) align.horizontal = mapAlign(cell.ht);
    if (cell.vt) align.vertical   = mapVAlign(cell.vt);
    if (cell.tb || cell.wrap) align.wrapText = true;
    if (Object.keys(align).length) excelCell.alignment = align;

    // 폰트 (fs, fc, bl, it, cl 등)
    const font = {};
    if (cell.fs) font.size = Number(cell.fs);
    if (cell.fc) font.color = { argb: toARGB(cell.fc) };
    if (cell.bl) font.bold = !!cell.bl;
    if (cell.it) font.italic = !!cell.it;
    // 취소선/밑줄키가 셀에 있다면 아래 확장 가능: font.strike, font.underline
    if (Object.keys(font).length) excelCell.font = font;

    // 배경색(bg)
    if (cell.bg) {
      excelCell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: toARGB(cell.bg) }
      };
    }
  }

  function toARGB(hex) {
    // "#RRGGBB" → "FFRRGGBB"
    const h = String(hex || '').replace('#','').trim();
    if (h.length === 6) return 'FF' + h.toUpperCase();
    if (h.length === 8) return h.toUpperCase();
    return 'FFFFFFFF';
  }
  function mapAlign(ht) {
    // luckysheet: 'left'|'center'|'right' 또는 1/2/3 등으로 오는 경우도 존재
    const v = typeof ht === 'string' ? ht.toLowerCase() : ht;
    if (v===1||v==='left') return 'left';
    if (v===2||v==='center') return 'center';
    if (v===3||v==='right') return 'right';
    return undefined;
  }
  function mapVAlign(vt) {
    const v = typeof vt === 'string' ? vt.toLowerCase() : vt;
    if (v===1||v==='top') return 'top';
    if (v===2||v==='middle' || v==='center') return 'middle';
    if (v===3||v==='bottom') return 'bottom';
    return undefined;
  }

  // 테두리: luckysheet borderInfo → exceljs
  function applyBorders(ws, borderInfo) {
    if (!Array.isArray(borderInfo)) return;
    for (const b of borderInfo) {
      if (b.rangeType === 'cell' && b.value) {
        const { row_index:r, col_index:c, l, r:rt, t, b:bt } = b.value;
        const excelCell = ws.getCell(r+1, c+1);
        const border = {};
        if (l)  border.left   = { style: mapBorder(l.style),  color: { argb: toARGB(l.color) } };
        if (rt) border.right  = { style: mapBorder(rt.style), color: { argb: toARGB(rt.color) } };
        if (t)  border.top    = { style: mapBorder(t.style),  color: { argb: toARGB(t.color) } };
        if (bt) border.bottom = { style: mapBorder(bt.style), color: { argb: toARGB(bt.color) } };
        if (Object.keys(border).length) excelCell.border = border;
      }
      // rangeType === 'range' 등은 필요 시 추가 확장 가능
    }
  }
  function mapBorder(styleNum) {
    // luckysheet: 1~? → exceljs: 'thin','medium','dashed','dotted','double' 등
    // 보편 맵핑(필요 시 조정)
    switch (styleNum) {
      case 1: return 'thin';
      case 2: return 'medium';
      case 3: return 'dashed';
      case 4: return 'dotted';
      case 5: return 'double';
      default: return 'thin';
    }
  }

  // 병합: config.merge { key: { r,c,rs,cs } }
  function applyMerges(ws, mergeCfg) {
    if (!mergeCfg) return;
    for (const key of Object.keys(mergeCfg)) {
      const m = mergeCfg[key];
      if (!m) continue;
      const sr = m.r + 1, sc = m.c + 1;
      const er = m.r + m.rs, ec = m.c + m.cs;
      try { ws.mergeCells(sr, sc, er, ec); } catch(_) {}
    }
  }

  // 행/열 크기/숨김: config.rowlen/columnlen, rowhidden/colhidden
  function applySizeAndHidden(ws, sheet) {
    const cfg = sheet.config || {};
    if (cfg.columnlen) {
      const cols = Object.keys(cfg.columnlen).map(x => parseInt(x, 10));
      for (const c of cols) {
        const w = pxToWidth(cfg.columnlen[c]);
        ws.getColumn(c+1).width = w;
      }
    }
    if (cfg.colhidden) {
      const cols = Object.keys(cfg.colhidden).map(x => parseInt(x, 10));
      for (const c of cols) {
        const hiddenVal = cfg.colhidden[c];
        ws.getColumn(c+1).hidden = !!hiddenVal || hiddenVal === 0;
      }
    }
    if (cfg.rowlen) {
      const rows = Object.keys(cfg.rowlen).map(x => parseInt(x, 10));
      for (const r of rows) {
        const h = pxToPt(cfg.rowlen[r]);
        ws.getRow(r+1).height = h;
      }
    }
    if (cfg.rowhidden) {
      const rows = Object.keys(cfg.rowhidden).map(x => parseInt(x, 10));
      for (const r of rows) {
        const hiddenVal = cfg.rowhidden[r];
        ws.getRow(r+1).hidden = !!hiddenVal || hiddenVal === 0;
      }
    }
  }

  btn.addEventListener('click', async (e) => {
    e.preventDefault();

    const LS = getLS();
    if (!LS || typeof LS.getluckysheetfile !== 'function') {
      alert('Luckysheet 인스턴스를 찾을 수 없습니다.');
      return;
    }
    const files = LS.getluckysheetfile();
    if (!files || !files.length) {
      alert('다운로드할 시트가 없습니다.');
      return;
    }

    try {
      await ensureExcelJS();
      const wb = new ExcelJS.Workbook();
      const usedNames = new Set();

      for (const sheet of files) {
        const wsName = safeName(sheet.name, usedNames);
        const ws = wb.addWorksheet(wsName);

        // 데이터 영역 크기 파악
        const data = sheet.data || [];
        let maxR = data.length;
        let maxC = 0;
        for (let r = 0; r < data.length; r++) {
          const row = data[r];
          if (Array.isArray(row)) maxC = Math.max(maxC, row.length);
        }
        // 값/스타일 채우기
        for (let r = 0; r < maxR; r++) {
          for (let c = 0; c < maxC; c++) {
            const cell = (data[r] && data[r][c]) || null;
            if (!cell) continue;
            applyCellValue(ws, r+1, c+1, cell);
          }
        }

        // 병합/테두리/크기/숨김 등 적용
        applyMerges(ws, sheet.config && sheet.config.merge);
        applyBorders(ws, sheet.config && sheet.config.borderInfo);
        applySizeAndHidden(ws, sheet);
      }

      // 다운로드
      const buf = await wb.xlsx.writeBuffer();
      const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'luckysheet_export.xlsx';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
    } catch (err) {
      console.error(err);
      alert('엑셀 내보내기 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : err));
    }
  });
});
