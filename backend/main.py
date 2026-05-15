from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio, httpx, os, logging, jwt, uuid, json, re, random, ssl
import aiomysql

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
JWT_SECRET        = os.getenv("JWT_SECRET", "dev-secret-troque-em-producao-2026")
JWT_EXPIRES_H     = int(os.getenv("JWT_EXPIRES_H", "24"))

if ANTHROPIC_API_KEY:
    logger.info(f"✅ Chave: {ANTHROPIC_API_KEY[:12]}...{ANTHROPIC_API_KEY[-4:]}")
else:
    logger.error("❌ ANTHROPIC_API_KEY não encontrada!")

app = FastAPI(title="Programando o Futuro API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
@app.on_event("startup")
async def startup():
    await init_db()
security = HTTPBearer()


db_pool = None

# ── BANCO DE DADOS ───────────────────────────────────────────────────────────
async def init_db():
    global db_pool
    ssl_ctx = ssl.create_default_context(
        cafile=os.path.join(os.path.dirname(__file__), "ca.pem")
    )
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    db_pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST", ""),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        db=os.getenv("DB_NAME", "defaultdb"),
        ssl=ssl_ctx,
        autocommit=True,
        minsize=1,
        maxsize=10,
    )
    await criar_tabelas()
    logger.info("✅ Banco de dados conectado!")

async def criar_tabelas():
    sql_statements = [
        """CREATE TABLE IF NOT EXISTS usuarios (
            id VARCHAR(36) PRIMARY KEY,
            nome VARCHAR(120) NOT NULL,
            email VARCHAR(120) NOT NULL UNIQUE,
            senha VARCHAR(255) NOT NULL,
            avatar_iniciais VARCHAR(10),
            aceite_lgpd BOOLEAN DEFAULT TRUE,
            aceite_menor BOOLEAN DEFAULT FALSE,
            teste_inicial_concluido BOOLEAN DEFAULT FALSE,
            modulos_concluidos JSON DEFAULT ('[]'),
            cidade VARCHAR(100),
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS respostas_teste (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id VARCHAR(36) NOT NULL,
            pergunta_id VARCHAR(20) NOT NULL,
            valor TEXT,
            texto_livre TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_usuario_pergunta (usuario_id, pergunta_id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE IF NOT EXISTS respostas_modulo (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id VARCHAR(36) NOT NULL,
            modulo_id VARCHAR(10) NOT NULL,
            pergunta_id VARCHAR(30) NOT NULL,
            valor TEXT,
            texto_livre TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_usuario_modulo_pergunta (usuario_id, modulo_id, pergunta_id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE IF NOT EXISTS perfis (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id VARCHAR(36) NOT NULL UNIQUE,
            dados JSON NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""",
        """CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR(36) PRIMARY KEY,
            usuario_id VARCHAR(36) NOT NULL,
            status ENUM('processando','concluido','erro') DEFAULT 'processando',
            erro TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )"""
    ]
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            for sql in sql_statements:
                await cur.execute(sql)
    logger.info("✅ Tabelas verificadas/criadas!")


# ── Modelos Pydantic ───────────────────────────────────────────────────────────
class CadastroBody(BaseModel):
    nome: str
    email: str
    senha: str
    aceite_lgpd: bool
    aceite_menor: bool

class LoginBody(BaseModel):
    email: str
    senha: str

class RespostaBody(BaseModel):
    perguntaId: str
    valor: str
    textoLivre: Optional[str] = None  # campo aberto opcional

class FinalizarTesteBody(BaseModel):
    respostas: list[dict]

class RespostaModuloBody(BaseModel):
    perguntaId: str
    valor: str
    textoLivre: Optional[str] = None

class ContextoLivreBody(BaseModel):
    chave: str
    texto: str

