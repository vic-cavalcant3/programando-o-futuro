(function () {
  const path = window.location.pathname;
  const moduloMatch = path.match(/modulo(\d+)\.html$/);
  const isTesteInicial = path.endsWith('/perguntas.html') || path.endsWith('\\perguntas.html');
  const moduloId = moduloMatch ? String(moduloMatch[1]).padStart(2, '0') : null;
  const storageKey = isTesteInicial ? 'pf_respostas_teste_api' : `pf_modulo_${moduloId}_api`;

  let perguntas = [];
  let currentQ = 1;
  let respostas = {};
  let enviando = false;

  const params = new URLSearchParams(window.location.search);
  const qParam = parseInt(params.get('q'), 10);

  function perguntaAtual() {
    return perguntas[currentQ - 1];
  }

  function normalizarResposta(raw) {
    if (typeof raw === 'object' && raw !== null) return raw;
    return { valor: raw || '', textoLivre: '' };
  }

  function respostaDaPergunta(q) {
    return normalizarResposta(respostas[q.id]);
  }

  function salvarLocal() {
    localStorage.setItem(storageKey, JSON.stringify(respostas));
  }

  function carregarLocal() {
    try {
      respostas = JSON.parse(localStorage.getItem(storageKey) || '{}');
    } catch (_) {
      respostas = {};
    }
  }

  function aplicarEstilosExtras() {
    if (document.getElementById('questionarioApiStyles')) return;
    const style = document.createElement('style');
    style.id = 'questionarioApiStyles';
    style.textContent = `
      .text-answer {
        width: 100%;
        min-height: 52px;
        background: rgba(17,24,39,0.8);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        color: #f0f6ff;
        font-family: 'Manrope', sans-serif;
        font-size: 0.92rem;
        outline: none;
        resize: vertical;
      }
      .text-answer:focus {
        border-color: rgba(37,99,235,0.55);
        background: rgba(37,99,235,0.07);
      }
      .free-label {
        display: block;
        color: rgba(255,255,255,0.45);
        font-family: 'Manrope', sans-serif;
        font-size: 0.78rem;
        line-height: 1.5;
        margin: 0.2rem 0 0.55rem;
      }
      .question-error {
        display: none;
        background: rgba(220,38,38,0.12);
        border: 1px solid rgba(220,38,38,0.28);
        border-radius: 12px;
        color: #fca5a5;
        font-family: 'Manrope', sans-serif;
        font-size: 0.82rem;
        padding: 0.75rem 1rem;
        margin-bottom: 1rem;
        text-align: center;
      }
    `;
    document.head.appendChild(style);
  }

  function mostrarErro(msg) {
    let el = document.getElementById('questionError');
    if (!el) {
      el = document.createElement('div');
      el.id = 'questionError';
      el.className = 'question-error';
      document.getElementById('questionCard')?.prepend(el);
    }
    el.textContent = msg;
    el.style.display = 'block';
  }

  function esconderErro() {
    const el = document.getElementById('questionError');
    if (el) el.style.display = 'none';
  }

  function respostaPreenchida(q) {
    const resposta = respostaDaPergunta(q);
    if (q.tipo === 'texto' || q.tipo === 'numero' || q.tipo === 'texto_livre' || !q.opcoes) {
      return String(resposta.valor || '').trim().length > 0 || q.obrigatorio === false;
    }
    return String(resposta.valor || '').trim().length > 0;
  }

  function renderPergunta(goingBack = false) {
    if (!perguntas.length) return;

    const q = perguntaAtual();
    const card = document.getElementById('questionCard');
    const btnVoltar = document.getElementById('btnVoltar');
    const list = document.getElementById('optionsList');

    esconderErro();
    card.className = 'question-card' + (goingBack ? ' going-back' : '');
    document.getElementById('questionNum').textContent = `Pergunta ${String(currentQ).padStart(2, '0')}`;
    document.getElementById('questionText').textContent = q.texto;
    document.getElementById('navCurrent').textContent = currentQ;
    document.getElementById('navTotal').textContent = perguntas.length;
    document.getElementById('progressBar').style.width = `${(currentQ / perguntas.length) * 100}%`;
    btnVoltar.disabled = currentQ === 1;
    list.innerHTML = '';

    const resposta = respostaDaPergunta(q);

    if (q.opcoes && q.opcoes.length) {
      q.opcoes.forEach((op) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'option-btn font-manrope' + (resposta.valor === op.letra ? ' selected' : '');
        btn.innerHTML = `<div class="option-letter font-jakarta">${op.letra}</div><span>${op.texto}</span>`;
        btn.onclick = () => selecionarResposta(q, op.letra);
        list.appendChild(btn);
      });

      if (q.textoLivre) {
        const label = document.createElement('label');
        label.className = 'free-label';
        label.textContent = q.textoLivre;
        const textarea = document.createElement('textarea');
        textarea.className = 'text-answer';
        textarea.rows = 3;
        textarea.placeholder = 'Opcional';
        textarea.value = resposta.textoLivre || '';
        textarea.addEventListener('input', () => {
          respostas[q.id] = { ...respostaDaPergunta(q), textoLivre: textarea.value };
          salvarLocal();
        });
        list.appendChild(label);
        list.appendChild(textarea);
      }
    } else {
      const input = document.createElement(q.tipo === 'texto_livre' ? 'textarea' : 'input');
      input.className = 'text-answer';
      input.placeholder = q.placeholder || 'Digite sua resposta';
      if (q.tipo === 'numero') input.type = 'number';
      if (q.tipo === 'texto_livre') input.rows = 5;
      input.value = resposta.valor || '';
      input.addEventListener('input', () => {
        respostas[q.id] = { valor: input.value, textoLivre: '' };
        salvarLocal();
        atualizarBtnProximo();
      });
      list.appendChild(input);
      setTimeout(() => input.focus(), 50);
    }

    atualizarBtnProximo();
    history.replaceState(null, '', `?q=${currentQ}`);
  }

  async function selecionarResposta(q, valor) {
    respostas[q.id] = { ...respostaDaPergunta(q), valor };
    salvarLocal();
    renderPergunta();
    // Salva no servidor em background — não trava a UI
    salvarResposta(q).catch(() => {});
  }

  async function salvarResposta(q) {
    const resposta = respostaDaPergunta(q);
    if (isTesteInicial) {
      return testeApi.salvarResposta(q.id, resposta.valor, resposta.textoLivre || '');
    }
    return modulosApi.salvarResposta(moduloId, q.id, resposta.valor, resposta.textoLivre || '');
  }

  async function salvarTodas() {
    for (const q of perguntas) {
      if (respostaPreenchida(q)) await salvarResposta(q);
    }
  }

  function atualizarBtnProximo() {
    const q = perguntaAtual();
    const btn = document.getElementById('btnProximo');
    const isLast = currentQ === perguntas.length;
    const enabled = q && respostaPreenchida(q);

    btn.className = 'btn-proximo font-jakarta' + (enabled ? ' enabled' : '');
    btn.innerHTML = isLast
      ? `Finalizar <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>`
      : `Próxima <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
    btn.onclick = isLast ? finalizar : proximaPergunta;
  }

  function proximaPergunta() {
    const q = perguntaAtual();
    if (!respostaPreenchida(q)) return;
    if (currentQ >= perguntas.length) {
      finalizar();
      return;
    }
    currentQ++;
    renderPergunta(false);
  }

  function voltarPergunta() {
    if (currentQ <= 1) return;
    currentQ--;
    renderPergunta(true);
  }

  async function finalizar() {
    if (enviando) return;
    const faltando = perguntas.find((q) => !respostaPreenchida(q));
    if (faltando) {
      currentQ = perguntas.indexOf(faltando) + 1;
      renderPergunta();
      mostrarErro('Responda esta pergunta para continuar.');
      return;
    }

    enviando = true;
    const btn = document.getElementById('btnProximo');
    btn.textContent = 'Enviando...';
    btn.disabled = true;

    try {
      // Salva todas em paralelo — muito mais rápido que sequencial
      await Promise.allSettled(
        perguntas.filter(q => respostaPreenchida(q)).map(q => salvarResposta(q))
      );

      if (isTesteInicial) {
        const payload = perguntas.map((q) => ({
          perguntaId: String(q.id),
          valor: respostaDaPergunta(q).valor,
          textoLivre: respostaDaPergunta(q).textoLivre || ''
        }));
        const data = await testeApi.finalizar(payload);
        localStorage.setItem('pf_job_id', data.jobId);
        localStorage.removeItem(storageKey);
        window.location.href = 'resultado.html';
        return;
      }

      const data = await modulosApi.finalizar(moduloId);
      localStorage.removeItem(storageKey);
      if (data.jobId) localStorage.setItem('pf_job_id', data.jobId);
      window.location.href = data.jobId ? 'resultado.html' : 'minha_jornada.html';
    } catch (error) {
      mostrarErro(error?.detail?.erro || error?.erro || error?.detail || 'Não foi possível enviar suas respostas.');
      btn.disabled = false;
      enviando = false;
      atualizarBtnProximo();
    }
  }

  function sair() {
    salvarLocal();
    window.location.href = isTesteInicial ? 'inicial_logada.html' : 'minha_jornada.html';
  }

  async function carregarPerguntas() {
    aplicarEstilosExtras();
    carregarLocal();

    const protegido = await protegerPagina({
      precisaMapaFeito: isTesteInicial ? false : null
    });
    if (!protegido) return;

    try {
      const data = isTesteInicial
        ? await testeApi.perguntas()
        : await modulosApi.perguntas(moduloId);
      perguntas = data.perguntas || [];
      currentQ = qParam && qParam >= 1 && qParam <= perguntas.length ? qParam : 1;
      renderPergunta();
    } catch (error) {
      if (!isTesteInicial && error?.status === 403) {
        mostrarErro(error?.detail?.erro || 'Responda todas as perguntas iniciais para liberar os módulos.');
        setTimeout(() => {
          window.location.href = 'inicial_logada.html';
        }, 1800);
        return;
      }
      mostrarErro(error?.detail?.erro || error?.erro || error?.detail || 'Não foi possível carregar as perguntas.');
    }
  }

  window.proximaPergunta = proximaPergunta;
  window.voltarPergunta = voltarPergunta;
  window.finalizarTeste = finalizar;
  window.finalizarModulo = finalizar;
  window.sair = sair;

  carregarPerguntas();
})();