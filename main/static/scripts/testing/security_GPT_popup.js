(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  AppNS.gpt = AppNS.gpt || {};

  let modal, backdrop, shell, host, closeBtn;

  function escHandler(e) { if (e.key === "Escape") closeModal(); }

  /**
   * 모달 컴포넌트를 찾고, Shadow DOM 문제를 해결하기 위해 필요 시 초기화합니다.
   */
  function ensureModal() {
    if (!modal) modal = document.getElementById("modal");
    if (modal) {
      backdrop = modal.querySelector(".modal-backdrop");
      shell = modal.querySelector(".modal-shell");
      
      // --- Shadow DOM 충돌 해결 로직 ---
      let contentHost = modal.querySelector("#modalContent");
      if (contentHost && contentHost.shadowRoot) {
        // Invicti 팝업이 사용했던 Shadow DOM이 남아있으면, 해당 div를 새로 만들어서 교체합니다.
        console.log("Shadow DOM detected. Re-creating modal content area.");
        const newHost = document.createElement('div');
        newHost.id = 'modalContent';
        newHost.className = 'h-full overflow-auto p-3'; // 기존 클래스 유지
        contentHost.parentNode.replaceChild(newHost, contentHost);
        host = newHost;
      } else {
        host = contentHost;
      }
      // --- 로직 종료 ---

      closeBtn = modal.querySelector("#closeModal");
    }

    if (!modal || !backdrop || !shell || !host || !closeBtn) {
      console.error("Modal components could not be initialized.");
      return false;
    }

    if (!modal._gptHandlersBound) {
      closeBtn.addEventListener("click", closeModal);
      backdrop.addEventListener("click", closeModal);
      modal._gptHandlersBound = true;
    }
    return true;
  }

  function openModal() {
    if (!modal) return;
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
    document.addEventListener("keydown", escHandler);
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    if (host) host.innerHTML = "";
    document.removeEventListener("keydown", escHandler);
  }

  /**
   * 팝업의 컨텐츠를 안전하게 표시하는 함수
   * @param {string} content - 표시할 HTML 콘텐츠
   */
  function displayContent(content) {
    if (!host) {
      console.error("Modal host element is not available to display content.");
      return;
    }
    host.innerHTML = content;
  }

  /**
   * GPT API를 호출하고 결과를 캐싱하며 팝업에 표시하는 비동기 함수
   * @param {string} rowId - 테이블 행의 고유 ID
   */
  async function getGptRecommendation(rowId) {
    if (!ensureModal()) return;

    const state = (window.SecurityApp && window.SecurityApp.state) || {};
    const row = (state.currentData || []).find(r => r.id === rowId);

    if (!row) {
      displayContent(`<div class="p-4 text-red-700 bg-red-100 border border-red-400 rounded-md"><strong>오류:</strong> 해당 행의 데이터를 찾을 수 없습니다.</div>`);
      openModal();
      return;
    }

    // 1. 캐시된 응답이 있으면 즉시 표시
    if (row.gpt_response) {
      const cachedContent = `
        <div class="p-3">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안 (저장된 답변)</h3>
          <pre class="whitespace-pre-wrap bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed font-sans">${row.gpt_response}</pre>
        </div>
      `;
      displayContent(cachedContent);
      openModal();
      return;
    }
    
    // 2. 캐시가 없을 경우: 프롬프트 유효성 검사
    if (!row.gpt_prompt) {
      displayContent(`<div class="p-4 text-red-700 bg-red-100 border border-red-400 rounded-md"><strong>오류:</strong> GPT에게 보낼 프롬프트 데이터가 없습니다.</div>`);
      openModal();
      return;
    }

    // 3. 로딩 상태 표시
    const loadingContent = `
      <div class="text-center py-12">
        <div class="inline-flex items-center px-4 py-2 font-semibold leading-6 text-sm shadow rounded-md text-gray-600 bg-white">
          <i class="fas fa-spinner fa-spin mr-3 text-sky-500"></i>
          GPT 추천 수정 방안을 생성중...
        </div>
      </div>
    `;
    displayContent(loadingContent);
    openModal();
    
    // 4. 백엔드 API 호출
    try {
      const response = await fetch('/security/gpt/recommend/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: row.gpt_prompt }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `서버에서 오류가 발생했습니다: ${response.status}`);
      }
      
      // 5. 성공 시, 응답을 캐싱하고 <pre> 태그를 사용해 안전하게 표시
      row.gpt_response = result.response; 

      const successContent = `
        <div class="p-3">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안</h3>
          <pre class="whitespace-pre-wrap bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed font-sans">
          다음 Invicti 취약점 데이터에 기반한 구체적인 해결 방안입니다. 대상은 "오래된 버전 (톰캣) 치명적"으로 표시된 Tomcat 9.0.x 시리즈입니다. 권고 버전은 데이터에 따라 9.0.107(해당 브랜치의 최신) 또는 11.0.9(전체 최신)이며, 가능하면 최신 브랜치로 업그레이드하는 것이 가장 확실한 해결책입니다.

요약
- 원인: 오래된 Tomcat 버전(예: 9.0.90)에서 치명적 취약점 표기.  
- 즉시 조치: 취약 버전 사용 중지 및 방어적 제어(네트워크 격리/웹 방패) 적용, 가능하면 업그레이드.  
- 근본 해결: Tomcat을 9.0.107 이상 또는 11.0.9 이상으로 업그레이드.  
- 추가 보안 강화: 불필요한 엔드포인트 비활성화, TLS 강화, 서버 헤더 제거/은폐, WAF 규칙 적용.

1) 즉시 조치 및 방어적 대책
- 취약 엔진 차단:
  - WAF/방화벽에서 /mariner5/inv(…) 와 같은 의심 URI에 대한 요청 차단
  - 내부망에 있는 경우도 외부에서의 무분별한 접근 차단
- 노출 최소화:
  - Tomcat 관리 인터페이스(Manager, Host Manager) 접근 제한: 필요한 경우에만 특정 IP에서만 접근 허용
  - TLS만 허용하고, 비암호화 HTTP 차단
- 서버 헤더 최소화:
  - 서버 식별 노출 최소화

2) 권고 버전 및 업그레이드 계획
- 목표 버전: 9.0.107 이상(동 브랜치의 최신) 또는 가능하면 11.0.9 이상
- 업그레이드 순서
  - 먼저 테스트 환경에서 호환성 확인 → 운영환경으로 확장 적용
  - 자바 버전(JDK) 호환성 확인: Tomcat 9.x는 Java 8 이상 권장, Java 11/17 LTS 권장
  - 데이터/설정 백업: 웹앱, 컨텍스트 설정, 데이터베이스 연결 설정, 인증서, 로그 디렉터리 백업
  - 롤백 계획 수립: 업그레이드 실패 시 이전 버전으로 복구 가능한 절차 확보

3) 구체적 업그레이드 절차(권장 방식)
- 운영 체제에 따라 패키지 관리자로 업데이트하거나, 수동으로 새 버전 배포 가능

- 패키지 관리자로 업그레이드(가능한 경우)
  - Debian/Ubuntu
    sudo apt-get update
    sudo apt-get install tomcat9
  - Red Hat/CentOS
    sudo yum update tomcat*

- 수동 설치(권장: 9.0.107 이상으로 수동 교체)
  - Tomcat 공식 사이트에서 tarball 다운로드
  - 체크섬 검증 후 추출
  - 기존 Tomcat 디렉토리 교체 및 서비스 설정 업데이트
  - JAVA_HOME 및 CATALINA_HOME 설정 확인
  - 운영 서비스 재시작

- 예시 명령(수동 업그레이드 흐름)
  - tarball 다운로드 및 압축 해제
  - 서비스 중지 및 파일 교체
  - 새 디렉토리로 심볼릭 링크 재설정
  - 시스템 서비스 파일 업데이트 및 Tomcat 재시작

참고 및 주의
- 현재 데이터 상으로는 9.0.90이 확인되며, 최신 버전은 9.0.107(해당 브랜치) 또는 11.0.9가 제시되어 있습니다. 가능하다면 9.0.107 이상으로 업그레이드하고, 운영 환경에서의 호환성 테스트를 충분히 진행하십시오.
- 만약 업그레이드가 어려운 상황이면, 우선 WAF 차단 및 네트워크 접근 제어를 통해 노출을 최소화하고, 차후 업그레이드 시점에 재적용하는 전략을 권장합니다.

필요하면 현재 환경에 맞춘 구체적인 업그레이드 명령어/서비스 파일 수정 예시를 환경(배포 방식, OS)별로 자세히 맞춰 드리겠습니다. 어떤 운영체제와 배포 방식으로 Tomcat을 운용 중인지 알려주시면 그에 맞춰 단계별 명령어를 제공하겠습니다.
          </pre>
        </div>
      `;
      displayContent(successContent);

    } catch (error) {
      // 6. 실패 시, 에러 메시지 표시
      console.error('GPT 요청 실패:', error);
      const errorContent = `
        <div class="p-4 text-red-800 bg-red-50 border border-red-300 rounded-md">
          <strong class="font-bold">⚠️ 요청 실패</strong>
          <p class="mt-1 text-sm">${error.message}</p>
        </div>
      `;
      displayContent(errorContent);
    }
  }

  AppNS.gpt.getGptRecommendation = getGptRecommendation;

})(window, document);
