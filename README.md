# EVE Industry Tool

Aplicação **desktop local** para industrialistas do **EVE Online** calcularem custos de produção, margens de lucro e oportunidades de importação. Integra com EVE SSO (OAuth2) e ESI API para dados ao vivo de personagem, mercado e estruturas.

Interface gráfica nativa via **NiceGUI** — abre como janela desktop, sem browser externo.

---

## Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| **Calculadora de Produção** | BOM recursivo, ME por item e por estrutura, bônus de estrutura, job cost (SCI + facility tax + SCC), taxas, lucro bruto e líquido |
| **Comparação de Preços no BOM** | Seleção de estrutura de manufatura por sub-componente — identifica o que vale importar ou fabricar em outra instalação |
| **Fila de Produção** | Jobs planejados com BOM agregado, lista de compras unificada com botão de cópia |
| **Ranking de Importação** | Itens com maior margem entre mercado fonte e local, com cálculo de frete |
| **Comparador de Lista** | Cola uma lista de itens e compara custo de importar vs comprar localmente |
| **Projeção de Mercado** | Histórico ESI com charts de volume e preço, projeção 7/14/30 dias |
| **Reprocessamento** | Calcula se vale reprocessar o item ou vendê-lo diretamente |
| **Estruturas de Manufatura** | Cadastro de Raitaru/Azbel/Sotiyo com bônus ME aplicado no cálculo |
| **Descoberta de Estruturas** | Escaneia assets pessoais para encontrar citadelas acessíveis com mercado |
| **Mercados Privados** | Crawl automático a cada 15 min de ordens de estruturas Upwell |
| **Login via EVE SSO** | Acesso a skills, assets e mercados privados do personagem |

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| GUI | NiceGUI (`native=True`) + pywebview |
| Backend | Python 3.11+, SQLAlchemy async (aiosqlite) |
| Banco | SQLite (WAL mode) |
| Auth | EVE SSO (OAuth2) |
| Dados EVE | ESI API + SDE (Static Data Export via EVERef/Fuzzwork) |

---

## Arquitetura de dados

O app segue o padrão **cache-first com atualizações em background**:

- Todas as consultas leem do banco SQLite local (resposta imediata)
- Chamadas à ESI só ocorrem para atualizar o banco, nunca para responder ao usuário diretamente
- Refresh de preços em massa (ex: todas as ordens de Jita) roda via `asyncio.create_task` — sem bloquear a UI
- Scheduler interno: recrawl de estruturas a cada 15 min, limpeza de ordens a cada 1h, rediscovery a cada 6h

---

## Pré-requisitos

