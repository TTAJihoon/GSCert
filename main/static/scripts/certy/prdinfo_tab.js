document.addEventListener('DOMContentLoaded', function () {
  const tabs = document.querySelectorAll('.main-tab');
  const pre = document.getElementById('preInputContent');
  const res = document.getElementById('resultSheetContent');

  function refreshLuckysheet() {
    if (!window.luckysheet) return;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        try {
          if (typeof luckysheet.resize === 'function') luckysheet.resize();
        } catch (e) { /* no-op */ }
        window.dispatchEvent(new Event('resize'));
      });
    });
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', function () {
      const targetTab = this.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      this.classList.add('active');
      if (targetTab === 'preInput') {
        pre.classList.add('active');
      } else if (targetTab === 'resultSheet') {
        res.classList.add('active');
        refreshLuckysheet();
      }
    });
  });

  if ('ResizeObserver' in window && res) {
    const ro = new ResizeObserver(() => {
      if (res.classList.contains('active')) refreshLuckysheet();
    });
    ro.observe(res);
  }

  // 클라우드 환경 구성: O/X에 따라 세부영역 표시
  const cloudRadios = document.querySelectorAll('input[name="cloud_config"]');
  const cloudEnvironmentSection = document.getElementById('cloudEnvironmentSection');
  function updateCloudVisibility() {
    const isYes = document.getElementById('cloud_yes').checked;
    cloudEnvironmentSection.classList.toggle('hidden-section', !isYes);
  }
  cloudRadios.forEach(r => r.addEventListener('change', updateCloudVisibility));
  updateCloudVisibility();

  const reCertSelect = document.getElementById('reCertType');
  const reCertLookupSection = document.getElementById('reCertLookupSection');
  const reCertResultSection = document.getElementById('reCertResultSection');
  const reCertResultText = document.getElementById('reCertResultText');
  const btnLookupCert = document.getElementById('btnLookupCert');
  const reCertNumberInput = document.getElementById('reCertNumberInput');

  // 재인증 구분 드롭다운 변경 시 조회 영역 표시/숨김 처리
  function updateReCertVisibility() {
    const isApplicable = reCertSelect.value !== '해당사항 없음';
    reCertLookupSection.classList.toggle('hidden-section', !isApplicable);
    // 선택이 바뀌면 결과 영역은 항상 숨김 처리
    reCertResultSection.classList.add('hidden-section');
    reCertResultText.value = ''; // 결과 내용 초기화
  }
  reCertSelect.addEventListener('change', updateReCertVisibility);
  updateReCertVisibility(); // 초기 상태 반영

  // '조회' 버튼 클릭 이벤트
  btnLookupCert.addEventListener('click', function() {
    const certNo = reCertNumberInput.value.trim();
    if (!certNo) {
      alert('기존 인증 제품 번호를 입력하세요.');
      return;
    }

    // 로딩 중임을 표시 (예: 버튼 텍스트 변경)
    btnLookupCert.textContent = '조회 중...';
    btnLookupCert.disabled = true;
    reCertResultSection.classList.add('hidden-section');

    // 백엔드 API 호출 (URL은 urls.py에 설정된 경로와 일치해야 함)
    fetch(`/lookup_cert_info/?cert_no=${encodeURIComponent(certNo)}`)
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(result => {
        if (result.success) {
          const data = result.data;
          // 성공적으로 데이터를 받아오면 textarea에 형식에 맞춰 텍스트 작성
          reCertResultText.value =
            `- 기 인증번호: ${data.cert_id}\n` +
            `- 기 인증 제품명 및 버전: ${data.product_name}\n` +
            `- 기 인증 제품 WD: ${data.total_wd}`;
          reCertResultSection.classList.remove('hidden-section');
        } else {
          // 서버에서 '못 찾음' 등의 메시지를 보냈을 경우
          alert(result.message || '데이터를 조회하지 못했습니다.');
        }
      })
      .catch(error => {
        // 네트워크 오류 등 fetch 자체의 실패
        console.error('Fetch Error:', error);
        alert('데이터 조회 중 오류가 발생했습니다. 콘솔을 확인해주세요.');
      })
      .finally(() => {
        // 성공/실패 여부와 관계없이 버튼 상태를 원상 복구
        btnLookupCert.textContent = '조회';
        btnLookupCert.disabled = false;
      });
  });

  // 보안성 시험 면제 여부: O일 때만 세부영역 표시
  const securityRadios = document.querySelectorAll('input[name="security_config"]');
  const securitySection1 = document.getElementById('securitySection1');
  const securitySection2 = document.getElementById('securitySection2');
  const securitySection3 = document.getElementById('securitySection3');
  function updateSecurityVisibility() {
    const isYes = document.getElementById('security_yes').checked;
    securitySection1.classList.toggle('hidden-section', !isYes);
    securitySection2.classList.toggle('hidden-section', !isYes);
    securitySection3.classList.toggle('hidden-section', !isYes);
  }
  securityRadios.forEach(r => r.addEventListener('change', updateSecurityVisibility));
  updateSecurityVisibility();
});