# ── Perguntas do Teste Inicial (completo) ──────────────────────────────────────
PERGUNTAS_TESTE = [
    # BLOCO 1 — Quem você é
    {"id":"1","bloco":"Quem você é","texto":"Qual é o seu nome completo?","tipo":"texto","placeholder":"Digite seu nome completo","obrigatorio":True},
    {"id":"2","bloco":"Quem você é","texto":"Quantos anos você tem?","tipo":"numero","placeholder":"Ex: 17","obrigatorio":True},
    {"id":"3","bloco":"Quem você é","texto":"Em qual cidade e estado você mora?","tipo":"texto","placeholder":"Ex: São Paulo - SP","obrigatorio":True},
    {"id":"4","bloco":"Quem você é","texto":"Você está no ensino médio ou já concluiu?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Estou no 1º ano"},
        {"letra":"B","texto":"Estou no 2º ano"},
        {"letra":"C","texto":"Estou no 3º ano"},
        {"letra":"D","texto":"Já terminei o ensino médio"},
        {"letra":"E","texto":"Não terminei o ensino médio"},
    ],"textoLivre":"Quer adicionar algo sobre sua situação escolar?"},
    {"id":"5","bloco":"Quem você é","texto":"Sua escola é pública ou privada?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Pública"},
        {"letra":"B","texto":"Privada / particular"},
        {"letra":"C","texto":"Bolsista em escola privada"},
    ]},
    {"id":"6","bloco":"Quem você é","texto":"Você já fez o ENEM?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Sim, já fiz e tenho minhas notas"},
        {"letra":"B","texto":"Sim, mas não lembro exatamente as notas"},
        {"letra":"C","texto":"Ainda não fiz, vou fazer esse ano"},
        {"letra":"D","texto":"Ainda não fiz e não sei quando vou fazer"},
    ],"textoLivre":"Se tiver suas notas, pode colocar aqui (ex: Linguagens 650, Matemática 600...)"},

    # BLOCO 2 — Situação financeira real
    {"id":"7","bloco":"Sua situação financeira","texto":"Qual é a renda mensal aproximada da sua família?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Até R$ 1.412 (1 salário mínimo)"},
        {"letra":"B","texto":"Entre R$ 1.412 e R$ 3.000"},
        {"letra":"C","texto":"Entre R$ 3.000 e R$ 6.000"},
        {"letra":"D","texto":"Acima de R$ 6.000"},
        {"letra":"E","texto":"Prefiro não informar"},
    ],"textoLivre":"Quer descrever melhor sua situação? (ex: minha mãe trabalha sozinha, moramos de aluguel...)"},
    {"id":"8","bloco":"Sua situação financeira","texto":"Você precisa trabalhar enquanto estuda?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Sim, preciso trabalhar para me sustentar"},
        {"letra":"B","texto":"Sim, ajudo em casa mas não dependo só de mim"},
        {"letra":"C","texto":"Talvez, se não conseguir bolsa ou financiamento"},
        {"letra":"D","texto":"Não, minha família consegue me manter enquanto estudo"},
    ]},
    {"id":"9","bloco":"Sua situação financeira","texto":"Você teria como pagar alguma mensalidade de faculdade?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Não, preciso de curso gratuito ou bolsa integral"},
        {"letra":"B","texto":"Talvez, com financiamento (FIES) ou bolsa parcial"},
        {"letra":"C","texto":"Sim, consigo pagar mensalidade com esforço"},
        {"letra":"D","texto":"Sim, sem problemas"},
    ]},
    {"id":"10","bloco":"Sua situação financeira","texto":"Você tem acesso a computador e internet em casa?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Só tenho celular com internet limitada"},
        {"letra":"B","texto":"Tenho celular e acesso a computador às vezes"},
        {"letra":"C","texto":"Tenho computador com internet razoável"},
        {"letra":"D","texto":"Tenho boa estrutura tecnológica em casa"},
    ]},

    # BLOCO 3 — Onde você quer chegar
    {"id":"11","bloco":"Onde você quer chegar","texto":"Você pode se deslocar para estudar em outra cidade?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Não, preciso estudar na minha cidade"},
        {"letra":"B","texto":"Sim, cidades próximas (até 1h de distância)"},
        {"letra":"C","texto":"Sim, qualquer cidade do meu estado"},
        {"letra":"D","texto":"Sim, posso me mudar para qualquer lugar"},
    ]},
    {"id":"12","bloco":"Onde você quer chegar","texto":"Em quanto tempo você quer estar trabalhando na sua área?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"O mais rápido possível — em até 1 ano"},
        {"letra":"B","texto":"Entre 1 e 2 anos (curso técnico ou tecnólogo)"},
        {"letra":"C","texto":"Entre 3 e 5 anos (graduação)"},
        {"letra":"D","texto":"Mais de 5 anos (graduação + pós)"},
    ]},
    {"id":"13","bloco":"Onde você quer chegar","texto":"O que mais te importa na sua futura carreira?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Ganhar bem — quero estabilidade financeira"},
        {"letra":"B","texto":"Fazer algo que eu ame, mesmo que ganhe menos"},
        {"letra":"C","texto":"Ter liberdade e flexibilidade no trabalho"},
        {"letra":"D","texto":"Ajudar pessoas e causar impacto social"},
        {"letra":"E","texto":"Crescer e ser reconhecido profissionalmente"},
    ],"textoLivre":"Tem algo mais específico que você quer da sua carreira?"},
    {"id":"14","bloco":"Onde você quer chegar","texto":"Você já tem alguma ideia de curso ou área?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Sim, já tenho um curso definido na cabeça"},
        {"letra":"B","texto":"Tenho algumas opções mas estou indeciso"},
        {"letra":"C","texto":"Tenho uma área geral mas não sei o curso"},
        {"letra":"D","texto":"Não faço ideia ainda"},
    ],"textoLivre":"Se tiver, qual curso ou área você está pensando?"},

    # BLOCO 4 — Quem você é por dentro
    {"id":"15","bloco":"Quem você é por dentro","texto":"O que você mais gosta de fazer no seu tempo livre?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Mexer com tecnologia, programar, criar coisas no computador"},
        {"letra":"B","texto":"Ler, escrever, pesquisar sobre assuntos que me interessam"},
        {"letra":"C","texto":"Estar com pessoas, organizar eventos, conversar"},
        {"letra":"D","texto":"Desenhar, criar, fazer coisas com as mãos"},
        {"letra":"E","texto":"Praticar esportes ou atividades ao ar livre"},
    ],"textoLivre":"Tem algo que você ama fazer que não está nas opções?"},
    {"id":"16","bloco":"Quem você é por dentro","texto":"Quando você precisa resolver um problema difícil, como age?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Analiso tudo com calma antes de agir"},
        {"letra":"B","texto":"Peço ajuda para alguém de confiança"},
        {"letra":"C","texto":"Testo soluções na prática até funcionar"},
        {"letra":"D","texto":"Busco informações e pesquiso bastante"},
    ]},
    {"id":"17","bloco":"Quem você é por dentro","texto":"Como você se sente trabalhando em grupo?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Amo — aprendo muito com os outros"},
        {"letra":"B","texto":"Depende do grupo, às vezes sim às vezes não"},
        {"letra":"C","texto":"Prefiro trabalhar sozinho, rendo mais"},
        {"letra":"D","texto":"Gosto de liderar o grupo"},
    ]},
    {"id":"18","bloco":"Quem você é por dentro","texto":"Qual dessas frases mais combina com você?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Sou curioso — adoro aprender coisas novas"},
        {"letra":"B","texto":"Sou prático — prefiro fazer do que ficar teorizando"},
        {"letra":"C","texto":"Sou criativo — penso fora da caixa"},
        {"letra":"D","texto":"Sou organizado — gosto de planejar e executar"},
        {"letra":"E","texto":"Sou empático — me importo muito com as pessoas"},
    ]},

    # BLOCO 5 — Contexto de vida
    {"id":"19","bloco":"Seu contexto de vida","texto":"Você tem alguma experiência de trabalho?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Nunca trabalhei"},
        {"letra":"B","texto":"Já fiz bicos ou trabalhos informais"},
        {"letra":"C","texto":"Fui ou sou Jovem Aprendiz"},
        {"letra":"D","texto":"Já fiz estágio"},
        {"letra":"E","texto":"Já trabalhei com carteira assinada"},
    ],"textoLivre":"Conta um pouco dessa experiência se quiser (o que fazia, o que aprendeu...)"},
    {"id":"20","bloco":"Seu contexto de vida","texto":"Tem alguém na sua família ou círculo próximo que trabalha numa área que você admira?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Sim, e isso me influencia na minha escolha"},
        {"letra":"B","texto":"Sim, mas quero seguir um caminho diferente"},
        {"letra":"C","texto":"Não, serei o primeiro da família nessa área"},
        {"letra":"D","texto":"Não pensei nisso ainda"},
    ],"textoLivre":"Se quiser, conte quem é e o que faz"},
    {"id":"21","bloco":"Seu contexto de vida","texto":"O que mais te preocupa quando pensa no seu futuro profissional?","tipo":"opcoes","opcoes":[
        {"letra":"A","texto":"Não ter dinheiro para estudar"},
        {"letra":"B","texto":"Escolher errado e se arrepender"},
        {"letra":"C","texto":"Não conseguir emprego na área escolhida"},
        {"letra":"D","texto":"Decepcionar minha família"},
        {"letra":"E","texto":"Não me sentir capaz ou inteligente o suficiente"},
    ],"textoLivre":"Quer desabafar algo sobre esse medo? A IA leva isso em consideração na análise"},
    {"id":"22","bloco":"Seu contexto de vida","texto":"Se você pudesse escrever uma carta para o seu eu daqui a 5 anos, o que diria?","tipo":"texto_livre","placeholder":"Escreva à vontade — pode ser algo simples como 'quero estar feliz' ou mais detalhado. Isso ajuda a IA a entender o que realmente importa para você.","obrigatorio":False},
]