- Python 3.11 ou superior
- Conta de desenvolvedor EVE Online com aplicação registrada em [developers.eveonline.com](https://developers.eveonline.com)

**Escopos ESI necessários** (configurar na aplicação EVE Developer):
```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-assets.read_assets.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1
esi-universe.read_structures.v1
```

**Callback URL** da aplicação EVE: `http://localhost:8765/auth/callback`

---

## Instalação

### 1. Clonar o repositório

```bash
git clone <url-do-repo>
cd "EVE ONLINE - ajudante da industria"
```

### 2. Instalar dependências

**Windows (recomendado):**
```
0_instalar.bat
```
O script verifica Python, instala dependências e orienta a configuração do `.env`.

**Manual:**
```bash
pip install -r eve_industry_tool/requirements.txt
```

### 3. Configurar credenciais EVE SSO

Crie o arquivo `eve_industry_tool/.env`:

```env
EVE_CLIENT_ID=seu_client_id
EVE_CLIENT_SECRET=seu_client_secret
EVE_CALLBACK_URL=http://localhost:8765/auth/callback
SECRET_KEY=uma_chave_secreta_aleatoria_longa
```

### 4. Importar dados do SDE

Baixa e importa itens, blueprints e materiais do Static Data Export (**apenas uma vez**):

```bash
python eve_industry_tool/scripts/import_sde.py
```

### 5. Iniciar o app

**Windows:**
```
1_iniciar.bat
```

**Manual:**
```bash
cd eve_industry_tool
python -m app.main
```

A janela desktop abre automaticamente.

---

## Estrutura do Projeto

```
eve_industry_tool/
├── app/
│   ├── main.py                    # Entry point NiceGUI (native=True), scheduler, OAuth callback
│   ├── config.py                  # Configurações e variáveis de ambiente
│   ├── ui/                        # Páginas e componentes NiceGUI
│   │   ├── auth_page.py           # Login EVE SSO
│   │   ├── dashboard_page.py      # Dashboard inicial
│   │   ├── items_page.py          # Browser de itens
│   │   ├── industry_page.py       # Calculadora de produção + BOM recursivo
│   │   ├── reprocessing_page.py   # Calculadora de reprocessamento
│   │   ├── queue_page.py          # Fila de produção + lista de compras
│   │   ├── ranking_page.py        # Ranking de importação + comparador de lista
│   │   ├── ranking_item_page.py   # Projeção de mercado com charts
│   │   ├── settings_page.py       # Configurações + estruturas de manufatura
│   │   └── components/
│   │       ├── bom_tree.py        # Árvore BOM expansível com ME e estação por nó
│   │       ├── cost_breakdown.py  # Painel custo/lucro
│   │       ├── structure_selector.py
│   │       └── price_chart.py     # Charts ECharts
│   ├── services/                  # Lógica de negócio
│   │   ├── esi_client.py          # Wrapper async da ESI API
│   │   ├── market_service.py      # Cache de preços, refresh de mercado
│   │   ├── industry_calculator.py # Fórmulas de custo e lucro
│   │   ├── blueprint_service.py   # BOM recursivo com pré-carregamento em batch
│   │   ├── crawler_service.py     # Crawl de mercados de estruturas (background)
│   │   ├── discovery_service.py   # Descoberta de estruturas via assets
│   │   ├── job_runner.py          # Fila de jobs async com deduplicação
│   │   ├── settings_service.py    # Load/save de configurações do usuário
│   │   └── character_service.py   # Dados de personagem, skills, token refresh
│   ├── models/                    # ORM SQLAlchemy (16 tabelas)
│   └── database/
│       └── database.py            # Setup SQLite, migrations no startup
├── scripts/
│   ├── import_sde.py              # Importação do SDE (EVERef ou Fuzzwork)
│   ├── atualizar_estruturas.py    # Descoberta de estruturas via ESI
│   ├── atualizar_precos_mercado.py
│   └── ordens_null.py             # Ordens de estruturas nullsec
├── 0_instalar.bat                 # Instalação guiada (Windows)
├── 1_iniciar.bat                  # Iniciar o app (Windows)
├── requirements.txt
└── .env                           # Credenciais (não versionado)
```

---

## Scripts Auxiliares

```bash
# Atualizar estruturas Upwell via ESI
python eve_industry_tool/scripts/atualizar_estruturas.py

# Atualizar preços de mercado manualmente
python eve_industry_tool/scripts/atualizar_precos_mercado.py

# Importar ordens de estruturas nullsec
python eve_industry_tool/scripts/ordens_null.py --listar
python eve_industry_tool/scripts/ordens_null.py --id <structure_id>
```

---

## Fórmulas

### Custo de Produção
```
Material Cost = Σ(quantidade × preço_unitário)
Job Cost      = item_value_ajustado × (SCI + facility_tax + SCC)
Total         = Material Cost + Job Cost
```

### Lucro
```
Gross Profit = sell_price - total_cost
Net Profit   = sell_price × (1 - broker_fee - sales_tax) - total_cost
```

### Material Efficiency
```
qty = ceil(qty_base × (1 - blueprint_ME/100) × (1 - estrutura_ME/100))
```

Aplica-se por nó do BOM — cada sub-componente pode ter estrutura e ME independentes.

### Margem de Importação
```
Margem = preço_local × (1 - sales_tax - broker_fee) - preço_fonte - frete/un.
```

---

## Observações

- O banco (`database.db`) é criado automaticamente na primeira execução — não é versionado
- Migrations de schema rodam no startup sem destruir dados existentes
- Todos os dados ficam locais — nada é enviado além da ESI oficial da CCP
- A ESI não expõe rigs de estruturas; o cadastro de bônus ME é manual em Configurações
- Não afiliado à CCP Games
