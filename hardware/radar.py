# hardware/radar.py
# Yazar: Mimar
# Kurallar: BLE Infazi (0x0104), Tek Kisi Modu, Kâhin (Yakin=Rana, Uzak=Aryen), Seraf Ihlali (2-3m). "pass" YOKTUR.

import serial
import time
import threading
import logging
import sys
from pathlib import Path

# Anayasa (config.py) bağlantısı
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "radar.log",
    level=logging.WARNING,
    format="%(asctime)s - [RADAR] - %(message)s"
)

class RadarEye:
    def __init__(self, security_callback=None, health_callback=None):
        """
        Sistemin karanlıkta gören 24GHz Radar Gözü.
        BLE yayını donanımsal olarak susturulur. 
        Uyku verileri Tekil/Çiftil senaryoya göre Hanedan üyelerine işlenir.
        """
        self.port = config.RADAR_PORT
        self.baudrate = config.RADAR_BAUDRATE
        self.ser = None
        self.is_active = False
        self._stop_event = threading.Event()
        self.lock = threading.Lock()

        # Dışarıdan gelecek tetikleyiciler (Zihin veya Seraf bağlayacak)
        self.security_callback = security_callback
        self.health_callback = health_callback

        # Radar Anlık Durum Belleği
        self.target_state = 0
        self.moving_distance = 0
        self.moving_energy = 0
        self.static_distance = 0
        self.static_energy = 0

        # Güvenlik Kilitleri (Seraf)
        self.security_mode_armed = False
        self.security_range_max = 300 # 3 Metre (cm)
        self.security_range_min = 200 # 2 Metre (cm) (2-3 Metre Kuralı)
        
        # Kâhin Uyku ve Mesafe Kilitleri
        self.bed_split_distance = 200 # 200 cm altı Rana (Yakın), üstü Aryen (Uzak)
        self.single_person_mode = None # "Aryen" veya "Rana" atanırsa çift kişi kuralı ezilir

    def _connect(self):
        """UART bağlantısını açar ve BLE yayınını acımasızca keser."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            sys.stdout.write(f"\r[RADAR] UART {self.port} baglandi. 24GHz Aktif.\033[K\n")
            sys.stdout.flush()
            
            self._silence_bluetooth()
            return True
        except serial.SerialException as e:
            logging.error(f"Radar UART baglantisi kurulamadi: {e}")
            return False

    def _silence_bluetooth(self):
        """HLK-LD2410B konfigürasyon moduna geçip BLE radyosunu sonsuza dek kör eder."""
        with self.lock:
            try:
                # 1. Config Modu Aktif
                self.ser.write(bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x04, 0x00, 0xFF, 0x00, 0x01, 0x00, 0x04, 0x03, 0x02, 0x01]))
                time.sleep(0.1)

                # 2. BLE İnfaz Komutu (0x0104 Param: 0x0000 -> OFF)
                self.ser.write(bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x04, 0x00, 0x04, 0x01, 0x00, 0x00, 0x04, 0x03, 0x02, 0x01]))
                time.sleep(0.1)

                # 3. Config Modu Çıkış
                self.ser.write(bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0xFE, 0x00, 0x04, 0x03, 0x02, 0x01]))
                time.sleep(0.1)

                self.ser.reset_input_buffer()
                sys.stdout.write("\r[SERAF] Siber Zafiyet Kapatildi: Radar BLE yayini donanimsal katledildi.\033[K\n")
                sys.stdout.flush()
            except Exception as e:
                logging.error(f"BLE Susturma basarisiz: {e}")

    def arm_security_mode(self, state: bool):
        """Hanedan komutuyla Seraf Güvenlik Kalkanını tetikler."""
        with self.lock:
            self.security_mode_armed = state
            mode_str = "AKTIF (2-3m Ihlal Takibi)" if state else "KAPALI"
            sys.stdout.write(f"\r[SERAF] Guvenlik Kalkani: {mode_str}\033[K\n")
            sys.stdout.flush()

    def set_single_person_mode(self, member_name: str):
        """Zihin komutuyla yatakta tek kişi olduğunu mühürler."""
        with self.lock:
            if member_name in config.DYNASTY_MEMBERS:
                self.single_person_mode = member_name
                sys.stdout.write(f"\r[KÂHIN] Tek Kisi Uyku Modu Aktif. Tum veriler {member_name} profiline yazilacak.\033[K\n")
            else:
                self.single_person_mode = None
                sys.stdout.write(f"\r[KÂHIN] Cift Kisi Uyku Modu (Yakin=Rana, Uzak=Aryen) Aktif.\033[K\n")
            sys.stdout.flush()

    def _parse_frame(self, frame_data: bytes):
        """13 Byte'lık Hex Paket Çözümleyici."""
        if len(frame_data) < 23:
            return

        with self.lock:
            self.target_state = frame_data[8]
            self.moving_distance = frame_data[9] + (frame_data[10] << 8)
            self.moving_energy = frame_data[11]
            self.static_distance = frame_data[12] + (frame_data[13] << 8)
            self.static_energy = frame_data[14]

        self._evaluate_threat_and_health()

    def _evaluate_threat_and_health(self):
        """Hanedan kurallarının radar verisine göre işlendiği infaz merkezi."""
        with self.lock:
            current_state = self.target_state
            m_dist = self.moving_distance
            s_dist = self.static_distance
            is_armed = self.security_mode_armed
            single_mode = self.single_person_mode

        # 1. Seraf Güvenlik Modu (Ev boşken 2-3m ihlal)
        if is_armed:
            if current_state != 0:
                target_dist = m_dist if current_state in [1, 3] else s_dist
                if self.security_range_min <= target_dist <= self.security_range_max:
                    if self.security_callback:
                        self.security_callback(target_dist) # İhlal Var
                else:
                    if self.security_callback:
                        self.security_callback(-1) # Hedef uzaklaştı / Menzil dışı
            else:
                if self.security_callback:
                    self.security_callback(-1) # Ortam boş

        # 2. Kâhin Uyku Analizi Modu (Alarm kapalıyken nefes okunuyorsa)
        if not is_armed and current_state in [2, 3]: 
            if self.health_callback:
                if single_mode is not None:
                    # Yatakta tek kişi var, mesafe ayrımı yapmadan veriyi emredilen kişiye yaz.
                    self.health_callback(single_mode, s_dist, self.static_energy)
                else:
                    # Yatakta iki kişi var: Yakın olan DAİMA Rana, Uzak olan DAİMA Aryen.
                    hanedan_uyesi = "Rana" if s_dist < self.bed_split_distance else "Aryen"
                    self.health_callback(hanedan_uyesi, s_dist, self.static_energy)

    def _radar_loop(self):
        """Hex paketlerini kaçırmadan okuyan asenkron döngü."""
        header = bytes([0xF4, 0xF3, 0xF2, 0xF1])
        tail = bytes([0xF8, 0xF7, 0xF6, 0xF5])
        buffer = bytearray()

        while not self._stop_event.is_set() and self.is_active:
            try:
                if self.ser.in_waiting > 0:
                    buffer.extend(self.ser.read(self.ser.in_waiting))
                    
                    while True:
                        start_idx = buffer.find(header)
                        if start_idx == -1:
                            buffer.clear()
                            break
                        
                        if start_idx > 0:
                            buffer = buffer[start_idx:]
                            
                        end_idx = buffer.find(tail)
                        if end_idx == -1:
                            break
                            
                        frame = buffer[:end_idx + len(tail)]
                        self._parse_frame(frame)
                        
                        buffer = buffer[end_idx + len(tail):]
                else:
                    time.sleep(0.01)
            except Exception as e:
                logging.error(f"Radar veri yolu tikandi: {e}")
                time.sleep(0.5)

    def start(self):
        if self._connect():
            self.is_active = True
            self._stop_event.clear()
            self.thread = threading.Thread(target=self._radar_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.is_active = False
        self._stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join()
        if self.ser and self.ser.is_open:
            self.ser.close()
            sys.stdout.write("\r[RADAR] Sensör uyku moduna alindi ve port bosaltildi.\033[K\n")
            sys.stdout.flush()

if __name__ == "__main__":
    def dummy_sec_cb(dist):
        if dist != -1:
            sys.stdout.write(f"\r[GÜVENLİK] IHLAL! Mesafe: {dist} cm\033[K")
        sys.stdout.flush()

    def dummy_health_cb(member, dist, energy):
        if energy > 0:
            sys.stdout.write(f"\r[KÂHİN] {member} solunum tespit edildi. (Mesafe: {dist}cm, Enerji: {energy}/100)\033[K")
            sys.stdout.flush()

    radar = RadarEye(security_callback=dummy_sec_cb, health_callback=dummy_health_cb)
    radar.start()
    radar.arm_security_mode(False) # Test için Kâhin modunda başlat
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        radar.stop()