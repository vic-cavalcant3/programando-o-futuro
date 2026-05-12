function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebarOverlay').classList.add('open');
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