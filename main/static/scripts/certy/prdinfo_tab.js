document.addEventListener('DOMContentLoaded', function() {
  const tabs = document.querySelectorAll('.main-tab');
  const contents = document.querySelectorAll('.tab-content');

  tabs.forEach(tab => {
    tab.addEventListener('click', function() {
      const targetTab = this.getAttribute('data-tab');
      
      // 모든 탭에서 active 클래스 제거
      tabs.forEach(t => t.classList.remove('active'));
      contents.forEach(c => c.classList.remove('active'));
      
      // 클릭된 탭과 해당 콘텐츠에 active 클래스 추가
      this.classList.add('active');
      if (targetTab === 'preInput') {
        document.getElementById('preInputContent').classList.add('active');
      } else if (targetTab === 'resultSheet') {
        document.getElementById('resultSheetContent').classList.add('active');
      }
    });
  });

  // 클라우드 환경 구성 라디오 버튼 이벤트
  const cloudRadios = document.querySelectorAll('input[name="cloud_config"]');
  const cloudEnvironmentSection = document.getElementById('cloudEnvironmentSection');

  cloudRadios.forEach(radio => {
    radio.addEventListener('change', function() {
      if (this.value === 'yes') {
        cloudEnvironmentSection.classList.remove('hidden-section');
      } else {
        cloudEnvironmentSection.classList.add('hidden-section');
      }
    });
  });
});
