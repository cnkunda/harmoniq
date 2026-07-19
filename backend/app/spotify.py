"""Spotify OAuth (PKCE) + taste aggregation — PRIORITIES §67.

Tokens live only in this module's in-memory store (keyed by opaque `client_session`).
Never log access tokens, refresh tokens, or authorization codes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import math
import os
import random
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.schemas import SpotifyPlaybackState, SpotifyTasteProfile

logger = logging.getLogger("harmoniq.spotify")

ACCOUNTS_BASE = "https://accounts.spotify.com"
API_BASE = "https://api.spotify.com/v1"
SCOPES = "user-top-read user-read-recently-played user-read-playback-state playlist-read-private playlist-modify-public playlist-modify-private user-modify-playback-state"

_RATE_LIMIT_MAX_RETRIES = 5
_RATE_LIMIT_BASE_DELAY_MS = 1000

_pending: dict[str, tuple[str, str, Literal["native", "web"]]] = {}
"""state -> (code_verifier, client_session, return_platform)."""

_tokens: dict[str, _TokenBundle] = {}
"""client_session -> tokens."""


class SpotifySessionExpired(Exception):
    """Raised when the refresh token cannot be refreshed — client must re-authorize."""


@dataclass
class _TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: float


def spotify_feature_disabled() -> bool:
    return os.getenv("HARMONIQ_SKIP_SPOTIFY", "").strip() == "1"


def spotify_client_id() -> str | None:
    raw = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    return raw or None


def spotify_redirect_uri() -> str:
    """Must match a redirect URI configured for the Spotify app."""
    return (
        os.getenv("HARMONIQ_SPOTIFY_REDIRECT_URI", "").strip()
        or "http://127.0.0.1:8000/auth/spotify/callback"
    )


def spotify_web_post_login_url() -> str:
    """Browser users return here after OAuth (Expo web dev server)."""
    return os.getenv("HARMONIQ_SPOTIFY_WEB_RETURN", "").strip() or "http://127.0.0.1:8081"


def native_oauth_redirect_scheme() -> str:
    return os.getenv("HARMONIQ_SPOTIFY_APP_SCHEME", "").strip() or "harmoniq"


def _pkce_verifier() -> str:
    v = secrets.token_urlsafe(48)
    if len(v) < 43:
        v = v + secrets.token_urlsafe(32)
    return v[:128]


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _require_configured() -> str:
    cid = spotify_client_id()
    if not cid:
        raise RuntimeError("SPOTIFY_CLIENT_ID is not set (Spotify OAuth is unavailable).")
    return cid


# ---- Rate-limit-aware HTTP client wrapper ----


async def _spotify_api_call(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    data_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
    max_retries: int = _RATE_LIMIT_MAX_RETRIES,
) -> httpx.Response:
    """Make a Spotify API call with automatic 429 retry and exponential backoff.

    Respects the Retry-After header when present. Uses jittered exponential
    backoff between retries when no Retry-After header is provided.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    data=data_body,
                )
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt > max_retries:
                raise RuntimeError(f"Spotify API timeout after {attempt} attempts.") from exc
            delay = _RATE_LIMIT_BASE_DELAY_MS * (2 ** (attempt - 1)) * (0.5 + 0.5 * random.random())
            logger.warning("Spotify API timeout (attempt %d/%d), retrying in %dms", attempt, max_retries, int(delay))
            await asyncio.sleep(delay / 1000.0)
            continue

        if res.status_code == 429:
            if attempt > max_retries:
                logger.error("Spotify rate limit exhausted after %d retries.", max_retries)
                raise RuntimeError("Spotify API rate limit exceeded. Try again later.")
            raw = res.headers.get("Retry-After", "")
            if raw:
                try:
                    delay = float(raw)
                except ValueError:
                    delay = _RATE_LIMIT_BASE_DELAY_MS * (2 ** (attempt - 1)) / 1000.0
            else:
                delay = _RATE_LIMIT_BASE_DELAY_MS * (2 ** (attempt - 1)) * (0.5 + 0.5 * random.random()) / 1000.0
            logger.warning(
                "Spotify 429 rate limited (attempt %d/%d), retrying in %.1fs",
                attempt, max_retries, delay,
            )
            await asyncio.sleep(delay)
            continue

        return res

    msg = f"Spotify API call failed after {max_retries + 1} attempts."
    raise RuntimeError(msg) from last_exc


