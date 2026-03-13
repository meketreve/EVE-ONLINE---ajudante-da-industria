import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    EVE_CLIENT_ID: str = os.getenv("EVE_CLIENT_ID", "")
    EVE_CLIENT_SECRET: str = os.getenv("EVE_CLIENT_SECRET", "")
    EVE_CALLBACK_URL: str = os.getenv("EVE_CALLBACK_URL", "http://localhost:8000/auth/callback")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

    ESI_BASE_URL: str = "https://esi.evetech.net/latest"
    SSO_BASE_URL: str = "https://login.eveonline.com"

    DATABASE_URL: str = "sqlite+aiosqlite:///./database.db"

    # EVE SSO scopes required
    SSO_SCOPES: str = (
        "esi-skills.read_skills.v1 "
        "esi-characters.read_blueprints.v1 "
        "esi-markets.structure_markets.v1 "
        "esi-universe.read_structures.v1 "
        "esi-corporations.read_structures.v1 "
        "esi-assets.read_assets.v1"            # descoberta via personal assets
    )


settings = Settings()
