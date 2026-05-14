// ============================================================
// js/api.js — Central de comunicação com o back-end
// Programando o Futuro
// ============================================================

const API_URL = 'https://programando-o-futuro.onrender.com';

// ── Token helpers ──────────────────────────────────────────
const auth = {
  getToken:  ()      => localStorage.getItem('pf_token'),
  setToken:  (t)     => localStorage.setItem('pf_token', t),
  getUser:   ()      => JSON.parse(localStorage.getItem('pf_user') || 'null'),
  setUser:   (u)     => localStorage.setItem('pf_user', JSON.stringify(u)),
  clear:     ()      => { localStorage.removeItem('pf_token'); localStorage.removeItem('pf_user'); },
  isLogged:  ()      => !!localStorage.getItem('pf_token'),
};

// ── Fetch base ─────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const { skipAuthRedirect = false, ...fetchOptions } = options;
  const token = auth.getToken();
  const headers = { 'Content-Type': 'application/json', ...(fetchOptions.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...fetchOptions, headers });

  const data = await res.json();

  if (res.status === 401 && !path.startsWith('/api/auth/') && !skipAuthRedirect) {
    auth.clear();
    window.location.href = determinarLoginPath();
    return;
  }

  if (!res.ok) throw { status: res.status, ...data };
  return data;
}

function determinarLoginPath() {
  // Descobre se está em /pages/ ou na raiz
  return homePath();
}

function pagePath(pageName) {
  return window.location.pathname.includes('/pages/') ? pageName : `pages/${pageName}`;
}

function homePath() {
  return window.location.pathname.includes('/pages/') ? '../index.html' : 'index.html';
}

function destinoUsuario(usuario = auth.getUser()) {
  return usuario?.teste_inicial_concluido
    ? pagePath('inicial_mapa_feito.html')
    : pagePath('inicial_logada.html');
}

async function redirecionarUsuarioLogado({ silencioso = false } = {}) {
  if (!auth.isLogged()) return false;

  try {
    const usuario = await authApi.me({ skipAuthRedirect: true });
    auth.setUser(usuario);
    window.location.href = destinoUsuario(usuario);
    return true;
  } catch (error) {
    auth.clear();
    if (!silencioso) window.location.href = determinarLoginPath();
    return false;
  }
}

async function protegerPagina({ precisaMapaFeito = null } = {}) {
  if (!auth.isLogged()) {
    window.location.href = homePath();
    return false;
  }

  try {
    const usuario = await authApi.me({ skipAuthRedirect: true });
    auth.setUser(usuario);

    if (precisaMapaFeito === true && !usuario.teste_inicial_concluido) {
      window.location.href = pagePath('inicial_logada.html');
      return false;
    }

    if (precisaMapaFeito === false && usuario.teste_inicial_concluido) {
      window.location.href = pagePath('inicial_mapa_feito.html');
      return false;
    }

    return usuario;
  } catch (error) {
    auth.clear();
    window.location.href = homePath();
    return false;
  }
}

// ── API methods ────────────────────────────────────────────
const api = {
  get:    (path)        => apiFetch(path),
  post:   (path, body)  => apiFetch(path, { method: 'POST',  body: JSON.stringify(body) }),
  patch:  (path, body)  => apiFetch(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path)        => apiFetch(path, { method: 'DELETE' }),
};

// ── Auth calls ─────────────────────────────────────────────
const authApi = {
  async cadastro(nome, email, senha) {
    const data = await api.post('/api/auth/cadastro', {
      nome, email, senha,
      aceite_lgpd: true,
      aceite_menor: false
    });
    auth.setToken(data.token);
    auth.setUser(data.usuario);
    return data;
  },

  async login(email, senha) {
    const data = await api.post('/api/auth/login', { email, senha });
    auth.setToken(data.token);
    auth.setUser(data.usuario);
    return data;
  },

  me(options = {}) {
    return apiFetch('/api/auth/me', { skipAuthRedirect: options.skipAuthRedirect });
  },

  atualizarPerfil: (dados) => api.patch('/api/auth/perfil', dados),

  logout() {
    auth.clear();
    window.location.href = determinarLoginPath();
  }
};

// ── Teste inicial ──────────────────────────────────────────
const testeApi = {
  perguntas:  ()             => api.get('/api/testeinicial/perguntas'),
  progresso:  ()             => api.get('/api/testeinicial/progresso'),
  respostasDestaque: (limite = 3, aleatorio = true) =>
  api.get(`/api/testeinicial/respostas/destaque?limite=${limite}&aleatorio=${aleatorio}`),
  salvarResposta: (perguntaId, valor, textoLivre = '') =>
    api.patch('/api/testeinicial/resposta', { perguntaId: String(perguntaId), valor, textoLivre }),
  finalizar: (respostas)     => api.post('/api/testeinicial/finalizar', { respostas }),
  status:    (jobId)         => api.get(`/api/resultado/status?jobId=${jobId}`),
  resultado: ()              => api.get('/api/resultado'),
};

// ── Módulos ────────────────────────────────────────────────
const modulosApi = {
  listar:         ()              => api.get('/api/modulos'),
  perguntas:      (id)            => api.get(`/api/modulos/${id}/perguntas`),
  progresso:      (id)            => api.get(`/api/modulos/${id}/progresso`),
  salvarResposta: (id, perguntaId, valor, textoLivre = '') =>
    api.patch(`/api/modulos/${id}/resposta`, { perguntaId: String(perguntaId), valor, textoLivre }),
  finalizar:      (id)            => api.post(`/api/modulos/${id}/finalizar`, {}),
};

// ── Perfil / Mapa / Jornada ────────────────────────────────
const perfilApi = {
  get:            ()  => api.get('/api/perfil'),
  mapa:           ()  => api.get('/api/mapa'),
  jornadaProgresso: () => api.get('/api/jornada/progresso'),
};

// ── UI helpers ─────────────────────────────────────────────
function showErro(msg, containerId = 'erroMsg') {
  let el = document.getElementById(containerId);
  if (!el) {
    el = document.createElement('div');
    el.id = containerId;
    el.className = 'auth-alert';
    el.setAttribute('role', 'alert');

    const authCard = document.querySelector('.auth-card');
    if (authCard) {
      authCard.prepend(el);
    } else {
      document.querySelector('.question-wrap, main')?.appendChild(el);
    }
  }
  el.textContent = msg;
  el.style.display = 'block';
}

function hideErro(containerId = 'erroMsg') {
  const el = document.getElementById(containerId);
  if (el) el.style.display = 'none';
}

function setLoading(btnEl, loading, textoOriginal) {
  if (loading) {
    btnEl.disabled = true;
    btnEl.style.opacity = '0.6';
    btnEl.textContent = 'Aguarde...';
  } else {
    btnEl.disabled = false;
    btnEl.style.opacity = '1';
    btnEl.innerHTML = textoOriginal;
  }
}

// ── Guard: redireciona se não logado ──────────────────────
function requireAuth() {
  return protegerPagina();
}
