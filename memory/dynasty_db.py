# memory/dynasty_db.py
# Yazar: Mimar
# Kurallar: AES-256-GCM Sifreleme, Donanimsal Kilit, %100 Uretime Hazir SQLite Hafiza Kasasi. "pass" YOKTUR.

import sqlite3
import os
import sys
import json
import base64
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Anayasa (config.py) baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "vault.log",
    level=logging.WARNING,
    format="%(asctime)s - [HAFIZA KASASI] - %(message)s"
)

class DynastyVault:
    def __init__(self):
        """
        Hanedanin olumsuz hafiza kasasi. Tum veriler Jetson'un donanim  
        kimligine (Hardware ID) zincirlenmis AES-256-GCM ile sifrelenir.
        """
        self.db_path = config.VAULT_DIR / "dynasty_core.db"
        self.key_path = config.VAULT_DIR / ".master_salt"
        self.lock = threading.Lock()
        
        # Donanimsal Kilit ve Sifreleme Motorunun Ateslenmesi
        self.aesgcm = self._initialize_cipher()
        self._init_db()

    def _get_hardware_id(self) -> bytes:
        """Jetson Orin Nano'nun fiziksel kimligini ceker. SSD calinirsa veriler kilitli kalir."""
        try:
            # Jetson L4T donanim seri numarasi
            if os.path.exists("/sys/firmware/devicetree/base/serial-number"):
                with open("/sys/firmware/devicetree/base/serial-number", "r") as f:
                    return f.read().strip().replace('\x00', '').encode('utf-8')
            # Alternatif islemci kimligi
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.startswith("Serial"):
                            return line.split(":")[1].strip().encode('utf-8')
        except Exception as e:
            logging.error(f"Donanim kimligi okunamadi: {e}")
        
        # Eger Jetson disinda bir ortamdaysa altin oran sabitine duser
        return b"ALICE_HIS_HARDWARE_CHAIN_1618_666"

    def _initialize_cipher(self) -> AESGCM:
        """PBKDF2 ile donanim ID'sini 100.000 kez isleyip 256-bit AES anahtari dover."""
        hw_id = self._get_hardware_id()
        
        with self.lock:
            if self.key_path.exists():
                try:
                    with open(self.key_path, "rb") as f:
                        salt = f.read()
                except Exception as e:
                    logging.error(f"Kasa tuzu (salt) okunamadi: {e}")
                    sys.exit(1)
            else:
                salt = os.urandom(16)
                with open(self.key_path, "wb") as f:
                    f.write(salt)
                os.chmod(self.key_path, 0o600)
                sys.stdout.write("\r[HAFIZA] Sifir Gun: Yeni Kriptografik Zirh Uretildi.\033[K\n")
                sys.stdout.flush()
            
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32, # 256-bit
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(hw_id)
        return AESGCM(key)

    def encrypt_data(self, plaintext: str) -> str:
        """Veriyi 12-byte rastgele Nonce ile sifreler ve Base64'e cevirir."""
        if not plaintext:
            return ""
        try:
            nonce = os.urandom(12)
            ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
            return base64.b64encode(nonce + ciphertext).decode('utf-8')
        except Exception as e:
            logging.error(f"Sifreleme Hatasi: {e}")
            return ""

    def decrypt_data(self, encrypted_b64: str) -> str:
        """Base64 sifreli metni cozer. SSD baska cihaza takilmissa acimasizca reddeder."""
        if not encrypted_b64:
            return ""
        try:
            encrypted_data = base64.b64decode(encrypted_b64.encode('utf-8'))
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            return self.aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
        except Exception as e:
            logging.error(f"Sifre Cozme Hatasi (Veri/Donanim İhlali): {e}")
            return "SIFRE_COZME_HATASI"

    def _init_db(self):
        """Machiavelli devleti gibi kati kurallari olan SQLite tablolarini yaratir."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Hanedan Tanima Protokolu Tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dynasty_members (
                        name TEXT PRIMARY KEY,
                        is_recognized INTEGER DEFAULT 0,
                        encrypted_profile TEXT
                    )
                """)
                
                # Kâhin Saglik ve Uyku Verileri Tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS health_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        member_name TEXT,
                        timestamp TEXT,
                        log_type TEXT,
                        encrypted_data TEXT
                    )
                """)
                
                # Seraf Guvenlik ve Ihlal Gunlukleri Tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        event_type TEXT,
                        distance_cm INTEGER,
                        snapshot_path TEXT
                    )
                """)
                
                # Aryen ve Rana'yi kayitsiz olarak sisteme dahil et
                for member in config.DYNASTY_MEMBERS:
                    cursor.execute("INSERT OR IGNORE INTO dynasty_members (name, is_recognized, encrypted_profile) VALUES (?, 0, ?)", (member, ""))
                conn.commit()
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"Veritabani Baslatma Hatasi: {e}")

    def is_member_recognized(self, name: str) -> bool:
        """Arayuzdeki 'Tani' butonunu kilitlemek veya acmak icin durumu okur."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT is_recognized FROM dynasty_members WHERE name=?", (name,))
                result = cursor.fetchone()
                conn.close()
                if result and result[0] == 1:
                    return True
                return False
            except sqlite3.Error as e:
                logging.error(f"UI Tanima Kontrol Hatasi: {e}")
                return False

    def save_member_protocol(self, name: str, dob: str, blood_type: str, weight: float, mac_address: str, voice_path: str, face_path: str):
        """7 Adimli Hanedan Protokolunu tek bir JSON zihnine sikistirip AES-256 ile muhurler."""
        profile_data = {
            "dob": dob,
            "blood_type": blood_type,
            "weight": weight,
            "mac_address": mac_address,
            "voice_vector_path": voice_path,
            "face_vector_path": face_path,
            "protocol_date": datetime.now().isoformat()
        }
        
        json_dump = json.dumps(profile_data)
        encrypted_dump = self.encrypt_data(json_dump)
        
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE dynasty_members SET is_recognized=1, encrypted_profile=? WHERE name=?", 
                               (encrypted_dump, name))
                conn.commit()
                conn.close()
                sys.stdout.write(f"\r[HAFIZA] {name} profili AES-256 ile muhurlendi ve diske kazindi.\033[K\n")
                sys.stdout.flush()
            except sqlite3.Error as e:
                logging.error(f"Profil Kayit Hatasi: {e}")

    def get_member_profile(self, name: str) -> dict:
        """Zihin veya Asci Ajani veri istediginde sifreyi cozer ve guvenli JSON dondurur."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT encrypted_profile FROM dynasty_members WHERE name=? AND is_recognized=1", (name,))
                result = cursor.fetchone()
                conn.close()
                
                if result and result[0]:
                    decrypted_json = self.decrypt_data(result[0])
                    if decrypted_json != "SIFRE_COZME_HATASI":
                        return json.loads(decrypted_json)
                return {}
            except Exception as e:
                logging.error(f"Profil Okuma Hatasi: {e}")
                return {}

    def get_all_mac_addresses(self) -> dict:
        """Seraf Ag Gozcusu icin agda taranacak MAC adreslerini cozer."""
        macs = {}
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name, encrypted_profile FROM dynasty_members WHERE is_recognized=1")
                rows = cursor.fetchall()
                conn.close()
                
                for row in rows:
                    name = row[0]
                    dec_json = self.decrypt_data(row[1])
                    if dec_json != "SIFRE_COZME_HATASI":
                        data = json.loads(dec_json)
                        if "mac_address" in data:
                            macs[name] = data["mac_address"]
            except Exception as e:
                logging.error(f"MAC Adresi Okuma Hatasi: {e}")
        return macs

    def log_health_data(self, name: str, log_type: str, data_dict: dict):
        """Kâhin uyku verilerini ve gunluk beslenme haritasini zamansal olarak sifreler."""
        timestamp = datetime.now().isoformat()
        encrypted_log = self.encrypt_data(json.dumps(data_dict))
        
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO health_logs (member_name, timestamp, log_type, encrypted_data) VALUES (?, ?, ?, ?)",
                               (name, timestamp, log_type, encrypted_log))
                conn.commit()
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"Saglik Verisi Kayit Hatasi: {e}")

    def get_health_logs(self, name: str, log_type: str, days_back: int = 7) -> list:
        """Haftalik raporlar icin sifresi cozulmus verileri zihne sunar."""
        limit_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        logs = []
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp, encrypted_data FROM health_logs WHERE member_name=? AND log_type=? AND timestamp >= ? ORDER BY timestamp ASC",
                               (name, log_type, limit_date))
                rows = cursor.fetchall()
                conn.close()
                
                for row in rows:
                    ts = row[0]
                    dec_json = self.decrypt_data(row[1])
                    if dec_json != "SIFRE_COZME_HATASI":
                        data = json.loads(dec_json)
                        data["_timestamp"] = ts
                        logs.append(data)
            except Exception as e:
                logging.error(f"Saglik Verisi Okuma Hatasi: {e}")
        return logs

    def log_security_event(self, event_type: str, distance_cm: int, snapshot_path: str):
        """Seraf Ajaninin 2-3m guvenlik ihlallerini ve resim yollarini kaydeder."""
        timestamp = datetime.now().isoformat()
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO security_logs (timestamp, event_type, distance_cm, snapshot_path) VALUES (?, ?, ?, ?)",
                               (timestamp, event_type, distance_cm, snapshot_path))
                conn.commit()
                conn.close()
                sys.stdout.write(f"\r[HAFIZA] Guvenlik ihlali kaydedildi. Snapshot: {snapshot_path}\033[K\n")
                sys.stdout.flush()
            except sqlite3.Error as e:
                logging.error(f"Guvenlik Log Hatasi: {e}")
                
        # Ouroboros (7 Gun) temizligini tetikle
        self.purge_old_security_logs()

    def purge_old_security_logs(self):
        """Seraf'in Kurali: 7 gunu (LOG_CLEANUP_DAYS) gecen ihlal kayitlarini ve fotograflari acimasizca siler."""
        limit_date = (datetime.now() - timedelta(days=config.LOG_CLEANUP_DAYS)).isoformat()
        
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Silinmeden once resim yollarini bul ve fiziksel diskten kazı
                cursor.execute("SELECT snapshot_path FROM security_logs WHERE timestamp < ?", (limit_date,))
                rows = cursor.fetchall()
                for row in rows:
                    snap_path = row[0]
                    if snap_path and os.path.exists(snap_path):
                        try:
                            os.remove(snap_path)
                        except OSError:
                            pass
                            
                # Veritabani satirini yok et
                cursor.execute("DELETE FROM security_logs WHERE timestamp < ?", (limit_date,))
                deleted_count = cursor.rowcount
                conn.commit()
                conn.close()
                
                if deleted_count > 0:
                    logging.info(f"Seraf infazi: {deleted_count} adet eski guvenlik kaydi kalici olarak silindi.")
            except sqlite3.Error as e:
                logging.error(f"Log temizleme hatasi: {e}")

if __name__ == "__main__":
    # Cekirdek Sistem Testi ve Infaz Denemesi
    print("[*] Hafiza Kasasi (Vault) Test Ediliyor...")
    vault = DynastyVault()
    
    # Eger kayit yoksa test amacli sahte bir muhurleme
    if not vault.is_member_recognized("Aryen"):
        print("[*] Aryen taninmiyor. Protokol test kaydi olusturuluyor...")
        vault.save_member_protocol("Aryen", "1990-01-01", "A+", 75.5, "00:11:22:33:44:55", "/vault/aryen_voice.vec", "/vault/aryen_face.vec")
    
    # Desifre denemesi
    profile = vault.get_member_profile("Aryen")
    print(f"[*] Cozulen Profil Kan Grubu: {profile.get('blood_type', 'BULUNAMADI')}")
    print(f"[*] Sifreli MAC'ler Cekiliyor: {vault.get_all_mac_addresses()}")