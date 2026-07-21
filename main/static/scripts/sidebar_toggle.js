// 좌측 검색/입력 영역 접기·펴기 공용 스크립트.
// 버튼에 data-sidebar-toggle="<CSS 선택자>" 를 지정하면, 클릭 시 해당 요소에
// 'sidebar-collapsed' 클래스를 토글한다(페이지별 CSS가 그 클래스로 레이아웃 처리).
// 상태는 페이지 경로별로 localStorage 에 저장되어 다음 방문 시에도 유지된다.
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-sidebar-toggle]').forEach(function (btn) {
        const target = document.querySelector(btn.getAttribute('data-sidebar-toggle'));
        if (!target) return;

        const storageKey = 'sidebarCollapsed:' + location.pathname;

        let initiallyCollapsed = false;
        try {
            initiallyCollapsed = localStorage.getItem(storageKey) === '1';
        } catch (error) {
            initiallyCollapsed = false;
        }
        if (initiallyCollapsed) {
            target.classList.add('sidebar-collapsed');
        }

        btn.addEventListener('click', function () {
            const isCollapsed = target.classList.toggle('sidebar-collapsed');
            try {
                localStorage.setItem(storageKey, isCollapsed ? '1' : '0');
            } catch (error) {
                // localStorage 를 쓸 수 없는 환경에서도 토글 자체는 계속 동작한다.
            }
        });
    });
});
