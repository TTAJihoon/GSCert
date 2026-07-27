document.addEventListener('DOMContentLoaded', () => {
  const resultsContent = document.getElementById('resultsContent');
  const btnDate = document.getElementById('sortByDateBtn');
  const btnSimilarity = document.getElementById('sortBySimilarityBtn');
  let dateDescending = true;
  let similarityDescending = true;

  function parseCertificationDate(productElement) {
    const labels = productElement.querySelectorAll('.product-tags > p');
    for (const label of labels) {
      if (label.textContent.trim() !== '인증일자') continue;
      const value = label.nextElementSibling?.textContent?.trim();
      if (!value) return new Date(0);
      return new Date(value.replace(/\./g, '-'));
    }
    return new Date(0);
  }

  function parseSimilarity(productElement) {
    const text = productElement.querySelector('.similarity-score')?.textContent || '';
    const match = text.match(/([\d.]+)%/);
    return match ? parseFloat(match[1]) : 0;
  }

  function sortProducts(compareFn) {
    const products = Array.from(resultsContent.querySelectorAll('.similar-product'));
    products.sort(compareFn);
    products.forEach(product => resultsContent.appendChild(product));
  }

  function setActiveButton(activeButton, descending) {
    for (const button of [btnDate, btnSimilarity]) {
      const icon = button.querySelector('.sort-direction');
      const isActive = button === activeButton;
      button.classList.toggle('active', isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      icon.className = `fas ${isActive ? (descending ? 'fa-sort-down' : 'fa-sort-up') : 'fa-sort'} sort-direction`;
    }
  }

  btnDate.addEventListener('click', () => {
    const descending = dateDescending;
    sortProducts((a, b) => {
      const dateA = parseCertificationDate(a);
      const dateB = parseCertificationDate(b);
      return descending ? dateB - dateA : dateA - dateB;
    });
    setActiveButton(btnDate, descending);
    dateDescending = !dateDescending;
  });

  btnSimilarity.addEventListener('click', () => {
    const descending = similarityDescending;
    sortProducts((a, b) => {
      const similarityA = parseSimilarity(a);
      const similarityB = parseSimilarity(b);
      return descending
        ? similarityB - similarityA
        : similarityA - similarityB;
    });
    setActiveButton(btnSimilarity, descending);
    similarityDescending = !similarityDescending;
  });
});
