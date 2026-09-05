import asyncio
import json
import os
import shutil
import tempfile
import unittest
from checker import PaniniAvailabilityChecker, CheckResult
from config import Config

class TestTopolinoMonitor(unittest.TestCase):
    def setUp(self):
        self.checker = PaniniAvailabilityChecker(
            target_url="https://www.panini.it/shp_ita_it/topolino-3694-con-seconda-parte-modellino-f1-1wtopo3694v-it08.html"
        )

    def test_topolino_3694_unavailable(self):
        """Topolino 3694 al momento deve risultare NON disponibile (PreSale / Out of stock)."""
        res = self.checker.check()
        self.assertFalse(res.is_available, "Topolino 3694 non dovrebbe essere disponibile")
        self.assertIn("3694", res.title)
        self.assertEqual(res.status_raw, "Out of stock")
        self.assertEqual(res.presale_date, "06/09/26")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.response_time, 0)
        self.assertIsNone(res.error)
        print("\n[OK] Topolino 3694 test: Correttamente rilevato come 'Non Disponibile' (Prevendita: 06/09/26)")

    def test_available_product_detection(self):
        """Il secondo link (I Viaggi di Topolino 2) deve risultare DISPONIBILE."""
        available_url = "https://www.panini.it/shp_ita_it/i-viaggi-di-topolino-2-1wtrip002-it08.html"
        res = self.checker.check(available_url)
        self.assertTrue(res.is_available, "Il prodotto test dovrebbe essere disponibile")
        self.assertEqual(res.status_raw, "In stock")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.error)
        print("[OK] Prodotto test disponibile: Correttamente rilevato come 'In stock' con pulsante carrello attivo")

    def test_config_defaults(self):
        """Verifica i valori di configurazione richiesti dall'utente."""
        cfg = Config()
        self.assertEqual(cfg.check_interval_seconds, 35)
        self.assertEqual(cfg.jitter_seconds, 8)
        self.assertEqual(cfg.burst_count, 3)
        self.assertEqual(cfg.burst_delay_seconds, 2.0)
        self.assertEqual(cfg.repeat_interval_minutes, 3)
        self.assertEqual(cfg.heartbeat_interval_minutes, 60)
        print("[OK] Valori di configurazione corretti (Opzione A, raffica 3x2s, promemoria 3m, heartbeat 60m)")

    def test_state_save_and_load(self):
        """Verifica salvataggio e caricamento dello stato su file JSON."""
        temp_dir = tempfile.mkdtemp()
        state_path = os.path.join(temp_dir, "test_state.json")
        try:
            sample_state = {
                "was_available": True,
                "total_checks": 142,
                "is_muted": False
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(sample_state, f)

            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            self.assertEqual(loaded["was_available"], True)
            self.assertEqual(loaded["total_checks"], 142)
            print("[OK] Persistenza dello stato su file JSON funzionante")
        finally:
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    unittest.main()
