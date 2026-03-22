# EVE Online — Ajudante da Indústria: Análise Completa do Projeto

## 1. Visão Geral

Aplicação **desktop local** para industrialistas de EVE Online calcularem custos de produção, margens de lucro e oportunidades de importação. Integra com EVE SSO (OAuth2) e ESI API para dados ao vivo de personagem, mercado e estruturas.

**Status**: Funcional, em desenvolvimento ativo. Todos os 12 itens do todo.md marcados como DONE.

**Formato**: Programa local com interface gráfica nativa (janela desktop), sem necessidade de browser externo.

---

## 2. Stack Tecnológico

### Stack Nova (GUI Desktop)

| Camada | Tecnologia | Motivo da Escolha |
|--------|-----------|-------------------|
| **GUI** | **NiceGUI** (`native=True`) | Python puro, janela desktop nativa via pywebview, Material Design, async integrado, charts nativos |
| **Lógica de Negócio** | Python 3.11+ (mantido) | Sem mudanças — services reutilizados 100% |
| **Banco de Dados** | SQLite + SQLAlchemy async (mantido) | Sem mudanças |
| **Autenticação** | EVE SSO (OAuth2) | Callback interceptado pelo servidor embutido do NiceGUI |
| **APIs Externas** | ESI API + SDE (mantido) | Sem mudanças |
| **Charts** | NiceGUI ECharts / Plotly | Integrado nativamente, substitui Chart.js |
| **HTTP interno** | NiceGUI built-in server | Substitui FastAPI — não exposto ao usuário |

### Stack Anterior (Web) — Substituída

| Camada | Tecnologia Removida | Substituída Por |
|--------|--------------------|--------------------|
| Framework web | FastAPI + Uvicorn | NiceGUI (servidor embutido, invisível) |
| Templates | Jinja2 + HTMX | Componentes Python do NiceGUI |
| Estilização | CSS manual + Chart.js | Material Design 3 (automático) + ECharts |
| Rotas HTTP | `api/*.py` (8 arquivos) | Páginas NiceGUI (`ui.page`) |

### Por que NiceGUI?

- **Zero HTML/CSS/JS** para escrever — tudo em Python
- **`native=True`** abre como janela desktop real (sem browser visível)
- **Async nativo** — compatível com `aiosqlite` e `httpx` sem adaptação
- **Componentes prontos**: tabelas, formulários, diálogos, tabs, notificações
- **Charts**: ECharts e Plotly integrados (substitui Chart.js)
- **Mantém 100%** de `services/`, `models/`, `database/` sem alteração
- **OAuth2**: o servidor embutido recebe o callback do EVE SSO normalmente

---

## 3. Estrutura de Diretórios

### Nova Estrutura (GUI Desktop com NiceGUI)

```
eve_industry_tool/
├── app/
│   ├── main.py                          # Ponto de entrada NiceGUI (ui.run native=True)
│   ├── config.py                        # Configurações, credenciais EVE, URLs ESI (mantido)
│   ├── ui/                              # Páginas e componentes NiceGUI (substitui api/ + templates/)
│   │   ├── auth_page.py                 # Tela de login EVE SSO (abre browser OAuth2)
│   │   ├── items_page.py                # Browser de itens com busca
│   │   ├── industry_page.py             # Calculadora de custo + resultado
│   │   ├── market_page.py               # Overview de mercado e estruturas
│   │   ├── settings_page.py             # Configurações do app
│   │   ├── reprocessing_page.py         # Calculadora de reprocessamento
│   │   ├── ranking_page.py              # Ranking de importações
│   │   ├── ranking_item_page.py         # Projeção de mercado com charts
│   │   ├── queue_page.py                # Fila de produção
│   │   ├── discovery_page.py            # Descoberta de estruturas
│   │   └── components/                  # Componentes reutilizáveis
│   │       ├── bom_tree.py              # Árvore BOM recursiva
│   │       ├── materials_table.py       # Tabela de materiais com preços
│   │       ├── cost_breakdown.py        # Painel de custo/lucro
│   │       ├── structure_selector.py    # Dropdown de estruturas
│   │       └── price_chart.py           # Chart de preço/volume (ECharts)
│   ├── services/                        # Camada de lógica de negócio (MANTIDA INTEIRA)
│   │   ├── esi_client.py               # Sem alteração
│   │   ├── industry_calculator.py      # Sem alteração
│   │   ├── blueprint_service.py        # Sem alteração
│   │   ├── market_service.py           # Sem alteração
│   │   ├── character_service.py        # Sem alteração
│   │   ├── discovery_service.py        # Sem alteração
│   │   ├── crawler_service.py          # Sem alteração
│   │   └── job_runner.py               # Sem alteração
│   ├── models/                          # ORM SQLAlchemy (MANTIDO INTEIRO)
│   │   ├── user.py
│   │   ├── character.py
│   │   ├── item.py
│   │   ├── blueprint.py
│   │   ├── production_queue.py
│   │   ├── user_settings.py
│   │   ├── manufacturing_structure.py
│   │   ├── cache.py
│   │   ├── market_order.py
│   │   ├── market_snapshot.py
│   │   ├── market_structure.py
│   │   ├── structure.py
│   │   ├── job.py
│   │   └── reprocessing.py
│   └── database/
│       └── database.py                  # Sem alteração
├── scripts/                             # Scripts utilitários (mantidos)
│   ├── import_sde.py
│   ├── atualizar_estruturas.py
│   ├── atualizar_precos_mercado.py
│   └── ordens_null.py
├── database.db
├── requirements.txt
└── .env

REMOVIDO:
├── app/api/          # Substituído por app/ui/
├── app/templates/    # Substituído por componentes Python NiceGUI
├── static/style.css  # Substituído por estilo automático Material Design
```

### O que muda vs. o que fica igual

| Componente | Ação | Detalhe |
|-----------|------|---------|
| `app/api/*.py` | **Removido** | Substituído por `app/ui/*.py` |
| `app/templates/*.html` | **Removido** | Substituído por componentes NiceGUI Python |
| `static/style.css` | **Removido** | Material Design automático |
| `app/main.py` | **Reescrito** | `ui.run(native=True, ...)` em vez de `uvicorn` |
| `app/services/*.py` | **Mantido** | Zero alterações necessárias |
| `app/models/*.py` | **Mantido** | Zero alterações necessárias |
| `app/database/*.py` | **Mantido** | Zero alterações necessárias |
| `scripts/*.py` | **Mantido** | Zero alterações necessárias |
| `config.py` | **Mantido** | Zero alterações necessárias |

---

## 4. Schema do Banco de Dados (18 Tabelas)

