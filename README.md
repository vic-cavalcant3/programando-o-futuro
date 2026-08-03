# 🎯 Programando o Futuro

Plataforma web que usa a **API do Claude (Anthropic)** para ajudar estudantes a descobrirem caminhos de carreira de forma personalizada. Através de um questionário inteligente, o sistema gera um **mapa visual de carreira** com cursos, áreas recomendadas, instituições de ensino e os próximos passos sugeridos.

Projeto desenvolvido em equipe como trabalho de faculdade.

## ✨ Funcionalidades

- Questionário interativo para mapear interesses e perfil do estudante
- Geração de recomendações personalizadas via integração com a API do Claude (Anthropic)
- Mapa visual com caminhos de carreira, cursos e instituições recomendadas
- Backend com API própria para processar respostas e armazenar progresso

## 🛠️ Tecnologias utilizadas

**Backend**
- Python
- FastAPI
- MySQL

**Frontend**
- HTML5
- CSS3
- JavaScript

**Infraestrutura**
- Deploy na [Render](https://render.com)
- Integração com API do Claude (Anthropic)

## 📁 Estrutura do projeto

```
programando-o-futuro/
├── backend/
│   ├── main.py            # Ponto de entrada da API (FastAPI)
│   ├── requirements.txt   # Dependências Python
│   ├── data.json          # Dados de apoio do questionário
│   └── utils/
│       └── teste_carga.py # Script de teste de carga da API
├── js/
│   ├── api.js              # Comunicação com o backend
│   ├── questionario-api.js # Lógica do questionário
│   ├── sidebar.js
│   └── footer.js
├── pages/                  # Páginas do frontend
├── partials/                # Componentes reutilizáveis de HTML
├── styles/                  # Estilos do projeto
└── index.html
```

## 🚀 Como rodar o projeto localmente

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

Basta abrir o arquivo `index.html` em um navegador ou servir a pasta raiz com um servidor local (ex: extensão Live Server do VS Code).

> ⚠️ É necessário configurar as variáveis de ambiente com a chave da API do Claude (Anthropic) e as credenciais do banco de dados MySQL antes de rodar o backend.

## 👥 Equipe

Projeto desenvolvido em equipe por:

- [Victor Cavalcante](https://github.com/vic-cavalcant3)
- [Mateus Alcantara](https://github.com/MateusAlcantara13)
- Yago Dias dos Santos
- [Ricardo Ongari Rodrigues](https://github.com/RicardoOngari)
- [Lucas Gomes](https://github.com/lucasgsilva102-oss)

## 📌 Status

✅ Projeto finalizado

## 📄 Licença

Este projeto foi desenvolvido para fins acadêmicos.
