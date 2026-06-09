// Null_check
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('queryForm');
    const clearButton = document.getElementById('clearSearchBtn');

    if (clearButton) {
        clearButton.addEventListener('click', function() {
            form.querySelectorAll('input').forEach(function(input) {
                const inputType = (input.getAttribute('type') || 'text').toLowerCase();
                if (inputType === 'hidden' || input.name === 'csrfmiddlewaretoken') {
                    return;
                }
                input.value = '';
            });
            if (typeof setYearsAgo === 'function') {
                setYearsAgo(10);
            }
            const firstInput = document.getElementById('gsnum');
            if (firstInput) firstInput.focus();
        });
    }

    form.addEventListener('submit', function(e) {
        const gsnum = document.getElementById('gsnum').value.trim();
        const project = document.getElementById('project').value.trim();
        const company = document.getElementById('company').value.trim();
        const product = document.getElementById('product').value.trim();
        const swType = document.getElementById('sw_type').value.trim();
        const tester = document.getElementById('tester').value.trim();
        const comment = document.getElementById('comment').value.trim();

        if (!gsnum && !project && !company && !product && !swType && !tester && !comment) {
            e.preventDefault();
            alert('검색 조건을 입력해주세요');
            return false;
        }
    });
});
