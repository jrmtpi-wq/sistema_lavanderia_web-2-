(() => {
  const menuButton = document.getElementById('mobile-menu-button');
  menuButton.onclick = event => {
    // Mouse hover already opens the menu before the click arrives.
    if (event.pointerType === 'mouse' && document.querySelector('.sidebar.open')) return;
    toggleMobileMenu();
  };
  menuButton.addEventListener('pointerenter', event => {
    if (event.pointerType === 'mouse' && !document.querySelector('.sidebar.open')) {
      toggleMobileMenu();
    }
  });
  function fold(selector, title) {
    const card = document.querySelector(selector);
    if (!card) return;
    const details = document.createElement('details');
    details.className = 'layout-tools';
    const summary = document.createElement('summary');
    summary.textContent = title;
    details.append(summary);
    card.before(details);
    details.append(card);
  }
  fold('#page-passadoria > .card:first-child', 'Calculadora de capacidade da passadoria');
  fold('#page-passadoriarobo > .card:first-child', 'Calculadora de capacidade dos robôs');
  fold('#laser-tab-fila > .card:first-child', 'Adicionar e programar itens na fila de laser');
  // Preserve form nodes and their handlers when opening and closing tool sections.
  document.querySelectorAll('.panel-head button').forEach(button => {
    if (button.querySelector('.fa-times') && !button.textContent.trim()) {
      button.textContent = '×';
      button.setAttribute('aria-label', 'Fechar janela');
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.querySelector('.sidebar.open')) {
      toggleMobileMenu();
      document.getElementById('mobile-menu-button').focus();
    }
  });
})();
