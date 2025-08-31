document.addEventListener('DOMContentLoaded', function() {
  // ── 탭 전환
  const tabs = document.querySelectorAll('.main-tab');
  const contents = document.querySelectorAll('.tab-content');

  tabs.forEach(tab => {
    tab.addEventListener('click', function() {
      const targetTab = this.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      contents.forEach(c => c.classList.remove('active'));

      this.classList.add('active');
      if (targetTab === 'preInput') {
        document.getElementById('preInputContent').classList.add('active');
      } else if (targetTab === 'resultSheet') {
        document.getElementById('resultSheetContent').classList.add('active');
      }
    });
  });

  // ── ① 클라우드 환경 구성(옵션1): O/X에 따라 세부영역 표시
  const cloudRadios = document.querySelectorAll('input[name="cloud_config"]');
  const cloudEnvironmentSection = document.getElementById('cloudEnvironmentSection');

  function updateCloudVisibility() {
    const isYes = document.getElementById('cloud_yes').checked;
    cloudEnvironmentSection.classList.toggle('hidden-section', !isYes);
  }
  cloudRadios.forEach(r => r.addEventListener('change', updateCloudVisibility));
  updateCloudVisibility(); // 초기 상태 반영

  // ── ③ 보안성 시험 면제 여부(옵션3): O일 때만 세부영역 표시
  const securityRadios = document.querySelectorAll('input[name="security_exempt"]');
  const securityDetailsSection = document.getElementById('securityDetailsSection');

  function updateSecurityVisibility() {
    const isYes = document.getElementById('security_yes').checked;
    securityDetailsSection.classList.toggle('hidden-section', !isYes);
  }
  securityRadios.forEach(r => r.addEventListener('change', updateSecurityVisibility));
  updateSecurityVisibility(); // 초기 상태 반영

  // ── ② SaaS형 제품(옵션4): O일 때만 ④ 재인증 구분(옵션2) 표시
  const saasRadios = document.querySelectorAll('input[name="saas_enabled"]');
  const reapprovalSection = document.getElementById('reapprovalSection');

  function updateSaaSVisibility() {
    const isYes = document.getElementById('saas_yes').checked;
    reapprovalSection.classList.toggle('hidden-section', !isYes);
  }
  saasRadios.forEach(r => r.addEventListener('change', updateSaaSVisibility));
  updateSaaSVisibility(); // 초기 상태 반영
});
