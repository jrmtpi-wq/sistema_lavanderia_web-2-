function validarHora24(value){
  const texto=String(value||'').trim();
  const match=/^(\d{1,2}):(\d{2})$/.exec(texto);
  if(!match)return null;
  const hora=Number(match[1]), minuto=Number(match[2]);
  if(hora<0||hora>23||minuto<0||minuto>59)return null;
  return `${String(hora).padStart(2,'0')}:${String(minuto).padStart(2,'0')}`;
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.chrona-time').forEach(input=>{
    input.addEventListener('blur',()=>{
      const normalized=validarHora24(input.value);
      input.setCustomValidity(normalized?'':'Use o formato HH:MM, entre 00:00 e 23:59.');
      if(normalized)input.value=normalized;
    });
  });
});
