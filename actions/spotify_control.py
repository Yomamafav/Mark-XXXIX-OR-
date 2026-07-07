import json
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_spotify():
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    base = _base_dir()
    keys_path = base / "config" / "api_keys.json"
    try:
        with open(keys_path, "r", encoding="utf-8") as f:
            keys = json.load(f)
        client_id     = keys.get("spotify_client_id", "")
        client_secret = keys.get("spotify_client_secret", "")
    except Exception:
        raise RuntimeError("Could not read config/api_keys.json.")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Add spotify_client_id and spotify_client_secret to config/api_keys.json. "
            "Get them from developer.spotify.com → Your Apps."
        )

    cache_path = str(base / "config" / ".spotify_cache")
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8888/callback",
        scope=(
            "user-read-playback-state "
            "user-modify-playback-state "
            "user-read-currently-playing"
        ),
        cache_path=cache_path,
        open_browser=True,
    ))
    return sp


def spotify_control(parameters: dict, player=None) -> str:
    try:
        sp = _get_spotify()
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Spotify connection failed: {e}"

    action = parameters.get("action", "play")

    try:
        if action == "play":
            query = parameters.get("query", "").strip()
            if not query:
                sp.start_playback()
                return "Resumed playback."
            search_type = parameters.get("type", "track")
            results     = sp.search(q=query, type=search_type, limit=1)
            items       = results.get(search_type + "s", {}).get("items", [])
            if not items:
                return f"Nothing found on Spotify for: {query}"
            item = items[0]
            uri  = item["uri"]
            name = item.get("name", query)
            if search_type == "track":
                sp.start_playback(uris=[uri])
            else:
                sp.start_playback(context_uri=uri)
            return f"Playing: {name}"

        if action == "pause":
            sp.pause_playback()
            return "Paused."

        if action == "resume":
            sp.start_playback()
            return "Resumed."

        if action == "next":
            sp.next_track()
            return "Skipped to next track."

        if action == "previous":
            sp.previous_track()
            return "Previous track."

        if action == "current_track":
            current = sp.current_playback()
            if not current or not current.get("item"):
                return "Nothing is playing right now."
            track   = current["item"]
            artists = ", ".join(a["name"] for a in track.get("artists", []))
            name    = track.get("name", "Unknown")
            return f"Now playing: {name} by {artists}"

        if action == "volume":
            vol = max(0, min(100, int(parameters.get("volume", 50))))
            sp.volume(vol)
            return f"Volume set to {vol}%."

    except spotipy.exceptions.SpotifyException as e:
        if "NO_ACTIVE_DEVICE" in str(e):
            return "No active Spotify device found. Open Spotify on your PC first."
        return f"Spotify error: {e}"
    except Exception as e:
        return f"Spotify error: {e}"

    return f"Unknown spotify action: {action}"
