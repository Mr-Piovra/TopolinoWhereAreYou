import asyncio
import json
import logging
import os
import random
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional

from aiohttp import web
from bot import TelegramMonitorBot
from checker import CheckResult, PaniniAvailabilityChecker
from config import config

# Configurazione Logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TopolinoMonitor")

class TopolinoMonitorService:
    def __init__(self):
        self.config = config
        self.checker = PaniniAvailabilityChecker(
            target_url=config.target_url,
            proxy_url=config.proxy_url
        )
        self.bot = TelegramMonitorBot(
            config=config,
            on_manual_check=self._do_manual_check,
            on_interval_change=self._on_interval_changed,
        )
        
        self.is_running: bool = True
        self.was_available: bool = False
        self.last_recurring_alert: Optional[datetime] = None
        self.last_heartbeat_time: datetime = datetime.now()
        self.recurring_cycle: int = 0
        self.consecutive_errors: int = 0
        self.api_runner: Optional[web.AppRunner] = None

        self._load_state()

    def _load_state(self):
        """Carica lo stato persistente dal file JSON se esiste."""
        if os.path.exists(self.config.state_file):
            try:
                with open(self.config.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.was_available = data.get("was_available", False)
                    self.bot.total_checks = data.get("total_checks", 0)
                    self.bot.is_muted = data.get("is_muted", False)
                    logger.info("Stato precedente caricato: was_available=%s, checks=%s", self.was_available, self.bot.total_checks)
            except Exception as e:
                logger.warning("Impossibile caricare il file di stato: %s", e)

    def _save_state(self):
        """Salva lo stato corrente su disco."""
        try:
            os.makedirs(os.path.dirname(self.config.state_file) or ".", exist_ok=True)
            with open(self.config.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "was_available": self.was_available,
                    "total_checks": self.bot.total_checks,
                    "is_muted": self.bot.is_muted,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.debug("Errore salvataggio stato: %s", e)

    def _do_manual_check(self) -> CheckResult:
        """Funzione invocata dal comando /check di Telegram."""
        return self.checker.check()


    async def _init_http_api(self):
        """Avvia un server HTTP asincrono leggero per comandi esterni da Watchdog/host."""
        app = web.Application()
        app.router.add_get('/status', self._api_status)
        app.router.add_get('/check', self._api_check)
        app.router.add_post('/check', self._api_check)
        app.router.add_post('/interval', self._api_interval)
        app.router.add_post('/stop', self._api_stop)
        app.router.add_post('/mute', self._api_stop)
        app.router.add_post('/resume', self._api_resume)
        app.router.add_post('/test', self._api_test)

        self.api_runner = web.AppRunner(app)
        await self.api_runner.setup()
        site = web.TCPSite(self.api_runner, self.config.api_host, self.config.api_port)
        await site.start()
        logger.info(f"API HTTP interna avviata su http://{self.config.api_host}:{self.config.api_port}")

    async def _api_status(self, request: web.Request) -> web.Response:
        uptime = (datetime.now() - self.bot.start_time).total_seconds()
        last_res = self.bot.last_check_result
        return web.json_response({
            "service": "topolino-monitor",
            "is_available": self.was_available,
            "title": last_res.title if last_res else "Topolino 3694",
            "price": last_res.price if last_res else 10.35,
            "presale_date": last_res.presale_date if last_res else None,
            "status_raw": last_res.status_raw if last_res else "In attesa del primo check",
            "total_checks": self.bot.total_checks,
            "check_interval_seconds": self.config.check_interval_seconds,
            "jitter_seconds": self.config.jitter_seconds,
            "is_muted": self.bot.is_muted,
            "last_check_time": self.bot.last_check_time.isoformat() if self.bot.last_check_time else None,
            "uptime_seconds": int(uptime),
            "target_url": self.config.target_url
        })

    async def _api_check(self, request: web.Request) -> web.Response:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self.checker.check)
        self.bot.total_checks += 1
        self.bot.last_check_result = result
        self.bot.last_check_time = datetime.now()
        return web.json_response({
            "is_available": result.is_available,
            "title": result.title,
            "price": result.price,
            "presale_date": result.presale_date,
            "status_raw": result.status_raw,
            "response_time": result.response_time,
            "status_code": result.status_code,
            "error": result.error,
            "signals": result.signals
        })

    async def _api_interval(self, request: web.Request) -> web.Response:
        val = request.query.get("val")
        if not val and request.can_read_body:
            try:
                body = await request.json()
                val = body.get("val") or body.get("interval")
            except Exception:
                pass
        try:
            new_interval = int(val)
            if new_interval < 5 or new_interval > 600:
                return web.json_response({"error": "L'intervallo deve essere tra 5 e 600 secondi"}, status=400)
            self.config.check_interval_seconds = new_interval
            self._on_interval_changed(new_interval)
            return web.json_response({"ok": True, "check_interval_seconds": new_interval})
        except (ValueError, TypeError):
            return web.json_response({"error": "Parametro val non valido"}, status=400)

    async def _api_stop(self, request: web.Request) -> web.Response:
        self.bot.is_muted = True
        self._save_state()
        return web.json_response({"ok": True, "is_muted": True, "message": "Promemoria ricorrenti silenziati"})

    async def _api_resume(self, request: web.Request) -> web.Response:
        self.bot.is_muted = False
        self._save_state()
        return web.json_response({"ok": True, "is_muted": False, "message": "Promemoria ricorrenti riattivati"})

    async def _api_test(self, request: web.Request) -> web.Response:
        asyncio.create_task(self.bot.send_burst_alert(
            title="Topolino 3694 Con Seconda Parte Modellino F1 (TEST)",
            price=10.35,
            url=self.config.target_url,
            is_simulation=True
        ))
        return web.json_response({"ok": True, "message": "Allarme test a raffica inviato"})

    def _on_interval_changed(self, new_val: int):
        """Callback invocata dal comando /interval di Telegram."""
        logger.info("Intervallo di controllo aggiornato a %s secondi", new_val)

    async def start(self):
        """Avvia il monitor e il bot Telegram concorrentemente."""
        logger.info("==================================================")
        logger.info("🚀 TOPOLINO 3694 DISPONIBILITÀ MONITOR AVVIATO")
        logger.info("Target URL: %s", self.config.target_url)
        logger.info("Intervallo: %ss (±%ss jitter)", self.config.check_interval_seconds, self.config.jitter_seconds)
        logger.info("Allarmi burst: %s notifiche a distanza di %ss", self.config.burst_count, self.config.burst_delay_seconds)
        logger.info("Promemoria ricorrente: ogni %s minuti", self.config.repeat_interval_minutes)
        logger.info("Heartbeat: ogni %s minuti", self.config.heartbeat_interval_minutes)
        logger.info("==================================================")

        warnings = self.config.validate()
        for w in warnings:
            logger.warning("ATTENZIONE: %s", w)

        # Avvia micro API HTTP interna
        try:
            await self._init_http_api()
        except Exception as e:
            logger.error(f"Errore avvio API HTTP: {e}")

        # Inizializza il bot Telegram
        await self.bot.initialize()

        # Invia messaggio di benvenuto / avvio a Telegram se configurato
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            try:
                await self.bot.application.bot.send_message(
                    chat_id=self.config.telegram_chat_id,
                    text=(
                        "🤖 <b>Monitor Topolino 3694 Online!</b>\n\n"
                        f"• <b>Target:</b> Topolino 3694 (Modellino F1)\n"
                        f"• <b>Frequenza:</b> ogni {self.config.check_interval_seconds}s\n"
                        f"• <b>Heartbeat:</b> ogni ora\n\n"
                        "Il sistema è attivo e ti avviserà non appena sarà acquistabile!"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error("Impossibile inviare notifica di avvio a Telegram: %s", e)

        # Loop di monitoraggio principale
        while self.is_running:
            try:
                await self._check_cycle()
            except asyncio.CancelledError:
                logger.info("Monitoraggio interrotto.")
                break
            except Exception as e:
                logger.error("Errore inatteso nel ciclo di monitoraggio: %s", e, exc_info=True)

            # Calcolo sleep con jitter casuale anti-blocco
            jitter = random.uniform(-self.config.jitter_seconds, self.config.jitter_seconds)
            sleep_duration = max(5.0, self.config.check_interval_seconds + jitter)
            logger.debug("Prossimo controllo tra %.1f secondi...", sleep_duration)

            try:
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

    async def _check_cycle(self):
        """Esegue un singolo ciclo di controllo e gestisce gli allarmi."""
        result = self.checker.check()
        self.bot.total_checks += 1
        self.bot.last_check_result = result
        self.bot.last_check_time = datetime.now()

        if result.error:
            self.consecutive_errors += 1
            logger.warning("Controllo fallito (%s/%s): %s", self.consecutive_errors, 5, result.error)
            if self.consecutive_errors >= 5:
                logger.error("5 errori consecutivi. Eseguo backoff di 60 secondi.")
                await asyncio.sleep(60)
            return

        self.consecutive_errors = 0
        presale_info = f" [Prevendita: {result.presale_date}]" if result.presale_date else ""
        logger.info(
            "Check #%d: is_available=%s, status=%s, price=%s, time=%.2fs%s",
            self.bot.total_checks,
            result.is_available,
            result.status_raw,
            f"{result.price:.2f}€" if result.price else "N/D",
            result.response_time,
            presale_info
        )

        now = datetime.now()

        # CASO 1: Diventa disponibile! (Transizione da False -> True)
        if result.is_available and not self.was_available:
            logger.info("🚨 PRODOTTO DIVENTATO DISPONIBILE! Attivazione allarme a raffica!")
            self.was_available = True
            self.bot.is_muted = False
            self.recurring_cycle = 1
            self.last_recurring_alert = now
            self._save_state()

            # 3 notifiche a distanza di 2 secondi
            await self.bot.send_burst_alert(
                title=result.title,
                price=result.price,
                url=self.config.target_url
            )

        # CASO 2: È ancora disponibile (Promemoria ogni 3 minuti fino a /stop)
        elif result.is_available and self.was_available:
            if not self.bot.is_muted and self.last_recurring_alert:
                delta_min = (now - self.last_recurring_alert).total_seconds() / 60.0
                if delta_min >= self.config.repeat_interval_minutes:
                    self.recurring_cycle += 1
                    self.last_recurring_alert = now
                    logger.info("Invio promemoria disponibilità #%d", self.recurring_cycle)
                    await self.bot.send_recurring_alert(
                        title=result.title,
                        price=result.price,
                        url=self.config.target_url,
                        cycle=self.recurring_cycle
                    )

        # CASO 3: Torna esaurito (Transizione da True -> False)
        elif not result.is_available and self.was_available:
            logger.info("Prodotto tornato non disponibile (Sold Out).")
            self.was_available = False
            self.bot.is_muted = False
            self._save_state()
            await self.bot.send_sold_out_notice(title=result.title)

        # Gestione Heartbeat Orario (ogni 60 minuti)
        if self.config.heartbeat_interval_minutes > 0:
            heartbeat_delta = (now - self.last_heartbeat_time).total_seconds() / 60.0
            if heartbeat_delta >= self.config.heartbeat_interval_minutes:
                self.last_heartbeat_time = now
                await self.bot.send_heartbeat()

        self._save_state()

    async def stop(self):
        """Ferma il servizio, l'API HTTP e il bot Telegram."""
        self.is_running = False
        if self.api_runner:
            try:
                await self.api_runner.cleanup()
            except Exception as e:
                logger.debug(f"Errore cleanup API runner: {e}")
        await self.bot.stop()
        self._save_state()
        logger.info("Servizio arrestato correttamente.")

async def main():
    service = TopolinoMonitorService()
    loop = asyncio.get_running_loop()

    # Gestione segnali SIGINT e SIGTERM (anche dentro Docker)
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Ricevuto segnale di arresto...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Su piattaforme non-Unix / Windows
            pass

    monitor_task = asyncio.create_task(service.start())

    # Attendi eventuale segnale di stop
    await stop_event.wait()
    logger.info("Terminazione in corso...")
    monitor_task.cancel()
    await service.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Chiusura programma.")
