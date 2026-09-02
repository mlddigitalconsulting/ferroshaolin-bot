#!/usr/bin/env python3
"""Setup credenziali Meta per FerroShaolin Automazioni.

Legge .env (App ID, App Secret, token breve dal Graph API Explorer) e:
 1. scambia il token breve con un token utente a lunga durata (~60 giorni)
 2. recupera la pagina Facebook collegata (id + page token, senza scadenza)
 3. recupera l'ID dell'account Instagram Business collegato alla pagina
 4. scrive tutto nel .env

Non stampa mai i token a video: solo nomi e ID.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"
GRAPH = "https://graph.facebook.com/v23.0"


def load_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def save_env(updates: dict) -> None:
    lines = ENV_PATH.read_text().splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        key = stripped.partition("=")[0].strip() if "=" in stripped and not stripped.startswith("#") else None
        if key and key in updates:
            out.append(f"{key}={updates[key]}")
        else:
            out.append(line)
    ENV_PATH.write_text("\n".join(out) + "\n")


def get(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"ERRORE API ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    env = load_env()
    for k in ("META_APP_ID", "META_APP_SECRET", "META_SHORT_TOKEN"):
        if not env.get(k):
            sys.exit(f"Campo {k} vuoto nel .env: compilalo prima di lanciare lo script.")

    # 1. token a lunga durata
    long_tok = env.get("META_LONG_TOKEN")
    if not long_tok:
        data = get(f"{GRAPH}/oauth/access_token", {
            "grant_type": "fb_exchange_token",
            "client_id": env["META_APP_ID"],
            "client_secret": env["META_APP_SECRET"],
            "fb_exchange_token": env["META_SHORT_TOKEN"],
        })
        long_tok = data["access_token"]
        save_env({"META_LONG_TOKEN": long_tok})
        print("1/3  Token a lunga durata: OK (valido ~60 giorni)")
    else:
        print("1/3  Token a lunga durata: già presente, salto")

    # 2. pagina collegata
    data = get(f"{GRAPH}/me/accounts", {
        "fields": "id,name,access_token",
        "access_token": long_tok,
    })
    pages = data.get("data", [])
    if not pages:
        sys.exit("Nessuna pagina trovata: nel popup di login la pagina FerroShaolin non è stata autorizzata.")
    if len(pages) > 1:
        print("Trovate più pagine autorizzate:")
        for p in pages:
            print(f"  - {p['name']} (id {p['id']})")
        sys.exit("Rilancia dopo aver ristretto l'app alla sola pagina FerroShaolin, o dimmi quale usare.")
    page = pages[0]
    save_env({"PAGE_ID": page["id"], "PAGE_TOKEN": page["access_token"]})
    print(f"2/3  Pagina: {page['name']} (id {page['id']})")

    # 3. account Instagram collegato
    data = get(f"{GRAPH}/{page['id']}", {
        "fields": "instagram_business_account{id,username}",
        "access_token": page["access_token"],
    })
    ig = data.get("instagram_business_account")
    if not ig:
        sys.exit("La pagina non ha un account Instagram Business collegato: verificare il collegamento in Meta Business Suite.")
    save_env({"IG_USER_ID": ig["id"]})
    print(f"3/3  Instagram: @{ig.get('username', '?')} (id {ig['id']})")

    print("\nSetup completato: .env aggiornato.")


if __name__ == "__main__":
    main()
