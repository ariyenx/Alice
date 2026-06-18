# network/kali_scanner.py
# Yazar: Mimar
# Kurallar: ip neigh / arp-scan ile ag MAC tarar. Zihne raporlar. Alarmi OTOMATIK TETIKLEMEZ. "pass" YOKTUR.

import os
import sys
import subprocess
import threading
import time
import re
import logging
from pathlib import Path

# Anayasa (config.py) baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Hafiza Kasasi (Vault) verilerini okuyabilmek icin
sys.path.append(str(Path(__file__).resolve().parent.parent / "memory"))
try:
    from dynasty_db import DynastyVault
except ImportError:
    DynastyVault = None

logging.basicConfig(
    filename=config.LOG_DIR / "kali_scanner.log",
    level=logging.WARNING,
    format="%(asctime)s - [AĞ GÖZCÜSÜ] - %(message)s"
)

class CyberWatcher:
    def __init__(self, vault: DynastyVault = None):
        """
        Ag Gözcüsü (Istihbarat Ajani). Yabanci MAC tespiti yapar.
        Evden ayrilma durumunda guvenligi OTONOM TETIKLEMEZ (Manuel emir gerektirir).
        Sadece Hanedan uyelerinin evde olup olmadigini Zihne fisildar.
        """
        self.vault = vault
        self.is_active = False
        self._stop_event = threading.Event()
        self.scan_interval = 33 # Altin oran
        
        self.active_hanedan_members = set()
        self.unknown_macs = set()
        self.lock = threading.Lock()
        
        self.mac_regex = re.compile(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})")

    def _execute_arp_scan(self) -> set:
        """Linux ARP tablosunu ve arp-scan aracini hibrit kullanarak tespiti garantiler."""
        detected_macs = set()
        try:
            # 1. Aşama: arp-scan
            result = subprocess.run(['sudo', 'arp-scan', '--localnet', '--numeric', '--quiet', '--ignoredups'], 
                                    capture_output=True, text=True, timeout=15)
            for line in result.stdout.split('\n'):
                match = self.mac_regex.search(line)
                if match:
                    detected_macs.add(match.group(0).lower().replace('-', ':'))
        except Exception as e:
            logging.warning(f"arp-scan calistirilamadi: {e}. İkinci aşamaya (ip neigh) geciliyor.")
            
        try:
            # 2. Aşama: ip neigh (Yedek Kali Taktigi)
            result = subprocess.run(['ip', 'neigh', 'show'], capture_output=True, text=True, check=True)
            for line in result.stdout.split('\n'):
                parts = line.split()
                if 'lladdr' in parts:
                    mac_index = parts.index('lladdr') + 1
                    if mac_index < len(parts):
                        mac_addr = parts[mac_index].lower().replace('-', ':')
                        if mac_addr != "00:00:00:00:00:00":
                            detected_macs.add(mac_addr)
        except Exception as e:
            logging.error(f"ip neigh hatasi: {e}")
            
        return detected_macs

    def _patrol_network(self):
        """Sessiz Istihbarat Devriyesi."""
        sys.stdout.write("\r[SİBER GÖZCÜ] Sessiz ağ devriyesi başlatıldı. Sızmalar izleniyor...\033[K\n")
        sys.stdout.flush()
        
        while not self._stop_event.is_set() and self.is_active:
            live_macs = self._execute_arp_scan()
            
            known_macs_dict = {}
            if self.vault:
                known_macs_dict = self.vault.get_all_mac_addresses()
            
            currently_home = set()
            known_mac_values = set()
            
            # MAC Eslestirmeleri
            for name, saved_mac in known_macs_dict.items():
                clean_saved_mac = saved_mac.lower().replace('-', ':')
                known_mac_values.add(clean_saved_mac)
                if clean_saved_mac in live_macs:
                    currently_home.add(name)
            
            # Yabanci Cihaz Filtreleme
            current_unknowns = set()
            for live_mac in live_macs:
                if live_mac not in known_mac_values:
                    current_unknowns.add(live_mac)
            
            # Durum Guncelleme
            with self.lock:
                if self.active_hanedan_members != currently_home:
                    self.active_hanedan_members = currently_home.copy()
                    home_str = ", ".join(self.active_hanedan_members) if self.active_hanedan_members else "Sistemde kayitli kimse yok"
                    sys.stdout.write(f"\r[SİBER GÖZCÜ] Evdeki Hanedan Üyeleri: {home_str}\033[K\n")
                    sys.stdout.flush()
                self.unknown_macs = current_unknowns.copy()
            
            # Yabanci ag sizmalarini Hafiza Kasasina logla
            if len(current_unknowns) > 0 and self.vault:
                for umac in current_unknowns:
                    self.vault.log_security_event("YABANCI_MAC_TESPITI", 0, f"Wi-Fi İhlali: {umac}")
                    
            self._stop_event.wait(self.scan_interval)

    def is_member_home(self, name: str) -> bool:
        """Zihin tarafindan sorgulanan gercek zamanli 3. Seviye dogrulama."""
        with self.lock:
            return name in self.active_hanedan_members

    def start(self):
        if self.is_active:
            return
        self.is_active = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._patrol_network, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_active = False
        self._stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join()
        sys.stdout.write("\r[SİBER GÖZCÜ] Devriye durduruldu.\033[K\n")
        sys.stdout.flush()

if __name__ == "__main__":
    vault_instance = DynastyVault() if DynastyVault else None
    watcher = CyberWatcher(vault=vault_instance)
    watcher.start()
    try:
        time.sleep(2)
        print(f"[*] Evdeki Hanedan Uyeleri: {watcher.active_hanedan_members}")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()