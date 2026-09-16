/* Shared confirmation for machine scheduling and operator mode. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'conclusao-dialog';
  dialog.setAttribute('aria-labelledby', 'conclusao-titulo');
  document.body.append(dialog);
  let saving = false;
  let afterClose = null;
  dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  dialog.addEventListener('close', () => { if (afterClose) afterClose(); });

  async function confirmAction(carga, action, refresh) {
    if (dialog.open || saving) return;
    afterClose = refresh;
    const complete = action === 'concluir';
    const operator = document.getElementById('operator-name').value.trim();
    dialog.innerHTML = `<form><h2 id="conclusao-titulo">${complete ? 'Concluir' : 'Iniciar'} carga ${carga.numero}</h2>
      <p>OP ${opEscape(carga.op || 'não informada')} · ${opEscape(carga.referencia)}</p>
      <p class="operation-note">A data e a hora reais serão registradas automaticamente ao confirmar (horário de Brasília).</p>
      <label class="gestao-field">Operador<input id="conclusao-operador" required maxlength="80" value="${opEscape(operator)}" autocomplete="name"></label>
      ${complete ? `<div class="gestao-grid"><label class="gestao-field">Quilos realizados<input id="conclusao-peso" type="number" min="0.001" max="1000000" step="0.001" required value="${Number(carga.peso) > 0 ? Number(carga.peso) : ''}"></label>
      <label class="gestao-field">Peças realizadas<input id="conclusao-pecas" type="number" min="1" max="10000000" step="1" required value="${Number(carga.pecas) > 0 ? Number(carga.pecas) : ''}"></label></div>
      <p class="operation-note">Confira as quantidades realizadas. Os valores acima foram preenchidos com a programação.</p>
      ${carga.status === 'aguardando' ? '<p class="operation-note">Esta carga não tem início registrado. A confirmação registra somente a conclusão, sem criar um horário de início.</p>' : ''}` : ''}
      <p id="conclusao-erro" role="alert"></p><div class="gestao-actions"><button class="btn btn-primary" type="submit">${complete ? 'Confirmar conclusão' : 'Confirmar início'}</button><button class="btn btn-ghost" type="button" id="conclusao-cancelar">Cancelar</button></div></form>`;
    dialog.querySelector('#conclusao-cancelar').onclick = () => dialog.close();
    dialog.querySelector('form').onsubmit = async event => {
      event.preventDefault();
      if (saving) return;
      const operador = dialog.querySelector('#conclusao-operador').value.trim();
      if (!operador) { dialog.querySelector('#conclusao-erro').textContent = 'Informe o operador.'; return; }
      const payload = {acao: action, operador, revisao: carga.revisao};
      if (complete) {
        payload.peso = dialog.querySelector('#conclusao-peso').value;
        payload.pecas = dialog.querySelector('#conclusao-pecas').value;
      }
      saving = true;
      dialog.querySelectorAll('button').forEach(b => b.disabled = true);
      try {
        await operationFetch(`/api/operacao/cargas/${carga.id}/apontar`, payload);
        document.getElementById('operator-name').value = operador;
        toast(complete ? 'Conclusão registrada com quilos e peças.' : 'Início registrado.', 'success');
        dialog.close();
      } catch (error) {
        dialog.querySelector('#conclusao-erro').textContent = error.message;
      } finally {
        saving = false;
        dialog.querySelectorAll('button').forEach(b => b.disabled = false);
      }
    };
    dialog.showModal();
  }

  const originalPatch = patchCarga;
  patchCarga = async function(id, field, value) {
    if (field !== 'status') return originalPatch(id, field, value);
    try {
      const data = await operationFetch(`/api/operacao/maquinas/${currentMaqId}`);
      const carga = data.cargas.find(c => c.id === id);
      if (!carga) throw new Error('Carga não encontrada. Atualize a máquina.');
      await loadCargas(); // Restore the saved status while confirmation is pending.
      if (carga.status === value) return;
      if (carga.status === 'concluido' || value === 'aguardando' || carga.status === 'pausado') {
        toast('Use o modo operador para acompanhar a carga. Conclusões registradas não podem ser reabertas pela programação.', 'info');
        return;
      }
      await confirmAction(carga, value === 'concluido' ? 'concluir' : 'iniciar', () => loadCargas());
    } catch (error) { toast(error.message, 'error'); }
  };

  const originalSave = saveOperatorAction;
  saveOperatorAction = async function(button) {
    if (button.dataset.action !== 'concluir') return originalSave(button);
    try {
      const data = await operationFetch(`/api/operacao/maquinas/${document.getElementById('operator-machine').value}`);
      const carga = data.cargas.find(c => c.id === Number(button.dataset.id));
      if (!carga) throw new Error('Carga não encontrada. Atualize a fila.');
      await confirmAction(carga, 'concluir', () => loadOperator());
    } catch (error) { document.getElementById('operator-feedback').textContent = error.message; }
  };
})();