| Tabela | Propósito | Status |
|--------|----------|--------|
| `users` | Contas de usuário | Completo |
| `characters` | Personagens EVE + tokens OAuth | Completo |
| `items` | Catálogo de itens (SDE) | Completo |
| `blueprints` | Especificações de blueprints | Completo |
| `blueprint_materials` | Requisitos de materiais | Completo |
| `production_queue` | Fila de produção do usuário | Completo |
| `user_settings` | Configurações globais do app | Completo |
| `market_price_cache` | Cache de preços (TTL 5 min) | Completo |
| `market_orders_raw` | Ordens brutas dos crawls | Completo |
| `market_snapshots` | Dados agregados de mercado por estrutura | Completo |
| `structures` | Metadata de estruturas Upwell | Completo |
| `structure_discovery_sources` | Auditoria de descoberta | Completo |
| `market_structures` | Índice de estruturas descobertas | Completo |
| `structure_cache` | Cache de info de estruturas (TTL 24h) | Completo |
| `skill_cache` | Skills de personagens (TTL 1h) | Completo |
| `manufacturing_structures` | Complexos de manufatura registrados manualmente | Completo |
| `discovery_jobs` | Histórico de jobs de descoberta | Completo |
| `crawl_jobs` | Histórico de jobs de crawl | Completo |
| `reprocessing_materials` | Rendimentos de reprocessamento | Completo |

**Pragmas SQLite**:
- `PRAGMA journal_mode=WAL` — leitores não bloqueiam escritores
- `PRAGMA synchronous=NORMAL` — seguro com WAL, mais rápido que FULL
- `PRAGMA busy_timeout=30000` — aguarda até 30s por locks

**Migrations** (em `database.py → create_tables()`):
- `total_volume` em `market_price_cache`
- `default_freight_cost_per_m3` em `user_settings`
- `portion_size` em `items`
- `default_structure_me_bonus` e `default_structure_te_bonus` em `user_settings`

---

## 5. Telas e Navegação (NiceGUI)

No modelo desktop com NiceGUI, não há rotas HTTP expostas ao usuário. A navegação é feita via `ui.navigate.to()` ou `ui.tabs` dentro da janela. O servidor embutido do NiceGUI trata apenas o callback OAuth2 internamente.

### Estrutura de Navegação

```
Janela Principal (native=True)
├── [Tabs laterais ou topo]
│   ├── 🏠 Dashboard
│   ├── 🔧 Calculadora de Produção
│   │   └── Detalhe de item (painel expansível)
│   ├── 🔄 Reprocessamento
│   ├── 📦 Fila de Produção
│   ├── 📈 Ranking de Importações
│   │   └── Projeção de Mercado (sub-painel com charts)
│   ├── 🏪 Mercado
│   ├── 🏭 Estruturas de Manufatura
│   ├── 🔍 Descoberta de Estruturas
│   └── ⚙️ Configurações
└── [Status bar]: personagem logado, última atualização, jobs em execução
```

### Páginas e Ações

| Página | Arquivo | Ações |
|--------|---------|-------|
| **Login** | `auth_page.py` | Abre browser EVE SSO, aguarda callback, fecha browser |
| **Itens** | `items_page.py` | Busca por nome, filtro por categoria, clique → Calculadora |
| **Calculadora** | `industry_page.py` | Formulário de runs/ME/estrutura, resultado em painel lateral |
| **Reprocessamento** | `reprocessing_page.py` | Input de item + yield, exibe listas reprocessar/vender |
| **Fila** | `queue_page.py` | Adicionar itens, remover, "Ver Lista de Compras" (BOM agregado) |
| **Ranking** | `ranking_page.py` | Tabela de oportunidades, clicar → projeção de mercado |
| **Projeção** | `ranking_item_page.py` | Charts ECharts de volume e preço histórico |
| **Mercado** | `market_page.py` | Estruturas conhecidas, stats de cache, botão refresh |
| **Estruturas Manufatura** | `components/structure_selector.py` | CRUD: adicionar/remover Raitaru/Azbel/Sotiyo |
| **Descoberta** | `discovery_page.py` | Disparar descoberta, listar estruturas, histórico de jobs |
| **Configurações** | `settings_page.py` | Todos os campos de taxas, fonte de mercado, frete, ME/TE |

### Rota Interna OAuth2 (invisível ao usuário)

O NiceGUI expõe um endpoint HTTP interno para receber o callback do EVE SSO:

```python
# Em main.py — registrado no servidor embutido NiceGUI
app.add_route("/auth/callback", handle_oauth_callback)
```

O usuário nunca vê URLs — o browser abre automaticamente para login e fecha após autenticação.

---

## 6. Lógica de Negócio Principal

### Custo de Produção
```
Custo de Material = Σ(quantidade × preço_material)
Custo de Job      = system_cost_index + facility_tax + SCC_surcharge
Custo Total       = Custo de Material + Custo de Job + broker_fee + sales_tax + logistics + freight
```

### Lucro
```
Lucro Bruto = preço_venda - custo_produção
Lucro Líquido = preço_venda - custo_produção - taxas - tarifas
```

### ME Efficiency
```
quantidade_ajustada = ceil(qty × (1 - bp_me/100) × (1 - structure_me/100))
```

### Ranking de Importações
```
Margem de Importação = preço_local_sell - (preço_fonte_sell + freight_cost_por_m3 × volume) - taxas
```

### Taxas de Negociação (via Skills)
- Lê `Broker Relations` e `Accounting` da ESI (cache 1h)
- Sobrescreve taxas padrão no cálculo de custo/lucro

---

## 7. Serviços

### ESI Client (`esi_client.py`)
- Troca de código OAuth2 e refresh de token
- Endpoints: character info, skills, blueprints, market orders, estruturas, assets
- `ESIError` com status codes e retry logic

### Industry Calculator (`industry_calculator.py`)
- `calculate_production_cost()` — materiais + job cost
- `calculate_profit()` — lucro líquido após taxas
- `apply_me_level()` — redução de quantidade por ME

### Blueprint Service (`blueprint_service.py`)
- `get_blueprint_by_product()` — busca blueprint que produz um item
- `get_blueprint_materials()` — materiais com ME aplicado
- `get_recursive_bom()` — expansão recursiva de componentes
- `BOMNode` — estrutura de árvore com quantidades, ME, flags buy-as-is
- `aggregate_bom_leaves()` — soma quantidades de folhas
- Suporte a: ME por item, flags buy-as-is, bônus de estrutura, detecção de ciclos

### Market Service (`market_service.py`)
- `get_prices_cache_only()` — lê cache sem chamar ESI
- `refresh_prices_for_types()` — força refresh via ESI
- `get_best_price()` — melhor sell/buy em uma região
- `get_prices_for_materials()` — preços em lote para materiais
- TTLs: 5 min para regiões públicas, 4h para estruturas privadas

### Character Service (`character_service.py`)
- `get_fresh_token()` — refresh automático se expirado
- `get_trading_fees_for_character()` — calcula taxas reais via skills ESI
- `get_market_options()` — grupos de mercado público + estruturas privadas

