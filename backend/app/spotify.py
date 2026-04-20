"""Spotify OAuth (PKCE) + taste aggregation — PRIORITIES §67.

Tokens live only in this module's in-memory store (keyed by opaque `client_session`).
Never log access tokens, refresh tokens, or authorization codes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.schemas import SpotifyTasteProfile

logger = logging.getLogger("harmoniq.spotify")

ACCOUNTS_BASE = "https://accounts.spotify.com"
API_BASE = "https://api.spotify.com/v1"
SCOPES = "user-top-read user-read-recently-played"

_pending: dict[str, tuple[str, str, Literal["native", "web"]]] = {}
"""state -> (code_verifier, client_session, return_platform)."""

_tokens: dict[str, _TokenBundle] = {}
"""client_session -> tokens."""


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
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{ACCOUNTS_BASE}/api/token",
            data=body,
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
        raise ValueError("No refresh token stored for this session.")
    cid = _require_configured()
    body = {
        "grant_type": "refresh_token",
        "refresh_token": bundle.refresh_token,
        "client_id": cid,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{ACCOUNTS_BASE}/api/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code != 200:
        logger.warning("Spotify token refresh failed status=%s", res.status_code)
        raise ValueError("Spotify token refresh failed.")
    data = res.json()
    access = data.get("access_token")
    expires_in = int(data.get("expires_in") or 3600)
    new_refresh = data.get("refresh_token")
    if not isinstance(access, str) or not access:
        raise ValueError("Spotify refresh response missing access_token.")
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
        raise ValueError("Spotify is not connected for this device session.")
    if time.time() >= bundle.expires_at:
        bundle = await _refresh_access_token(key, bundle)
    return bundle.access_token


async def _fetch_parallel(token: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {token}"}
        ra, rt, rr = await asyncio.gather(
            client.get(
                f"{API_BASE}/me/top/artists",
                headers=headers,
                params={"time_range": "medium_term", "limit": "20"},
            ),
            client.get(
                f"{API_BASE}/me/top/tracks",
                headers=headers,
                params={"time_range": "medium_term", "limit": "20"},
            ),
            client.get(
                f"{API_BASE}/me/player/recently-played",
                headers=headers,
                params={"limit": "20"},
            ),
        )
    for label, res in (("top_artists", ra), ("top_tracks", rt), ("recent", rr)):
        if res.status_code != 200:
            logger.warning("Spotify parallel fetch %s status=%s", label, res.status_code)
            raise RuntimeError(f"Spotify API error ({res.status_code}) for {label}.")
    return ra.json(), rt.json(), rr.json()


async def _audio_features(token: str, track_ids: list[str]) -> list[dict[str, Any]]:
    if not track_ids:
        return []
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(track_ids), 100):
            chunk = track_ids[i : i + 100]
            res = await client.get(
                f"{API_BASE}/audio-features",
                headers={"Authorization": f"Bearer {token}"},
                params={"ids": ",".join(chunk)},
            )
            if res.status_code != 200:
                logger.warning("Spotify audio-features batch failed status=%s", res.status_code)
                raise RuntimeError("Spotify audio-features request failed.")
            data = res.json()
            feats = data.get("audio_features")
            if isinstance(feats, list):
                for item in feats:
                    if isinstance(item, dict):
                        out.append(item)
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
