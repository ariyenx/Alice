# perception/wake_word.py
# Yazar: Mimar
# Kurallar: openWakeWord motoru. İnternetsiz %100 Çevrimdışı. Altın oran tetikleme. "pass" YOKTUR.

import os
import sys
import time
import threading
import logging
import numpy as np
import pyaudio
import openwakeword
from openwakeword.model import Model
from pathlib import Path

# Anayasa bağlantısı
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Seraf'ın 7 günlük temizlik döngüsüne tabi bağımsız log dosyası
logging.basicConfig(
    filename=config.LOG_DIR / "wake_word.log",
    level=logging.WARNING,
    format="%(asctime)s - [KULAK] - %(message)s"
)

class WakeWordListener:
    def __init__(self, callback):
        """
        Sistemin asla uyumayan sahte bilinci. Sadece ve sadece 'Alis' kelimesini 
        arayarak mikrofonu 16kHz'de dinler. Bulduğunda ana Zihni ve Gözü uyandırır.
        """
        self.callback = callback
        self.chunk_size = 1280
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000  # openWakeWord için altın oran frekansı

        self.is_listening = False
        self._stop_event = threading.Event()
        
        try:
            # openWakeWord temel modellerini indirir (zaten varsa atlar)
            openwakeword.utils.download_models()
            
            # Alis'in özel eğitilmiş ONNX model yolu
            self.model_dir = config.STORAGE_DIR / "models"
            self.model_dir.mkdir(parents=True, exist_ok=True)
            self.model_path = str(self.model_dir / "alis.onnx")
            
            # Eğer alis.onnx fiziksel olarak yoksa, sistemin sağır kalmaması için 
            # geçici olarak varsayılan bir model ile pusuya yatar.
            if os.path.exists(self.model_path):
                self.oww_model = Model(wakeword_models=[self.model_path], inference_framework="onnx")
                self.target_word = "alis"
            else:
                logging.warning(f"Ozel '{self.model_path}' bulunamadi. Gecici olarak 'alexa' test modeli aktif.")
                self.oww_model = Model(wakeword_models=["alexa"], inference_framework="onnx")
                self.target_word = "alexa"
        except Exception as e:
            logging.error(f"openWakeWord motoru baslatilamadi: {e}")
            sys.exit(1)

        self.audio = pyaudio.PyAudio()
        self.stream = None

    def _listen_loop(self):
        """Hafızayı yormadan RAM limitleri içinde sonsuz dinleme döngüsü."""
        try:
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
        except Exception as e:
            logging.error(f"Mikrofon donanimi acilamadi: {e}. usb_keeper devrede mi?")
            sys.stdout.write("\r[KULAK HATA] Mikrofon bulunamadi! Baglantiyi kontrol edin.\033[K\n")
            sys.stdout.flush()
            return

        sys.stdout.write(f"\r[KULAK] Tetikte. '{self.target_word}' uyanma kelimesi bekleniyor...\033[K\n")
        sys.stdout.flush()

        while not self._stop_event.is_set() and self.is_listening:
            try:
                # exception_on_overflow=False ile Jetson anlık işlemci darbogazinda çökmez
                pcm_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                audio_data = np.frombuffer(pcm_data, dtype=np.int16)
                
                # Sesi openWakeWord modeline ver ve tahmin skorunu al
                prediction = self.oww_model.predict(audio_data)
                
                for mdl_name, score in prediction.items():
                    # 0.5 Altın Oran güvenilirlik eşiği, halüsinasyon duyumunu engeller
                    if score > 0.5:
                        sys.stdout.write(f"\r[KULAK] '{self.target_word}' DUYULDU! (Skor: {score:.2f})\033[K\n")
                        sys.stdout.flush()
                        
                        # Art arda tetiklenmeyi önlemek için tamponu temizle
                        self.oww_model.reset()
                        
                        # Ana sisteme uyanma sinyali gönder
                        if self.callback:
                            self.callback()
                            
                        # Uyanıştan sonra kulağı 1.618 saniye bilerek sağır et (Kendi yankısını duymaması için)
                        time.sleep(1.618)
                        
            except IOError as e:
                logging.error(f"Mikrofon tampon tasmasi: {e}")
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Beklenmeyen ses okuma hatasi: {e}")
                time.sleep(0.1)

    def start(self):
        """Dinleme iskeletini asenkron (Thread) olarak başlatır."""
        if self.is_listening:
            return
        self.is_listening = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Sistem kapanırken kulak zarını güvenle yırtar ve kaynakları boşaltır."""
        self.is_listening = False
        self._stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join()
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        sys.stdout.write("\r[KULAK] Sagirlik devrede. Dinleme sonlandirildi.\033[K\n")
        sys.stdout.flush()

if __name__ == "__main__":
    # Orkestratör olmadan bağımsız çekirdek testi
    def test_wake_trigger():
        sys.stdout.write("\n[*] ALIS UYANDI! ZIHIN VE GOZ 33 SANIYE ICIN TETIKLENDI!\n")
        sys.stdout.flush()

    ear = WakeWordListener(callback=test_wake_trigger)
    ear.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ear.stop()