### Discovery Service (`discovery_service.py`)
- `enqueue_asset_discovery()` — fila job de descoberta via assets
- Ciclo de vida: `discovered` → `resolved` → `market_accessible` / `market_denied` / `inactive`
- IDs de estrutura Upwell: `location_id >= 1,000,000,000,000`

### Crawler Service (`crawler_service.py`)
- `run_crawl_job()` — executa crawl de uma estrutura
- `schedule_recrawl_all()` — scheduler: recrawl todas estruturas acessíveis
- `cleanup_stale_orders()` — remove ordens com mais de 48h
- `_aggregate_snapshots()` — calcula melhor sell/buy, volumes, spread %

### Job Runner (`job_runner.py`)
- Fila async in-memory sem Redis
- `discovery_runner` — 3 workers para descoberta de assets
- `crawl_runner` — 2 workers para crawl de mercado
- Deduplicação por job_id

---

## 8. Scheduler (Tarefas Agendadas)

| Intervalo | Tarefa | Serviço |
|-----------|--------|---------|
| 15 min | Recrawl de estruturas | `crawler_service.schedule_recrawl_all()` |
| 1 hora | Limpeza de ordens antigas | `crawler_service.cleanup_stale_orders()` |
| 6 horas | Redescoberta de estruturas | `discovery_service._do_asset_discovery_all()` |

---

## 9. Autenticação e Segurança

**Fluxo OAuth2**:
1. Usuário clica "Login com EVE"
2. Redireciona para EVE SSO com state token (proteção CSRF)
3. Callback troca código por tokens
4. Tokens armazenados no DB (tabela character)
5. Sessão configurada (cookie 7 dias, assinado com `itsdangerous`)

**Scopes ESI necessários**:
```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-markets.structure_markets.v1
esi-universe.read_structures.v1
esi-corporations.read_structures.v1
esi-assets.read_assets.v1
```

**Token Refresh**: automático em resposta 401, proativo 60s antes do vencimento.

---

## 10. Configurações

**Defaults** (sobrescrevíveis via `/settings`):
```python
"default_market_source":        "region:10000002"  # Jita
"default_me_level":             0
"default_system_cost_index":    0.05    # 5%
"default_facility_tax":         0.0
"default_scc_surcharge":        0.015   # 1.5% (fixo)
"default_broker_fee_pct":       0.03    # 3%
"default_sales_tax_pct":        0.08    # 8%
"default_price_source":         "sell"
"default_freight_cost_per_m3":  0.0
"default_structure_me_bonus":   0.0
"default_structure_te_bonus":   0.0
```

**Variáveis de Ambiente** (`.env`):
```env
EVE_CLIENT_ID=
EVE_CLIENT_SECRET=
EVE_CALLBACK_URL=http://localhost:8000/auth/callback
SECRET_KEY=
```

---

## 11. TTLs de Cache

| Dado | TTL | Storage |
|------|-----|---------|
| Preços de mercado regional (público) | 5 minutos | `market_price_cache` |
| Mercado de estruturas privadas | 4 horas | `market_orders_raw` + `market_snapshots` |
| Skills de personagem | 1 hora | `skill_cache` |
| Info de estrutura | 24 horas | `structure_cache` |

---

## 12. Features Implementadas (Status)

### Completo e Funcional

1. **Autenticação EVE SSO** — OAuth2 completo com refresh de token
2. **Calculadora de Custo de Produção** — simples e recursivo (BOM expandido)
3. **Calculadora de Reprocessamento** — compara vender vs. reprocessar, gera lista para busca in-game
4. **BOM Recursivo** — expansão de componentes com sub-componentes fabricáveis
5. **Flags Buy-as-is** — marca itens para comprar ao invés de fabricar
6. **ME por Item** — eficiência material global + override por item individual
7. **Registro de Estruturas de Manufatura** — CRUD com bônus ME/TE configuráveis (já que ESI não expõe rigs)
8. **Comparação de Preços Side-by-Side** — mercado local vs. Jita/Amarr por material
9. **Fila de Produção com BOM Agregado** — lista de compras total de toda a fila
10. **Ranking de Importações** — compara mercado fonte vs. local, identifica oportunidades
11. **Projeção de Mercado** — histórico ESI (7/14/30 dias), charts de volume e preço, projeções
12. **Descoberta Automática de Estruturas** — via assets do personagem, com crawl automático
13. **Persistência de Configurações** — todas as taxas, fontes de preço, bônus de estrutura

### Em Desenvolvimento / Notas

- Campo de frete adicionado às configurações
- Bônus ME/TE de estruturas de manufatura totalmente integrado
- Campo `total_volume` no cache de preços para analytics futuro

### Limitações Conhecidas

- Invenção T2 incompleta (requer modelo de chance de sucesso, datacores, decryptors)
- ESI não expõe rigs de estruturas → entrada manual de ME/TE necessária
- Não é produto oficial da CCP Games

---

## 13. Scripts Utilitários

### `import_sde.py`
- Import único dos dados SDE (EVERef ou Fuzzwork)
- Popula: items, blueprints, materiais, rendimentos de reprocessamento
- `python scripts/import_sde.py`

### `atualizar_estruturas.py`
- Descobre estruturas Upwell via ESI
- Fontes: assets pessoais, assets corporativos, estruturas públicas, jobs de indústria
- `python scripts/atualizar_estruturas.py [--fonte assets|all]`

### `atualizar_precos_mercado.py`
- Refresh manual do cache de preços para Jita, Amarr, Dodixie, Rens, Hek
- `python scripts/atualizar_precos_mercado.py`

### `ordens_null.py`
- Import de ordens de estruturas null-sec diretamente
- `python scripts/ordens_null.py [--listar | --id STRUCTURE_ID]`

---

## 14. Componentes de UI (NiceGUI)

Todos os componentes são escritos em Python puro. Sem HTML, sem CSS manual, sem JavaScript.

### Padrão de Componente NiceGUI

```python
# Exemplo: calculadora de produção
@ui.page('/industry')
async def industry_page():
    with ui.tabs() as tabs:
        ui.tab('Calculadora')
        ui.tab('Ranking')
    with ui.tab_panels(tabs):
        with ui.tab_panel('Calculadora'):
            item_input = ui.select(options=items_list, label='Item')
            runs_input = ui.number(label='Runs', value=1)
            me_input   = ui.slider(min=0, max=10, label='ME Level')
            ui.button('Calcular', on_click=calculate)
        # resultado aparece em ui.card() atualizado via ui.update()
```

### Mapeamento de Telas → Componentes

