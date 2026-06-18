# network/cyber_tracker.py
# Yazar: Mimar
# Kurallar: arp-scan ve ip neigh hibrit tarama. Hanedan MAC Doğrulaması. "pass" YOKTUR.

import subprocess
import json
from pathlib import Path

class CyberTracker:
    def __init__(self, storage_dir):
        """Ağ üzerindeki MAC adreslerini tarayan Siber Gözcü"""
        self.db_path = Path(storage_dir) / "mac_database.json"
        
        # Gerçek cihazlarınızın MAC adreslerini buraya girin
        # (Telefonunuzdan rastgele/gizli MAC özelliğini kapatın)
        self.known_macs = {
            "Aryen": "00:11:22:33:44:55", 
            "Rana": "AA:BB:CC:DD:EE:FF"
        }
        self._load_database()

    def _load_database(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self.known_macs.update(json.load(f))
            except Exception:
                pass

    def save_mac(self, name: str, mac_address: str):
        if name in self.known_macs:
            self.known_macs[name] = mac_address.lower()
            try:
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(self.known_macs, f, indent=4)
            except Exception:
                pass

    def is_device_home(self, name: str) -> bool:
        """Kameraya gerek kalmadan cihazın ağda olup olmadığını teyit eder."""
        target_mac = self.known_macs.get(name, "").lower()
        if not target_mac:
            return False

        try:
            # IP komutu (Anında çalışır)
            res = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=2)
            if target_mac in res.stdout.lower():
                return True
            
            # ARP-Scan (Derin Tarama)
            res2 = subprocess.run(["arp-scan", "--localnet", "--quiet"], capture_output=True, text=True, timeout=5)
            if target_mac in res2.stdout.lower():
                return True
        except Exception:
            pass

        return False