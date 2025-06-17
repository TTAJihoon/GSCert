function toggleInputs() {
  const historyRadio = document.querySelector('input[name="selectType"][value="history"]');
  const companyInput = document.getElementById('company');
  const productInput = document.getElementById('product');
  const commentInput = document.getElementById('comment');

  if (historyRadio.checked) {
    commentInput.disabled = true;
    companyInput.disabled = false;
    productInput.disabled = false;
  } else {
    commentInput.disabled = false;
    companyInput.disabled = true;
    productInput.disabled = true;
  }
}

window.addEventListener('DOMContentLoaded', toggleInputs);

const radios = document.querySelectorAll('input[name="selectType"]');
radios.forEach(radio => radio.addEventListener('change', toggleInputs));