# ---- OAuth flow ----


def begin_authorization(
    client_session: str,
    *,
    return_platform: Literal["native", "web"],
) -> tuple[str, str]:
    """Return (state, authorize_url)."""
    _require_configured()
    if not client_session or len(client_session) > 256:
        raise ValueError("client_session must be a non-empty string (max 256 chars).")
    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(32)
    _pending[state] = (verifier, client_session.strip(), return_platform)
    cid = spotify_client_id()
    assert cid
    params = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": spotify_redirect_uri(),
        "scope": SCOPES,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
    }
    url = f"{ACCOUNTS_BASE}/authorize?{urlencode(params)}"
    return state, url


async def exchange_code(code: str, state: str) -> tuple[str, Literal["native", "web"]]:
    """Exchange authorization code; store tokens under `client_session`."""
    pending = _pending.get(state)
    if pending is None:
        raise ValueError("Unknown or expired OAuth state.")
    verifier, client_session, return_platform = pending
    cid = _require_configured()
    redirect_uri = spotify_redirect_uri()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cid,
        "code_verifier": verifier,
    }
    res = await _spotify_api_call(
        "POST",
        f"{ACCOUNTS_BASE}/api/token",
        data_body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if res.status_code != 200:
        _pending.pop(state, None)
        logger.warning("Spotify token exchange failed status=%s", res.status_code)
        raise ValueError("Spotify token exchange failed.")
    data = res.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = int(data.get("expires_in") or 3600)
    if not isinstance(access, str) or not access:
        _pending.pop(state, None)
        raise ValueError("Spotify token response missing access_token.")
    _tokens[client_session] = _TokenBundle(
        access_token=access,
        refresh_token=refresh if isinstance(refresh, str) else None,
        expires_at=time.time() + max(60, expires_in) - 30,
    )
    _pending.pop(state, None)
    logger.info("Spotify OAuth completed (tokens not logged).")
    return client_session, return_platform


def oauth_failure_redirect(return_platform: Literal["native", "web"], client_session: str) -> str:
    if return_platform == "native":
        scheme = native_oauth_redirect_scheme()
        q = urlencode({"result": "error", "client_session": client_session})
        return f"{scheme}://spotify-callback?{q}"
    base = spotify_web_post_login_url().rstrip("/")
    parsed = urlparse(base)
    merged = {k: v for k, v in parse_qsl(parsed.query, keep_blank_values=True)}
    merged["spotify_oauth"] = "0"
    merged["spotify_error"] = "1"
    merged["client_session"] = client_session
    new_query = urlencode(merged)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, new_query, parsed.fragment)
    )


def post_login_redirect(return_platform: Literal["native", "web"], client_session: str) -> str:
    if return_platform == "native":
        scheme = native_oauth_redirect_scheme()
        q = urlencode({"result": "success", "client_session": client_session})
        return f"{scheme}://spotify-callback?{q}"
    base = spotify_web_post_login_url().rstrip("/")
    parsed = urlparse(base)
    merged = {k: v for k, v in parse_qsl(parsed.query, keep_blank_values=True)}
    merged["spotify_oauth"] = "1"
    merged["client_session"] = client_session
    new_query = urlencode(merged)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, new_query, parsed.fragment)
    )


def pop_pending_for_state(state: str) -> tuple[str, Literal["native", "web"]] | None:
    """Remove pending OAuth row; used when Spotify returns an error to the callback."""
    row = _pending.pop(state, None)
    if row is None:
        return None
    _, client_session, return_platform = row
    return client_session, return_platform


def disconnect_client(client_session: str) -> None:
    _tokens.pop(client_session.strip(), None)
    stale_states = [s for s, (_, cs, _) in _pending.items() if cs == client_session.strip()]
    for s in stale_states:
        _pending.pop(s, None)


