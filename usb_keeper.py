# hardware/usb_keeper.py
# Yazar: Mimar
import os
import time
import subprocess
import logging
import threading
import sys
from pathlib import Path

# Üst dizinden config.py'yi çekmek için mutlak yol bağlaması
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Seraf'ın 7 günde bir temizleyeceği bağımsız log kaydı
logging.basicConfig(
    filename=config.LOG_DIR / "usb_keeper.log",
    level=logging.WARNING,
    format="%(asctime)s - [USB_BEKCISI] - %(levelname)s - %(message)s"
)

class USBKeeper:
    def __init__(self):
        """
        Seraf'ın donanım pençesi. Ses ve ekran arayüzlerinin güç tasarrufu 
        sebebiyle USB veriyolundan düşmesini acımasızca engeller.
        """
        self.check_interval = config.WAKE_LISTEN_SEC
        self._stop_event = threading.Event()
        self.sys_usb_path = "/sys/bus/usb/devices/"
        
        # LSUSB çıktısında aranacak hayati donanım imzaları
        self.critical_keywords = ["audio", "c-media", "waveshare", "atr", "odseven"]

    def lock_power_state(self):
        """Çekirdek düzeyinde USB hub'larına zorunlu uyanıklık yazar."""
        if not os.path.exists(self.sys_usb_path):
            return

        for device in os.listdir(self.sys_usb_path):
            power_path = os.path.join(self.sys_usb_path, device, "power", "control")
            autosuspend_path = os.path.join(self.sys_usb_path, device, "power", "autosuspend")

            if os.path.exists(power_path):
                try:
                    with open(power_path, 'w') as f:
                        f.write("on\n")
                except PermissionError:
                    pass

            if os.path.exists(autosuspend_path):
                try:
                    with open(autosuspend_path, 'w') as f:
                        f.write("-1\n")
                except PermissionError:
                    pass

    def shock_kernel(self):
        """Kritik aygıtlar koparsa sürücüleri udevadm ile yeniden tetikler."""
        logging.warning("Kritik donanım düşmesi algılandı. Çekirdek şoklanıyor (udevadm trigger).")
        try:
            subprocess.run(['sudo', 'udevadm', 'trigger', '--subsystem-match=usb'], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logging.error(f"Çekirdek şoku başarısız: {e}")

    def check_peripherals(self):
        """lsusb üzerinden donanımların fiziksel varlığını onaylar."""
        try:
            result = subprocess.run(['lsusb'], capture_output=True, text=True, check=True)
            output = result.stdout.lower()
            
            is_missing = True
            for keyword in self.critical_keywords:
                if keyword in output:
                    is_missing = False
                    break
            
            if is_missing:
                self.shock_kernel()
                
        except subprocess.CalledProcessError:
            logging.error("'lsusb' komutu işletilemedi.")

    def _monitor_loop(self):
        logging.info(f"USB Bekçisi Aktif. {self.check_interval} saniyelik altın döngü devrede.")
        
        while not self._stop_event.is_set():
            self.lock_power_state()
            self.check_peripherals()
            self._stop_event.wait(self.check_interval)

    def start(self):
        """Ajanı arka planda (daemon) otonom başlatır."""
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Sistem kapanırken ajanı güvenle durdurur."""
        self._stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join()

if __name__ == "__main__":
    keeper = USBKeeper()
    keeper.start()
    print(f"[*] USB Bekçisi {config.WAKE_LISTEN_SEC} saniye döngüsüyle devrede. Kapatmak için CTRL+C yapın.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        keeper.stop()
        print("\n[*] USB Bekçisi uykuya daldı.")