PERGUNTAS_MODULOS = {
    "01":{"titulo":"Perfil Pessoal","descricao":"Entendendo seus valores e jeito de ser.","perguntas":[
        {"id":"m01p01","texto":"Quando você precisa tomar uma decisão importante, você confia mais em:","opcoes":[{"letra":"A","texto":"O que o meu coração manda"},{"letra":"B","texto":"Dados, fatos e lógica"},{"letra":"C","texto":"O que pessoas de confiança me dizem"},{"letra":"D","texto":"Meus princípios e valores"}],"textoLivre":"Tem alguma decisão difícil que você enfrenta agora?"},
        {"id":"m01p02","texto":"Sob pressão, você geralmente:","opcoes":[{"letra":"A","texto":"Fica ansioso mas empurra para frente"},{"letra":"B","texto":"Foca e produz mais"},{"letra":"C","texto":"Busca apoio de alguém"},{"letra":"D","texto":"Trava e procrastina"}]},
        {"id":"m01p03","texto":"O que mais te motiva no dia a dia?","opcoes":[{"letra":"A","texto":"Reconhecimento e elogios"},{"letra":"B","texto":"Aprender algo novo"},{"letra":"C","texto":"Ajudar alguém"},{"letra":"D","texto":"Dinheiro e recompensa"},{"letra":"E","texto":"Desafios e metas"}]},
        {"id":"m01p04","texto":"Em um grupo, você costuma ser:","opcoes":[{"letra":"A","texto":"O líder que organiza tudo"},{"letra":"B","texto":"O que resolve os problemas técnicos"},{"letra":"C","texto":"O que une as pessoas"},{"letra":"D","texto":"O que executa e entrega"}]},
        {"id":"m01p05","texto":"Qual desses valores é mais importante para você?","opcoes":[{"letra":"A","texto":"Liberdade"},{"letra":"B","texto":"Segurança"},{"letra":"C","texto":"Impacto — mudar vidas"},{"letra":"D","texto":"Crescimento pessoal"},{"letra":"E","texto":"Família e estabilidade"}],"textoLivre":"Tem outro valor que guia sua vida que não está aqui?"},
        {"id":"m01p06","texto":"Quando você erra, o que você faz?","opcoes":[{"letra":"A","texto":"Me culpo muito e demoro para superar"},{"letra":"B","texto":"Analiso o que deu errado e mudo a rota"},{"letra":"C","texto":"Peço ajuda para resolver"},{"letra":"D","texto":"Sigo em frente rápido sem olhar para trás"}]},
        {"id":"m01p07","texto":"O que te faz sentir mais realizado?","opcoes":[{"letra":"A","texto":"Conquistar uma meta difícil"},{"letra":"B","texto":"Ver o impacto do meu trabalho na vida de alguém"},{"letra":"C","texto":"Resolver um problema complexo"},{"letra":"D","texto":"Criar algo original e único"}]},
        {"id":"m01p08","texto":"Como você prefere trabalhar no dia a dia?","opcoes":[{"letra":"A","texto":"Sozinho, com total autonomia"},{"letra":"B","texto":"Em equipe, colaborando sempre"},{"letra":"C","texto":"Com orientação de alguém mais experiente"},{"letra":"D","texto":"De forma híbrida — depende do momento"}]},
    ]},
    "02":{"titulo":"Interesses e Paixões","descricao":"Descobrindo o que te move de verdade.","perguntas":[
        {"id":"m02p01","texto":"Qual assunto te faz perder a noção do tempo quando pesquisa?","opcoes":[{"letra":"A","texto":"Tecnologia, ciência e inovação"},{"letra":"B","texto":"Arte, cultura, história e filosofia"},{"letra":"C","texto":"Negócios, finanças e empreendedorismo"},{"letra":"D","texto":"Saúde, corpo humano e bem-estar"},{"letra":"E","texto":"Educação, sociedade e política"}],"textoLivre":"Tem algum assunto específico que você ama que não está aqui?"},
        {"id":"m02p02","texto":"Se você pudesse aprender qualquer coisa de graça agora, o que escolheria?","tipo":"texto_livre","placeholder":"Escreva à vontade — pode ser qualquer coisa, do culinária à programação"},
        {"id":"m02p03","texto":"Que tipo de conteúdo você mais consome (YouTube, TikTok, etc.)?","opcoes":[{"letra":"A","texto":"Tecnologia, programação, ciência"},{"letra":"B","texto":"Arte, música, cinema, cultura"},{"letra":"C","texto":"Empreendedorismo, finanças, negócios"},{"letra":"D","texto":"Saúde, esporte, bem-estar"},{"letra":"E","texto":"Humor, entretenimento geral"}],"textoLivre":"Tem algum canal ou criador que você segue e admira muito?"},
        {"id":"m02p04","texto":"Se dinheiro não fosse problema, o que você faria como trabalho?","tipo":"texto_livre","placeholder":"Sonhe à vontade — essa resposta é muito importante para a IA entender você"},
        {"id":"m02p05","texto":"Qual tipo de problema você gostaria de ajudar a resolver no mundo?","opcoes":[{"letra":"A","texto":"Desigualdade social e pobreza"},{"letra":"B","texto":"Problemas de saúde e doenças"},{"letra":"C","texto":"Educação de qualidade para todos"},{"letra":"D","texto":"Tecnologia e inovação"},{"letra":"E","texto":"Meio ambiente e sustentabilidade"}],"textoLivre":"Tem outro problema que te preocupa?"},
        {"id":"m02p06","texto":"Em qual disciplina escolar você sempre se destacou (ou menos sofreu)?","opcoes":[{"letra":"A","texto":"Matemática e Física"},{"letra":"B","texto":"Português, Redação e Literatura"},{"letra":"C","texto":"Biologia e Química"},{"letra":"D","texto":"História e Geografia"},{"letra":"E","texto":"Artes e Educação Física"}],"textoLivre":"Se nenhuma, pode contar aqui"},
        {"id":"m02p07","texto":"Você já tentou criar ou construir algo por conta própria?","opcoes":[{"letra":"A","texto":"Sim, frequentemente — tenho projetos pessoais"},{"letra":"B","texto":"Já tentei algumas vezes"},{"letra":"C","texto":"Ainda não, mas tenho vontade"},{"letra":"D","texto":"Não tenho muito interesse nisso"}],"textoLivre":"Se sim, o que você criou ou tentou criar?"},
        {"id":"m02p08","texto":"Qual profissional você mais admira (pode ser famoso ou alguém da sua vida)?","tipo":"texto_livre","placeholder":"Ex: meu tio é médico e eu admiro muito o que ele faz..."},
    ]},
    "03":{"titulo":"Habilidades e Estilo","descricao":"O que você já sabe fazer bem.","perguntas":[
        {"id":"m03p01","texto":"O que as pessoas sempre pedem sua ajuda?","opcoes":[{"letra":"A","texto":"Resolver problemas técnicos ou de tecnologia"},{"letra":"B","texto":"Criar algo bonito ou criativo"},{"letra":"C","texto":"Organizar, planejar ou tomar decisões"},{"letra":"D","texto":"Ouvir, aconselhar, apoiar emocionalmente"},{"letra":"E","texto":"Explicar assuntos ou ensinar"}],"textoLivre":"Tem outra coisa que as pessoas sempre te pedem?"},
        {"id":"m03p02","texto":"Como você prefere aprender algo novo?","opcoes":[{"letra":"A","texto":"Fazendo — aprendo na prática, errando e tentando"},{"letra":"B","texto":"Assistindo vídeos ou lendo por conta"},{"letra":"C","texto":"Com alguém me explicando pessoalmente"},{"letra":"D","texto":"Em sala de aula com professor"}]},
        {"id":"m03p03","texto":"Qual habilidade você acha que tem mais desenvolvida?","opcoes":[{"letra":"A","texto":"Raciocínio lógico e análise"},{"letra":"B","texto":"Comunicação — falar e escrever bem"},{"letra":"C","texto":"Criatividade e originalidade"},{"letra":"D","texto":"Organização e planejamento"},{"letra":"E","texto":"Empatia e relações humanas"}]},
        {"id":"m03p04","texto":"Como você lida com prazos e responsabilidades?","opcoes":[{"letra":"A","texto":"Entrego antes — sou muito organizado"},{"letra":"B","texto":"Entrego no prazo, mas na última hora"},{"letra":"C","texto":"Às vezes atraso, mas entrego"},{"letra":"D","texto":"Tenho dificuldade com prazos"}],"textoLivre":"Quer comentar algo sobre como você se organiza?"},
        {"id":"m03p05","texto":"Se você tivesse que apresentar um trabalho agora, como faria?","opcoes":[{"letra":"A","texto":"Com dados, gráficos e resultados concretos"},{"letra":"B","texto":"Com slides bonitos e apresentação visual"},{"letra":"C","texto":"Contando uma história envolvente"},{"letra":"D","texto":"Com relatório detalhado e bem estruturado"}]},
        {"id":"m03p06","texto":"Você considera que aprende rápido coisas novas?","opcoes":[{"letra":"A","texto":"Sim, geralmente pego rápido"},{"letra":"B","texto":"Depende do assunto"},{"letra":"C","texto":"Demoro mais, mas aprendo bem"},{"letra":"D","texto":"Tenho dificuldade e preciso de bastante apoio"}]},
        {"id":"m03p07","texto":"Qual sua maior qualidade segundo as pessoas que convivem com você?","tipo":"texto_livre","placeholder":"O que familiares, amigos ou professores costumam elogiar em você?"},
        {"id":"m03p08","texto":"Qual é a sua maior dificuldade que você gostaria de superar?","tipo":"texto_livre","placeholder":"Pode ser qualquer coisa — timidez, matemática, organização... seja honesto"},
    ]},
    "04":{"titulo":"Vida e Contexto Real","descricao":"Entendendo sua realidade para traçar um caminho possível.","perguntas":[
        {"id":"m04p01","texto":"Como é sua rotina diária hoje?","opcoes":[{"letra":"A","texto":"Só estudo — tenho tempo livre"},{"letra":"B","texto":"Estudo e ajudo nas tarefas de casa"},{"letra":"C","texto":"Estudo e trabalho parte do dia"},{"letra":"D","texto":"Trabalho o dia todo e estudo quando dá"}],"textoLivre":"Quer descrever melhor como é o seu dia a dia?"},
        {"id":"m04p02","texto":"Sua família apoia sua escolha profissional?","opcoes":[{"letra":"A","texto":"Sim, totalmente — me incentivam"},{"letra":"B","texto":"Apoiam, mas com algumas ressalvas"},{"letra":"C","texto":"São neutros — não incentivam nem bloqueiam"},{"letra":"D","texto":"Preferem que eu siga outro caminho"},{"letra":"E","texto":"Não temos muito diálogo sobre isso"}],"textoLivre":"Quer contar mais sobre como sua família vê seus planos?"},
        {"id":"m04p03","texto":"Você tem alguma limitação física, de saúde ou outra que possa influenciar sua escolha de carreira?","opcoes":[{"letra":"A","texto":"Não, nenhuma"},{"letra":"B","texto":"Sim, mas não impede minha escolha"},{"letra":"C","texto":"Sim, preciso levar isso em consideração"},{"letra":"D","texto":"Prefiro não informar"}],"textoLivre":"Se quiser compartilhar para a IA considerar, fique à vontade"},
        {"id":"m04p04","texto":"Você tem alguma crença religiosa, cultural ou familiar que influencia sua visão de carreira?","opcoes":[{"letra":"A","texto":"Sim, influencia bastante"},{"letra":"B","texto":"Um pouco, mas não define minha escolha"},{"letra":"C","texto":"Não, não influencia"},{"letra":"D","texto":"Prefiro não comentar"}],"textoLivre":"Quer explicar como isso influencia?"},
        {"id":"m04p05","texto":"Você tem internet boa o suficiente para fazer um curso EAD?","opcoes":[{"letra":"A","texto":"Sim, sem problemas"},{"letra":"B","texto":"Internet razoável, às vezes trava"},{"letra":"C","texto":"Só no celular, dados limitados"},{"letra":"D","texto":"Não tenho acesso adequado"}]},
        {"id":"m04p06","texto":"Você conhece os programas do governo para entrar na faculdade? (SISU, ProUni, FIES)","opcoes":[{"letra":"A","texto":"Sim, conheço bem todos"},{"letra":"B","texto":"Já ouvi falar mas não entendo direito"},{"letra":"C","texto":"Não conheço nenhum"},{"letra":"D","texto":"Já tentei algum deles"}],"textoLivre":"Se já tentou ou tem dúvidas sobre algum, pode descrever aqui"},
        {"id":"m04p07","texto":"Se você pudesse pedir uma coisa para esse sistema de orientação, o que seria?","tipo":"texto_livre","placeholder":"Ex: quero saber se consigo entrar em medicina sem pagar nada, ou quero entender como funciona o técnico..."},
        {"id":"m04p08","texto":"Tem algo importante sobre você que não foi perguntado e que acha que deve influenciar sua análise?","tipo":"texto_livre","placeholder":"Esse é seu espaço livre — escreva o que quiser. A IA vai ler tudo isso.","obrigatorio":False},
    ]},
}