| Tela Antiga (HTML) | Componente NiceGUI | Elementos Principais |
|--------------------|--------------------|----------------------|
| `items.html` | `items_page.py` | `ui.input` (busca), `ui.table` (lista), `ui.select` (categoria) |
| `item_detail.html` | `industry_page.py` | `ui.select`, `ui.number`, `ui.slider`, `ui.card`, `ui.tree` (BOM) |
| `reprocessing.html` | `reprocessing_page.py` | `ui.select`, `ui.number`, `ui.table` |
| `production_queue.html` | `queue_page.py` | `ui.table`, `ui.button`, `ui.dialog` (BOM agregado) |
| `ranking.html` | `ranking_page.py` | `ui.table` com filtros, `ui.badge` (lucro/prejuízo) |
| `ranking_item.html` | `ranking_item_page.py` | `ui.echart` (volume), `ui.echart` (preço), `ui.table` (histórico) |
| `market.html` | `market_page.py` | `ui.table` (estruturas), `ui.button` (refresh), `ui.badge` (status) |
| `settings.html` | `settings_page.py` | `ui.number`, `ui.select`, `ui.switch`, `ui.button` |
| `login.html` | `auth_page.py` | `ui.button` (abre browser OAuth2), `ui.spinner` (aguardando) |
| Partials HTMX | `components/*.py` | Funções Python que retornam elementos `ui.*` |

### Charts (substitui Chart.js)

```python
# ECharts integrado no NiceGUI
ui.echart({
    'xAxis': {'type': 'category', 'data': dates},
    'yAxis': {'type': 'value'},
    'series': [{'type': 'bar', 'data': volumes}]
})
```

---

## 15. Dependências

### Nova (GUI Desktop)

```
nicegui              # Framework GUI desktop (inclui servidor web embutido)
pywebview            # Renderiza janela nativa (usado pelo nicegui native=True)
sqlalchemy[asyncio] # ORM + async (mantido)
aiosqlite            # Driver SQLite async (mantido)
httpx                # Cliente HTTP async (mantido)
python-dotenv       # Suporte a .env (mantido)
```

### Removidas

```
fastapi              # REMOVIDO — NiceGUI tem servidor embutido
uvicorn[standard]   # REMOVIDO — não necessário
jinja2               # REMOVIDO — UI em Python puro
python-multipart    # REMOVIDO — formulários via componentes NiceGUI
itsdangerous        # REMOVIDO — sessão gerenciada pelo NiceGUI storage
```

---

## 16. Fluxo de Dados

```
Janela Desktop (NiceGUI native=True)
        │ evento (clique, input)
        ↓
  Página NiceGUI (ui/*)
        │ chama diretamente
        ↓
  Services Layer (services/*.py)  ←→  SQLite DB (aiosqlite)
        │                                    ↕
        ↓                              ESI API (httpx)
  Atualiza componentes UI                    ↕
  (ui.update / ui.notify)             SDE (import único)
```

**Exemplo — Cálculo de Custo (novo fluxo)**:
1. Usuário preenche formulário na janela (item, runs, ME, estrutura)
2. Clica "Calcular" → chama função Python diretamente (sem HTTP)
3. Função: carrega settings → busca blueprint → `get_recursive_bom()` → `get_prices_cache_only()` → `calculate_production_cost()` → atualiza `ui.card` com resultado
4. UI atualiza instantaneamente (sem reload, sem HTMX)

**Fluxo OAuth2**:
1. Usuário clica "Login com EVE" na janela
2. `webbrowser.open(eve_sso_url)` — abre browser padrão do sistema
3. EVE SSO redireciona para `http://localhost:PORT/auth/callback`
4. Servidor embutido NiceGUI captura o código
5. Troca por tokens, salva no DB, notifica a janela via `ui.notify`
6. Browser pode ser fechado

---

## 17. Comandos

```bash
# Instalar dependências
pip install -r requirements.txt

# Import SDE (uma vez)
python scripts/import_sde.py

# Rodar o app (abre janela desktop)
python app/main.py

# Rodar testes
pytest

# Lint
ruff check .
```

**`main.py` (estrutura básica)**:
```python
from nicegui import ui, app as nicegui_app
from app.ui import auth_page, items_page, industry_page  # etc.

# Registrar callback OAuth2
nicegui_app.add_route("/auth/callback", handle_oauth_callback)

# Iniciar scheduler e job runners no startup
@nicegui_app.on_startup
async def startup():
    await init_db()
    start_scheduler()

ui.run(
    native=True,          # abre como janela desktop (não browser)
    title="EVE Industry Tool",
    window_size=(1400, 900),
    reload=False,
)
```

---

## 18. Itens Todo (Status)

Todos os 12 itens do `todo.md` estão marcados como **DONE**:

1. Comparação de preços side-by-side para itens do BOM ✓
2. Fila de produção aprimorada com lista de materiais agregada ✓
3. ME por item do BOM (não só global) ✓
4. Cálculo recursivo de BOM (componentes de componentes) ✓
5. Flag para comprar item ao invés de fabricar ✓
6. Projeção de mercado com janelas de tempo configuráveis (1 sem / 2 sem / 1 mês) ✓
7. Updates de preço baseados em banco de dados para BOM (evitar chamadas ESI no meio do cálculo) ✓
8. Bônus de estrutura de manufatura (ME, TE) nas configurações ✓
9. Detecção automática de rigs de estrutura via assets pessoais ✓ (substituído por registro manual)
10. Registro de estruturas com entrada manual de bônus ✓
11. Gráficos de volume de mercado e análise preditiva ✓
12. Estruturas de manufatura (modelo ManufacturingStructure, CRUD, UI) ✓

---

## 19. Possíveis Melhorias Futuras

### Funcionalidades de Negócio
1. **Invenção T2** — modelo de sucesso, datacores, decryptors
2. **Histórico de Preços Persistente** — snapshots diários para tendências de longo prazo
3. **Bônus por Estação** — distinção entre bônus de rigs vs. base da estrutura
4. **Arbitragem Multi-Região** — comparação simultânea entre múltiplas regiões

### Melhorias de GUI (NiceGUI)
5. **System Tray** — app minimiza para bandeja do sistema, roda crawls em background
6. **Notificações Desktop** — alerta quando oportunidade de importação lucrativa aparece
7. **Tema Escuro/Claro** — NiceGUI suporta dark mode nativo
8. **Atalhos de Teclado** — navegação entre telas sem mouse
9. **Exportar para CSV/Excel** — `ui.download` com pandas para listas de materiais e fila
10. **Drag-and-drop na Fila** — reordenar itens da fila de produção visualmente

### Infraestrutura
11. **Backup do Banco** — mecanismo automático de backup do `database.db`
12. **Auto-updater** — verificação de nova versão ao iniciar

---

## 20. Otimizações de Banco de Dados e API

### Legenda de Severidade
- **CRÍTICO** — afeta performance do usuário diretamente, corrigir antes de tudo
- **Alto** — impacto mensurável em operações frequentes
- **Médio** — overhead real mas não bloqueia uso
- **Baixo** — boa prática, impacto pequeno

---

### 20.1 Banco de Dados — Problemas e Correções

#### CRÍTICO — N+1 Queries no BOM Recursivo
**Arquivo**: `services/blueprint_service.py`, linhas 86–88, 121–123, 144–146

