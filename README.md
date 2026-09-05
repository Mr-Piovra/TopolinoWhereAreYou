# 🐭 Topolino Where Are You - Monitor Panini 3694

Sistema ad alta affidabilità per il monitoraggio della disponibilità di **Topolino 3694 con Modellino F1** sul sito ufficiale Panini.it, con notifiche push istantanee via **Bot Telegram** e containerizzazione **Docker**.

---

## ⚡️ Funzionalità Principali

- 🛡 **Anti-Bot & Anti-Blocking Avanzato**:
  - Fingerprinting TLS/HTTP2 realistico basato su **Chrome 124** tramite `curl_cffi` (supera Fastly CDN, WAF e Queue-it senza blocchi).
  - Intervallo di polling dinamico con **jitter casuale** (es. 35s ± 8s) per evitare schemi di traffico automatizzati fissi.
  - Verifica su URL canonico pulito (evita trigger di blocco 403 causati da parametri di tracking arbitrari).
  - Backoff automatico intelligente in caso di errori o problemi di rete temporanei.
- 🎯 **Verifica Multi-Segnale (Affidabilità 100%)**:
  - Controllo incrociato su 4 livelli: Script JavaScript `product.status`, script `dataLayerProductDetail`, metadati JSON-LD `schema.org/InStock` e presenza del pulsante attivo `#product-addtocart-button`.
- 🚨 **Notifiche Telegram ad Alta Priorità**:
  - **Allarme a raffica**: 3 notifiche consecutive a distanza di 2 secondi con suono per svegliarti o attirare subito la tua attenzione.
  - **Promemoria ricorrente**: una notifica ogni 3 minuti finché il prodotto è disponibile.
  - **Comando `/stop`**: silenzia i promemoria una volta completato l'acquisto.
  - **Pulsante di acquisto rapido**: pulsante inline diretto *"🛒 ACQUISTA SUBITO SU PANINI"*.
  - **Heartbeat orario**: messaggio silenzioso ogni ora per confermarti che il monitor sul server è attivo e vegeto.
- 💬 **Bot Telegram Completamente Interattivo**:
  - `/status` - Mostra lo stato attuale del monitoraggio, prezzo, ultimo controllo, uptime e statistiche.
  - `/check` - Esegue all'istante un controllo in tempo reale su Panini.it e ti mostra l'esito.
  - `/interval <secondi>` - Modifica la velocità di controllo al volo (es. `/interval 20` prima della mezzanotte) senza riavviare il server.
  - `/stop` - Silenzia i promemoria ricorrenti.
  - `/resume` - Riattiva i promemoria ricorrenti.
  - `/test` - Simula l'allarme di disponibilità per testare suoneria e notifiche sul telefono.
  - `/help` - Mostra la lista dei comandi.
- 🐳 **Pronto per Docker & Docker Compose**:
  - Immagine leggera Python 3.11-slim.
  - Fuso orario impostato su `Europe/Rome`.
  - Persistenza dello stato su volume dedicato.

---

## 📋 Prerequisiti: Configurare Telegram (2 minuti)

### 1. Crea il Bot Telegram
1. Apri Telegram e cerca l'utente ufficiale **[@BotFather](https://t.me/BotFather)**.
2. Invia il comando `/newbot`.
3. Scegli un nome per il bot (es. `Topolino 3694 Monitor`) e uno username che finisca in `bot` (es. `topolino_3694_radar_bot`).
4. BotFather ti fornirà un **API Token** del tipo:
   `7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`

### 2. Trova il tuo Chat ID
1. Cerca su Telegram il bot **[@userinfobot](https://t.me/userinfobot)** oppure **[@getmyid_bot](https://t.me/getmyid_bot)** e premi `Avvia`.
2. Ti risponderà con il tuo ID numerico (es. `123456789`).
3. **Importante**: Apri la chat con il *tuo nuovo bot appena creato* e premi **"Avvia"** (`/start`) per autorizzarlo a scriverti.

---

## 🚀 Guida all'Uso

### Opzione A: Deployment su Server con Docker (Consigliata)

1. **Copia i file del progetto sul tuo server** (tramite git, rsync o scp).
2. Entra nella cartella e modifica il file `.env`:
   ```bash
   nano .env
   ```
   Inserisci il tuo `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
3. **Avvia il container con Docker Compose**:
   ```bash
   docker compose up -d --build
   ```
4. **Visualizza i log in tempo reale**:
   ```bash
   docker compose logs -f
   ```
5. Per fermare il servizio:
   ```bash
   docker compose down
   ```

---

### Opzione B: Esecuzione Locale (senza Docker)

1. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
2. Configura il file `.env`:
   ```bash
   cp .env.example .env
   # Apri .env e inserisci token e chat id
   ```
3. Avvia il monitor:
   ```bash
   python main.py
   ```

---

## ⚙️ Variabili d'Ambiente (`.env`)

| Variabile | Descrizione | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token ottenuto da @BotFather | *(obbligatorio)* |
| `TELEGRAM_CHAT_ID` | Tuo ID utente Telegram | *(obbligatorio)* |
| `TARGET_URL` | URL del prodotto Panini | `https://www.panini.it/shp_ita_it/topolino-3694-...` |
| `CHECK_INTERVAL_SECONDS` | Intervallo base di controllo | `35` |
| `JITTER_SECONDS` | Variazione casuale anti-bot (± sec) | `8` |
| `BURST_COUNT` | Notifiche a raffica all'uscita | `3` |
| `BURST_DELAY_SECONDS` | Pausa tra le notifiche a raffica | `2.0` |
| `REPEAT_INTERVAL_MINUTES` | Promemoria ricorrente finché disponibile | `3` |
| `HEARTBEAT_INTERVAL_MINUTES` | Frequenza messaggio di stato (min) | `60` (ogni ora) |
| `PROXY_URL` | Proxy HTTP/SOCKS5 opzionale | *(vuoto)* |
| `LOG_LEVEL` | Livello dettaglio log (`INFO`, `DEBUG`) | `INFO` |

---

## 🧪 Esecuzione Test di Verifica

Per verificare che la logica di parsing rilevi correttamente i prodotti disponibili ed esauriti:
```bash
python test_system.py
```
Il test interroga in tempo reale sia il link del 3694 (attualmente non disponibile) sia il link di test fornito (disponibile), verificando al 100% l'accuratezza dei segnali.

---

## 🔗 Integrazione con Server Watchdog / Bot Condiviso

Se disponi già di un bot Telegram attivo sul tuo server (come `server-watchdog`), puoi evitare conflitti di polling Telegram (`409 Conflict`) impostando nel file `.env`:

```env
ENABLE_POLLING=false
API_HOST=0.0.0.0
API_PORT=8085
```

In questa modalità:
1. **Notifiche Push Autonome**: `topolino_monitor` invia direttamente via Telegram API tutti gli allarmi immediati (raffica 3x sonori), promemoria ciclici e heartbeat orario.
2. **Micro API HTTP Interna**: Espone l'endpoint `http://127.0.0.1:8085` (`/status`, `/check`, `/interval`, `/stop`, `/resume`, `/test`).
3. **Comandi Centralizzati**: Il bot principale del server (es. `@JayAM02Bot`) inoltra i comandi con `/topolino`, `/topolino check`, `/topolino interval 20`, `/topolino stop`, `/topolino test`.
