# Installazione bot comment-to-DM sul Mac di Ale — guida per la call

Checklist per Mattia. Durata stimata: 15-20 minuti.
Ale ha Claude Code (desktop app): i comandi può incollarli lì o nel Terminale,
il risultato è lo stesso.

## PRIMA della call (Mattia, 5 min)

- [ ] Definire con Ale (anche via messaggio) **parole chiave** e **testo del DM**
      definitivi, e aggiornare `config.json` in questa cartella.
- [ ] Verificare che in questa cartella ci siano: `.env`, `bot.py`, `config.json`,
      `state.json`, `setup_token.py`, questa guida.

## In call — passo 1: trasferire la cartella (Ale è in Cina, niente AirDrop)

Via **SwissTransfer** (swisstransfer.com): caricare lo zip `ferroshaolin-bot.zip`,
**attivare la password di download** nelle opzioni, scadenza breve (1-7 giorni).
La password si comunica **a voce in call** (mai nello stesso messaggio del link).
Il pacchetto contiene il `.env` coi token: per questo la password è obbligatoria.

Ale scarica lo zip e lo scompatta: doppio click in `~/Downloads` →
`~/Downloads/ferroshaolin`.

## In call — passo 2: mettere in posizione (sul Mac di Ale)

```bash
mkdir -p ~/Automazioni && rm -rf ~/Automazioni/ferroshaolin && cp -R ~/Downloads/ferroshaolin ~/Automazioni/ferroshaolin && chmod 600 ~/Automazioni/ferroshaolin/.env && echo OK
```

## In call — passo 3: verificare Python

```bash
python3 --version
```

Se appare una finestra che chiede di installare gli "strumenti per sviluppatori":
Installa, attendere (~5 min), poi rilanciare il comando.

## In call — passo 4: giro di prova

```bash
python3 ~/Automazioni/ferroshaolin/bot.py
```

Nessun output = tutto bene (legge Instagram, nessun commento nuovo da gestire).
Se dà errori, fermarsi qui e chiamare Claude/Mattia.

## In call — passo 5: test dal vivo

Mattia (o Ale da un secondo account) commenta la parola chiave su un post
recente di @ferroshaolin, si rilancia il comando del passo 4 e si controlla:
DM arrivato + risposta pubblica sotto il commento + riga in
`~/Automazioni/ferroshaolin/bot.log`.

## In call — passo 6: avvio automatico (ogni 2 minuti)

Creare il file LaunchAgent:

```bash
cat > ~/Library/LaunchAgents/com.mld.ferroshaolin-commentdm.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mld.ferroshaolin-commentdm</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$HOME/Automazioni/ferroshaolin/bot.py</string>
  </array>
  <key>StartInterval</key><integer>120</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Automazioni/ferroshaolin/launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/Automazioni/ferroshaolin/launchd.log</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.mld.ferroshaolin-commentdm.plist && launchctl list | grep ferroshaolin
```

Se l'ultima riga mostra `com.mld.ferroshaolin-commentdm`, il bot è ATTIVO:
parte da solo a ogni accensione del Mac e controlla i commenti ogni 2 minuti.

## In call — passo 7: chiusura

- [ ] Spiegare ad Ale: il bot lavora solo col Mac acceso; a Mac spento i DM
      partono alla riaccensione (recupera fino a 7 giorni).
- [ ] Comandi da lasciare ad Ale:
      spegnere → `launchctl unload ~/Library/LaunchAgents/com.mld.ferroshaolin-commentdm.plist`
      accendere → `launchctl load ~/Library/LaunchAgents/com.mld.ferroshaolin-commentdm.plist`
      log → `open -e ~/Automazioni/ferroshaolin/bot.log`
- [ ] ⚠️ Da questo momento il bot gira SOLO dal Mac di Ale: Mattia non lancia
      più `bot.py` dal suo (due bot = DM doppi).
- [ ] Aggiornare `clienti/alessandro-ferrari/social-media/2026-08-28-comment-to-dm.md`
      (stato: ATTIVO, dove gira, keywords definitive) e fare `/fine`.

## Se in futuro il bot smette di funzionare

Errore `190` nel log = token scaduto/invalidato (es. cambio password Facebook
di Mattia). Rimedio: rigenerare il token nel Graph API Explorer (guida in
`fondamenta/metodi/instagram-comment-to-dm.md`, Fase 2), rilanciare
`setup_token.py` e ri-AirDroppare il `.env` ad Ale.

## Cambiare parole chiave o testo del DM

Basta modificare `~/Automazioni/ferroshaolin/config.json` sul Mac di Ale
(anche Ale da solo, chiedendo a Claude Code: "cambia il messaggio del bot in ...").
Nessun riavvio necessario: il passaggio successivo usa già i nuovi testi.
