import os

import httpx
from langgraph_sdk import Auth

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

auth = Auth()


@auth.authenticate
async def get_current_user(
    authorization: str | None,
) -> Auth.types.MinimalUserDict:
    """Validate a Supabase JWT and return the authenticated user identity.

    Calls the Supabase /auth/v1/user endpoint with the bearer token.
    On success, returns a MinimalUserDict with the user's Supabase UUID.
    On any failure, raises a 401 HTTPException.
    """
    if not authorization:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Missing authorization header"
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid authorization scheme"
        )
    token = parts[1]

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_SERVICE_KEY,
                },
            )
    except (httpx.HTTPError, ConnectionError) as e:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Failed to validate token"
        ) from e

    if response.status_code != 200:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid or expired token"
        )

    user = response.json()
    return {
        "identity": user["id"],
        "is_authenticated": True,
    }


@auth.on
async def add_owner(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """Scope all resources (threads, runs) to the authenticated user.

    Adds an 'owner' filter to metadata so each user can only access
    their own threads and runs.
    """
    filters = {"owner": ctx.user.identity}
    metadata = value.setdefault("metadata", {})
    metadata.update(filters)
    return filters