async def _refresh_access_token(client_session: str, bundle: _TokenBundle) -> _TokenBundle:
    if not bundle.refresh_token:
        raise SpotifySessionExpired("No refresh token stored for this session.")
    cid = _require_configured()
    body = {
        "grant_type": "refresh_token",
        "refresh_token": bundle.refresh_token,
        "client_id": cid,
    }
    res = await _spotify_api_call(
        "POST",
        f"{ACCOUNTS_BASE}/api/token",
        data_body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if res.status_code != 200:
        _tokens.pop(client_session, None)
        logger.warning("Spotify token refresh failed status=%s", res.status_code)
        raise SpotifySessionExpired("Spotify token refresh failed — re-authorization required.")
    data = res.json()
    access = data.get("access_token")
    expires_in = int(data.get("expires_in") or 3600)
    new_refresh = data.get("refresh_token")
    if not isinstance(access, str) or not access:
        _tokens.pop(client_session, None)
        raise SpotifySessionExpired("Spotify refresh response missing access_token.")
    out = _TokenBundle(
        access_token=access,
        refresh_token=new_refresh if isinstance(new_refresh, str) else bundle.refresh_token,
        expires_at=time.time() + max(60, expires_in) - 30,
    )
    _tokens[client_session] = out
    return out


async def _valid_access_token(client_session: str) -> str:
    key = client_session.strip()
    bundle = _tokens.get(key)
    if bundle is None:
        raise SpotifySessionExpired("Spotify is not connected for this device session.")
    if time.time() >= bundle.expires_at:
        bundle = await _refresh_access_token(key, bundle)
    return bundle.access_token


def _spotify_error_reason(res: httpx.Response) -> str:
    try:
        payload = res.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    err = payload.get("error")
    if isinstance(err, dict):
        reason = err.get("reason")
        if isinstance(reason, str):
            return reason.strip()
    return ""


# ---- Helper: authenticated GET ----


async def _spotify_get(
    client_session: str,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authenticated GET to a Spotify API path."""
    token = await _valid_access_token(client_session)
    res = await _spotify_api_call(
        "GET",
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    if res.status_code == 401:
        raise SpotifySessionExpired("Spotify token rejected — re-authorization required.")
    if res.status_code == 403:
        reason = _spotify_error_reason(res)
        if reason == "PREMIUM_REQUIRED":
            raise PermissionError("Spotify Premium is required.")
        raise PermissionError(f"Spotify API returned 403: {reason or 'forbidden'}")
    if res.status_code == 204:
        return {}
    if res.status_code != 200:
        logger.warning("Spotify GET %s failed status=%s", path, res.status_code)
        raise RuntimeError(f"Spotify API error ({res.status_code}) for {path}.")
    payload = res.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Spotify API returned non-object for {path}.")
    return payload


async def _spotify_put(
    client_session: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> None:
    """Authenticated PUT to a Spotify API path."""
    token = await _valid_access_token(client_session)
    res = await _spotify_api_call(
        "PUT",
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        json_body=json_body,
    )
    if res.status_code == 401:
        raise SpotifySessionExpired("Spotify token rejected — re-authorization required.")
    if res.status_code == 403:
        reason = _spotify_error_reason(res)
        if reason == "PREMIUM_REQUIRED":
            raise PermissionError("Spotify Premium is required.")
        raise PermissionError(f"Spotify API returned 403: {reason or 'forbidden'}")
    if res.status_code == 204:
        return
    logger.warning("Spotify PUT %s failed status=%s", path, res.status_code)
    raise RuntimeError(f"Spotify API error ({res.status_code}) for {path}.")


async def _spotify_post(
    client_session: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authenticated POST to a Spotify API path."""
    token = await _valid_access_token(client_session)
    res = await _spotify_api_call(
        "POST",
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        json_body=json_body,
    )
    if res.status_code == 401:
        raise SpotifySessionExpired("Spotify token rejected — re-authorization required.")
    if res.status_code == 403:
        reason = _spotify_error_reason(res)
        if reason == "PREMIUM_REQUIRED":
            raise PermissionError("Spotify Premium is required.")
        raise PermissionError(f"Spotify API returned 403: {reason or 'forbidden'}")
    if res.status_code == 204:
        return {}
    if res.status_code == 201:
        payload = res.json()
        return payload if isinstance(payload, dict) else {}
    if res.status_code != 200:
        logger.warning("Spotify POST %s failed status=%s", path, res.status_code)
        raise RuntimeError(f"Spotify API error ({res.status_code}) for {path}.")
    payload = res.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Spotify API returned non-object for {path}.")
    return payload


# ---- Taste profile ----


async def _fetch_parallel(token: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    ra_res, rt_res, rr_res = await asyncio.gather(
        _spotify_api_call("GET", f"{API_BASE}/me/top/artists", headers=headers, params={"time_range": "medium_term", "limit": "20"}),
        _spotify_api_call("GET", f"{API_BASE}/me/top/tracks", headers=headers, params={"time_range": "medium_term", "limit": "20"}),
        _spotify_api_call("GET", f"{API_BASE}/me/player/recently-played", headers=headers, params={"limit": "20"}),
    )
    for label, res in (("top_artists", ra_res), ("top_tracks", rt_res), ("recent", rr_res)):
        if res.status_code == 401:
            raise SpotifySessionExpired("Spotify token rejected during taste profile fetch.")
        if res.status_code != 200:
            logger.warning("Spotify parallel fetch %s status=%s", label, res.status_code)
            raise RuntimeError(f"Spotify API error ({res.status_code}) for {label}.")
    return ra_res.json(), rt_res.json(), rr_res.json()


async def _audio_features(token: str, track_ids: list[str]) -> list[dict[str, Any]]:
    if not track_ids:
        return []
    out: list[dict[str, Any]] = []
    for i in range(0, len(track_ids), 100):
        chunk = track_ids[i : i + 100]
        res = await _spotify_api_call(
            "GET",
            f"{API_BASE}/audio-features",
            headers={"Authorization": f"Bearer {token}"},
            params={"ids": ",".join(chunk)},
        )
        if res.status_code != 200:
            logger.warning("Spotify audio-features batch failed status=%s — continuing with default audio values", res.status_code)
            return []
        data = res.json()
        feats = data.get("audio_features")
        if isinstance(feats, list):
            for item in feats:
                if isinstance(item, dict):
                    out.append(item)
    return out


def _artists_from_item(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if isinstance(name, str) and name.strip():
            out.append(name.strip())
    return out


def _aggregate_taste_with_features(
    top_artist_names: list[str],
    top_genres: list[str],
    features: list[dict[str, Any]],
) -> SpotifyTasteProfile:
    energies: list[float] = []
    tempos: list[float] = []
    instrs: list[float] = []
    for f in features:
        e = f.get("energy")
        t = f.get("tempo")
        ins = f.get("instrumentalness")
        if isinstance(e, (int, float)) and float(e) == float(e):
            energies.append(float(e))
        if isinstance(t, (int, float)) and float(t) == float(t):
            tempos.append(float(t))
        if isinstance(ins, (int, float)) and float(ins) == float(ins):
            instrs.append(float(ins))

    def avg(vals: list[float]) -> float:
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    return SpotifyTasteProfile(
        top_genres=top_genres,
        top_artists=top_artist_names[:20],
        energy_avg=round(avg(energies), 4),
        tempo_avg=round(avg(tempos), 2),
        instrumentalness_avg=round(avg(instrs), 4),
    )


async def build_taste_profile(client_session: str) -> SpotifyTasteProfile:
    token = await _valid_access_token(client_session)
    artists_raw, tracks_raw, recent_raw = await _fetch_parallel(token)

    genre_counts: dict[str, int] = {}
    top_artist_names: list[str] = []
    items = artists_raw.get("items")
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            name = it.get("name")
            if isinstance(name, str) and name.strip():
                top_artist_names.append(name.strip())
            genres = it.get("genres")
            if isinstance(genres, list):
                for g in genres:
                    if isinstance(g, str) and g.strip():
                        gg = g.strip().lower()
                        genre_counts[gg] = genre_counts.get(gg, 0) + 1
    top_genres = [g for g, _ in sorted(genre_counts.items(), key=lambda kv: (-kv[1], kv[0]))][:15]

    track_ids: list[str] = []
    track_items = tracks_raw.get("items")
    if isinstance(track_items, list):
        for it in track_items:
            if not isinstance(it, dict):
                continue
            tid = it.get("id")
            if isinstance(tid, str) and tid:
                track_ids.append(tid)

    recent_items = recent_raw.get("items")
    if isinstance(recent_items, list):
        for row in recent_items:
            if not isinstance(row, dict):
                continue
            tr = row.get("track")
            if isinstance(tr, dict):
                tid = tr.get("id")
                if isinstance(tid, str) and tid and tid not in track_ids:
                    track_ids.append(tid)

    feats = await _audio_features(token, track_ids)
    return _aggregate_taste_with_features(top_artist_names, top_genres, feats)


async def get_playback_state(client_session: str) -> SpotifyPlaybackState:
    """Fetch `GET /me/player` and normalize for cursor follow mode.

    Spotify playback state APIs require Premium for reliable device state.
    """

    token = await _valid_access_token(client_session)
    res = await _spotify_api_call(
        "GET",
        f"{API_BASE}/me/player",
        headers={"Authorization": f"Bearer {token}"},
    )
    if res.status_code == 204:
        raise RuntimeError("No active Spotify playback. Start a track on a Premium device.")
    if res.status_code == 401:
        raise SpotifySessionExpired("Spotify is not connected for this device session.")
    if res.status_code == 403:
        reason = _spotify_error_reason(res)
        if reason == "PREMIUM_REQUIRED":
            raise PermissionError("Spotify Premium is required for playback-follow mode.")
        raise PermissionError("Spotify playback state is unavailable (forbidden).")
    if res.status_code != 200:
        logger.warning("Spotify playback state failed status=%s", res.status_code)
        raise RuntimeError(f"Spotify playback API error ({res.status_code}).")

    payload = res.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Spotify playback payload was invalid.")
    progress = payload.get("progress_ms")
    item = payload.get("item")
    track_id: str | None = None
    track_name: str | None = None
    artists: list[str] = []
    if isinstance(item, dict):
        rid = item.get("id")
        if isinstance(rid, str) and rid.strip():
            track_id = rid.strip()
        rname = item.get("name")
        if isinstance(rname, str) and rname.strip():
            track_name = rname.strip()
        artists = _artists_from_item(item.get("artists"))
    return SpotifyPlaybackState(
        is_playing=bool(payload.get("is_playing")),
        progress_ms=max(0, int(progress)) if isinstance(progress, (int, float)) else 0,
        playback_rate=1.0,
        track_id=track_id,
        track_name=track_name,
        artists=artists,
    )


# ---- Search ----


async def search(
    client_session: str,
    query: str,
    type_filter: str = "track,artist,album",
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Search the Spotify catalog. Wraps GET /search (not deprecated)."""
    if not query or not query.strip():
        raise ValueError("Search query must not be empty.")
    return await _spotify_get(
        client_session,
        "/search",
        params={
            "q": query.strip(),
            "type": type_filter.strip() or "track",
            "limit": max(1, min(50, limit)),
            "offset": max(0, min(1000, offset)),
        },
    )


# ---- Recommendations ----


async def get_recommendations(
    client_session: str,
    *,
    seed_artists: str | None = None,
    seed_genres: str | None = None,
    seed_tracks: str | None = None,
    limit: int = 20,
    market: str | None = None,
    **tunable_attributes: float | int | None,
) -> dict[str, Any]:
    """Get track recommendations. Wraps GET /recommendations (not-deprecated)."""
    params: dict[str, Any] = {
        "limit": max(1, min(100, limit)),
    }
    if seed_artists:
        params["seed_artists"] = seed_artists
    if seed_genres:
        params["seed_genres"] = seed_genres
    if seed_tracks:
        params["seed_tracks"] = seed_tracks
    if market:
        params["market"] = market
    for key, val in tunable_attributes.items():
        if val is not None:
            params[key] = val
    return await _spotify_get(client_session, "/recommendations", params=params)


async def get_available_genre_seeds(client_session: str) -> dict[str, Any]:
    """Get available genre seeds for recommendations. Wraps GET /recommendations/available-genre-seeds."""
    return await _spotify_get(client_session, "/recommendations/available-genre-seeds")


# ---- Playlists ----


async def get_current_user_playlists(
    client_session: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Get current user's playlists. Wraps GET /me/playlists."""
    return await _spotify_get(
        client_session,
        "/me/playlists",
        params={
            "limit": max(1, min(50, limit)),
            "offset": max(0, offset),
        },
    )


async def get_playlist(
    client_session: str,
    playlist_id: str,
    *,
    market: str | None = None,
    fields: str | None = None,
    additional_types: str | None = None,
) -> dict[str, Any]:
    """Get a playlist. Wraps GET /playlists/{playlist_id} (not deprecated)."""
    if not playlist_id or not playlist_id.strip():
        raise ValueError("playlist_id must not be empty.")
    params: dict[str, Any] = {}
    if market:
        params["market"] = market
    if fields:
        params["fields"] = fields
    if additional_types:
        params["additional_types"] = additional_types
    return await _spotify_get(client_session, f"/playlists/{playlist_id.strip()}", params=params)


async def get_playlist_items(
    client_session: str,
    playlist_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    market: str | None = None,
    fields: str | None = None,
    additional_types: str | None = None,
) -> dict[str, Any]:
    """Get items in a playlist. Wraps GET /playlists/{playlist_id}/items (not deprecated).

    This replaces the deprecated GET /playlists/{playlist_id}/tracks endpoint.
    """
    if not playlist_id or not playlist_id.strip():
        raise ValueError("playlist_id must not be empty.")
    params: dict[str, Any] = {
        "limit": max(1, min(100, limit)),
        "offset": max(0, offset),
    }
    if market:
        params["market"] = market
    if fields:
        params["fields"] = fields
    if additional_types:
        params["additional_types"] = additional_types
    return await _spotify_get(client_session, f"/playlists/{playlist_id.strip()}/items", params=params)


# ---- Player controls ----


async def start_playback(
    client_session: str,
    *,
    device_id: str | None = None,
    context_uri: str | None = None,
    uris: list[str] | None = None,
    offset: dict[str, Any] | None = None,
    position_ms: int | None = None,
) -> None:
    """Start or resume playback. Wraps PUT /me/player/play (not deprecated).

    Requires Spotify Premium. scopes: user-modify-playback-state
    """
    params: dict[str, str] = {}
    if device_id:
        params["device_id"] = device_id
    body: dict[str, Any] = {}
    if context_uri:
        body["context_uri"] = context_uri
    if uris is not None:
        body["uris"] = uris
    if offset is not None:
        body["offset"] = offset
    if position_ms is not None:
        body["position_ms"] = position_ms
    await _spotify_put(client_session, "/me/player/play", params=params or None, json_body=body or None)


async def pause_playback(
    client_session: str,
    *,
    device_id: str | None = None,
) -> None:
    """Pause playback. Wraps PUT /me/player/pause (not deprecated).

    Requires Spotify Premium. scopes: user-modify-playback-state
    """
    params: dict[str, str] = {}
    if device_id:
        params["device_id"] = device_id
    await _spotify_put(client_session, "/me/player/pause", params=params or None)


async def skip_to_next(
    client_session: str,
    *,
    device_id: str | None = None,
) -> None:
    """Skip to next track. Wraps POST /me/player/next (not deprecated).

    Requires Spotify Premium. scopes: user-modify-playback-state
    """
    params: dict[str, str] = {}
    if device_id:
        params["device_id"] = device_id
    await _spotify_post(client_session, "/me/player/next", params=params or None)


async def skip_to_previous(
    client_session: str,
    *,
    device_id: str | None = None,
) -> None:
    """Skip to previous track. Wraps POST /me/player/previous (not deprecated).

    Requires Spotify Premium. scopes: user-modify-playback-state
    """
    params: dict[str, str] = {}
    if device_id:
        params["device_id"] = device_id
    await _spotify_post(client_session, "/me/player/previous", params=params or None)


async def seek_to_position(
    client_session: str,
    position_ms: int,
    *,
    device_id: str | None = None,
) -> None:
    """Seek to a position in the current track. Wraps PUT /me/player/seek (not deprecated).

    Requires Spotify Premium. scopes: user-modify-playback-state
    """
    if position_ms < 0:
        raise ValueError("position_ms must be non-negative.")
    params: dict[str, Any] = {"position_ms": position_ms}
    if device_id:
        params["device_id"] = device_id
    await _spotify_put(client_session, "/me/player/seek", params=params)
