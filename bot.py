#!/usr/bin/env python3
"""Comment-to-DM per @ferroshaolin.

Un passaggio per esecuzione (pensato per launchd/cron ogni ~2 minuti):
 1. legge gli ultimi post dell'account Instagram
 2. cerca nei commenti nuovi le parole chiave di config.json
 3. a chi le scrive manda una private reply (DM) e, se configurata,
    una risposta pubblica sotto il commento
 4. segna in state.json i commenti già gestiti (mai doppioni)

Testi e parole chiave: config.json. Credenziali: .env. Log: bot.log.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
GRAPH = "https://graph.facebook.com/v23.0"
LOG_PATH = BASE / "bot.log"
STATE_PATH = BASE / "state.json"


def log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def load_env() -> dict:
    env = {}
    for line in (BASE / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def api_get(path: str, params: dict) -> dict:
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def api_post(path: str, payload: dict, token: str) -> dict:
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode({"access_token": token})
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def api_error(e: urllib.error.HTTPError) -> str:
    try:
        err = json.loads(e.read()).get("error", {})
        return f"{err.get('code')}/{err.get('error_subcode')}: {err.get('message')}"
    except Exception:
        return f"HTTP {e.code}"


def matches(text: str, keywords: list) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{re.escape(k.lower())}\b", t) for k in keywords)


def main() -> None:
    env = load_env()
    cfg = load_json(BASE / "config.json", None)
    if cfg is None:
        sys.exit("config.json mancante")
    for k in ("PAGE_ID", "PAGE_TOKEN", "IG_USER_ID"):
        if not env.get(k):
            sys.exit(f"{k} mancante nel .env: lanciare prima setup_token.py")

    token = env["PAGE_TOKEN"]
    state = load_json(STATE_PATH, {"replied": {}, "own_username": None})

    if not state.get("own_username"):
        me = api_get(env["IG_USER_ID"], {"fields": "username", "access_token": token})
        state["own_username"] = me.get("username", "")

    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["max_comment_age_days"])
    handled = 0

    media = api_get(f"{env['IG_USER_ID']}/media", {
        "fields": "id,timestamp",
        "limit": cfg["media_limit"],
        "access_token": token,
    }).get("data", [])

    for m in media:
        comments = api_get(f"{m['id']}/comments", {
            "fields": "id,text,timestamp,username",
            "limit": 50,
            "access_token": token,
        }).get("data", [])

        for c in comments:
            cid = c["id"]
            entry = state["replied"].get(cid)
            if entry and (entry.get("ok") or entry.get("attempts", 0) >= 3):
                continue
            if c.get("username", "") == state["own_username"]:
                continue
            ts = datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if ts < cutoff:
                continue
            if not matches(c.get("text", ""), cfg["keywords"]):
                continue

            entry = entry or {"attempts": 0}
            entry["attempts"] += 1
            try:
                api_post(f"{env['PAGE_ID']}/messages", {
                    "recipient": {"comment_id": cid},
                    "message": {"text": cfg["dm_message"]},
                }, token)
                entry["ok"] = True
                log(f"DM inviato a @{c.get('username')} (commento: {c.get('text', '')[:60]!r})")
                handled += 1
            except urllib.error.HTTPError as e:
                entry["error"] = api_error(e)
                log(f"ERRORE DM a @{c.get('username')}: {entry['error']}")

            if entry.get("ok") and cfg.get("public_reply"):
                try:
                    api_post(f"{cid}/replies", {"message": cfg["public_reply"]}, token)
                except urllib.error.HTTPError as e:
                    log(f"ERRORE risposta pubblica a @{c.get('username')}: {api_error(e)}")

            state["replied"][cid] = entry
            STATE_PATH.write_text(json.dumps(state, indent=1))
            time.sleep(1)

    STATE_PATH.write_text(json.dumps(state, indent=1))
    if handled:
        log(f"Passaggio completato: {handled} DM inviati")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        log(f"ERRORE API: {api_error(e)}")
        sys.exit(1)
    except Exception as e:
        log(f"ERRORE: {e}")
        sys.exit(1)
