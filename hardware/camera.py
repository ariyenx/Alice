# hardware/camera.py
# Yazar: Mimar
# Kurallar: YOLOv8-Nano (CUDA Tensor FP16), Tek Degiskenli RAM Kalkani, Hata Yutma Yok, "pass" YOKTUR.

import cv2
import time
import threading
import logging
import sys
from collections import Counter
from pathlib import Path
import numpy as np

try:
    import torch
    from ultralytics import YOLO
except ImportError as e:
    torch = None
    YOLO = None
    sys.stdout.write(f"\r[KIRMIZI ALARM] Ultralytics (YOLO) veya PyTorch eksik. İnfaz durduruldu: {e}\033[K\n")
    sys.stdout.flush()
    raise RuntimeError(f"YOLO kütüphaneleri eksik: {e}")

# Anayasa (config.py) baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "camera.log",
    level=logging.WARNING,
    format="%(asctime)s - [ŞAHİN GÖZÜ] - %(message)s"
)

class CameraEye:
    def __init__(self, security_callback=None):
        """
        Sistemin Otonom Optik Korteksi. 
        YOLOv8-Nano ile nesne ve insanlari saliseler icinde analiz eder. 
        RAM sismesini engellemek icin tespit listesini surekli ayni degiskene (overwrite) ezer.
        """
        self.camera_index = config.CAMERA_PORT if hasattr(config, 'CAMERA_PORT') else 0
        self.cap = None
        self.is_active = False
        self._stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # Seraf Ajanı (Güvenlik İnfazı) Tetikleyicisi
        self.security_callback = security_callback
        self.security_armed = False

        # RAM Kalkanı: Liste asla uzamaz, sadece bu tek degiskenin uzerine ezilir.
        self.live_targets = "Kamera henüz taranmadı"
        self.latest_frame = np.array([])
        self.person_detected = False

        self.models_dir = config.STORAGE_DIR / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.yolo_model_path = self.models_dir / "yolov8n.pt"

        # Ingilizce COCO etiketlerini Zihin icin Turkceye donduren sözlük
        self.tr_map = {
            "person": "insan", "cat": "kedi", "dog": "köpek", "cell phone": "telefon",
            "laptop": "bilgisayar", "bottle": "şişe", "chair": "sandalye", "car": "araba",
            "tv": "televizyon", "backpack": "sırt çantası", "book": "kitap", "knife": "bıçak"
        }

        self.yolo_model = None
        self.device = "cpu"
        self._load_yolo()

    def _load_yolo(self):
        """YOLOv8-Nano motorunu Jetson'un Tensor Cekirdeklerine FP16 ile mühürler."""
        sys.stdout.write("\r[ŞAHİN GÖZÜ] YOLOv8-Nano Motoru Yükleniyor...\033[K\n")
        sys.stdout.flush()

        try:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.yolo_model = YOLO(str(self.yolo_model_path) if self.yolo_model_path.exists() else "yolov8n.pt")
            
            # Eger model root dizine indiyse, çevrimdışı kalması için mühürlü alana tasi
            if not self.yolo_model_path.exists() and Path("yolov8n.pt").exists():
                import shutil
                shutil.move("yolov8n.pt", str(self.yolo_model_path))
                self.yolo_model = YOLO(str(self.yolo_model_path))

            # Tensor cekirdeklerini isinma turuyle uyar (Warmup) donanimsal gecikmeyi onler
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            self.yolo_model.predict(
                source=dummy_frame, 
                device=self.device, 
                half=(self.device == "cuda"), # FP16 Yari Hassasiyet Optimizasyonu
                verbose=False
            )
            sys.stdout.write(f"\r[ŞAHİN GÖZÜ] Motor {self.device.upper()} üzerinde devrede. Optik görüş kusursuz.\033[K\n")
            sys.stdout.flush()
        except Exception as e:
            logging.error(f"YOLO Yükleme Hatası: {e}")
            raise RuntimeError(f"Donanım Hatası: YOLO motoru çöktü. {e}")

    def _connect(self) -> bool:
        """Donanımsal kamera portunu açar ve Jetson hızına optimize eder."""
        try:
            # Jetson kameraları için V4L2 öncelikli denenir
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_index)
                
            if self.cap.isOpened():
                # Performans ve Altin Oran (VRAM) icin cozunurlugu 640x480 kisitla
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
                # RAM sismesini onleyen en kritik hamle: Buffer size 1 yapilir, eski kareler copedir.
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                sys.stdout.write("\r[ŞAHİN GÖZÜ] Donanımsal optik sensör aktif.\033[K\n")
                sys.stdout.flush()
                return True
                
            logging.error(f"Kamera (Index {self.camera_index}) fiziksel olarak bulunamadı.")
            return False
        except Exception as e:
            logging.error(f"Kamera bağlantı hatası: {e}")
            raise RuntimeError(f"Kamera başlatılamadı: {e}")

    def arm_security(self, state: bool):
        """Seraf Ajanını teyakkuza gecirir veya kapatir."""
        with self.lock:
            self.security_armed = state
            mode_str = "AKTİF (İnsan İhlali Bekleniyor)" if state else "KAPALI"
            sys.stdout.write(f"\r[SERAF] Gözetleme Kalkanı: {mode_str}\033[K\n")
            sys.stdout.flush()

    def _vision_loop(self):
        """
        Göz döngüsü. Kamerayı 30 FPS okur ancak YOLO'yu saniyede sadece 4-5 kez çalistirarak 
        Jetson islemcisini termal darbogazdan (Thermal Throttling) kurtarir.
        """
        last_yolo_time = 0.0
        yolo_interval = 0.25 # Saniyede 4 infaz
        
        while not self._stop_event.is_set() and self.is_active:
            if self.cap is None or not self.cap.isOpened():
                logging.error("Kamera sensör kopması tespit edildi. Otonom yeniden deneniyor...")
                if self._connect():
                    time.sleep(1)
                else:
                    time.sleep(3)
                continue

            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logging.warning("Sensörden boş kare geldi. Atlanıyor.")
                    time.sleep(0.1)
                    continue

                # Zihin ve Arayüz (Biyometri) için saf, işlenmemiş anlık kareyi mühürle
                with self.lock:
                    self.latest_frame = frame.copy()

                current_time = time.time()
                # YOLO İnfazı (0.45 Güvenilirlik Altın Oranıyla)
                if self.yolo_model is not None and (current_time - last_yolo_time) >= yolo_interval:
                    last_yolo_time = current_time
                    
                    results = self.yolo_model.predict(
                        source=frame, 
                        device=self.device,
                        half=(self.device == "cuda"), # FP16 yarım hassasiyet kuralı
                        conf=0.45,
                        verbose=False
                    )
                    
                    detected_names = []
                    human_found = False
                    
                    if len(results) > 0 and len(results[0].boxes) > 0:
                        for box in results[0].boxes:
                            class_id = int(box.cls[0])
                            class_name = results[0].names[class_id]
                            
                            if class_name == "person":
                                human_found = True
                                
                            tr_name = self.tr_map.get(class_name, class_name)
                            detected_names.append(tr_name)

                    # RAM ŞİŞİRMEYEN MUTLAK KURAL: Eski listeyi yok et, anlık durumu EZİP (overwrite) yaz.
                    if len(detected_names) > 0:
                        counts = Counter(detected_names)
                        summary = ", ".join([f"{count} {name}" for name, count in counts.items()])
                        with self.lock:
                            self.live_targets = summary
                            self.person_detected = human_found
                    else:
                        with self.lock:
                            self.live_targets = "Görüş alanı temiz."
                            self.person_detected = False

                    # Güvenlik Kalkanı İnfazı (Seraf 2-3m İhlali + İnsan Teyidi)
                    with self.lock:
                        armed = self.security_armed

                    if armed and human_found and self.security_callback:
                        self.security_callback(frame.copy())
                        
                # Donguyu kisa uyut (CPU/Sistem rahatlamasi)
                time.sleep(0.01)

            except cv2.error as ce:
                logging.error(f"OpenCV Okuma Hatası: {ce}")
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Optik Döngü İnfaz Hatası: {e}")
                time.sleep(1)

    def get_frame(self) -> np.ndarray:
        """Arayüz (UI) veya Zihin (Moondream Bayrak Yarışı) anlık fotoğraf isterse bunu sunar."""
        with self.lock:
            if self.latest_frame is not None and self.latest_frame.size > 0:
                return self.latest_frame.copy()
            return np.array([])

    def get_live_targets(self) -> str:
        """Zihin sorduğunda ('Şu an odada ne var?') RAM dostu kısa özeti fırlatır."""
        with self.lock:
            return self.live_targets

    def is_human_present(self) -> bool:
        """Seraf Radarı tetiklendiğinde doğrulamak için çağrılan güvenlik kilidi."""
        with self.lock:
            return self.person_detected

    def start(self):
        """Optik Gözü otonom olarak uyandırır."""
        if self.is_active:
            return
        if self._connect():
            self.is_active = True
            self._stop_event.clear()
            self.thread = threading.Thread(target=self._vision_loop, daemon=True)
            self.thread.start()
        else:
            raise RuntimeError("Kamera donanımı başlatılamadı, sistem infaz edildi.")

    def stop(self):
        """Uyku veya kapatma emriyle sensörü mühürler."""
        self.is_active = False
        self._stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2.0)
            
        with self.lock:
            if self.cap and self.cap.isOpened():
                self.cap.release()
            self.latest_frame = np.array([])
            self.live_targets = "Kamera kapalı."
            self.person_detected = False
            
        sys.stdout.write("\r[ŞAHİN GÖZÜ] Optik sensör kapatıldı ve VRAM tahliye edildi.\033[K\n")
        sys.stdout.flush()

if __name__ == "__main__":
    def dummy_seraf_callback(frame):
        sys.stdout.write("\r[SERAF] İNSAN İHLALİ! Fotoğraf çekiliyor...\033[K")
        sys.stdout.flush()

    # Orkestratör olmadan YOLO Cekirdek Testi
    cam = CameraEye(security_callback=dummy_seraf_callback)
    cam.start()
    
    sys.stdout.write("[*] YOLO Nano Aktif. 10 saniye çalışacak. Kameranın karşısına geçin.\n")
    cam.arm_security(True) # İnsan arayacak
    
    try:
        for _ in range(10):
            time.sleep(1)
            sys.stdout.write(f"\r[*] Canlı Görüş Avı: {cam.get_live_targets()} | İnsan var mı: {cam.is_human_present()}\033[K")
            sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write("\n[*] İnfaz durduruldu.\n")
    finally:
        sys.stdout.write("\n")
        cam.stop()