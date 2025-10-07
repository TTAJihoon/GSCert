(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.gpt = {}; // GPT 관련 함수들을 위한 네임스페이스 생성

  const API_ENDPOINT = "/security/gpt/recommend/";
  const PLACEHOLDER_TEXT = "GPT 분석 버튼을 눌러주세요.";

  async function getGptRecommendation(recordId) {
    const rec = App.state.currentData.find((r) => r.id === recordId);
    if (!rec) return;

    // 1. 캐시 확인 (디버깅 중에도 매번 새로 생성하기 위해 이 부분을 잠시 비활성화할 수 있습니다.)
    //    또는 페이지를 새로고침하여 캐시를 초기화할 수 있습니다.
    if (rec.gpt_recommendation && rec.gpt_recommendation !== PLACEHOLDER_TEXT) {
      App.popup.showGptRecommendation(recordId);
      return;
    }

    // 2. invicti_analysis HTML에서 데이터 추출 (기존과 동일)
    const parser = new DOMParser();
    const doc = parser.parseFromString(rec.invicti_analysis, 'text/html');

    const vulnDescEl = doc.querySelector('.vuln-desc');
    const title = vulnDescEl?.querySelector('h2')?.innerText.trim() || '제목 없음';
    const description = Array.from(vulnDescEl?.querySelectorAll('p') || [])
                             .map(p => p.innerText.trim()).join('\n');

    let impact = '정보 없음';
    const impactHeader = Array.from(doc.querySelectorAll('h3.fw600')).find(h3 => h3.innerText.trim() === 'Impact');
    if (impactHeader && impactHeader.nextElementSibling) {
        impact = impactHeader.nextElementSibling.innerText.trim();
    }
    
    let remediation = '정보 없음';
    const remediationHeader = Array.from(doc.querySelectorAll('.more-detail h4')).find(h4 => h4.innerText.trim() === '대책');
    if (remediationHeader) {
        let content = '';
        let nextEl = remediationHeader.nextElementSibling;
        while(nextEl && nextEl.tagName !== 'H4') {
            content += nextEl.innerText.trim() + '\n\n';
            nextEl = nextEl.nextElementSibling;
        }
        remediation = content.trim();
    }

    // 3. LLM에 보낼 프롬프트 생성 (기존과 동일)
    const prompt = `
다음 보안 취약점 보고서 내용을 바탕으로, 개발자가 쉽게 이해하고 조치할 수 있도록 간결한 수정 가이드를 작성해 줘.

**취약점:** ${title}

**설명:** ${description}
- **영향:** ${impact}

**기존 해결 방안:**
${remediation}
    `.trim();
    
    // ======================= [핵심 수정 부분] =======================

    // [디버깅] 생성된 프롬프트를 gpt_recommendation 필드에 저장합니다.
    rec.gpt_recommendation = prompt;

    // [디버깅] GPT API를 호출하는 대신, 생성된 프롬프트 내용을 팝업에 바로 표시합니다.
    App.popup.showGptRecommendation(recordId);

    /*
    // [디버깅] 실제 API 호출 부분은 잠시 주석 처리합니다.
    try {
      const csrf = (document.querySelector('#queryForm input[name="csrfmiddlewaretoken"]') || {}).value
                || (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || "";

      const response = await fetch(API_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf
        },
        body: JSON.stringify({ prompt: prompt })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || '서버에서 응답을 받지 못했습니다.');
      }
      
      const data = await response.json();
      
      rec.gpt_recommendation = data.recommendation;
      App.popup.showGptRecommendation(recordId);

    } catch (error) {
      console.error('GPT 추천 생성 실패:', error);
      rec.gpt_recommendation = `오류가 발생했습니다: ${error.message}`;
      App.popup.showGptRecommendation(recordId);
      setTimeout(() => { rec.gpt_recommendation = PLACEHOLDER_TEXT; }, 2000);
    }
    */
    // =============================================================
  }

  // 함수를 App 객체에 공개
  App.gpt.getGptRecommendation = getGptRecommendation;

})(window);
