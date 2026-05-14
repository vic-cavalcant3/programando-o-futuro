function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebarOverlay').classList.add('open');
    const usuario = auth.getUser();
    if (usuario) {
      const sidebarAvatar = document.getElementById('sidebarAvatar');
      const sidebarNome   = document.getElementById('sidebarNome');
      const sidebarEmail  = document.getElementById('sidebarEmail');
      if (sidebarAvatar) sidebarAvatar.textContent = usuario.avatar_iniciais || '??';
      if (sidebarNome)   sidebarNome.textContent   = usuario.nome || '';
      if (sidebarEmail)  sidebarEmail.textContent  = usuario.email || '';
    }
  }
  function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('open');
  }
  
  fetch('../partials/sidebar.html')
  .then(r => r.text())
  .then(html => {
    document.body.insertAdjacentHTML('beforeend', html);
  });