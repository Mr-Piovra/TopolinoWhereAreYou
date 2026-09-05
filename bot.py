import asyncio
import html
import logging
from datetime import datetime
from typing import Callable, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from checker import CheckResult
from config import Config

logger = logging.getLogger("TopolinoBot")

class TelegramMonitorBot:
    def __init__(
        self,
        config: Config,
        on_manual_check: Optional[Callable[[], CheckResult]] = None,
        on_interval_change: Optional[Callable[[int], None]] = None,
    ):
        self.config = config
        self.on_manual_check = on_manual_check
        self.on_interval_change = on_interval_change
        
        self.application: Optional[Application] = None
        self.is_muted: bool = False
        self.total_checks: int = 0
        self.last_check_result: Optional[CheckResult] = None
        self.last_check_time: Optional[datetime] = None
        self.start_time: datetime = datetime.now()

    def _is_authorized(self, update: Update) -> bool:
        """Verifica che il messaggio provenga dalla chat autorizzata."""
        if not self.config.telegram_chat_id:
            return True
        chat_id = str(update.effective_chat.id)
        authorized_id = str(self.config.telegram_chat_id).strip()
        return chat_id == authorized_id

    async def initialize(self):
        """Inizializza l'applicazione Telegram Bot."""
        if not self.config.telegram_bot_token:
            logger.warning("Token Telegram non fornito. Il bot interattivo non verrà avviato.")
            return

        self.application = ApplicationBuilder().token(self.config.telegram_bot_token).build()

        # Registrazione gestori comandi
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("help", self._cmd_help))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("check", self._cmd_check))
        self.application.add_handler(CommandHandler("interval", self._cmd_interval))
        self.application.add_handler(CommandHandler("stop", self._cmd_stop))
        self.application.add_handler(CommandHandler("resume", self._cmd_resume))
        self.application.add_handler(CommandHandler("test", self._cmd_test))

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot Telegram avviato e in ascolto per comandi.")

    async def stop(self):
        """Arresto pulito del bot."""
        if self.application:
            logger.info("Arresto bot Telegram in corso...")
            if self.application.updater:
                await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    # --- Comandi Telegram ---

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            await update.message.reply_text(f"⛔️ Accesso non autorizzato. Tuo Chat ID: {update.effective_chat.id}")
            return

        text = (
            "👋 <b>Benvenuto nel monitor Topolino 3694!</b>\n\n"
            "Sto monitorando costantemente Panini.it per avvisarti all'istante non appena "
            "il modellino sarà acquistabile!\n\n"
            "<b>Comandi disponibili:</b>\n"
            "• /status - Stato attuale del monitor e del prodotto\n"
            "• /check - Esegui un controllo immediato in tempo reale\n"
            "• /interval &lt;sec&gt; - Modifica la frequenza di polling (es. <code>/interval 20</code>)\n"
            "• /stop - Silenzia i promemoria ricorrenti dopo l'allarme\n"
            "• /resume - Riattiva i promemoria ricorrenti\n"
            "• /test - Simula l'allarme di disponibilità\n"
            "• /help - Mostra questo messaggio"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._cmd_start(update, context)

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        uptime = datetime.now() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        last_check_str = self.last_check_time.strftime("%H:%M:%S (%d/%m)") if self.last_check_time else "Nessuno"
        
        status_disp = "❓ Sconosciuto"
        price_str = "N/D"
        presale_str = "N/D"
        if self.last_check_result:
            if self.last_check_result.is_available:
                status_disp = "🟢 <b>DISPONIBILE!</b>"
            else:
                status_disp = "🔴 Non disponibile"
            
            if self.last_check_result.price:
                price_str = f"{self.last_check_result.price:.2f} €"
            if self.last_check_result.presale_date:
                presale_str = self.last_check_result.presale_date

        text = (
            "📊 <b>Stato Monitor Topolino 3694:</b>\n\n"
            f"• <b>Disponibilità:</b> {status_disp}\n"
            f"• <b>Data prevendita sul sito:</b> {html.escape(presale_str)}\n"
            f"• <b>Prezzo rilevato:</b> {price_str}\n"
            f"• <b>Ultimo controllo:</b> {last_check_str}\n"
            f"• <b>Controlli totali eseguiti:</b> {self.total_checks}\n"
            f"• <b>Intervallo base:</b> {self.config.check_interval_seconds}s (±{self.config.jitter_seconds}s jitter)\n"
            f"• <b>Stato Allarme:</b> {'🔕 Silenziato (/stop)' if self.is_muted else '🔔 Attivo'}\n"
            f"• <b>Uptime:</b> {uptime_str}\n\n"
            f"🔗 <a href='{self.config.target_url}'>Link Pagina Panini</a>"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def _cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        msg = await update.message.reply_text("🔄 Controllo in tempo reale su Panini.it in corso...")
        
        if self.on_manual_check:
            res = self.on_manual_check()
            self.last_check_result = res
            self.last_check_time = datetime.now()
            self.total_checks += 1
            
            if res.is_available:
                status_text = "🟢 <b>DISPONIBILE ORA! CORRI AD ACQUISTARE!</b>"
            else:
                status_text = "🔴 <b>Non ancora disponibile.</b>"
                
            price_text = f"{res.price:.2f} €" if res.price else "N/D"
            presale_text = res.presale_date or "N/D"
            
            text = (
                f"{status_text}\n\n"
                f"• <b>Prodotto:</b> {html.escape(res.title)}\n"
                f"• <b>Prezzo:</b> {price_text}\n"
                f"• <b>Prevendita indicata:</b> {html.escape(presale_text)}\n"
                f"• <b>Tempo di risposta:</b> {res.response_time:.2f}s (HTTP {res.status_code})\n"
                f"• <b>Stato raw:</b> <code>{res.status_raw}</code>\n\n"
                f"🔗 <a href='{self.config.target_url}'>Vai alla pagina prodotto</a>"
            )
            keyboard = [[InlineKeyboardButton("🛒 Apri Pagina Panini", url=self.config.target_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        else:
            await msg.edit_text("⚠️ Funzione di controllo manuale non disponibile.")

    async def _cmd_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                f"⏱ Intervallo attuale: <b>{self.config.check_interval_seconds}s</b>.\n"
                "Per cambiarlo, usa: <code>/interval &lt;secondi&gt;</code> (es. <code>/interval 20</code>)",
                parse_mode=ParseMode.HTML
            )
            return

        try:
            new_val = int(args[0])
            if new_val < 5:
                await update.message.reply_text("⚠️ L'intervallo minimo consigliato è di 5 secondi per evitare ban.")
                return
            if new_val > 600:
                await update.message.reply_text("⚠️ Intervallo troppo lungo (massimo 600 secondi).")
                return

            self.config.check_interval_seconds = new_val
            if self.on_interval_change:
                self.on_interval_change(new_val)

            await update.message.reply_text(
                f"✅ Intervallo aggiornato a <b>{new_val} secondi</b> (±{self.config.jitter_seconds}s jitter).",
                parse_mode=ParseMode.HTML
            )
        except ValueError:
            await update.message.reply_text("❌ Valore non valido. Specifica un numero intero in secondi (es. <code>/interval 25</code>).", parse_mode=ParseMode.HTML)

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        self.is_muted = True
        await update.message.reply_text(
            "🔕 <b>Promemoria ricorrenti silenziati!</b>\n"
            "Non riceverai più notifiche ogni 3 minuti per questa disponibilità.\n"
            "Il monitoraggio continua in background. Per riattivare le notifiche scrivi /resume.",
            parse_mode=ParseMode.HTML
        )

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        self.is_muted = False
        await update.message.reply_text(
            "🔔 <b>Promemoria ricorrenti riattivati!</b>",
            parse_mode=ParseMode.HTML
        )

    async def _cmd_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        await update.message.reply_text("🧪 Invio simulazione delle 3 notifiche a raffica (distanza 2s)...")
        await self.send_burst_alert(
            title="Topolino 3694 Con Seconda Parte Modellino F1 (TEST)",
            price=10.35,
            url=self.config.target_url,
            is_simulation=True
        )

    # --- Funzioni di Notifica Outbound ---

    async def send_burst_alert(self, title: str, price: Optional[float], url: str, is_simulation: bool = False):
        """Invia 3 notifiche consecutive a distanza di 2 secondi con suono e massima priorità."""
        if not self.application or not self.config.telegram_chat_id:
            return

        chat_id = self.config.telegram_chat_id
        price_str = f"{price:.2f} €" if price else "10,35 €"
        keyboard = [[InlineKeyboardButton("🛒 ACQUISTA SUBITO SU PANINI", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        sim_tag = " [TEST SIMULAZIONE]" if is_simulation else ""

        messages = [
            (
                f"🚨🚨🚨 <b>TOPOLINO 3694 È DISPONIBILE!</b>{sim_tag} 🚨🚨🚨\n\n"
                f"📖 <b>Prodotto:</b> {html.escape(title)}\n"
                f"💰 <b>Prezzo:</b> {price_str}\n"
                f"⏰ <b>Rilevato alle:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"👉 Clicca sul pulsante in basso per aprire subito la pagina di acquisto!"
            ),
            (
                f"⚡️⚡️ <b>SECONDO AVVISO - DISPONIBILE ORA!</b>{sim_tag} ⚡️⚡️\n\n"
                f"Il pezzo risulta acquistabile su Panini.it. Non perdere tempo prima che esaurisca!\n\n"
                f"🔗 {url}"
            ),
            (
                f"🔥🔥 <b>TERZO AVVISO - CORRI!</b>{sim_tag} 🔥🔥\n\n"
                f"Riceverai un promemoria ogni {self.config.repeat_interval_minutes} minuti.\n"
                f"👉 Per fermare i promemoria una volta acquistato, scrivi <code>/stop</code> in questa chat."
            ),
        ]

        for idx, text in enumerate(messages):
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup if idx == 0 else None,
                    disable_notification=False,  # Notifica con suono squillante
                    disable_web_page_preview=False
                )
            except Exception as e:
                logger.error("Errore invio notifica burst %s: %s", idx + 1, e)

            if idx < len(messages) - 1:
                await asyncio.sleep(self.config.burst_delay_seconds)

    async def send_recurring_alert(self, title: str, price: Optional[float], url: str, cycle: int):
        """Invia notifica ogni 3 minuti finché non riceve /stop o non torna non disponibile."""
        if not self.application or not self.config.telegram_chat_id or self.is_muted:
            return

        chat_id = self.config.telegram_chat_id
        price_str = f"{price:.2f} €" if price else "10,35 €"
        keyboard = [[InlineKeyboardButton("🛒 ACQUISTA SUBITO", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            f"⏰ <b>PROMEMORIA DISPONIBILITÀ (#{cycle})</b>\n\n"
            f"<b>Topolino 3694 è ancora disponibile su Panini.it!</b>\n"
            f"Prezzo: {price_str}\n\n"
            f"Hai già completato l'acquisto? Scrivi <code>/stop</code> per silenziare questi avvisi."
        )

        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_notification=False
            )
        except Exception as e:
            logger.error("Errore invio notifica ricorrente: %s", e)

    async def send_heartbeat(self):
        """Invia un messaggio orario per confermare che il bot è attivo."""
        if not self.application or not self.config.telegram_chat_id:
            return

        chat_id = self.config.telegram_chat_id
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() // 3600)
        
        status_disp = "🔴 Non ancora disponibile"
        if self.last_check_result and self.last_check_result.is_available:
            status_disp = "🟢 DISPONIBILE!"

        text = (
            f"💓 <b>Heartbeat Orario - Monitor Attivo</b>\n\n"
            f"• <b>Stato prodotto:</b> {status_disp}\n"
            f"• <b>Controlli effettuati finora:</b> {self.total_checks}\n"
            f"• <b>In esecuzione da:</b> {hours} ore\n"
            f"• <b>Frequenza:</b> ogni {self.config.check_interval_seconds}s (±{self.config.jitter_seconds}s)\n\n"
            f"Tutto procede regolarmente. Ti avviserò all'istante non appena apre la vendita!"
        )

        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_notification=True  # Silenzioso per non disturbare ogni ora
            )
            logger.info("Heartbeat orario inviato con successo.")
        except Exception as e:
            logger.error("Errore invio heartbeat: %s", e)

    async def send_sold_out_notice(self, title: str):
        """Avvisa se il prodotto, dopo essere stato disponibile, torna esaurito."""
        if not self.application or not self.config.telegram_chat_id:
            return

        chat_id = self.config.telegram_chat_id
        text = (
            f"ℹ️ <b>Aggiornamento: Prodotto Esaurito</b>\n\n"
            f"<b>{html.escape(title)}</b> non risulta più acquistabile (Out of stock).\n"
            f"Il monitoraggio continua attivo per eventuali restock improvvisi."
        )
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error("Errore invio avviso sold out: %s", e)