**Problema**: Dentro do loop de recursão, uma query separada é executada para cada `type_id` de item:
```python
# Executado para cada nó da árvore BOM
item_row = await db.execute(select(Item).where(Item.type_id == product_type_id))
item = item_row.scalar_one_or_none()
```
Para um BOM de 3 níveis com 50 materiais, isso gera 50–100 queries `SELECT` na tabela `items`.

**Correção**: Coletar todos os `type_id` necessários em uma passagem prévia, buscar em lote com `IN`, depois usar dicionário em memória durante a recursão:
```python
# 1 query ao invés de 50
all_ids = collect_all_type_ids(blueprint_id)
items_map = {r.type_id: r for r in await db.execute(
    select(Item).where(Item.type_id.in_(all_ids))
).scalars().all()}
# recursão usa items_map[type_id] — sem queries adicionais
```

---

#### Alto — Índices Compostos Ausentes

**Problema 1 — `market_orders_raw`**
**Arquivo**: `models/market_order.py`, `services/crawler_service.py`, linha ~287

A query de snapshot filtra por `structure_id + is_stale`:
```python
select(...).where(
    MarketOrder.structure_id == structure_id,
    MarketOrder.is_stale == False,
)
```
Sem índice composto, SQLite faz full table scan. Com 10k+ ordens por estrutura o custo é O(n).

**Correção**:
```python
# Em models/market_order.py
__table_args__ = (
    Index("ix_orders_structure_stale_type", "structure_id", "is_stale", "type_id"),
)
```

**Problema 2 — `structures`**
**Arquivo**: `models/structure.py`, `services/crawler_service.py`, linha ~386

Query de recrawl filtra e ordena:
```python
select(Structure.structure_id, Structure.last_crawled_at)
    .where(Structure.status == "market_accessible")
    .order_by(Structure.last_crawled_at.asc().nullsfirst())
```
O `ORDER BY` obriga SQLite a ordenar em memória os resultados filtrados.

**Correção**:
```python
Index("ix_structures_status_crawled", "status", "last_crawled_at")
```

**Problema 3 — `market_price_cache`**
**Arquivo**: `models/cache.py`, `services/market_service.py`, linha ~390

A `UniqueConstraint("type_id, market_type, market_id, order_type")` existe, mas queries de leitura em lote filtram por `(market_type, market_id, order_type)` sem `type_id` primeiro — o índice da constraint não é usado eficientemente.

**Correção**: Índice separado para leituras em lote:
```python
Index("ix_price_cache_market", "market_type", "market_id", "order_type")
```

---

#### Médio — Double Cache Read na Calculadora
**Arquivo**: `api/industry.py`, linhas 166–191

Preços dos materiais são lidos do cache duas vezes: uma leitura inicial e uma segunda após possível refresh, mesmo quando `force_refresh=False` e os dados já estavam no cache.

**Correção**: Reutilizar o resultado da primeira leitura se não houver cache miss:
```python
mat_prices, mat_age = await get_prices_cache_only(mat_ids, ...)
if has_missing and force_refresh:
    await refresh_prices_for_types(missing_ids, ...)
    mat_prices, mat_age = await get_prices_cache_only(mat_ids, ...)  # só re-lê se necessário
```

---

#### Médio — 100 Tasks Async Paralelas para Leitura de Cache
**Arquivo**: `services/market_service.py`, linhas 229–236

```python
cached_results = await asyncio.gather(
    *[_read_price_cache(db, tid, ...) for tid in type_ids]  # 1 task por type_id
)
```
Para 100 materiais, cria 100 tasks concorrentes de leitura no SQLite. O overhead de criação de tasks supera o benefício — o aiosqlite serializa internamente de qualquer forma.

A função `get_prices_cache_only()` (linhas 125–138) já faz isso corretamente com um único `IN`. A chamada acima é redundante e mais lenta.

**Correção**: Substituir por uma única query batch com `IN`, igual ao padrão de `get_prices_cache_only()`.

---

#### Médio — Commits Excessivos no Crawler
**Arquivo**: `services/crawler_service.py`, linhas 205–241

Commit a cada 500 ordens:
```python
for i in range(0, len(orders), 500):
    for o in batch:
        await db.execute(...)  # um por um
    await db.commit()  # 1 commit por batch de 500
```
Para uma estrutura com 20.000 ordens = 40 commits. Cada commit faz flush do WAL.

**Correção**: Executar todos os inserts e um único `db.commit()` no final. O WAL mode do SQLite já garante atomicidade. Se a proteção contra lock longo for necessária, usar batches de 2.000 com 10 commits ao invés de 40.

---

#### Baixo — Inserts Individuais na Descoberta
**Arquivo**: `services/discovery_service.py`, linhas 146–178

Para cada estrutura descoberta, 2 `execute()` separados. Para 100 estruturas = 200 calls.

**Correção**: Bulk insert com `INSERT INTO ... VALUES (...), (...), (...)`:
```python
await db.execute(
    insert(Structure).values([
        {"structure_id": sid, ...} for sid in candidate_ids
    ]).prefix_with("OR IGNORE")
)
```

---

#### Baixo — Crescimento Ilimitado de `market_snapshots`
**Arquivo**: `models/market_snapshot.py`, `services/crawler_service.py`

Upserts de snapshots nunca purgam entradas de itens que deixaram de ser negociados na estrutura. O banco cresce 1–10 MB/mês dependendo da atividade.

**Correção**: No scheduler de limpeza (já existe em `cleanup_stale_orders`), adicionar:
```python
# Remove snapshots de itens sem ordens ativas há mais de 7 dias
await db.execute(text("""
    DELETE FROM market_snapshots
    WHERE (structure_id, type_id) NOT IN (
        SELECT structure_id, type_id FROM market_orders_raw
        WHERE is_stale = 0
    )
"""))
```

---

#### Baixo — Migrations Silenciam Todos os Erros
**Arquivo**: `app/database/database.py`, linhas 70–82

```python
except Exception:
    pass  # silencia tudo: typos, permission errors, deadlocks
```

**Correção**: Capturar apenas o erro esperado:
```python
import sqlite3
except Exception as e:
    if "already exists" not in str(e).lower():
        raise  # relança erros reais
```

---

### 20.2 ESI API — Problemas e Correções

#### Alto — Paginação Sequencial (Páginas 1 a N)
**Arquivo**: `services/esi_client.py`, linhas 67–95

A função `_get_paginated()` busca páginas uma a uma:
```python
while page <= total_pages:
    response = await self.client.get(url, params={"page": page})
    page += 1  # aguarda página atual antes de pedir a próxima
```

**Impacto real**:
- Estrutura com 8 páginas de ordens: 8 × ~150ms = **~1,2 segundos**
- Com concorrência: páginas 2–8 em paralelo = **~300ms** (4× mais rápido)

