const form = document.querySelector('.filtros');
const imprimir = document.getElementById('imprimir');
const tipo = document.getElementById('tipo');
function maquinaVisivel() {
  const label = document.getElementById('filtro-maquina');
  label.hidden = tipo.value !== 'producao';
  label.querySelector('select').disabled = label.hidden;
  const conclusao = document.getElementById('filtro-conclusao');
  conclusao.hidden = tipo.value !== 'producao';
  conclusao.querySelector('select').disabled = conclusao.hidden;
  document.getElementById('busca-label').textContent = tipo.value === 'producao'
    ? 'Buscar OP ou referência' : 'Buscar OP, referência, cliente ou responsável';
}
maquinaVisivel();
form.addEventListener('input', () => {
  imprimir.disabled = true;
  document.getElementById('alterado').hidden = false;
  maquinaVisivel();
});
form.addEventListener('submit', event => {
  const inicio = form.elements.inicio;
  const fim = form.elements.fim;
  fim.setCustomValidity(inicio.value > fim.value ? 'O fim deve ser igual ou posterior ao início.' : '');
  if (!form.reportValidity()) event.preventDefault();
});
form.elements.fim.addEventListener('input', () => form.elements.fim.setCustomValidity(''));
form.elements.inicio.addEventListener('input', () => form.elements.fim.setCustomValidity(''));
imprimir.addEventListener('click', () => window.print());

// Calendar rendered in the page, including in browsers without a native date picker.
document.querySelectorAll('.abrir-calendario').forEach(trigger => {
  const input = document.getElementById(trigger.dataset.campo);
  const panel = document.getElementById(trigger.getAttribute('aria-controls'));
  let month;
  const iso = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  function close(focus = false) {
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (focus) trigger.focus();
  }
  function button(text, label, action) {
    const element = document.createElement('button');
    element.type = 'button';
    element.textContent = text;
    element.setAttribute('aria-label', label);
    element.addEventListener('click', action);
    return element;
  }
  function select(date) {
    input.value = iso(date);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    close(true);
  }
  function render() {
    panel.replaceChildren();
    const nav = document.createElement('div');
    nav.className = 'calendario-nav';
    const title = document.createElement('strong');
    title.setAttribute('aria-live', 'polite');
    title.textContent = month.toLocaleDateString('pt-BR', {month: 'long', year: 'numeric'});
    function move(delta, label) {
      month.setMonth(month.getMonth() + delta);
      render();
      panel.querySelector(`[aria-label="${label}"]`).focus();
    }
    nav.append(button('‹', 'Mês anterior', () => move(-1, 'Mês anterior')), title,
      button('›', 'Próximo mês', () => move(1, 'Próximo mês')));
    const grid = document.createElement('div');
    grid.className = 'calendario-dias';
    ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].forEach(day => {
      const label = document.createElement('span');
      label.textContent = day;
      grid.append(label);
    });
    for (let n = 0; n < month.getDay(); n++) grid.append(document.createElement('span'));
    const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    for (let day = 1; day <= count; day++) {
      const date = new Date(month.getFullYear(), month.getMonth(), day);
      const cell = button(String(day), date.toLocaleDateString('pt-BR'), () => select(date));
      cell.dataset.date = iso(date);
      cell.setAttribute('aria-pressed', String(input.value === iso(date)));
      grid.append(cell);
    }
    const actions = document.createElement('div');
    actions.className = 'calendario-acoes';
    actions.append(button('Hoje', 'Selecionar hoje', () => select(new Date())), button('Fechar', 'Fechar calendário', () => close(true)));
    panel.append(nav, grid, actions);
  }
  trigger.addEventListener('click', () => {
    if (!panel.hidden) return close();
    document.querySelectorAll('.abrir-calendario[aria-expanded="true"]').forEach(other => other.click());
    const date = input.value ? new Date(`${input.value}T12:00:00`) : new Date();
    month = new Date(date.getFullYear(), date.getMonth(), 1);
    render();
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    (panel.querySelector('[aria-pressed="true"]') || panel.querySelector('[data-date]')).focus();
  });
  document.addEventListener('click', event => {
    if (!event.composedPath().includes(trigger.closest('.campo-data'))) close();
  });
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(true); }
  });
});
