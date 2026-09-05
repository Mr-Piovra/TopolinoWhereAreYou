import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Carica variabili dal file .env se presente
load_dotenv()

@dataclass
class Config:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    
    target_url: str = os.getenv(
        "TARGET_URL", 
        "https://www.panini.it/shp_ita_it/topolino-3694-con-seconda-parte-modellino-f1-1wtopo3694v-it08.html"
    ).strip()
    
    # Intervallo base di controllo in secondi (Opzione A: 30-45s)
    check_interval_seconds: int = int(os.getenv("CHECK_INTERVAL_SECONDS", "35"))
    # Jitter casuale in secondi (± JITTER_SECONDS) per evitare cadenza regolare
    jitter_seconds: int = int(os.getenv("JITTER_SECONDS", "8"))
    
    # Numero di notifiche immediate a raffica quando diventa disponibile
    burst_count: int = int(os.getenv("BURST_COUNT", "3"))
    # Pausa in secondi tra una notifica a raffica e la successiva
    burst_delay_seconds: float = float(os.getenv("BURST_DELAY_SECONDS", "2.0"))
    
    # Minuti tra una notifica e la successiva finché l'utente non invia /stop
    repeat_interval_minutes: int = int(os.getenv("REPEAT_INTERVAL_MINUTES", "3"))
    
    # Intervallo del messaggio "Heartbeat" in minuti (60 min = ogni ora)
    heartbeat_interval_minutes: int = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "60"))
    
    # Proxy opzionale (es. http://user:pass@host:port oppure socks5://...)
    proxy_url: Optional[str] = os.getenv("PROXY_URL") or None
    
    # Percorso del file di stato persistente
    state_file: str = os.getenv("STATE_FILE", "data/monitor_state.json")
    
    # Livello di log
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Abilita il polling Telegram autonomo (impostare a False se si condivide il token bot con un altro servizio)
    enable_polling: bool = os.getenv("ENABLE_POLLING", "true").lower() in ("true", "1", "yes")

    # Micro API HTTP interna per integrazione comandi (status, check, interval, stop)
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8085"))

    def validate(self) -> list[str]:
        warnings = []
        if not self.telegram_bot_token:
            warnings.append("TELEGRAM_BOT_TOKEN non è impostato. Le notifiche Telegram non funzioneranno.")
        if not self.telegram_chat_id:
            warnings.append("TELEGRAM_CHAT_ID non è impostato. Le notifiche Telegram non funzioneranno.")
        return warnings

config = Config()