**Correção**: Buscar a página 1 primeiro (para obter `X-Pages`), depois buscar as demais em paralelo com semáforo:
```python
async def _get_paginated(self, url, params=None):
    r1 = await self._get(url, params={**(params or {}), "page": 1})
    total_pages = int(r1.headers.get("X-Pages", 1))
    results = list(r1.json())
    if total_pages > 1:
        sem = asyncio.Semaphore(5)  # máx 5 requests simultâneos
        async def fetch(p):
            async with sem:
                return (await self._get(url, params={**(params or {}), "page": p})).json()
        pages = await asyncio.gather(*[fetch(p) for p in range(2, total_pages + 1)])
        for page in pages:
            results.extend(page)
    return results
```
Afeta: `get_structure_market()`, `get_market_orders()`, `get_character_blueprints()`, `get_character_assets()`.

---

#### Alto — Sem ETags / Requisições Condicionais
**Arquivo**: `services/esi_client.py`, função `_get()`, linha ~54

Toda requisição ESI baixa a resposta completa mesmo que os dados não tenham mudado. A ESI suporta `ETag` / `If-None-Match` — resposta `304 Not Modified` usa ~0% de banda.

**Impacto**: Skills de um personagem raramente mudam, mas são re-baixadas integralmente a cada hora. Ordens regionais de Jita (4k+ itens, ~30 páginas) são baixadas completas a cada 5 min.

**Correção**: Armazenar ETag junto com dados no cache e enviar no próximo request:
```python
# Ao salvar no cache
cache_entry.etag = response.headers.get("ETag")

# Ao requisitar
headers = {}
if cached_entry and cached_entry.etag:
    headers["If-None-Match"] = cached_entry.etag
response = await self.client.get(url, headers=headers)
if response.status_code == 304:
    return cached_entry.data  # sem download
```

---

#### Médio — Race Condition no Refresh de Token
**Arquivo**: `services/character_service.py`, linhas 125–142

Se duas tarefas async verificam `is_token_expired()` ao mesmo tempo e ambas encontram `True`, ambas fazem refresh — duas chamadas ESI desnecessárias, e a segunda pode invalidar o token da primeira (dependendo do servidor OAuth2).

**Correção**: Usar um lock por personagem:
```python
_token_locks: dict[int, asyncio.Lock] = {}

async def get_fresh_token(character, db):
    lock = _token_locks.setdefault(character.character_id, asyncio.Lock())
    async with lock:
        if character.is_token_expired():  # re-checa dentro do lock
            await _do_refresh(character, db)
    return character.access_token
```

---

#### Médio — Crawler Não Lembra Qual Personagem Tem Acesso
**Arquivo**: `services/crawler_service.py`, linhas 73–136

A cada crawl, tenta todos os personagens em ordem até um funcionar com 200. Se o primeiro personagem nunca tem acesso (403), gasta 1 call ESI desnecessária a cada ciclo de 15 minutos.

**Correção**: Armazenar `last_successful_character_id` na tabela `structures` e tentar esse personagem primeiro:
```python
# Em Structure model — adicionar coluna:
last_successful_character_id = Column(BigInteger, nullable=True)

# No crawler:
tokens.sort(key=lambda t: t[0] != structure.last_successful_character_id)
```

---

#### Médio — Assets de Personagens Buscados Sequencialmente
**Arquivo**: `services/discovery_service.py`, linhas 126–128

Com múltiplos personagens, `get_character_assets()` é chamado um a um. Para 5 personagens com paginação, isso é 5 × N páginas de espera serial.

**Correção**: Buscar assets de todos os personagens em paralelo:
```python
asset_lists = await asyncio.gather(*[
    esi_client.get_character_assets(char_id, token)
    for char_id, token in characters
])
```

---

#### Baixo — Token Pode Expirar Durante Crawl Multi-Página
**Arquivo**: `services/crawler_service.py`, linhas 156–186

Se um token expira entre a página 1 e a página 8 do crawl, a requisição falha com 401 e o crawl inteiro precisa ser refeito.

**Correção**: Verificar expiração antes de cada página (ou ao menos a cada 3 páginas):
```python
for page in range(2, total_pages + 1):
    if character.token_expires_in_seconds() < 60:
        token = await get_fresh_token(character, db)
    result = await esi_client.get(url, token=token, page=page)
```

---

### 20.3 Resumo Priorizado (ROI × Esforço)

| # | Problema | Arquivo | Severidade | Ganho Esperado | Esforço |
|---|---------|---------|-----------|----------------|---------|
| 1 | N+1 queries no BOM | `blueprint_service.py:86` | **CRÍTICO** | 50–100 queries → 2 queries | Baixo |
| 2 | Paginação sequencial ESI | `esi_client.py:67` | Alto | 4× mais rápido no crawl | Médio |
| 3 | Índice composto `market_orders_raw` | `models/market_order.py` | Alto | Elimina full table scan | Muito Baixo |
| 4 | Índice composto `structures` | `models/structure.py` | Alto | ORDER BY sem sort em memória | Muito Baixo |
| 5 | Double cache read | `api/industry.py:166` | Médio | -1 query por cálculo | Muito Baixo |
| 6 | 100 tasks paralelas no cache | `market_service.py:229` | Médio | Reduz overhead de tasks | Baixo |
| 7 | Commits excessivos no crawler | `crawler_service.py:241` | Médio | 40 commits → 1 commit | Baixo |
| 8 | ETags ausentes | `esi_client.py:54` | Alto (banda) | Reduz tráfego ESI em 60-80% | Alto |
| 9 | Race condition refresh de token | `character_service.py:125` | Médio | Previne duplo refresh | Baixo |
| 10 | Crawler não lembra personagem | `crawler_service.py:73` | Médio | -1 call ESI por ciclo de 15 min | Baixo |
| 11 | Assets sequenciais | `discovery_service.py:126` | Médio | N× mais rápido (N = personagens) | Muito Baixo |
| 12 | Inserts individuais na descoberta | `discovery_service.py:146` | Baixo | -200ms na descoberta | Baixo |
| 13 | Crescimento ilimitado snapshots | `crawler_service.py:350` | Baixo | Controla tamanho do DB | Muito Baixo |
| 14 | Migrations silenciam erros | `database.py:70` | Baixo | Evita erros ocultos | Muito Baixo |

**Quick wins imediatos (< 30 min cada, itens 3, 4, 5, 11, 13, 14)**: Só adicionar índices e ajustar 3 linhas de código — sem risco de regressão.

---

## 21. Plano de Implementação

O plano é dividido em 5 fases. As fases 1 e 2 não dependem da GUI — podem ser feitas agora, antes de qualquer mudança de interface. As fases 3 e 4 constroem a interface NiceGUI sobre a base já otimizada. A fase 5 adiciona funcionalidades novas.

### Visão Geral das Fases

