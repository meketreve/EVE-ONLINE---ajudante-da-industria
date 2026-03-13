# EVE Industry Tool

Aplicação web local para industrialistas do **EVE Online** calcularem custos de produção, margens de lucro e rentabilidade de itens, integrando dados reais do jogo via ESI e mercados de estruturas privadas.

---

## Funcionalidades

- **Calculadora de produção** — custo de materiais, job cost (SCI + facility tax + SCC), broker fee, sales tax, lucro bruto e líquido
- **Mercados públicos e privados** — preços de hubs regionais (ex: Jita) e estruturas Upwell acessíveis ao personagem
- **Ranking de lucro** — itens mais rentáveis com base nos preços em cache
- **Fila de produção** — lista de jobs planejados por personagem
- **Descoberta de estruturas** — escaneia assets pessoais para encontrar cidadelas e complexos com acesso ao mercado
- **Configurações globais** — define ME, SCI, taxas e mercado padrão para todos os cálculos
- **Login via EVE SSO** — acesso a dados de personagem, skills e mercados privados

---

## Stack

| Camada     | Tecnologia                              |
|------------|-----------------------------------------|
| Backend    | Python 3.11+, FastAPI, SQLAlchemy async |
| Banco      | SQLite (WAL mode, aiosqlite)            |
| Frontend   | Jinja2, HTMX, CSS                       |
| Auth       | EVE SSO (OAuth2)                        |
| Dados EVE  | ESI API + SDE (Static Data Export)      |

---

## Pré-requisitos

- Python 3.11 ou superior
- Conta de desenvolvedor EVE Online com uma aplicação registrada em [developers.eveonline.com](https://developers.eveonline.com)

**Escopos ESI necessários:**
```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-assets.read_assets.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1
```

---

## Instalação

### 1. Clonar o repositório

```bash
git clone <url-do-repo>
cd "EVE ONLINE - ajudante da industria"
```

### 2. Criar e ativar ambiente virtual

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r eve_industry_tool/requirements.txt
```

### 4. Configurar credenciais EVE SSO

Crie um arquivo `.env` dentro de `eve_industry_tool/`:

```env
EVE_CLIENT_ID=seu_client_id
EVE_CLIENT_SECRET=seu_client_secret
EVE_CALLBACK_URL=http://localhost:8000/auth/callback
SECRET_KEY=uma_chave_secreta_qualquer
```

### 5. Importar dados do SDE

Baixa e importa itens, blueprints e materiais do Static Data Export da CCP:

```bash
# Windows
1_importar_sde.bat

# Direto
python eve_industry_tool/scripts/import_sde.py
```

> A importação pode demorar alguns minutos na primeira vez.

### 6. Iniciar o servidor

```bash
# Windows
3_iniciar.bat

# Direto
cd eve_industry_tool
uvicorn app.main:app --reload
```

Acesse: [http://localhost:8000](http://localhost:8000)

---

## Scripts Auxiliares

### `2_atualizar_estruturas.bat`

Descobre estruturas Upwell acessíveis ao personagem logado e testa acesso ao mercado de cada uma.

```bash
# Usa todas as fontes (corporação + assets pessoais)
2_atualizar_estruturas.bat

# Apenas assets pessoais
2_atualizar_estruturas.bat --fonte assets
```

### `ordens_null.bat`

Importa ordens de compra/venda de estruturas em nullsec diretamente para o cache de preços.

```bash
# Lista estruturas disponíveis
ordens_null.bat --listar

# Importa ordens de uma estrutura específica
ordens_null.bat --id 1046664001931
```

---

## Estrutura do Projeto

```
eve_industry_tool/
├── app/
│   ├── main.py                  # Entry point FastAPI
│   ├── config.py                # Configurações e variáveis de ambiente
│   ├── api/                     # Rotas HTTP
│   │   ├── auth.py              # EVE SSO (login, callback, logout)
│   │   ├── items.py             # Listagem e detalhe de itens
│   │   ├── industry.py          # Calculadora e ranking de lucro
│   │   ├── market.py            # Visão geral do mercado
│   │   ├── discovery.py         # Descoberta e crawl de estruturas
│   │   └── settings.py          # Configurações do usuário
│   ├── services/                # Lógica de negócio
│   │   ├── esi_client.py        # Client HTTP para a ESI
│   │   ├── market_service.py    # Preços de região e estruturas
│   │   ├── industry_calculator.py # Cálculo de custo e lucro
│   │   ├── blueprint_service.py # Materiais e blueprints
│   │   ├── crawler_service.py   # Crawl de ordens de estruturas
│   │   ├── discovery_service.py # Descoberta de estruturas via assets
│   │   ├── job_runner.py        # Fila de jobs em background
│   │   └── character_service.py # Tokens e dados de personagem
│   ├── models/                  # Modelos SQLAlchemy
│   ├── database/
│   │   └── database.py          # Engine, sessão, pragmas SQLite
│   └── templates/               # Templates Jinja2
├── scripts/
│   ├── import_sde.py            # Importação do SDE
│   ├── atualizar_estruturas.py  # Descoberta de estruturas
│   ├── ordens_null.py           # Ordens de estruturas nullsec
│   └── atualizar_precos_mercado.py
├── static/
│   └── style.css
└── requirements.txt
```

---

## Fluxo de Dados

```
Browser → FastAPI → Services → ESI API
                 ↘           ↘
                  SQLite ← Scripts externos
```

- **ESI**: dados ao vivo (personagem, skills, assets, ordens de estruturas)
- **SDE**: dados estáticos importados uma vez (itens, blueprints, materiais)
- **Scripts externos**: populam o cache de preços sem bloquear o servidor web
- **Job runner interno**: crawl de estruturas em background após descoberta

---

## Desenvolvimento

```bash
# Rodar testes
pytest

# Lint
ruff check .

# Servidor com reload automático
uvicorn app.main:app --reload
```

---

## Observações

- O banco de dados (`database.db`) é criado automaticamente na primeira execução
- Todos os dados ficam locais — nada é enviado a servidores externos além da ESI oficial
- Não afiliado à CCP Games
