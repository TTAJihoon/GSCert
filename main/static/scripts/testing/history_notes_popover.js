// '특이사항' 열의 재인증/재계약 버튼: hover 시 툴팁 표시, 클릭하면 고정(pinned),
// 다른 곳을 클릭하면 고정 해제. 하나의 delegated 클릭 핸들러로 두 동작을 모두 처리한다.
document.addEventListener('click', function (event) {
    // 고정된 팝업 안쪽(텍스트 드래그/선택 등) 클릭은 고정 상태를 건드리지 않는다.
    if (event.target.closest('.notes-popover')) {
        return;
    }

    const clickedBtn = event.target.closest('.notes-btn[data-has-tooltip="true"]');

    document.querySelectorAll('.notes-btn.pinned').forEach(function (btn) {
        if (btn !== clickedBtn) {
            btn.classList.remove('pinned');
        }
    });

    if (clickedBtn) {
        clickedBtn.classList.toggle('pinned');
    }
});