```
Fase 1 — Quick Wins (banco + API)     [~2h]   sem riscos, ganho imediato
Fase 2 — Otimizações estruturais      [~1 dia] refatora serviços críticos
Fase 3 — Migração para NiceGUI        [~3 dias] substitui api/ + templates/
Fase 4 — Integração e polish          [~1 dia] scheduler, OAuth2, testes
Fase 5 — Novas funcionalidades        [aberto] melhorias pós-migração
```

---

### Fase 1 — Quick Wins de Banco e API
**Pré-requisito**: nenhum | **Risco**: muito baixo | **Tempo estimado**: ~2 horas

Todas as tarefas são mudanças pontuais e independentes. Nenhuma quebra compatibilidade.

#### 1.1 Adicionar índices compostos ausentes
**Arquivos**: `models/market_order.py`, `models/structure.py`, `models/cache.py`

- Adicionar `Index("ix_orders_structure_stale_type", "structure_id", "is_stale", "type_id")` em `MarketOrder`
- Adicionar `Index("ix_structures_status_crawled", "status", "last_crawled_at")` em `Structure`
- Adicionar `Index("ix_price_cache_market", "market_type", "market_id", "order_type")` em `MarketPriceCache`
- Adicionar blocos `ALTER TABLE ... ADD INDEX` correspondentes em `database.py → create_tables()`

#### 1.2 Corrigir double cache read na calculadora
**Arquivo**: `api/industry.py`, linhas 166–191

Envolver a segunda leitura em condicional `if cache_miss and force_refresh`.

#### 1.3 Paralelizar fetch de assets por personagem
**Arquivo**: `services/discovery_service.py`, linhas 126–128

Trocar chamadas sequenciais por `asyncio.gather()`.

#### 1.4 Adicionar poda de snapshots órfãos ao scheduler
**Arquivo**: `services/crawler_service.py`, função `cleanup_stale_orders()`

Inserir DELETE de snapshots sem ordens ativas correspondentes.

#### 1.5 Corrigir migrations para não suprimir todos os erros
**Arquivo**: `app/database/database.py`, linhas 70–82

Capturar apenas `OperationalError` com mensagem `"already exists"`.

#### 1.6 Armazenar `last_successful_character_id` na estrutura
**Arquivos**: `models/structure.py`, `services/crawler_service.py`

Adicionar coluna + migration + lógica de ordenação no início do crawl.

---

### Fase 2 — Otimizações Estruturais
**Pré-requisito**: Fase 1 concluída | **Risco**: médio | **Tempo estimado**: ~1 dia

Mudanças que tocam na lógica central dos serviços. Exigem testes antes de continuar.

#### 2.1 Resolver N+1 no BOM recursivo
**Arquivo**: `services/blueprint_service.py`

1. Criar função `collect_required_type_ids(blueprint_id, db)` que percorre a árvore uma vez sem buscar dados completos, retornando apenas todos os `type_id` necessários.
2. Buscar todos os `Item` e `Blueprint` em 2 queries com `IN`.
3. Passar os dicionários `items_map` e `blueprints_map` para `get_recursive_bom()` — sem queries adicionais durante a recursão.

#### 2.2 Paginação concorrente no ESI client
**Arquivo**: `services/esi_client.py`, função `_get_paginated()`

1. Buscar página 1 → extrair `X-Pages`.
2. Se `total_pages > 1`, buscar páginas 2-N com `asyncio.gather` + `asyncio.Semaphore(5)`.
3. Concatenar resultados em ordem.
4. Validar com `get_structure_market()`, `get_market_orders()`, `get_character_assets()`.

#### 2.3 Substituir 100 tasks de cache por query batch
**Arquivo**: `services/market_service.py`, linhas 229–236

Remover o `asyncio.gather` com uma task por `type_id`. Substituir por uma única query `SELECT ... WHERE type_id IN (...)` igual ao padrão de `get_prices_cache_only()`.

#### 2.4 Reduzir commits no crawler para commit único
**Arquivo**: `services/crawler_service.py`, função de inserção de ordens

Remover `await db.commit()` dentro do loop. Executar todos os inserts, depois um `commit()` único ao final. Se a transação ficar muito longa (>50k ordens), usar 2 batches de 25k.

#### 2.5 Lock de refresh de token por personagem
**Arquivo**: `services/character_service.py`

Adicionar dicionário `_token_locks: dict[int, asyncio.Lock]` e envolver o bloco de refresh em `async with lock`.

#### 2.6 Bulk inserts na descoberta de estruturas
**Arquivo**: `services/discovery_service.py`

Substituir loop de inserts individuais por `insert(Structure).values([...])` com `prefix_with("OR IGNORE")`.

---

### Fase 3 — Migração para NiceGUI
**Pré-requisito**: Fase 2 concluída (serviços estáveis) | **Risco**: alto (reescrita de UI) | **Tempo estimado**: ~3 dias

Criar `app/ui/` do zero. Manter `app/api/` intacto até todas as telas estarem funcionando, depois remover.

#### 3.1 Setup do NiceGUI e estrutura base
**Arquivos novos**: `app/main_gui.py`, `app/ui/__init__.py`

1. Instalar: `pip install nicegui pywebview`
2. Criar `main_gui.py` com `ui.run(native=True, title="EVE Industry Tool", window_size=(1400, 900))`
3. Registrar rota `/auth/callback` no servidor embutido do NiceGUI
4. Configurar `@nicegui_app.on_startup` para `init_db()` e `start_scheduler()`
5. Criar `app/ui/layout.py` com navegação lateral (tabs fixas)

#### 3.2 Tela de Login e OAuth2
**Arquivo novo**: `app/ui/auth_page.py`

1. Página inicial: botão "Login com EVE Online", spinner de espera
2. `webbrowser.open(eve_sso_url)` ao clicar
3. Callback em `/auth/callback`: trocar código por tokens, salvar personagem, redirecionar para dashboard
4. Exibir nome do personagem logado na barra de status

#### 3.3 Browser de Itens
**Arquivo novo**: `app/ui/items_page.py`

1. `ui.input` para busca com debounce (300ms)
2. `ui.select` para filtro de categoria
3. `ui.table` paginada com colunas: nome, categoria, volume
4. Clique na linha abre a tela da calculadora com o item pré-selecionado

#### 3.4 Calculadora de Produção
**Arquivo novo**: `app/ui/industry_page.py`, `app/ui/components/bom_tree.py`, `app/ui/components/cost_breakdown.py`

1. Formulário: item, runs, ME global, estrutura de manufatura, fonte de mercado, recursive toggle
2. Botão "Calcular" → chama `services` diretamente (sem HTTP)
3. Resultado em `ui.card`: breakdown de custo, tabela de materiais com comparação de preços, árvore BOM expansível
4. Componente `bom_tree.py`: `ui.tree` com toggles buy-as-is e ME por item

#### 3.5 Calculadora de Reprocessamento
**Arquivo novo**: `app/ui/reprocessing_page.py`

