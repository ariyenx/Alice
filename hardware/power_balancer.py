# hardware/power_balancer.py
# Yazar: Mimar
# Kurallar: 8GB Birleşik Bellek %66.6 Altın Oran sınırı. "pass" veya simülasyon YOKTUR.

import os
import time
import subprocess
import logging
import threading
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "power_balancer.log",
    level=logging.WARNING,
    format="%(asctime)s - [GUC_DENGELEYICI] - %(message)s"
)

class PowerBalancer:
    def __init__(self):
        self.critical_limit = config.RAM_CRITICAL_PERCENT
        self.critical_temp = 66.6
        self.check_interval = 7
        self.is_throttled = False
        self._stop_event = threading.Event()
        self.thermal_path = "/sys/class/thermal/thermal_zone0/temp"

    def read_ram_percent(self):
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            total_mem = 0
            available_mem = 0
            for line in lines:
                if line.startswith('MemTotal:'):
                    total_mem = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    available_mem = int(line.split()[1])
            if total_mem > 0:
                return ((total_mem - available_mem) / total_mem) * 100.0
            return 0.0
        except Exception as e:
            logging.error(f"RAM okuma hatasi: {e}")
            return 0.0

    def read_temperature(self):
        try:
            if os.path.exists(self.thermal_path):
                with open(self.thermal_path, 'r') as f:
                    return int(f.read().strip()) / 1000.0
            return 0.0
        except Exception as e:
            logging.error(f"Isi okuma hatasi: {e}")
            return 0.0

    def enforce_balance(self, ram_usage, temperature):
        if ram_usage >= self.critical_limit:
            logging.warning(f"RAM %{ram_usage:.1f} asildi! Onbellek infazi devrede.")
            sys.stdout.write(f"\r[DENGELEYICI] RAM %{ram_usage:.1f} asildi! Sistem kurtariliyor...\033[K\n")
            sys.stdout.flush()
            try:
                subprocess.run("sync", shell=True, check=True)
                subprocess.run("echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null", shell=True, check=True)
            except subprocess.CalledProcessError as e:
                logging.error(f"Onbellek infaz hatasi: {e}")

        if temperature >= self.critical_temp and not self.is_throttled:
            logging.warning(f"Termal sinir asildi: {temperature:.1f}C. Jetson gucu kesiliyor.")
            sys.stdout.write(f"\r[DENGELEYICI] Isi {temperature:.1f}C! Zorla sogutuluyor...\033[K\n")
            sys.stdout.flush()
            try:
                subprocess.run(["sudo", "nvpmodel", "-m", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run("echo 255 | sudo tee /sys/devices/pwm-fan/target_pwm > /dev/null", shell=True)
                self.is_throttled = True
            except Exception as e:
                logging.error(f"Sogutma hatasi: {e}")
                
        elif temperature < (self.critical_temp - 10) and self.is_throttled:
            sys.stdout.write(f"\r[DENGELEYICI] Sistem Stabil. Maksimum performans geri dondu.\033[K\n")
            sys.stdout.flush()
            try:
                subprocess.run(["sudo", "nvpmodel", "-m", "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["sudo", "jetson_clocks"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.is_throttled = False
            except Exception as e:
                logging.error(f"Maksimum guc donusu hatasi: {e}")

    def _monitor_loop(self):
        logging.info("Guc Dengeleyici Aktif.")
        while not self._stop_event.is_set():
            self.enforce_balance(self.read_ram_percent(), self.read_temperature())
            self._stop_event.wait(self.check_interval)

    def start(self):
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join()
        if self.is_throttled:
            try:
                subprocess.run(["sudo", "nvpmodel", "-m", "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["sudo", "jetson_clocks"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logging.error(f"Kapanis guc donusu hatasi: {e}")

if __name__ == "__main__":
    balancer = PowerBalancer()
    balancer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        balancer.stop()
        sys.stdout.write("\n[*] Dengeleyici durduruldu.\n")