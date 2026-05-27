fetch('../partials/footer.html')
.then(r => r.text())
.then(html => {
  document.getElementById('footer-placeholder').innerHTML = html;
});

function abrirSuporte(e) {
  if (e) e.preventDefault();
  document.getElementById('suporteOverlay').classList.add('open');
}
function fecharSuporte(e) {
  if (e && e.target !== document.getElementById('suporteOverlay')) return;
  document.getElementById('suporteOverlay').classList.remove('open');
  document.getElementById('suporteMsg').textContent = '';
  document.getElementById('suporteMsg').className = 'suporte-msg font-manrope';
}
async function enviarSuporte() {
  const nome = document.getElementById('suporteNome').value.trim();
  const email = document.getElementById('suporteEmail').value.trim();
  const mensagem = document.getElementById('suporteMensagem').value.trim();
  const msg = document.getElementById('suporteMsg');
  if (!nome || !email || !mensagem) {
    msg.textContent = 'Preencha todos os campos.';
    msg.className = 'suporte-msg font-manrope erro';
    return;
  }
  // Abre cliente de e-mail como fallback (sem backend de email configurado)
  const assunto = encodeURIComponent('Suporte - Programando o Futuro');
  const corpo = encodeURIComponent(`Nome: ${nome}\nE-mail: ${email}\n\n${mensagem}`);
  window.location.href = `mailto:contato@programandoofuturo.com.br?subject=${assunto}&body=${corpo}`;
  msg.textContent = 'Abrindo seu cliente de e-mail...';
  msg.className = 'suporte-msg font-manrope ok';
}
function compartilhar(e) {
  e.preventDefault();
  const url = window.location.origin;
  if (navigator.share) {
    navigator.share({ title: 'Programando o Futuro', text: 'Descubra sua área ideal com orientação vocacional por IA!', url });
  } else {
    navigator.clipboard.writeText(url).then(() => {
      alert('Link copiado para a área de transferência!');
    });
  }
}