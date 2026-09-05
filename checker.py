import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup
from curl_cffi import requests

logger = logging.getLogger("PaniniChecker")

@dataclass
class CheckResult:
    is_available: bool
    title: str = "Topolino"
    price: Optional[float] = None
    currency: str = "EUR"
    status_raw: str = "Unknown"
    presale_date: Optional[str] = None
    signals: Dict[str, Any] = field(default_factory=dict)
    response_time: float = 0.0
    status_code: int = 0
    error: Optional[str] = None

class PaniniAvailabilityChecker:
    def __init__(self, target_url: str, proxy_url: Optional[str] = None, timeout: int = 20):
        self.target_url = target_url
        self.proxy_url = proxy_url
        self.timeout = timeout
        self.session: Optional[requests.Session] = None
        self._init_session()

    def _init_session(self):
        """Inizializza una sessione curl_cffi con fingerprint Chrome 124 TLS/HTTP2."""
        proxies = None
        if self.proxy_url:
            proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        self.session = requests.Session(
            impersonate="chrome124",
            proxies=proxies,
            headers=headers
        )

    def check(self, url: Optional[str] = None) -> CheckResult:
        """
        Effettua la verifica di disponibilità analizzando i 4 segnali chiave
        della pagina Magento di Panini.
        """
        target = url or self.target_url
        t0 = time.time()
        
        try:
            if not self.session:
                self._init_session()
                
            response = self.session.get(target, timeout=self.timeout, allow_redirects=True)
            elapsed = time.time() - t0
            status_code = response.status_code

            # Verifica eventuale pagina di coda Queue-it
            if "queue-it.net" in response.url:
                logger.warning("Rilevato redirect a Queue-it: %s", response.url)
                return CheckResult(
                    is_available=False,
                    status_raw="Queue-it Redirect",
                    response_time=elapsed,
                    status_code=status_code,
                    error="Redirect attivo a Queue-it (coda virtuale attiva su Panini)"
                )

            if status_code != 200:
                logger.warning("Risposta HTTP inattesa da Panini: %s", status_code)
                return CheckResult(
                    is_available=False,
                    status_raw=f"HTTP_{status_code}",
                    response_time=elapsed,
                    status_code=status_code,
                    error=f"HTTP status code {status_code}"
                )

            html = response.text
            return self._parse_html(html, elapsed, status_code)

        except Exception as e:
            elapsed = time.time() - t0
            logger.error("Errore durante il controllo Panini: %s", e)
            # Ricrea la sessione in caso di errore di connessione/socket rotto
            try:
                self._init_session()
            except Exception:
                pass
            return CheckResult(
                is_available=False,
                status_raw="Error",
                response_time=elapsed,
                status_code=0,
                error=str(e)
            )

    def _parse_html(self, html: str, elapsed: float, status_code: int) -> CheckResult:
        """Estrae e confronta i molteplici indicatori di disponibilità."""
        signals = {}
        title = "Topolino"
        price = None
        status_raw = "Unknown"
        presale_date = None

        # 1. Script 'const product = {...}'
        m_prod = re.search(r'const\s+product\s*=\s*(\{.+?\});', html, re.DOTALL)
        prod_obj = {}
        if m_prod:
            try:
                prod_obj = json.loads(m_prod.group(1))
                signals["product_js_status"] = prod_obj.get("status")
                signals["product_js_stock"] = prod_obj.get("stock")
                title = prod_obj.get("name") or title
                price = prod_obj.get("salePrice") or prod_obj.get("price")
                status_raw = prod_obj.get("status", status_raw)
            except Exception as e:
                logger.debug("Errore parsing const product: %s", e)

        # 2. Script dataLayerProductDetail: { ... "product_availability": "available"|"not_purchasable" }
        m_dl = re.search(r'\"dataLayerProductDetail\":\s*(\{.+?\})\s*\}', html, re.DOTALL)
        if m_dl:
            try:
                dl_obj = json.loads(m_dl.group(1))
                signals["dataLayer_availability"] = dl_obj.get("product_availability")
                if not price and "price" in dl_obj:
                    price = dl_obj.get("price")
            except Exception as e:
                logger.debug("Errore parsing dataLayer: %s", e)

        # 3. Schema.org JSON-LD
        m_schema = re.search(r'(\{\"@context\":\"https://schema\.org/\",\"@type\":\"Product\".+?\})</script>', html, re.DOTALL)
        if m_schema:
            try:
                schema_obj = json.loads(m_schema.group(1))
                offers = schema_obj.get("offers", {})
                signals["schema_availability"] = offers.get("availability")
                if not price and "price" in offers:
                    price = float(offers.get("price"))
                if title == "Topolino" and "name" in schema_obj:
                    title = schema_obj.get("name")
            except Exception as e:
                logger.debug("Errore parsing schema.org: %s", e)

        # 4. DOM Parsing (BeautifulSoup o regex veloce)
        button_present = 'id="product-addtocart-button"' in html
        unavail_div = 'class="stock unavailable"' in html
        signals["button_addtocart_present"] = button_present
        signals["stock_unavailable_div_present"] = unavail_div

        # Estrai data prevendita (es. "Disponibile dal: 06/09/26")
        m_presale = re.search(r'class="product-presale-alert"[^>]*>.*?<span>Disponibile dal:</span>\s*<strong>([^<]+)</strong>', html, re.DOTALL)
        if m_presale:
            presale_date = m_presale.group(1).strip()
            signals["presale_date"] = presale_date

        # Valutazione finale disponibilità
        is_in_stock_js = signals.get("product_js_status") == "In stock"
        is_dl_available = signals.get("dataLayer_availability") == "available"
        is_schema_instock = "InStock" in str(signals.get("schema_availability", ""))
        is_dom_available = button_present and not unavail_div

        # Se almeno uno dei segnali ufficiali indica "In stock" o "available"
        is_available = is_in_stock_js or is_dl_available or is_schema_instock or is_dom_available

        return CheckResult(
            is_available=is_available,
            title=title,
            price=price,
            status_raw=status_raw,
            presale_date=presale_date,
            signals=signals,
            response_time=elapsed,
            status_code=status_code,
            error=None
        )
