# EVE Industry Profit Tool

Aplicação web local para cálculo de **custos e lucro líquido na indústria do EVE Online**, integrando dados da **ESI (EVE Swagger Interface)**, mercados públicos e estruturas privadas acessíveis ao personagem.

O objetivo é fornecer uma ferramenta prática para **industrialistas analisarem produção, custo de materiais e lucro real**, considerando todos os fatores relevantes da indústria do jogo.

---

# 1. Objetivo do Projeto

Criar uma aplicação local com interface web que permita:

- Calcular **custo total de produção**
- Calcular **lucro bruto e lucro líquido**
- Analisar **rentabilidade de itens industriais**
- Integrar dados do **personagem e corporação via EVE SSO**
- Utilizar **dados reais do mercado**
- Permitir **configuração manual de custos**
- Suportar **blueprints, invention e produção completa**

A aplicação será **multiusuário**, com autenticação via conta do EVE Online.

---

# 2. Características Principais

## Funcionalidades principais

O sistema permitirá:

- Login via **EVE Online SSO**
- Integração com **personagem e corporação**
- Listagem de **todos os itens fabricáveis do jogo**
- Organização por **categorias**
- Cálculo completo de indústria:
  - custo de materiais
  - custo de job
  - impostos
  - taxas
  - logística
  - invention
- Integração com **mercados públicos e privados**
- Configuração manual da origem de recursos
- Fila de produção
- Ranking de itens mais lucrativos

---

# 3. Escopo da Versão MVP

A primeira versão do sistema incluirá:

### Autenticação

- Login via **EVE SSO**
- Registro automático do personagem
- Registro da corporação

### Navegação de itens

- Lista completa de itens fabricáveis
- Filtros por categoria
- Busca por item

### Tela de item

Mostra:

- materiais necessários
- blueprint utilizada
- custo de produção
- custo total
- preço de mercado
- lucro bruto
- **lucro líquido**

### Configuração de custos

Usuário poderá definir:

- preço de compra de materiais
- preço manual
- material minerado (custo custom)
- origem de recursos

### Preços de mercado

Fontes de preço:

- hubs públicos
- estruturas privadas
- preço manual

### Atualização de dados

Sem jobs automáticos.

Atualização ocorrerá por:

- botão "Atualizar dados"
- atualização sob demanda

### Fila de produção

Usuário poderá montar uma lista de itens para produzir.

---

# 4. Funcionalidades Planejadas (Após MVP)

Funcionalidades futuras:

- favoritos
- watchlist de itens
- exportação CSV
- exportação planilha
- análise histórica de lucro
- otimização de produção
- cálculo de lucro por hora

---

# 5. Arquitetura do Sistema

## Estrutura geral


Browser
│
│ HTTP
▼
FastAPI Server
│
├── Auth (EVE SSO)
├── Industry Engine
├── Market Engine
├── Blueprint Engine
└── Database
│
▼
SQLite


---

# 6. Stack Tecnológica

## Backend

- Python
- FastAPI
- SQLAlchemy
- HTTPX

## Frontend

Interface simples e moderna usando:

- Jinja2
- HTMX
- CSS moderno

Foco principal:

- desktop
- responsivo para mobile

## Banco de dados

SQLite

Motivo:

- aplicação local
- simples
- fácil distribuição

---

# 7. Estrutura de Diretórios


eve_industry_tool/
│
├── app/
│ ├── main.py
│ ├── config.py
│ │
│ ├── api/
│ │ ├── auth.py
│ │ ├── items.py
│ │ ├── industry.py
│ │ └── market.py
│ │
│ ├── services/
│ │ ├── esi_client.py
│ │ ├── market_service.py
│ │ ├── blueprint_service.py
│ │ └── industry_calculator.py
│ │
│ ├── models/
│ │ ├── user.py
│ │ ├── character.py
│ │ ├── blueprint.py
│ │ ├── item.py
│ │ └── production_queue.py
│ │
│ ├── database/
│ │ └── database.py
│ │
│ └── templates/
│
├── static/
│
└── database.db


---

