import re
from docx.table import Table, _Cell
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# --- 표 파싱 (vMerge, gridSpan) [최종 로직] ---
def parse_table(docx_table: Table):
    """
    [최종 로직] docx 테이블 객체를 [row, col, rowspan, colspan, text] 형식으로 변환합니다.
    사용자 가이드에 맞춘 '가상 그리드' 방식 + OxmlElement 직접 접근.
    """

    # { (r, c) : {"cell_data": [r, c, rs, cs, text], "is_start": True/False } }
    grid = {}
    max_rows = len(docx_table.rows)
    max_cols = 0
    tbl = docx_table._tbl # OxmlElement 접근

    # OxmlElement를 사용하여 XML 직접 분석으로 최대 열 개수 계산 (가장 정확)
    try:
        grid_cols = tbl.tblGrid.gridCol_lst if tbl.tblGrid is not None else []
        if grid_cols:
            max_cols = len(grid_cols)
        else: # tblGrid가 없는 경우 fallback
             # print("  [경고] tblGrid 정보 없음. Fallback 열 개수 계산.")
             for tr in tbl.tr_lst:
                  current_row_cols = 0
                  for tc in tr.xpath('./w:tc'):
                       grid_span_val = 1
                       tcPr = tc.find(qn('w:tcPr'))
                       if tcPr is not None:
                           gridSpan = tcPr.find(qn('w:gridSpan'))
                           if gridSpan is not None and gridSpan.val is not None:
                               try: grid_span_val = int(gridSpan.val)
                               except ValueError: pass
                       current_row_cols += grid_span_val
                  max_cols = max(max_cols, current_row_cols)
    except Exception as e:
         print(f"  [경고] 테이블 열 개수 계산 실패: {e}. Fallback 사용.")
         max_cols = max(len(row.cells) for row in docx_table.rows) if max_rows > 0 else 0


    final_cells_list = []

    for r_idx, row in enumerate(docx_table.rows):

        real_c_idx = 0
        tr = tbl.tr_lst[r_idx]
        tc_elements = tr.xpath('./w:tc') # 직계 자식 tc만

        for tc in tc_elements:
            cell = _Cell(tc, docx_table) # _Cell 객체 사용

            # (r_idx, real_c_idx)가 점유되었는지 확인
            while (r_idx, real_c_idx) in grid and real_c_idx < max_cols:
                real_c_idx += 1

            if real_c_idx >= max_cols:
                break

            # OxmlElement 사용하여 속성 접근
            tcPr = tc.tcPr
            vmerge_val = None
            colspan_val = 1

            if tcPr is not None:
                vMerge = tcPr.vMerge
                if vMerge is not None:
                    vmerge_val = vMerge.val or 'continue' # val 없으면 continue

                gridSpan = tcPr.gridSpan
                if gridSpan is not None and gridSpan.val is not None:
                    try: colspan_val = int(gridSpan.val)
                    except ValueError: pass

            text = cell.text.strip()
            rowspan_val = 1

            if vmerge_val == 'continue':
                # [가이드] 이어지는 셀
                root_cell_info = None
                for r_scan in range(r_idx - 1, -1, -1):
                    if (r_scan, real_c_idx) in grid:
                        candidate_info = grid[(r_scan, real_c_idx)]
                        if candidate_info["is_start"]:
                           root_cell_info = candidate_info
                           break
                        break # 바로 위가 시작 아니면 중단

                if root_cell_info:
                    root_cell_data = root_cell_info["cell_data"]
                    # [가이드] rowspan 계산: 루트 셀의 rowspan 값 증가
                    root_cell_data[2] += 1
                    # 현재 셀의 공간(colspan까지)을 루트 셀 정보로 채움
                    for c_offset in range(colspan_val):
                        if real_c_idx + c_offset < max_cols:
                            grid[(r_idx, real_c_idx + c_offset)] = {"cell_data": root_cell_data, "is_start": False}

                real_c_idx += colspan_val
                continue

            # 'restart' 또는 vMerge가 없는 셀
            current_cell_data = [r_idx + 1, real_c_idx + 1, rowspan_val, colspan_val, text]
            final_cells_list.append(current_cell_data)

            # 그리드 기록
            is_start_cell = (vmerge_val == 'restart' or vmerge_val is None)
            for r_offset in range(rowspan_val): # 현재는 1
                for c_offset in range(colspan_val):
                    if r_idx + r_offset < max_rows and real_c_idx + c_offset < max_cols:
                        grid[(r_idx + r_offset, real_c_idx + c_offset)] = {"cell_data": current_cell_data, "is_start": is_start_cell}

            real_c_idx += colspan_val

    return {"table": final_cells_list}