# ── JWT helpers ────────────────────────────────────────────────────────────────
def gerar_token(usuario_id: str, email: str) -> str:
    payload = {"sub": usuario_id, "email": email, "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRES_H)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verificar_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"erro": "Token expirado", "codigo": "TOKEN_EXPIRADO"})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail={"erro": "Token inválido", "codigo": "TOKEN_INVALIDO"})

async def get_usuario(token: dict = Depends(verificar_token)) -> dict:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM usuarios WHERE id = %s", (token["sub"],))
            u = await cur.fetchone()
            if not u:
                raise HTTPException(status_code=401, detail={"erro": "Usuário não encontrado", "codigo": "USUARIO_NAO_ENCONTRADO"})
            u["modulos_concluidos"] = json.loads(u["modulos_concluidos"]) if isinstance(u["modulos_concluidos"], str) else (u["modulos_concluidos"] or [])
            u["teste_inicial_concluido"] = bool(u["teste_inicial_concluido"])
            return u

# ── IA ─────────────────────────────────────────────────────────────────────────
def montar_prompt_base(nome: str, linhas_teste: str, linhas_mod: str) -> str:
    return f"""Você é um orientador vocacional humanizado, especialista no sistema educacional e de trabalho brasileiro.
Você está analisando o perfil de um jovem que pode estar perdido, com medo ou sem dinheiro para estudar.
Sua missão é ser honesto, acolhedor e prático — dando um caminho REAL considerando a situação financeira, localização e contexto de vida dele.

Considere SEMPRE:
- Se a renda é baixa: priorize SISU (universidade pública via ENEM), ProUni (bolsa integral/parcial), FIES, institutos federais (IFSP, IFCE etc.) e cursos técnicos gratuitos
- Se precisar trabalhar: sugira cursos noturnos, EAD acessível, cursos técnicos rápidos
- Se não fez ENEM: oriente sobre como se preparar e quando fazer
- Seja específico com nomes de instituições, cursos e programas reais do Brasil

DADOS DO USUÁRIO:
Nome: {nome}

Respostas do Teste Inicial:
{linhas_teste}
{linhas_mod}

Retorne SOMENTE um JSON válido (sem markdown, sem texto adicional) neste formato:
{{
  "areaPrincipal": "string",
  "areaPrincipalJustificativa": "string — no máximo 140 caracteres, explicando por que esta área ficou em 1º lugar",
  "percentualCompatibilidade": 85,
  "areasSecundarias": [{{"nome": "string", "percentual": 70, "justificativa": "string — no máximo 140 caracteres explicando por que esta área também combina"}}],
  "perfilLabel": "string — título claro e direto do perfil em até 6 palavras",
  "perfilResumoClaro": "string — frase curta de até 120 caracteres",
  "mensagemPersonalizada": "string — mensagem acolhedora e honesta de 2-3 frases diretamente para o jovem, usando o nome dele",
  "skills": ["string — habilidades identificadas"],
  "pontosDeMelhoria": ["string — 2-3 pontos para desenvolver"],
  "caminhos": [
    {{
      "titulo": "string",
      "descricao": "string",
      "prazo": "string",
      "custo": "string",
      "dificuldade": "string",
      "passos": [{{"titulo": "string", "descricao": "string"}}]
    }}
  ],
  "faculdades": [
    {{"nome": "string", "tipo": "publica|privada|federal", "cidade": "string", "nota_enem": 0, "bolsa": false, "programa": "string"}}
  ],
  "cursosTecnicos": [
    {{"nome": "string", "instituicao": "string", "duracao": "string", "gratuito": true, "modalidade": "presencial|ead|hibrido"}}
  ],
  "cursos": [
    {{"nome": "string", "plataforma": "string", "gratuito": true, "url": "", "nivel": "iniciante|intermediario|avancado"}}
  ],
  "programasGoverno": [
    {{"nome": "string", "descricao": "string", "comoAcessar": "string", "linkOficial": "string"}}
  ],
  "proximosPassos": [
    {{"titulo": "string — acao curta em ate 80 chars", "descricao": "string — como executar em 2-3 frases"}}
  ],
  "alertas": ["string"],
  "mapaCarreira": [
    {{"id": "string", "titulo": "string", "sub": "string", "prazo": "string", "status": "done|active|locked"}}
  ],
  "respostasDestaque": {{
    "preferenciaTrabalho": "string",
    "ambienteIdeal": "string",
    "principalDesafio": "string",
    "sonho": "string"
  }}
}}"""

async def chamar_ia(prompt: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("Chave de API da Anthropic não configurada.")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": ANTHROPIC_MODEL, "max_tokens": 8192, "messages": [{"role": "user", "content": prompt}]},
            )
    except httpx.RequestError as err:
        raise RuntimeError(f"Falha de conexão com a Anthropic: {err}") from err

    if resp.status_code != 200:
        try:
            detalhe = resp.json()
        except Exception:
            detalhe = resp.text
        raise RuntimeError(f"Anthropic retornou HTTP {resp.status_code}: {detalhe}")
    texto = "".join(b.get("text","") for b in resp.json().get("content",[]))
    texto = texto.strip()
    # Remove bloco ```json ... ``` se existir
    texto = re.sub(r'```json\s*', '', texto)
    texto = re.sub(r'```\s*', '', texto)
    texto = texto.strip()
    # Extrai o JSON com regex (do primeiro { até o último })
    match = re.search(r'\{[\s\S]*\}', texto)
    if match:
        try:
            return json.loads(match.group())
        except Exception as parse_err:
            logger.error(f"Erro ao parsear JSON: {parse_err}")
    logger.error(f"JSON inválido: {texto[:300]}")
    raise RuntimeError("IA retornou formato inválido.")


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════════════════════

def perguntas_teste_ativas():
    return PERGUNTAS_TESTE

def ids_perguntas_teste_ativas():
    return {p["id"] for p in perguntas_teste_ativas()}

def ids_perguntas_teste_obrigatorias():
    return {p["id"] for p in perguntas_teste_ativas() if p.get("obrigatorio", True)}

def formatar_resposta_teste(pergunta: dict, resposta: dict) -> dict:
    valor = str(resposta.get("valor", "")).strip()
    opcoes = pergunta.get("opcoes") or []
    opcao = next((op for op in opcoes if op.get("letra") == valor), None)
    texto_resposta = opcao.get("texto") if opcao else valor
    texto_livre = str(resposta.get("textoLivre", "") or "").strip()
    if texto_livre:
        texto_resposta = f"{texto_resposta} — {texto_livre}" if texto_resposta else texto_livre
    return {
        "perguntaId": pergunta["id"],
        "bloco": pergunta.get("bloco", "Resposta"),
        "pergunta": pergunta["texto"],
        "resposta": texto_resposta,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/usuarios")
async def admin_usuarios(senha: str):
    if senha != os.getenv("ADMIN_SECRET", "25107Senai"):
        raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, nome, email, teste_inicial_concluido, modulos_concluidos, criado_em FROM usuarios")
            return await cur.fetchall()

@app.get("/api/admin/dados")
async def admin_dados(senha: str):
    if senha != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT COUNT(*) as total FROM usuarios")
            total_usuarios = (await cur.fetchone())["total"]
            await cur.execute("SELECT COUNT(*) as total FROM perfis")
            total_perfis = (await cur.fetchone())["total"]
            await cur.execute("SELECT COUNT(*) as total FROM respostas_teste")
            total_respostas = (await cur.fetchone())["total"]
            await cur.execute("SELECT COUNT(*) as total FROM jobs WHERE status='concluido'")
            total_jobs = (await cur.fetchone())["total"]
            await cur.execute("SELECT id, nome, email, teste_inicial_concluido, modulos_concluidos, criado_em FROM usuarios ORDER BY criado_em DESC")
            usuarios = await cur.fetchall()
            await cur.execute("SELECT j.id, j.usuario_id, j.status, j.erro, j.criado_em, u.nome FROM jobs j LEFT JOIN usuarios u ON j.usuario_id=u.id ORDER BY j.criado_em DESC LIMIT 50")
            jobs = await cur.fetchall()
            await cur.execute("SELECT p.usuario_id, p.criado_em, p.atualizado_em, u.nome, JSON_UNQUOTE(JSON_EXTRACT(p.dados, '$.areaPrincipal')) as area FROM perfis p LEFT JOIN usuarios u ON p.usuario_id=u.id ORDER BY p.criado_em DESC")
            perfis = await cur.fetchall()
            for u in usuarios:
                u["modulos_concluidos"] = json.loads(u["modulos_concluidos"]) if isinstance(u["modulos_concluidos"], str) else (u["modulos_concluidos"] or [])
                u["teste_inicial_concluido"] = bool(u["teste_inicial_concluido"])
                if u["criado_em"]: u["criado_em"] = u["criado_em"].isoformat()
            for j in jobs:
                if j["criado_em"]: j["criado_em"] = j["criado_em"].isoformat()
            for p in perfis:
                if p["criado_em"]: p["criado_em"] = p["criado_em"].isoformat()
                if p["atualizado_em"]: p["atualizado_em"] = p["atualizado_em"].isoformat()
    return {
        "metricas": {"usuarios": total_usuarios, "perfis": total_perfis, "respostas": total_respostas, "jobs_concluidos": total_jobs},
        "usuarios": usuarios, "jobs": jobs, "perfis": perfis
    }

@app.get("/api/admin/respostas/{usuario_id}")
async def admin_respostas_usuario(usuario_id: str, senha: str):
    if senha != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT pergunta_id, valor, texto_livre, criado_em FROM respostas_teste WHERE usuario_id=%s ORDER BY CAST(pergunta_id AS UNSIGNED)", (usuario_id,))
            respostas = await cur.fetchall()
            await cur.execute("SELECT dados FROM perfis WHERE usuario_id=%s", (usuario_id,))
            perfil = await cur.fetchone()
            for r in respostas:
                if r["criado_em"]: r["criado_em"] = r["criado_em"].isoformat()
    return {
        "respostas": respostas,
        "perfil_ia": json.loads(perfil["dados"]) if perfil else None
    }

@app.delete("/api/admin/usuario/{usuario_id}")
async def admin_deletar_usuario(usuario_id: str, senha: str):
    if senha != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM usuarios WHERE id=%s", (usuario_id,))
    return {"deletado": True}

@app.delete("/api/admin/reset")
async def admin_reset(senha: str):
    if senha != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM perfis")
            await cur.execute("DELETE FROM jobs")
            await cur.execute("DELETE FROM respostas_modulo")
            await cur.execute("DELETE FROM respostas_teste")
            await cur.execute("DELETE FROM usuarios")
    return {"resetado": True}
        
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/index.html", include_in_schema=False)
def serve_index_html():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/pages/{page}")
def serve_page(page: str):
    path = os.path.join(BASE_DIR, "pages", page)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Página não encontrada")
    return FileResponse(path)

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.post("/api/auth/cadastro", status_code=201)
async def cadastro(body: CadastroBody):
    if not body.aceite_lgpd:
        raise HTTPException(status_code=400, detail={"erro": "Aceite da LGPD é obrigatório", "codigo": "LGPD_REQUIRED"})
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id FROM usuarios WHERE email = %s", (body.email,))
            if await cur.fetchone():
                raise HTTPException(status_code=409, detail={"erro": "Email já cadastrado", "codigo": "EMAIL_DUPLICADO"})
            uid = str(uuid.uuid4())
            iniciais = "".join(p[0].upper() for p in body.nome.split()[:2])
            await cur.execute(
                "INSERT INTO usuarios (id, nome, email, senha, avatar_iniciais, aceite_lgpd, aceite_menor) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (uid, body.nome, body.email, body.senha, iniciais, body.aceite_lgpd, body.aceite_menor)
            )
            usuario = {
                "id": uid, "nome": body.nome, "email": body.email,
                "avatar_iniciais": iniciais, "aceite_lgpd": body.aceite_lgpd,
                "aceite_menor": body.aceite_menor, "teste_inicial_concluido": False,
                "modulos_concluidos": [], "criado_em": datetime.utcnow().isoformat()
            }
            logger.info(f"✅ Cadastro: {body.email}")
            return {"token": gerar_token(uid, body.email), "usuario": usuario}

@app.post("/api/auth/login")
async def login(body: LoginBody):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM usuarios WHERE email = %s AND senha = %s", (body.email, body.senha))
            u = await cur.fetchone()
            if not u:
                raise HTTPException(status_code=401, detail={"erro": "Credenciais inválidas", "codigo": "CREDENCIAIS_INVALIDAS"})
            u["modulos_concluidos"] = json.loads(u["modulos_concluidos"]) if isinstance(u["modulos_concluidos"], str) else (u["modulos_concluidos"] or [])
            u["teste_inicial_concluido"] = bool(u["teste_inicial_concluido"])
            return {"token": gerar_token(u["id"], body.email), "usuario": {k:v for k,v in u.items() if k!="senha"}}

@app.get("/api/auth/me")
async def me(usuario: dict = Depends(get_usuario)):
    return {k:v for k,v in usuario.items() if k!="senha"}

@app.patch("/api/auth/perfil")
async def atualizar_perfil(body: dict, usuario: dict = Depends(get_usuario)):
    campos_permitidos = ["nome", "email", "cidade"]
    updates = []
    values = []
    for campo in campos_permitidos:
        if campo in body and body[campo]:
            updates.append(f"{campo}=%s")
            values.append(str(body[campo]).strip())
    if "senha_nova" in body and body["senha_nova"]:
        if not body.get("senha_atual") or usuario["senha"] != body["senha_atual"]:
            raise HTTPException(status_code=400, detail={"erro": "Senha atual incorreta"})
        updates.append("senha=%s")
        values.append(str(body["senha_nova"]).strip())
    if "nome" in body and body["nome"]:
        partes = str(body["nome"]).strip().split()
        iniciais = "".join(p[0].upper() for p in partes[:2])
        updates.append("avatar_iniciais=%s")
        values.append(iniciais)
    if updates:
        values.append(usuario["id"])
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"UPDATE usuarios SET {', '.join(updates)} WHERE id=%s", values)
    return await get_usuario({"sub": usuario["id"]})

# ── Teste Inicial ──────────────────────────────────────────────────────────────
@app.get("/api/testeinicial/perguntas")
async def get_perguntas(usuario: dict = Depends(get_usuario)):
    perguntas = perguntas_teste_ativas()
    return {"perguntas": perguntas, "total": len(perguntas)}

@app.patch("/api/testeinicial/resposta")
async def salvar_resposta(body: RespostaBody, usuario: dict = Depends(get_usuario)):
    ids_validos = ids_perguntas_teste_ativas()
    if body.perguntaId not in ids_validos:
        raise HTTPException(status_code=400, detail={"erro": "Pergunta inicial inválida", "codigo": "PERGUNTA_INVALIDA"})
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO respostas_teste (usuario_id, pergunta_id, valor, texto_livre)
                   VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE valor=%s, texto_livre=%s""",
                (usuario["id"], body.perguntaId, body.valor, body.textoLivre or "",
                 body.valor, body.textoLivre or "")
            )
            await cur.execute("SELECT COUNT(*) as total FROM respostas_teste WHERE usuario_id=%s", (usuario["id"],))
            r = await cur.fetchone()
    return {"salvo": True, "respondidas": r[0], "total": len(ids_validos)}

@app.get("/api/testeinicial/progresso")
async def progresso_teste(usuario: dict = Depends(get_usuario)):
    ids_validos = ids_perguntas_teste_ativas()
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM respostas_teste WHERE usuario_id=%s", (usuario["id"],))
            r = await cur.fetchone()
    return {"respondidas": r[0], "total": len(ids_validos)}

@app.get("/api/testeinicial/respostas/destaque")
async def respostas_teste_destaque(limite: int = 3, aleatorio: bool = True, usuario: dict = Depends(get_usuario)):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT pergunta_id, valor, texto_livre FROM respostas_teste WHERE usuario_id=%s", (usuario["id"],))
            rows = await cur.fetchall()
    respostas_dict = {r["pergunta_id"]: {"valor": r["valor"], "textoLivre": r["texto_livre"]} for r in rows}
    perguntas_por_id = {p["id"]: p for p in perguntas_teste_ativas()}
    respondidas = [
        formatar_resposta_teste(perguntas_por_id[pid], resposta)
        for pid, resposta in sorted(respostas_dict.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999)
        if pid in perguntas_por_id and str(resposta.get("valor", "")).strip()
    ]
    limite = max(1, min(limite, 22))
    if aleatorio and limite < len(respondidas):
        selecionadas = random.sample(respondidas, limite)
    else:
        selecionadas = respondidas[:limite]
    return {"respostas": selecionadas}

@app.post("/api/testeinicial/finalizar")
async def finalizar_teste(body: FinalizarTesteBody, usuario: dict = Depends(get_usuario)):
    uid = usuario["id"]
    ids_validos = ids_perguntas_teste_ativas()
    ids_obrigatorios = ids_perguntas_teste_obrigatorias()
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            for r in body.respostas:
                pid = str(r["perguntaId"])
                if pid not in ids_validos:
                    continue
                await cur.execute(
                    """INSERT INTO respostas_teste (usuario_id, pergunta_id, valor, texto_livre)
                       VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE valor=%s, texto_livre=%s""",
                    (uid, pid, r.get("valor",""), r.get("textoLivre",""),
                     r.get("valor",""), r.get("textoLivre",""))
                )
            await cur.execute("SELECT pergunta_id, valor FROM respostas_teste WHERE usuario_id=%s", (uid,))
            rows = await cur.fetchall()
            respondidas = {row[0] for row in rows if str(row[1]).strip() and row[0] in ids_obrigatorios}
            if len(respondidas) < len(ids_obrigatorios):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "erro": "Responda todas as perguntas obrigatórias.",
                        "codigo": "TESTE_INICIAL_INCOMPLETO",
                        "respondidas": len(respondidas),
                        "total": len(ids_obrigatorios),
                    }
                )
            await cur.execute("UPDATE usuarios SET teste_inicial_concluido=TRUE WHERE id=%s", (uid,))
    job_id = str(uuid.uuid4())
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO jobs (id, usuario_id, status) VALUES (%s,%s,'processando')", (job_id, uid))
    usuario["teste_inicial_concluido"] = True
    asyncio.create_task(processar_resultado_ia_db(job_id, uid, usuario, "Teste inicial"))
    return {"processando": True, "jobId": job_id}


async def get_respostas_do_banco(usuario_id: str) -> dict:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT pergunta_id, valor, texto_livre FROM respostas_teste WHERE usuario_id=%s", (usuario_id,))
            rows = await cur.fetchall()
            return {r["pergunta_id"]: {"valor": r["valor"], "textoLivre": r["texto_livre"]} for r in rows}

async def get_respostas_modulo_do_banco(usuario_id: str, modulo_id: str) -> dict:
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT pergunta_id, valor, texto_livre FROM respostas_modulo WHERE usuario_id=%s AND modulo_id=%s", (usuario_id, modulo_id))
            rows = await cur.fetchall()
            return {r["pergunta_id"]: {"valor": r["valor"], "textoLivre": r["texto_livre"]} for r in rows}


async def modulo_desbloqueado_db(modulo_id: str, usuario: dict) -> bool:
    if modulo_id not in PERGUNTAS_MODULOS:
        return False
    concluidos = usuario.get("modulos_concluidos", [])
    ids = list(PERGUNTAS_MODULOS.keys())
    idx = ids.index(modulo_id)
    if modulo_id in concluidos:
        return True
    if idx == 0:
        return bool(usuario.get("teste_inicial_concluido", False))
    return ids[idx-1] in concluidos

async def processar_resultado_ia_db(job_id: str, uid: str, usuario: dict, origem: str = "Job"):
    try:
        rt = await get_respostas_do_banco(uid)
        rm = {}
        for mid in PERGUNTAS_MODULOS.keys():
            rm[mid] = await get_respostas_modulo_do_banco(uid, mid)
        
        def fmt_respostas(resps):
            linhas = []
            for pid, dados in sorted(resps.items()):
                if isinstance(dados, dict):
                    linha = f"  [{pid}] {dados.get('valor','')}"
                    if dados.get('textoLivre'):
                        linha += f" | Texto livre: \"{dados['textoLivre']}\""
                else:
                    linha = f"  [{pid}] {dados}"
                linhas.append(linha)
            return "\n".join(linhas) or "  Não respondido"

        linhas_teste = fmt_respostas(rt)
        linhas_mod = ""
        for mid, info in PERGUNTAS_MODULOS.items():
            linhas_mod += f"\nMódulo {mid} — {info['titulo']}:\n{fmt_respostas(rm.get(mid, {}))}"

        prompt = montar_prompt_base(usuario["nome"], linhas_teste, linhas_mod)
        resultado = await chamar_ia(prompt)

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO perfis (usuario_id, dados) VALUES (%s,%s)
                       ON DUPLICATE KEY UPDATE dados=%s, atualizado_em=CURRENT_TIMESTAMP""",
                    (uid, json.dumps(resultado), json.dumps(resultado))
                )
                await cur.execute("UPDATE jobs SET status='concluido' WHERE id=%s", (job_id,))
        logger.info(f"✅ {origem} {job_id} concluído")
    except Exception as e:
        erro = str(e) or repr(e)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE jobs SET status='erro', erro=%s WHERE id=%s", (erro, job_id))
        logger.exception(f"❌ {origem} {job_id} falhou: {erro}")

