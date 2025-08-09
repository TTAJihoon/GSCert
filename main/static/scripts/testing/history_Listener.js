// Null_check
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('queryForm');

    form.addEventListener('submit', function(e) {
        const gsnum = document.getElementById('gsnum').value.trim();
        const project = document.getElementById('project').value.trim();
        const company = document.getElementById('company').value.trim();
        const product = document.getElementById('product').value.trim();
        const comment = document.getElementById('comment').value.trim();

        if (!gsnum && !project && !company && !product && !comment) {
            e.preventDefault();
            alert('검색 조건을 입력해주세요');
            return false;
        }
    });
});
