fetch('../partials/footer.html')
  .then(r => r.text())
  .then(html => {
    const placeholder = document.getElementById('footer-placeholder');
    if (!placeholder) return;
    placeholder.innerHTML = html;
    // Reexecuta scripts injetados via innerHTML
    placeholder.querySelectorAll('script').forEach(s => {
      const script = document.createElement('script');
      script.textContent = s.textContent;
      document.body.appendChild(script);
    });
  });