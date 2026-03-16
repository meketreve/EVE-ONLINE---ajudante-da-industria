# EVE Industry Tool

Aplicação web local para industrialistas do **EVE Online** calcularem custos de produção, margens de lucro e oportunidades de importação, integrando dados reais do jogo via ESI API e mercados de estruturas privadas.

---

## Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| **Calculadora de Produção** | Custo de materiais com BOM recursivo, ME por item, bônus de estrutura, job cost (SCI + facility tax + SCC), broker fee, sales tax, lucro bruto e líquido |
| **Comparação de Preços no BOM** | Lado a lado entre o mercado ativo e Jita/Amarr para cada material — identifica o que vale importar |
| **Reprocessamento** | Calcula se vale reprocessar um item e vender os minerais ou vender o item diretamente |
| **Ranking de Importação** | Itens com maior margem entre mercado fonte (Jita/Amarr) e mercado local, com cálculo de frete |
| **Projeção de Mercado** | Página por item com histórico ESI, estatísticas de volume, projeção semanal/mensal e gráficos |
| **Fila de Produção** | Lista de jobs planejados com BOM agregado — lista de compras unificada de todos os itens |
| **Estruturas de Manufatura** | Cadastro manual de estruturas (Raitaru/Azbel/Sotiyo) com bônus ME/TE para uso no BOM |
| **Descoberta de Estruturas** | Escaneia assets pessoais para encontrar citadelas e complexos com acesso ao mercado |
| **Mercados Privados** | Crawl automático (a cada 15 min) de ordens de estruturas Upwell acessíveis |
| **Login via EVE SSO** | Acesso a skills de personagem (Accounting, Broker Relations), assets e mercados privados |

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy async |
| Banco | SQLite (WAL mode, aiosqlite) |
| Frontend | Jinja2, HTMX, CSS, Chart.js |
| Auth | EVE SSO (OAuth2) |
| Dados EVE | ESI API + SDE (Static Data Export) |

---

## Pré-requisitos

