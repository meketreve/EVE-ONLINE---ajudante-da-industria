"""
EVE Online SSO OAuth2 authentication routes.

Flow:
  1. GET /auth/login   → redirect user to EVE SSO
  2. GET /auth/callback → exchange code for tokens, persist character, set session
  3. GET /auth/logout  → clear session
"""

import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.database import get_db
from app.models.character import Character
from app.models.user import User
from app.services.esi_client import esi_client, ESIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_sso_url(state: str) -> str:
    """Construct the EVE SSO authorization URL."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "redirect_uri": settings.EVE_CALLBACK_URL,
        "client_id": settings.EVE_CLIENT_ID,
        "scope": settings.SSO_SCOPES,
        "state": state,
    }
    return f"{settings.SSO_BASE_URL}/v2/oauth/authorize?{urlencode(params)}"


@router.get("/login")
async def login(request: Request):
    """Redirect the user to EVE SSO for authentication."""
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    return RedirectResponse(url=_build_sso_url(state))


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle the OAuth2 callback from EVE SSO.

    Exchanges the code for tokens, fetches character info, upserts the
    character in the database and sets the session.
    """
    if error:
        logger.warning("EVE SSO returned error: %s", error)
        return RedirectResponse(url="/?error=sso_error")

    if not code:
        return RedirectResponse(url="/?error=missing_code")

    # Validate state to prevent CSRF
    stored_state = request.session.pop("oauth_state", None)
    if stored_state is None or stored_state != state:
        logger.warning("OAuth state mismatch. stored=%s received=%s", stored_state, state)
        return RedirectResponse(url="/?error=state_mismatch")

    # Exchange authorization code for tokens
    try:
        token_data = await esi_client.exchange_code_for_token(code)
    except ESIError as exc:
        logger.error("Token exchange failed: %s", exc)
        return RedirectResponse(url="/?error=token_exchange_failed")

    access_token: str = token_data["access_token"]
    refresh_token: str = token_data.get("refresh_token", "")
    expires_in: int = token_data.get("expires_in", 1200)
    token_expiry = esi_client.compute_expiry(expires_in)

    # Verify token and retrieve character info
    try:
        verify_data = await esi_client.verify_token(access_token)
    except ESIError as exc:
        logger.error("Token verification failed: %s", exc)
        return RedirectResponse(url="/?error=token_verify_failed")

    character_id: int = int(verify_data.get("CharacterID", 0))
    character_name: str = verify_data.get("CharacterName", "Unknown")

    if not character_id:
        return RedirectResponse(url="/?error=invalid_character")

    # Fetch character info for corporation_id
    corporation_id: int | None = None
    try:
        char_info = await esi_client.get_character_info(character_id)
        corporation_id = char_info.get("corporation_id")
    except ESIError as exc:
        logger.warning("Could not fetch character info: %s", exc)

    # Upsert character
    result = await db.execute(
        select(Character).where(Character.character_id == character_id)
    )
    character = result.scalar_one_or_none()

    if character is None:
        character = Character(
            character_id=character_id,
            character_name=character_name,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
            corporation_id=corporation_id,
        )
        db.add(character)
    else:
        character.character_name = character_name
        character.access_token = access_token
        character.refresh_token = refresh_token
        character.token_expiry = token_expiry
        character.corporation_id = corporation_id
        character.updated_at = datetime.utcnow()

    await db.flush()

    # Ensure a User row exists linked to this character
    user_result = await db.execute(
        select(User).where(User.character_id == character_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        user = User(character_id=character_id)
        db.add(user)

    await db.flush()

    # Store character_id in session
    request.session["character_id"] = character_id
    request.session["character_name"] = character_name

    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    """Clear the session and redirect to home."""
    request.session.clear()
    return RedirectResponse(url="/")
