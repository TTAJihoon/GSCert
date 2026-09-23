document.addEventListener('DOMContentLoaded', () => {
  const resultsContent = document.getElementById('resultsContent');
  if (!resultsContent) return;

  function applyCollapsedState(card, collapsed) {
    card.classList.toggle('is-collapsed', collapsed);
    const button = card.querySelector('.product-collapse-btn');
    if (!button) return;
    const label = collapsed ? '항목 펼치기' : '항목 접기';
    button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
    const icon = button.querySelector('i');
    if (icon) {
      icon.className = `fas ${collapsed ? 'fa-chevron-down' : 'fa-chevron-up'}`;
    }
  }

  resultsContent.addEventListener('click', event => {
    const button = event.target.closest('.product-collapse-btn');
    if (!button) return;
    const card = button.closest('.similar-product');
    if (!card) return;
    applyCollapsedState(card, !card.classList.contains('is-collapsed'));
  });
});