- Python 3.11 ou superior
- Conta de desenvolvedor EVE Online com uma aplicação registrada em [developers.eveonline.com](https://developers.eveonline.com)

**Escopos ESI necessários** (configurar na aplicação EVE Developer):
```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-assets.read_assets.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1
esi-universe.read_structures.v1
```

**Callback URL** da aplicação EVE: `http://localhost:8000/auth/callback`

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

> `SECRET_KEY` pode ser qualquer string aleatória longa — é usada para assinar os cookies de sessão.

### 5. Importar dados do SDE

Baixa e importa itens, blueprints e materiais do Static Data Export da CCP (necessário apenas uma vez):

```bash
# Windows
1_importar_sde.bat

# Direto
python eve_industry_tool/scripts/import_sde.py
```

> A importação pode demorar alguns minutos. O banco (`database.db`) é criado automaticamente.

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

## Configuração Inicial (primeira vez)

Após iniciar o servidor e acessar a interface:

### 1. Fazer login com EVE Online

Clique em **"Entrar com EVE Online"** no canto superior direito. O login autentica o personagem e libera:
- Leitura de skills (Accounting, Broker Relations) para cálculo automático de taxas
- Descoberta de estruturas privadas via assets pessoais
- Acesso a mercados de estruturas Upwell

### 2. Configurar parâmetros em **Configurações**

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| Mercado Padrão | Hub ou estrutura usada nos cálculos | Jita (The Forge) |
| ME (Material Efficiency) | Nível global do blueprint | 10 |
| Bônus ME da Estação (%) | Redução extra de materiais da estrutura + rigs | 3.0 |
| Bônus TE da Estação (%) | Redução de tempo da estrutura + rigs | 20.0 |
| System Cost Index | Índice de custo do sistema de manufatura | 0.05 (5%) |
| Facility Tax | Imposto da estrutura | 0.0 |
| SCC Surcharge | Fixo CCP: 1.5% | 0.015 |
| Broker Fee | Taxa de corretagem (override se sem skills) | 0.03 |
| Sales Tax | Imposto de venda (override se sem skills) | 0.08 |
| Custo de Frete (ISK/m³) | Usado no Ranking de Importação | 500 |

### 3. Cadastrar estruturas de manufatura (opcional)

Em **Configurações → Estruturas de Manufatura**, cadastre cada EC que você usa:

- **Nome**: identificação livre (ex: "Minha Azbel em Null")
- **Tipo**: Raitaru / Azbel / Sotiyo
- **Bônus ME (%)**: soma do bônus base da estrutura + todos os rigs instalados
- **Bônus TE (%)**: idem para tempo

> A ESI não expõe rigs de estruturas. O cadastro é manual. Exemplo: Azbel base -1% ME + Standup M-Set ME I -2% = ME bônus **3.0**.

### 4. Descobrir mercados de estruturas privadas

Em **Configurações → Gerenciamento de Mercado**, clique em **"Escanear Assets Pessoais"**. Isso varre seus assets para encontrar estruturas Upwell e testa o acesso ao mercado de cada uma. Após descoberta, o crawl automático roda a cada 15 minutos.

---

## Guia de Uso

### Calculadora de Produção

1. Acesse **Itens** e busque pelo nome do item
2. Clique no item para abrir a página de detalhe
3. Configure as opções na calculadora:
   - **Número de Runs**: quantidade de corridas do blueprint
   - **BOM Recursivo**: expande componentes fabricáveis (recomendado — mostra toda a cadeia)
   - **Estrutura de Manufatura**: selecione uma estrutura cadastrada para aplicar os bônus de ME/TE
4. Clique em **Calcular**

**Na tabela de materiais**, quando há dados de cache para Jita ou Amarr, aparecem colunas extras mostrando o preço no mercado de referência e a diferença (Δ) por unidade:
- Verde = mais barato no mercado ativo
- Vermelho = mais barato em Jita/Amarr (vale importar esse material)

**Na árvore BOM recursiva**:
- **FAB** = item fabricado (tem blueprint)
- **COMPRAR** = você marcou para comprar pronto
- Clique no ME inline de cada componente para ajustar a eficiência individualmente
- Botão **Comprar / Fabricar** para alternar por item

### Ranking de Importação

Acesse **Ranking** para ver itens com oportunidade de importação:

- **Oportunidades lucrativas**: preço local > (preço fonte + frete + taxas)
- **Sem concorrência local**: itens sem ordens de venda no mercado local

Clique em qualquer item para abrir a **página de projeção**, que mostra:
- Preços atuais (fonte vs local) e lucro líquido por unidade
- Projeção de volume (média diária × janela) para 7, 14 ou 30 dias
- Receita potencial diária e mensal
- Gráfico de volume histórico com barras de projeção futura
- Gráfico de preço médio com banda de volatilidade (min/max)
- Tabela de histórico diário completo

### Reprocessamento

Acesse **Reprocessamento** e cole uma lista de itens (um por linha ou separados por vírgula). O sistema calcula para cada item:
- Valor de venda direta
- Valor dos minerais após reprocessamento
- Recomendação: **Reprocessar** ou **Vender**

A saída é formatada no padrão de busca múltipla do inventário in-game para facilitar a seleção.

### Fila de Produção

1. Na página de qualquer item, use o formulário **"Adicionar à Fila"**
2. Acesse **Fila de Produção** para ver todos os jobs planejados
3. Clique em **"Ver Lista de Compras"** para gerar o BOM agregado de toda a fila:
   - Combina materiais de todos os itens pendentes
   - Usa o ME e bônus de estrutura configurados em Configurações
   - Mostra quantidade total de cada material e custo estimado

---

## Scripts Auxiliares

### `2_atualizar_estruturas.bat`

Descobre estruturas Upwell acessíveis via ESI e testa acesso ao mercado:

```bash
# Todas as fontes
2_atualizar_estruturas.bat

# Apenas assets pessoais
2_atualizar_estruturas.bat --fonte assets
```

### `ordens_null.bat`

Importa ordens de compra/venda de estruturas em nullsec diretamente para o cache:

```bash
# Lista estruturas disponíveis
ordens_null.bat --listar

# Importa ordens de uma estrutura específica
ordens_null.bat --id 1046664001931
```

### Comandos diretos (Python)

```bash
# Importar SDE (necessário apenas uma vez)
python eve_industry_tool/scripts/import_sde.py

# Atualizar estruturas
python eve_industry_tool/scripts/atualizar_estruturas.py

# Atualizar preços de mercado manualmente
python eve_industry_tool/scripts/atualizar_precos_mercado.py

# Importar ordens de estruturas nullsec
python eve_industry_tool/scripts/ordens_null.py --listar
python eve_industry_tool/scripts/ordens_null.py --id <structure_id>
```

---

## Comandos de Desenvolvimento

```bash
# Iniciar servidor com reload automático
cd eve_industry_tool
uvicorn app.main:app --reload

# Iniciar em porta diferente
uvicorn app.main:app --reload --port 8080

# Rodar testes
pytest

# Lint
ruff check .

# Lint com correção automática
ruff check . --fix
```

---

## Estrutura do Projeto

```
eve_industry_tool/
├── app/
│   ├── main.py                    # Entry point FastAPI, scheduler, fila de produção
│   ├── config.py                  # Configurações e variáveis de ambiente
│   ├── api/                       # Rotas HTTP
│   │   ├── auth.py                # EVE SSO (login, callback, logout)
│   │   ├── items.py               # Listagem e detalhe de itens
│   │   ├── industry.py            # Calculadora, ranking e projeção de mercado
│   │   ├── market.py              # Visão geral do mercado
│   │   ├── discovery.py           # Descoberta e crawl de estruturas
│   │   ├── settings.py            # Configurações globais
│   │   ├── reprocessing.py        # Cálculo de reprocessamento
│   │   └── manufacturing_structures.py  # Cadastro de estruturas de manufatura
│   ├── services/                  # Lógica de negócio
│   │   ├── esi_client.py          # Client HTTP para a ESI (com auto-refresh de token)
│   │   ├── market_service.py      # Preços de região e estruturas
│   │   ├── industry_calculator.py # Fórmulas de custo e lucro
│   │   ├── blueprint_service.py   # Materiais, blueprints e BOM recursivo
│   │   ├── crawler_service.py     # Crawl de ordens de estruturas
│   │   ├── discovery_service.py   # Descoberta de estruturas via assets
│   │   ├── job_runner.py          # Fila de jobs em background
│   │   └── character_service.py   # Tokens, skills e taxas por personagem
│   ├── models/                    # Modelos SQLAlchemy (ORM)
│   │   ├── user.py / character.py
│   │   ├── item.py / blueprint.py
│   │   ├── production_queue.py
│   │   ├── user_settings.py
│   │   ├── manufacturing_structure.py  # Estruturas de manufatura cadastradas
│   │   ├── cache.py               # Cache de preços, estruturas e skills
│   │   ├── market_order.py / market_snapshot.py
│   │   ├── structure.py / market_structure.py
│   │   └── job.py / reprocessing.py
│   ├── database/
│   │   └── database.py            # Engine SQLite, sessão, pragmas, migrations
│   └── templates/                 # Templates Jinja2 + HTMX
│       ├── base.html
│       ├── index.html / login.html
│       ├── items.html / item_detail.html
│       ├── ranking.html / ranking_item.html
│       ├── reprocessing.html
│       ├── production_queue.html
│       ├── market.html / settings.html
│       └── partials/              # Fragmentos HTMX
├── scripts/
│   ├── import_sde.py
│   ├── atualizar_estruturas.py
│   ├── atualizar_precos_mercado.py
│   └── ordens_null.py
├── static/
│   └── style.css
├── database.db                    # Banco SQLite (criado automaticamente)
├── requirements.txt
└── .env                           # Credenciais EVE SSO (não versionar)
```

---

## Fluxo de Dados

```
Browser → FastAPI → Services → ESI API
                 ↘           ↘
                  SQLite ← Scripts externos
```

- **ESI**: dados ao vivo — personagem, skills, assets, histórico de mercado, ordens de estruturas
- **SDE**: dados estáticos importados uma vez — itens, blueprints, materiais
- **Scheduler interno**: crawl de estruturas a cada 15 min, limpeza de ordens a cada 1h, rediscovery a cada 6h
- **Scripts externos**: populam cache de preços sem bloquear o servidor

---

## Fórmulas

### Custo de Produção

```
Material Cost  = Σ(quantidade × preço_unitário)
Job Cost       = item_value_ajustado × (SCI + facility_tax + SCC)
Total          = Material Cost + Job Cost
```

### Lucro

```
Gross Profit = sell_price - total_cost
Net Profit   = sell_price × (1 - broker_fee - sales_tax) - total_cost
```

### Material Efficiency (BOM)

```
qty_ajustada = ceil(qty_base × (1 - blueprint_ME/100) × (1 - estrutura_ME/100))
```

### Margem de Importação (Ranking)

```
Net Profit/un. = preço_local × (1 - sales_tax - broker_fee) - preço_fonte - frete/un.
```

---

## Observações

- O banco de dados (`database.db`) é criado automaticamente na primeira execução
- Migrations de schema rodam automaticamente no startup — nunca destruindo dados existentes
- Todos os dados ficam locais — nada é enviado a servidores externos além da ESI oficial da CCP
- A ESI não expõe rigs de estruturas; o cadastro de bônus ME/TE é manual
- Não afiliado à CCP Games
