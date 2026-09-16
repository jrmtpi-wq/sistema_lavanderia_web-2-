/* Relat?rio independente: conte?do vis?vel antes de imprimir. */
function imprimirMaquinaEmProcesso(){
  if(!currentMaqId){toast('Selecione uma m?quina antes de imprimir.','error');return;}
  window.location.assign('/imprimir/maquinas/'+encodeURIComponent(currentMaqId));
}