# ── Resultado ──────────────────────────────────────────────────────────────────
@app.get("/api/resultado/status")
async def resultado_status(jobId: str, usuario: dict = Depends(get_usuario)):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT status, erro FROM jobs WHERE id=%s", (jobId,))
            job = await cur.fetchone()
            if not job:
                raise HTTPException(status_code=404, detail={"erro": "Job não encontrado", "codigo": "JOB_NAO_ENCONTRADO"})
            data = {"status": job["status"]}
            if job["status"] == "erro":
                data["erro"] = job["erro"] or "A IA não conseguiu gerar o resultado agora."
            return data

@app.get("/api/resultado")
async def get_resultado(usuario: dict = Depends(get_usuario)):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT dados FROM perfis WHERE usuario_id=%s", (usuario["id"],))
            r = await cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail={"erro": "Resultado não encontrado", "codigo": "RESULTADO_NAO_ENCONTRADO"})
            return json.loads(r["dados"])

# ── Módulos ────────────────────────────────────────────────────────────────────
@app.get("/api/modulos")
async def get_modulos(usuario: dict = Depends(get_usuario)):
    uid = usuario["id"]
    concluidos = usuario.get("modulos_concluidos", [])
    teste_ok = usuario.get("teste_inicial_concluido", False)
    modulos = []
    anterior_ok = teste_ok
    for mid, info in PERGUNTAS_MODULOS.items():
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM respostas_modulo WHERE usuario_id=%s AND modulo_id=%s", (uid, mid))
                r = await cur.fetchone()
                respondidas = r[0]
        concluido = mid in concluidos
        status = "done" if concluido else ("active" if anterior_ok else "locked")
        modulos.append({
            "id": mid, "numero": mid, "titulo": info["titulo"],
            "descricao": info["descricao"], "status": status,
            "progresso": 100 if concluido else round((respondidas/8)*100)
        })
        anterior_ok = concluido
    return {"modulos": modulos}

