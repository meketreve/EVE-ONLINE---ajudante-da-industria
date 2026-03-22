# EVE Industry Tool

Aplicação **desktop local** para industrialistas do **EVE Online** calcularem custos de produção, margens de lucro e oportunidades de importação. Integra com EVE SSO (OAuth2) e ESI API para dados ao vivo de personagem, mercado e estruturas.

Interface gráfica nativa via **NiceGUI** — abre como janela desktop, sem browser externo.

---

## Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| **Calculadora de Produção** | BOM recursivo, ME por item, bônus de estrutura, job cost (SCI + facility tax + SCC), taxas, lucro bruto e líquido |
| **Comparação de Preços no BOM** | Mercado ativo vs Jita/Amarr por material — identifica o que vale importar |
| **Reprocessamento** | Calcula se vale reprocessar o item ou vendê-lo diretamente |
| **Fila de Produção** | Jobs planejados com BOM agregado — lista de compras unificada |
| **Ranking de Importação** | Itens com maior margem entre mercado fonte e local, com frete |
| **Projeção de Mercado** | Histórico ESI com charts de volume e preço, projeção 7/14/30 dias |
| **Estruturas de Manufatura** | Cadastro de Raitaru/Azbel/Sotiyo com bônus ME/TE |
| **Descoberta de Estruturas** | Escaneia assets pessoais para encontrar citadelas acessíveis |
| **Mercados Privados** | Crawl automático a cada 15 min de ordens de estruturas Upwell |
| **Login via EVE SSO** | Acesso a skills, assets e mercados privados do personagem |

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| GUI | NiceGUI (`native=True`) + pywebview |
| Backend | Python 3.11+, SQLAlchemy async |
| Banco | SQLite (WAL mode, aiosqlite) |
| Auth | EVE SSO (OAuth2) |
| Dados EVE | ESI API + SDE (Static Data Export) |

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
EVE_CALLBACK_URL=http://localhost:8765/auth/callback
SECRET_KEY=uma_chave_secreta_aleatoria_longa
```

### 5. Importar dados do SDE

Baixa e importa itens, blueprints e materiais do Static Data Export (apenas uma vez):

```bash
# Windows
1_importar_sde.bat

# Direto
python eve_industry_tool/scripts/import_sde.py
```

### 6. Iniciar o app

```bash
# Windows
3_iniciar.bat

# Direto
python eve_industry_tool/app/main.py
```

A janela desktop abre automaticamente.

---

## Estrutura do Projeto

```
eve_industry_tool/
├── app/
│   ├── main.py                    # Entry point NiceGUI (native=True)
│   ├── config.py                  # Configurações e variáveis de ambiente
│   ├── ui/                        # Páginas e componentes NiceGUI
│   │   ├── auth_page.py           # Login EVE SSO
│   │   ├── dashboard_page.py      # Dashboard inicial
│   │   ├── items_page.py          # Browser de itens
│   │   ├── industry_page.py       # Calculadora de produção + BOM
│   │   ├── reprocessing_page.py   # Calculadora de reprocessamento
│   │   ├── queue_page.py          # Fila de produção
│   │   ├── ranking_page.py        # Ranking de importações
│   │   ├── ranking_item_page.py   # Projeção de mercado com charts
│   │   ├── market_page.py         # Estruturas e status de cache
│   │   ├── discovery_page.py      # Descoberta de estruturas
│   │   ├── settings_page.py       # Configurações + estruturas de manufatura
│   │   └── components/
│   │       ├── bom_tree.py        # Árvore BOM expansível
│   │       ├── cost_breakdown.py  # Painel custo/lucro
│   │       ├── structure_selector.py
│   │       └── price_chart.py     # Charts ECharts
│   ├── services/                  # Lógica de negócio
│   │   ├── esi_client.py
│   │   ├── market_service.py
│   │   ├── industry_calculator.py
│   │   ├── blueprint_service.py
│   │   ├── crawler_service.py
│   │   ├── discovery_service.py
│   │   ├── job_runner.py
│   │   └── character_service.py
│   ├── models/                    # ORM SQLAlchemy
│   └── database/
│       └── database.py
├── scripts/
│   ├── import_sde.py
│   ├── atualizar_estruturas.py
│   ├── atualizar_precos_mercado.py
│   └── ordens_null.py
├── requirements.txt
└── .env                           # Credenciais (não versionar)
```

---

## Scripts Auxiliares

```bash
# Descobrir estruturas Upwell via ESI
2_atualizar_estruturas.bat
# ou: python eve_industry_tool/scripts/atualizar_estruturas.py

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

### Margem de Importação
```
Margem = preço_local × (1 - sales_tax - broker_fee) - preço_fonte - frete/un.
```

---

## Observações

- O banco (`database.db`) é criado automaticamente na primeira execução
- Migrations de schema rodam no startup sem destruir dados existentes
- Todos os dados ficam locais — nada é enviado além da ESI oficial da CCP
- A ESI não expõe rigs de estruturas; o cadastro de bônus ME/TE é manual
- Não afiliado à CCP Games