1. `ui.select` de item + `ui.number` de yield
2. Resultado em duas `ui.table`: "Reprocessar" (verde) e "Vender" (vermelho)
3. Botão "Copiar busca in-game" usa `ui.clipboard`

#### 3.6 Fila de Produção
**Arquivo novo**: `app/ui/queue_page.py`

1. `ui.table` com itens da fila, botão remover por linha
2. Botão "Adicionar" abre `ui.dialog` com seletor de item + quantidade
3. Botão "Ver Lista de Compras" abre `ui.dialog` com BOM agregado de toda a fila
4. Totais por material com custo estimado

#### 3.7 Ranking de Importações e Projeção
**Arquivos novos**: `app/ui/ranking_page.py`, `app/ui/ranking_item_page.py`, `app/ui/components/price_chart.py`

1. `ui.table` de oportunidades com filtros inline (lucro > 0, volume baixo)
2. Clique em item → painel lateral com projeção
3. Dois `ui.echart`: volume histórico (barras + banda de projeção) e preço (linha + volatilidade)
4. Tabela de histórico diário com todos os campos ESI

#### 3.8 Mercado e Estruturas
**Arquivo novo**: `app/ui/market_page.py`

1. Lista de estruturas conhecidas com status (badge colorido)
2. Stats de cache: última atualização, total de ordens, cobertura
3. Botões: "Forçar refresh", "Limpar cache", "Crawl imediato"

#### 3.9 Descoberta de Estruturas
**Arquivo novo**: `app/ui/discovery_page.py`

1. Botão "Descobrir via Assets" → dispara job, exibe spinner com progresso
2. Lista de estruturas com status e fontes de descoberta
3. Histórico de jobs com tempo, status e ordens encontradas
4. `ui.notify` quando job completa

#### 3.10 Estruturas de Manufatura
**Arquivo novo**: `app/ui/components/manufacturing_structures_list.py`

1. `ui.table` com nome, tipo, ME bonus, TE bonus
2. Botão "Adicionar" → `ui.dialog` com formulário
3. Botão de delete por linha com confirmação `ui.dialog`
4. Integrado na tela de configurações como seção expandível

#### 3.11 Configurações
**Arquivo novo**: `app/ui/settings_page.py`

1. Seções expansíveis: Mercado, Taxas, Estrutura, Frete
2. Todos os `ui.number`, `ui.select`, `ui.switch` mapeados para `user_settings`
3. Salvar com `ui.notify("Configurações salvas", type='positive')`

---

### Fase 4 — Integração, Scheduler e Testes
**Pré-requisito**: Fase 3 concluída | **Risco**: médio | **Tempo estimado**: ~1 dia

#### 4.1 Integrar scheduler ao ciclo de vida NiceGUI
**Arquivo**: `app/main_gui.py`

1. `@nicegui_app.on_startup`: inicializa DB, inicia `job_runner.discovery_runner`, `job_runner.crawl_runner`, registra tarefas do scheduler (15 min, 1h, 6h)
2. `@nicegui_app.on_shutdown`: para runners, fecha conexões
3. Status bar inferior na janela: "Último crawl: X min atrás | Jobs ativos: N"

#### 4.2 Notificações de background jobs na UI
**Arquivos**: `services/crawler_service.py`, `services/discovery_service.py`

Ao completar um crawl ou descoberta, emitir `ui.notify()` com resultado (estruturas encontradas, ordens atualizadas).

#### 4.3 ETags no ESI client (opcional nesta fase)
**Arquivo**: `services/esi_client.py`

1. Adicionar coluna `etag` nas tabelas de cache relevantes + migration
2. Implementar `_get()` com `If-None-Match` e tratamento de `304`
3. Testar com endpoint de skills (muda raramente — fácil de validar)

#### 4.4 Remover código legado
Após validar todas as telas NiceGUI:
- Remover `app/api/` (8 arquivos)
- Remover `app/templates/` (16 HTMLs + partials)
- Remover `static/style.css`
- Remover dependências `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `itsdangerous` do `requirements.txt`
- Renomear `main_gui.py` → `main.py`

#### 4.5 Testes de regressão
1. Recalcular mesmos itens antes e depois da migração — verificar valores idênticos
2. Testar OAuth2 do início ao fim
3. Disparar descoberta e crawl manualmente, verificar DB
4. Verificar scheduler roda sem erros após 30 minutos de uso

---

### Fase 5 — Novas Funcionalidades (pós-migração)
**Pré-requisito**: Fase 4 concluída | **Prioridade**: a definir

| # | Funcionalidade | Dependências | Complexidade |
|---|---------------|-------------|-------------|
| 5.1 | Invenção T2 (chance, datacores, decryptors) | Novo modelo DB + UI | Alta |
| 5.2 | System Tray (minimizar para bandeja) | `pystray` + NiceGUI | Baixa |
| 5.3 | Notificações desktop (oportunidades de importação) | `plyer` ou `win10toast` | Baixa |
| 5.4 | Exportar BOM/fila para CSV/Excel | `pandas` + `ui.download` | Baixa |
| 5.5 | Tema escuro/claro | `ui.dark_mode()` NiceGUI | Muito Baixa |
| 5.6 | Histórico de preços persistente (snapshots diários) | Nova tabela + chart | Média |
| 5.7 | ETags no ESI client (se não feito na Fase 4) | Ver seção 20.2 | Alta |
| 5.8 | Arbitragem multi-região | Novo endpoint ESI + UI | Média |
| 5.9 | Backup automático do `database.db` | `shutil.copy2` no scheduler | Muito Baixa |
| 5.10 | Drag-and-drop na fila de produção | NiceGUI sortable | Média |

---

### Dependências Entre Fases

```
Fase 1 ──────────────────────────────────► pode rodar hoje
   │
   └──► Fase 2 (serviços estabilizados)
             │
             └──► Fase 3 (UI NiceGUI, em paralelo com Fase 2 se desejado)
                       │
                       └──► Fase 4 (integração + remoção de legado)
                                 │
                                 └──► Fase 5 (novas features, qualquer ordem)
```

> Fase 3 pode começar em paralelo com Fase 2 se as telas forem construídas chamando os serviços existentes (não otimizados). As otimizações da Fase 2 são transparentes para a UI.

---

### Critérios de Conclusão por Fase

| Fase | Critério de Conclusão |
|------|-----------------------|
| **1** | Todos os índices criados, nenhuma regressão nos cálculos existentes |
| **2** | BOM de item T2 complexo retorna em < 500ms; crawl de estrutura com 8 páginas em < 400ms |
| **3** | Todas as 11 telas funcionando na janela NiceGUI; paridade funcional com versão web |
| **4** | App inicia com `python main.py`, sem `app/api/` ou `templates/`; scheduler rodando 1h sem erros |
| **5** | Cada feature validada individualmente antes do merge |
