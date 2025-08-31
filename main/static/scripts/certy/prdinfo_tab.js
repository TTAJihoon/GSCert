document.addEventListener('DOMContentLoaded', function () {
  const tabs = document.querySelectorAll('.main-tab');
  const pre = document.getElementById('preInputContent');
  const res = document.getElementById('resultSheetContent');

  // ▶ Luckysheet 강제 재계산(가장 안전한 방식: rAF 두 번 + window.resize)
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

  // ▶ 탭 전환
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
        // ✅ 숨김 해제 직후 Luckysheet 폭 재계산
        refreshLuckysheet();
      }
    });
  });

  // ▶ 결과 시트 컨테이너 크기 변화 감지(사이드바 접힘/창 크기 변경 등)
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
  updateCloudVisibility(); // 초기 상태 반영

  // 보안성 시험 면제 여부: O일 때만 세부영역 표시
  const securityRadios = document.querySelectorAll('input[name="security_config"]');
  const securitySection = document.getElementById('securitySection');

  function updateSecurityVisibility() {
    const isYes = document.getElementById('security_yes').checked;
    securitySection.classList.toggle('hidden-section', !isYes);
  }
  securityRadios.forEach(r => r.addEventListener('change', updateSecurityVisibility));
  updateSecurityVisibility(); // 초기 상태 반영
});
