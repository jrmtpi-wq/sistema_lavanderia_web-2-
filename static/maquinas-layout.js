// Keep the production queue visible; configuration is available on demand.
(() => {
  const panel = document.getElementById('maq-panel');
  const header = panel.querySelector('.panel-head');
  const content = panel.querySelector('.panel-sticky-top > div:last-child');
  const scroll = panel.querySelector('.panel-scroll-body');
  const settings = document.createElement('details');
  settings.id = 'maq-programacao';
  const summary = document.createElement('summary');
  summary.textContent = 'Programar cargas e calcular por OP';
  settings.append(summary);
  const fields = document.createElement('div');
  fields.className = 'maq-programacao-campos';
  content.querySelectorAll(':scope > .card').forEach(card => fields.append(card));
  settings.append(fields);
  const tools = document.createElement('div');
  tools.className = 'maq-acoes';
  const print = fields.querySelector('[onclick="imprimirMaquinaEmProcesso()"]');
  print.innerHTML = '<i class="fas fa-print" aria-hidden="true"></i> Imprimir cargas';
  print.title = 'Imprimir cargas em processo e aguardando';
  const close = header.querySelector('button');
  close.setAttribute('aria-label', 'Fechar máquina');
  close.textContent = '×';
  tools.append(print, close);
  header.append(tools);
  const columns = content.querySelector('.maq-cols-head');
  scroll.prepend(columns);
  content.append(settings);
  panel.classList.add('maq-layout-compacto', 'fullscreen');
  const originalOpen = openMaqPanel;
  openMaqPanel = async function(...args) {
    settings.open = false;
    await originalOpen(...args);
    scroll.scrollTop = 0;
    scroll.scrollLeft = 0;
  };
})();
