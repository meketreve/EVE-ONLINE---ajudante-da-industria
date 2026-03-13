# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local web application for EVE Online industrialists to calculate production costs, profit margins, and item rentability. Integrates with EVE SSO (OAuth2) and the ESI API.

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, HTTPX
- **Frontend**: Jinja2 templates, HTMX, CSS
- **Database**: SQLite (`database.db`)
- **Auth**: EVE SSO (OAuth2)
- **External data**: ESI API + SDE (Static Data Export)

## Commands

Once the project is scaffolded, the standard commands will be:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
uvicorn app.main:app --reload

# Run tests
pytest

# Lint
ruff check .
```

## Planned Directory Structure

```
eve_industry_tool/
├── app/
│   ├── main.py           # FastAPI app entry point
│   ├── config.py         # App configuration (ESI credentials, etc.)
│   ├── api/              # Route handlers (auth, items, industry, market)
│   ├── services/         # Business logic (esi_client, market_service, industry_calculator)
│   ├── models/           # SQLAlchemy models (user, character, blueprint, item, production_queue)
│   ├── database/         # DB setup and session management
│   └── templates/        # Jinja2 HTML templates
├── static/               # CSS, JS assets
└── database.db
```

## Architecture

**Request flow**: Browser → FastAPI → Services → ESI API / SQLite

**Core engines**:
- `Auth`: OAuth2 via EVE SSO — handles login redirect, code exchange, token storage (access + refresh)
- `Industry Engine` (`industry_calculator.py`): Computes production cost and profit
- `Market Engine` (`market_service.py`): Aggregates prices from public hubs, private structures, and manual overrides
- `Blueprint Engine` (`blueprint_service.py`): Handles T1 and T2 (invention) production specs

**Data sources**:
- **ESI**: Live data (character, corporation, skills, blueprints, market orders, private structures)
- **SDE**: Static game data (item list, blueprint materials, categories) — imported once
- **User config**: Manual cost overrides (mined materials, custom prices, logistics)

## Key Business Logic

**Production cost**:
```
Material Cost = Σ(quantity × material_price)
Job Cost = system_cost_index + facility_tax + SCC_tax
Total Cost = Material Cost + Job Cost + broker_fee + sales_tax + logistics + custom_costs
```

**Profit**:
```
Gross Profit = sale_price - production_cost
Net Profit   = sale_price - production_cost - taxes - fees
```

**Invention (T2)**: Requires success chance, datacores, and decryptors as cost inputs.

## Required ESI OAuth2 Scopes

```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1
```

## Key ESI Endpoints

- `GET /characters/{character_id}` — character info
- `GET /characters/{character_id}/skills` — skills
- `GET /characters/{character_id}/blueprints` — owned blueprints
- `GET /markets/{region_id}/orders` — public market
- `GET /markets/structures/{structure_id}` — private structure market (requires auth)
- `GET /universe/structures/{structure_id}` — structure info

## Data Refresh Strategy

No automatic background jobs. All data updates are **on-demand** (user-triggered). Use local cache to minimize API calls.

## Development Phases

1. Base setup (FastAPI + SQLite + project structure)
2. EVE SSO authentication
3. ESI integration (character/corp/skills)
4. SDE import (items, blueprints, materials)
5. Industry calculation engine
6. Market data integration
7. Frontend UI (pages, dashboards, ranking)
