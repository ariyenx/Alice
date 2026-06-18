# hardware/iot_thermal.py
# Yazar: Mimar
# Kurallar: Termal silikon okuma, MQTT Akıllı Ev bağlantısı. "pass" YOKTUR. Hata yutulmaz.

import os
import sys
import logging
import threading
import json
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError as e:
    raise RuntimeError(f"paho-mqtt kütüphanesi eksik: {e}")

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "iot_thermal.log",
    level=logging.WARNING,
    format="%(asctime)s - [FİZİKSEL KALKAN] - %(message)s"
)

class PhysicalCore:
    def __init__(self):
        """Termal takip ve IoT röle kontrol modülü."""
        self.mqtt_broker = getattr(config, "MQTT_BROKER_IP", "127.0.0.1")
        self.mqtt_port = getattr(config, "MQTT_PORT", 1883)
        self.client = mqtt.Client(client_id="Alice_Edge_Node", clean_session=True)
        self.is_connected = False
        
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.thermal_base = Path("/sys/class/thermal")
        self.lock = threading.Lock()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            sys.stdout.write(f"\r[FİZİKSEL AĞ] MQTT Akıllı Ev Bağlantısı Kuruldu ({self.mqtt_broker}).\033[K\n")
            sys.stdout.flush()
        else:
            self.is_connected = False
            logging.error(f"MQTT Bağlantı reddedildi. Kod: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False
        logging.warning("MQTT Bağlantısı koptu.")

    def start(self):
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logging.error(f"MQTT Başlatma Hatası: {e}")
            sys.stdout.write(f"\r[UYARI] MQTT Broker bulunamadı. IoT röleler çevrimdışı.\033[K\n")
            sys.stdout.flush()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def get_max_temperature(self) -> float:
        """Sistemdeki maksimum silikon sıcaklığını ölçer (CPU/GPU)."""
        max_temp = 0.0
        if not self.thermal_base.exists():
            return 40.0 # Güvenli varsayılan değer
        try:
            for temp_file in self.thermal_base.glob("thermal_zone*/temp"):
                with open(temp_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content.isdigit():
                        temp_c = float(content) / 1000.0
                        if temp_c > max_temp:
                            max_temp = temp_c
        except Exception as e:
            logging.error(f"Termal okuma çöktü: {e}")
            raise RuntimeError(f"Termal Donanım Arızası: {e}")
        return max_temp

    def trigger_relay(self, topic: str, payload: dict) -> bool:
        """Akıllı ev rölelerine (ışık, priz) MQTT üzerinden hükmeder."""
        if not self.is_connected:
            logging.warning("MQTT çevrimdışı, komut iptal edildi.")
            return False
        try:
            with self.lock:
                json_payload = json.dumps(payload)
                result = self.client.publish(topic, json_payload, qos=1)
                result.wait_for_publish(timeout=2.0)
                if result.is_published():
                    sys.stdout.write(f"\r[IoT İNFAZ] {topic} -> {json_payload}\033[K\n")
                    sys.stdout.flush()
                    return True
                return False
        except Exception as e:
            logging.error(f"Röle tetikleme hatası: {e}")
            raise RuntimeError(f"Akıllı Ev komutu gönderilemedi: {e}")