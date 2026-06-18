# config.py
# Yazar: Mimar
import os
from pathlib import Path

# ==============================================================================
# HİS - MATEMATİKSEL VE ALTIN ORAN SABİTLERİ
# ==============================================================================
GOLDEN_RATIO = 1.618
TOKEN_BASE_LIMIT = 1618          # Kusursuz zihin istikrarı sınırı
TOKEN_EXTENSION = 666            # Hanedan onayıyla sohbet uzatma hakkı
TOKEN_MAX_LIMIT = 2284           # Halüsinasyon duvarı (1618 + 666)

WAKE_LISTEN_SEC = 33             # "Alis" duyulduktan sonra aktif dinleme döngüsü (sn)
FILE_DESTROY_MIN = 33            # Wi-Fi/QR ile indirilen dosyanın imha süresi (dk)

CAMERA_HUNT_MINUTES = 7          # Uyku durumunda düşük FPS tarama süresi (dk)
BIOMETRIC_RETENTION_DAYS = 7     # Yabancı biyometrik veriyi saklama süresi (gün)
LOG_CLEANUP_DAYS = 7             # Seraf'ın geriye dönük log yok etme döngüsü (gün)
DYNASTY_QUESTIONS_COUNT = 7      # Hanedan tanıma protokolündeki soru sayısı

RAM_CRITICAL_PERCENT = 66.6      # Sistem RAM ve Isı uyarı eşiği

# ==============================================================================
# İNSAN TESPİTİ VE FREKANS KANUNLARI
# ==============================================================================
HUMAN_FREQ_MIN_HZ = 85.0         # İnsan sesi minimum frekans eşiği
HUMAN_FREQ_MAX_HZ = 255.0        # İnsan sesi maksimum frekans eşiği
WAKE_WORD = "alis"

# ==============================================================================
# DONANIM VE KAMERA (Jetson Orin Nano)
# ==============================================================================
CAMERA_IDLE_FPS = 5              # Enerji tasarrufu için pasif tarama hızı
CAMERA_ACTIVE_FPS = 15           # Canlı/nesne analizi için altın oran hızı
CAMERA_FOV_DEGREES = 90          # IMX219 Görüş Açısı

RADAR_PORT = "/dev/ttyTHS0"      # HLK-LD2410B UART Pini (Jetson 40-pin)
RADAR_BAUDRATE = 256000

# ==============================================================================
# HANEDAN KİMLİĞİ VE AĞ
# ==============================================================================
DYNASTY_MEMBERS = ["Aryen", "Rana"]
DYNASTY_MACS = {
    "Aryen": "XX:XX:XX:XX:XX:XX", 
    "Rana":  "YY:YY:YY:YY:YY:YY"
}
WIFI_API_PORT = 8000

# ==============================================================================
# DİZİN YOLLARI VE SSD ŞİFRELEME (VAULT) YAPISI
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"

VAULT_DIR = STORAGE_DIR / "vault"           # AES-256 Şifreli Veritabanı ve Biyometri
RAG_DIR = STORAGE_DIR / "offline_rag"       # Sıfır atık mmap (Wiki, PDF) RAG Deposu
MEDIA_DIR = STORAGE_DIR / "media"           # Akıllı Müzik ve Frekans Analizi
LOG_DIR = BASE_DIR / "logs"                 # 7 Günlük Sistem Logları
TEMP_DIR = STORAGE_DIR / "temp_wifi"        # 33 dakikada silinecek ağ aktarımları

# Zihin uyanmadan önce tüm dizinlerin fiziksel varlığını donanımda acımasızca sağla
for directory in [VAULT_DIR, RAG_DIR, MEDIA_DIR, LOG_DIR, TEMP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)