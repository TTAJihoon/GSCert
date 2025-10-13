from bs4 import BeautifulSoup
import re
from typing import Dict, Any, List, Optional

def _clean_text(el) -> str:
  if not el:
    return ""
  return el.get_text("\n", strip=True)

def _parse_table_new_schema(detail_div) -> Optional[Dict[str, Any]]:
  """
  vuln-detail 내부의 첫 테이블을 columns/rows 스키마로 파싱.
  columns: [{key,label}, ...]
  rows:    [{key:value, ...}, ...]
  """
  table = detail_div.find('table')
  if not table:
    return None

  first_tr = table.find('tr')
  if not first_tr:
    return None

  headers_raw = [th.get_text(strip=True) for th in first_tr.find_all(['th', 'td'])]
  # 표준화된 컬럼 키 매핑(최대한 의미 보존)
  mapping: List[tuple] = []
  for h in headers_raw:
    h_norm = h.replace(" ", "").lower()
    if ('메서드' in h) or ('method' in h_norm):
      mapping.append(("method", h))
    elif ('매개변수형식' in h) or ('형식' in h) or ('type' in h_norm):
      mapping.append(("type", h))
    elif ('매개변수' in h) or ('parameter' in h_norm) or ('param' in h_norm):
      mapping.append(("param", h))
    elif ('값' in h) or ('value' in h_norm):
      mapping.append(("value", h))
    else:
      mapping.append((f"col_{len(mapping)}", h))  # 알 수 없는 컬럼도 보존

  rows: List[Dict[str, str]] = []
  for tr in table.find_all('tr')[1:]:
    cells = [td.get_text("\n", strip=True) for td in tr.find_all(['td', 'th'])]
    if len(cells) < len(mapping):
      cells += [''] * (len(mapping) - len(cells))
    row_obj = {}
    for (key, _label), val in zip(mapping, cells[:len(mapping)]):
      row_obj[key] = val
    rows.append(row_obj)

  columns = [{"key": key, "label": label} for (key, label) in mapping]
  return {"columns": columns, "rows": rows}

def _find_proof_url(detail_div) -> Optional[str]:
  # '증명 URL' 또는 'Proof URL' 라벨 근처 a[href] 우선
  lab = detail_div.find(string=re.compile(r'증명\s*URL|Proof\s*URL', re.I))
  if lab and lab.parent:
    a = lab.parent.find('a', href=True)
    if a and a.get('href'):
      return a['href']
    a2 = lab.find_next('a', href=True)
    if a2 and a2.get('href'):
      return a2['href']
  # fallback: detail 내 첫 링크
  a = detail_div.find('a', href=True)
  return a['href'] if a else None

def _extract_pre_text(container, selector: str) -> Optional[str]:
  """
  container 안에서 selector로 찾아 pre/code를 텍스트(일반 문자열)로 추출
  """
  el = container.select_one(selector)
  if not el:
    return None
  pre = el.find('pre')
  if not pre:
    return _clean_text(el)
  code = pre.find('code')
  return code.get_text("\n", strip=False) if code else pre.get_text("\n", strip=False)

def _extract_vuln_detail_first_json(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
  """
  문서에서 '첫 번째' vuln-detail을 찾아 JSON 스키마로 반환.
  우선순위 컨테이너: div.vulns.highs → div.vulns → 문서 전체
  """
  container = soup.select_one('div.vulns.highs') or soup.select_one('div.vulns')
  if container:
    detail = container.select_one('div.vuln-detail')
  else:
    detail = soup.select_one('div.vuln-detail')

  if not detail:
    return None

  return {
    "table": _parse_table_new_schema(detail),
    "url": _find_proof_url(detail),
    "request": _extract_pre_text(detail, '.vuln-tab.vuln-req1-tab'),
    "response": _extract_pre_text(detail, '.vuln-tab.vuln-resp1-tab'),
  }

# ---------- 메인 추출 함수 ----------
def extract_vulnerability_sections(html_content: str) -> Dict[str, Any]:
  """
  전체 Invicti HTML에서
   - 원본 <style> 모아서 css로 반환
   - div.vuln-desc 블록들을 잘라 invicti_analysis(HTML 스니펫)로 rows에 싣기
   - 문서 전체 기준 '첫 번째' vuln-detail JSON(first_vuln_detail_json) 반환
  """
  soup = BeautifulSoup(html_content, 'html.parser')

  # 1) 원본 CSS 모으기
  head = soup.head or soup
  css_styles = []
  for style in head.find_all('style'):
    try:
      css_styles.append(style.get_text())
    except Exception:
      pass
  css_joined = "\n".join(css_styles)

  # 2) 첫 vuln-detail JSON
  first_vuln_detail_json = _extract_vuln_detail_first_json(soup)

  # 3) 각 vuln-desc 블록을 행으로 구성 (기존 로직과 유사)
  rows: List[Dict[str, Any]] = []
  # 심각도 그룹 예시: criticals / highs / mediums (필요시 확장)
  groups = ['criticals', 'highs', 'mediums']
  for grp in groups:
    for vuln_desc_div in soup.select(f'div.vuln-desc.{grp}'):
      # H2 (리포트 섹션 제목)
      h2 = vuln_desc_div.find('h2')
      h2_text = h2.get_text(strip=True) if h2 else 'Invicti Report'

      # 스니펫 추출: 현재 vuln-desc부터 '같은 레벨'의 다음 vuln-desc 직전까지
      # = 부모 기준 형제 흐름에서 현재 div 이후 ~ 다음 vuln-desc 전까지 수집
      parent = vuln_desc_div.parent
      siblings = list(parent.children) if parent else [vuln_desc_div]
      snippet_nodes = []
      hit = False
      for node in siblings:
        if node is vuln_desc_div:
          hit = True
        elif hit:
          # 다음 vuln-desc를 만나기 전에만 수집
          if getattr(node, 'get', None) and node.get('class') and ('vuln-desc' in node.get('class')):
            break
          snippet_nodes.append(node)

      # snippet HTML: 현재 vuln-desc + 수집한 형제들
      wrapper = BeautifulSoup('<div class="invicti-snippet"></div>', 'html.parser')
      container = wrapper.div
      container.append(vuln_desc_div)  # 현재 블록 자체 포함
      for n in snippet_nodes:
        # beautifulsoup에서 기존 트리에서 떼어 붙이므로 원본 변경 영향 없음(여기선 일회성)
        container.append(n)

      html_snippet = str(container)

      # 요약/레벨 등은 간단 기본값(필요시 세부 규칙으로 대체)
      defect_summary = (h2_text or '').split(' - ')[0][:100]
      defect_level = grp.upper()

      row = {
        "id": id(container),  # 프런트에서 유니크 키로만 사용
        "test_env_os": "시험환경\n모든 OS",
        "defect_summary": defect_summary,
        "defect_level": defect_level,
        "frequency": "A",
        "quality_attribute": "보안성",
        "defect_description": "상세는 Invicti 분석을 확인하세요.",
        "invicti_report": h2_text,
        "invicti_analysis": html_snippet,
        "gpt_recommendation": "추천 버튼을 눌러 GPT 프롬프트를 확인하세요.",
        # 행 단위 vuln-detail JSON은 '첫 행'에만 넣고 싶으면 여기서 조건 처리
        "vuln_detail_json": None,
      }
      rows.append(row)

  # 첫 행에만 row-level로 싣고 싶을 때
  if rows and first_vuln_detail_json:
    rows[0]["vuln_detail_json"] = first_vuln_detail_json

  return {
    "css": css_joined,
    "rows": rows,
    "first_vuln_detail_json": first_vuln_detail_json
  }