# 8. Integração com APIs do EVE Online

A aplicação usará principalmente duas fontes de dados:

### ESI (EVE Swagger Interface)

API oficial da CCP.

Fornece:

- dados de personagem
- corporações
- blueprints
- skills
- estruturas
- mercados privados
- indústria

Documentação:

https://developers.eveonline.com/docs/services/esi/

---

### EVE SSO

Sistema oficial de autenticação.

Permite:

- login com conta do EVE
- acesso a dados privados
- acesso a estruturas

Documentação:

https://developers.eveonline.com/docs/services/sso/

Fluxo:

1. Usuário clica em login
2. Redirecionado para EVE SSO
3. Autoriza aplicação
4. Aplicação recebe `authorization_code`
5. Troca por `access_token`
6. Usa token na ESI

---

# 9. Endpoints ESI Relevantes

## Personagem


GET /characters/{character_id}


---

## Corporação


GET /characters/{character_id}/corporationhistory


---

## Skills


GET /characters/{character_id}/skills


---

## Blueprints


GET /characters/{character_id}/blueprints


---

## Estruturas privadas


GET /universe/structures/{structure_id}


Requer autenticação.

---

## Mercado

### Mercado público


GET /markets/{region_id}/orders


---

### Mercado de estruturas


GET /markets/structures/{structure_id}


Requer autorização do personagem.

---

# 10. Dados Estáticos do Jogo

Alguns dados não vêm da ESI.

Eles vêm do **SDE (Static Data Export)**.

Usado para:

- lista completa de itens
- blueprints
- materiais
- categorias
- grupos

Documentação:

https://developers.eveonline.com/docs/guides/sde/

---

# 11. Cálculo de Custo Industrial

O cálculo de custo incluirá:

### Materiais

Somatório de:


quantidade_material * preço_material


---

### Job Cost

Inclui:

- system cost index
- facility tax
- SCC tax

---

### Impostos

- broker fee
- sales tax

---

### Custos adicionais

- combustível da estrutura
- logística
- custos customizados

---

# 12. Cálculo de Lucro

Lucro bruto:


preço_venda - custo_produção


Lucro líquido:


preço_venda

custo_produção

impostos

taxas


---

# 13. Configuração Manual de Recursos

Usuário poderá definir origem de materiais:

- comprar no market
- mineração própria
- estoque interno
- preço customizado

---

# 14. Módulo de Invention

Sistema separado para:

- T2 production
- chance de sucesso
- decryptors
- datacores

Cálculo inclui:


chance_success

custo_datacores

custo_decryptor


---

# 15. Ranking de Itens Lucrativos

O sistema poderá calcular:

- itens com maior lucro
- itens com melhor margem
- lucro por unidade

Ranking baseado em:


lucro_liquido


---

# 16. Segurança

Autenticação:

- OAuth2 via EVE SSO

Tokens armazenados:

- access token
- refresh token

Escopos mínimos recomendados:


esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1


---

# 17. Atualização de Dados

Não haverá cron jobs.

Atualização será:

- manual
- sob demanda

Com cache local.

---

# 18. Interface

Design:

- limpo
- moderno
- funcional

Inspirado em dashboards.

Foco:

- desktop
- responsivo

---

# 19. Roadmap de Desenvolvimento

## Fase 1

Base do projeto

- FastAPI
- SQLite
- estrutura do projeto

---

## Fase 2

Autenticação

- integração EVE SSO
- login
- armazenamento de tokens

---

## Fase 3

Integração ESI

- personagem
- corporação
- skills

---

## Fase 4

Importação de itens

- SDE
- blueprints

---

## Fase 5

Cálculo industrial

- custo materiais
- custo produção
- lucro

---

## Fase 6

Mercado

- hubs públicos
- estruturas privadas

---

## Fase 7

Interface

- páginas
- dashboards
- ranking

---

# 20. Objetivo Final

Criar uma ferramenta poderosa para industrialistas do EVE Online capaz de:

- analisar produção
- otimizar lucros
- integrar dados reais do jogo
- suportar múltiplos usuários
- funcionar localmente com interface web.