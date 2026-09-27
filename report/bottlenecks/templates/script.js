(() => {
  const input = document.getElementById('candidate-filter');
  const kindSelect = document.getElementById('candidate-kind-filter');
  const count = document.getElementById('candidate-count');
  const rows = Array.from(document.querySelectorAll('[data-candidate-row]'));
  const applyFilter = () => {
    const query = input.value.trim().toLocaleLowerCase();
    const kind = kindSelect.value;
    let visible = 0;
    rows.forEach((row) => {
      const kindMatches = kind === 'all' || row.dataset.kind === kind;
      const searchText = row.dataset.search || row.textContent;
      const textMatches = searchText.toLocaleLowerCase().includes(query);
      const matches = kindMatches && textMatches;
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    count.textContent = `${visible} / ${rows.length} candidates`;
  };
  input.addEventListener('input', applyFilter);
  kindSelect.addEventListener('change', applyFilter);
  applyFilter();
})();