@app.get("/api/modulos/{modulo_id}/perguntas")
async def get_perguntas_modulo(modulo_id: str, usuario: dict = Depends(get_usuario)):
    if modulo_id not in PERGUNTAS_MODULOS:
        raise HTTPException(status_code=404, detail={"erro": "Módulo não encontrado"})
    if not await modulo_desbloqueado_db(modulo_id, usuario):
        raise HTTPException(status_code=403, detail={"erro": "Módulo bloqueado. Responda todas as perguntas iniciais primeiro."})
    return {"perguntas": PERGUNTAS_MODULOS[modulo_id]["perguntas"], "total": len(PERGUNTAS_MODULOS[modulo_id]["perguntas"])}

@app.patch("/api/modulos/{modulo_id}/resposta")
async def salvar_resposta_modulo(modulo_id: str, body: RespostaModuloBody, usuario: dict = Depends(get_usuario)):
    if not await modulo_desbloqueado_db(modulo_id, usuario):
        raise HTTPException(status_code=403, detail={"erro": "Módulo bloqueado. Responda todas as perguntas iniciais primeiro."})
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO respostas_modulo (usuario_id, modulo_id, pergunta_id, valor, texto_livre)
                   VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE valor=%s, texto_livre=%s""",
                (usuario["id"], modulo_id, body.perguntaId, body.valor, body.textoLivre or "",
                 body.valor, body.textoLivre or "")
            )
            await cur.execute("SELECT COUNT(*) FROM respostas_modulo WHERE usuario_id=%s AND modulo_id=%s", (usuario["id"], modulo_id))
            r = await cur.fetchone()
    total = len(PERGUNTAS_MODULOS.get(modulo_id, {}).get("perguntas", []))
    return {"salvo": True, "respondidas": r[0], "total": total}

@app.get("/api/modulos/{modulo_id}/progresso")
async def progresso_modulo(modulo_id: str, usuario: dict = Depends(get_usuario)):
    total = len(PERGUNTAS_MODULOS.get(modulo_id, {}).get("perguntas", []))
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM respostas_modulo WHERE usuario_id=%s AND modulo_id=%s", (usuario["id"], modulo_id))
            r = await cur.fetchone()
    return {"respondidas": r[0], "total": total, "percentual": round((r[0]/total)*100) if total else 0}

@app.post("/api/modulos/{modulo_id}/finalizar")
async def finalizar_modulo(modulo_id: str, usuario: dict = Depends(get_usuario)):
    if not await modulo_desbloqueado_db(modulo_id, usuario):
        raise HTTPException(status_code=403, detail={"erro": "Módulo bloqueado. Responda todas as perguntas iniciais primeiro."})
    uid = usuario["id"]
    concluidos = list(usuario.get("modulos_concluidos", []))
    if modulo_id not in concluidos:
        concluidos.append(modulo_id)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE usuarios SET modulos_concluidos=%s WHERE id=%s", (json.dumps(concluidos), uid))
    if modulo_id == "04":
        job_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO jobs (id, usuario_id, status) VALUES (%s,%s,'processando')", (job_id, uid))
        usuario["modulos_concluidos"] = concluidos
        asyncio.create_task(processar_resultado_ia_db(job_id, uid, usuario, "Módulo 04"))
        return {"concluido": True, "jobId": job_id}
    return {"concluido": True, "proximoModulo": f"{int(modulo_id)+1:02d}"}

# ── Contexto livre extra ───────────────────────────────────────────────────────
@app.post("/api/contexto")
async def salvar_contexto(body: ContextoLivreBody, usuario: dict = Depends(get_usuario)):
    return {"salvo": True}

# ── Perfil ─────────────────────────────────────────────────────────────────────
@app.get("/api/perfil")
async def get_perfil(usuario: dict = Depends(get_usuario)):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT dados FROM perfis WHERE usuario_id=%s", (usuario["id"],))
            r = await cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail={"erro": "Perfil não gerado"})
            return json.loads(r["dados"])

@app.get("/api/mapa")
async def get_mapa(usuario: dict = Depends(get_usuario)):
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT dados FROM perfis WHERE usuario_id=%s", (usuario["id"],))
            r = await cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail={"erro": "Perfil não gerado"})
            dados = json.loads(r["dados"])
            return {"steps": dados.get("mapaCarreira", [])}

@app.get("/api/jornada/progresso")
async def jornada_prog(usuario: dict = Depends(get_usuario)):
    c = len(usuario.get("modulos_concluidos", []))
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT dados FROM perfis WHERE usuario_id=%s", (usuario["id"],))
            r = await cur.fetchone()
    dados = json.loads(r["dados"]) if r else {}
    return {"percentual": round((c/4)*100), "modulosCompletos": c, "totalModulos": 4,
            "habilidadesAtivas": dados.get("skills", []) if dados else []}


@app.post("/api/vagas")
async def buscar_vagas(body: dict, usuario: dict = Depends(get_usuario)):
    profissao = body.get("profissao", "")
    localizacao = body.get("localizacao", "Brasil")
    api_key = os.getenv("JSEARCH_API_KEY", "")
    
    if not api_key:
        raise HTTPException(status_code=500, detail="JSEARCH_API_KEY não configurada")
    if not profissao:
        raise HTTPException(status_code=400, detail="Profissão não informada")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://jsearch.p.rapidapi.com/search",
                headers={
                    "X-RapidAPI-Key": api_key,
                    "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
                },
                params={
                    "query": f"{profissao} {localizacao}",
                    "num_pages": "1",
                    "date_posted": "month"
                }
            )
        data = resp.json()
        vagas = []
        for job in data.get("data", [])[:6]:
            vagas.append({
                "titulo": job.get("job_title", ""),
                "empresa": job.get("employer_name", ""),
                "localizacao": f"{job.get('job_city', '')} {job.get('job_country', '')}".strip(),
                "link": job.get("job_apply_link", "#"),
                "descricao": (job.get("job_description", "")[:200] + "...") if job.get("job_description") else ""
            })
        return vagas
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao buscar vagas: {str(e)}")

# ── Arquivos estáticos (deve ficar após todas as rotas) ────────────────────────
app.mount("/js",       StaticFiles(directory=os.path.join(BASE_DIR, "js")),       name="js")
app.mount("/styles",   StaticFiles(directory=os.path.join(BASE_DIR, "styles")),   name="styles")
app.mount("/assets",   StaticFiles(directory=os.path.join(BASE_DIR, "assets")),   name="assets")
app.mount("/partials", StaticFiles(directory=os.path.join(BASE_DIR, "partials")), name="partials")
app.mount("/assets", StaticFiles(directory=os.path.join(BASE_DIR, "assets")), name="assets")
