"""
Authentication pages for NiceGUI.
/ and /login — show login button if not authenticated.
Handles OAuth2 callback via /auth/callback route.
"""

import logging
import secrets
import webbrowser
from datetime import datetime
from urllib.parse import urlencode

from nicegui import ui, app as nicegui_app

from app.config import settings

logger = logging.getLogger(__name__)


def _build_sso_url(state: str) -> str:
    """Constrói a URL de autorização do EVE SSO."""
    params = {
        "response_type": "code",
        "redirect_uri":  settings.EVE_CALLBACK_URL,
        "client_id":     settings.EVE_CLIENT_ID,
        "scope":         settings.SSO_SCOPES,
        "state":         state,
    }
    return f"{settings.SSO_BASE_URL}/v2/oauth/authorize?{urlencode(params)}"


@ui.page("/")
@ui.page("/login")
async def login_page():
    """Página de login / splash screen."""
    character_name = nicegui_app.storage.general.get("character_name")
    if character_name:
        ui.navigate.to("/dashboard")
        return

    with ui.column().classes("items-center justify-center w-full min-h-screen gap-6 bg-grey-10"):
        with ui.card().classes("q-pa-xl text-center bg-grey-9 shadow-8 rounded-lg"):
            ui.icon("rocket_launch").classes("text-6xl text-blue-grey-3 q-mb-md")
            ui.label("EVE Industry Tool").classes("text-h4 text-white font-bold q-mb-xs")
            ui.label("Ferramenta de análise de indústria para EVE Online").classes(
                "text-subtitle2 text-grey-5 q-mb-xl"
            )

            if not settings.EVE_CLIENT_ID:
                ui.label(
                    "Configure EVE_CLIENT_ID e EVE_CLIENT_SECRET no arquivo .env para habilitar o login."
                ).classes("text-caption text-orange-5 q-mb-md")

            waiting = {"active": False}

            async def do_login():
                state = secrets.token_urlsafe(32)
                nicegui_app.storage.general["oauth_state"] = state
                sso_url = _build_sso_url(state)
                webbrowser.open(sso_url)
                status_label.set_text("Aguardando callback do EVE SSO...")
                spinner.set_visibility(True)
                waiting["active"] = True

            ui.button(
                "Entrar com EVE Online",
                on_click=do_login,
                icon="login",
            ).props("unelevated size=lg color=blue-grey-7").classes("q-mb-md")

            status_label = ui.label("").classes("text-caption text-grey-5")
            spinner = ui.spinner("dots", size="md", color="blue-grey").classes("q-mt-sm")
            spinner.set_visibility(False)

            # Verifica a cada segundo se o callback completou e redireciona
            def check_auth():
                if waiting["active"] and nicegui_app.storage.general.get("character_name"):
                    ui.navigate.to("/dashboard")

            ui.timer(1.0, check_auth)

        with ui.row().classes("items-center gap-2 text-grey-6 text-caption"):
            ui.icon("info").classes("text-xs")
            ui.label("Seus dados ficam armazenados localmente. Nenhuma informação é enviada a terceiros.")
