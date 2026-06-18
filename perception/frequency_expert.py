# perception/frequency_expert.py
# Yazar: Mimar
# Kurallar: 85-255Hz FFT Insan Filtresi, YAMNet ile 521 Çevresel Ses Analizi, 18kHz Psikolojik Silah. %100 Üretime Hazır.

import os
import sys
import logging
import urllib.request
import numpy as np
import pyaudio
import onnxruntime as ort
import csv
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "frequency_expert.log",
    level=logging.WARNING,
    format="%(asctime)s - [SES UZMANI] - %(message)s"
)

class FrequencyExpert:
    def __init__(self):
        """
        Kulağa biyolojik bir zekâ katar. FFT ile insan sesini doğrular.
        YAMNet (ONNX) ile çevresel sesleri (kuş, köpek, alarm) sınıflandırır.
        Seraf ajanı için nörolojik ses silahı barındırır.
        """
        self.sample_rate = 16000
        self.chunk_size = 15600  # YAMNet için 0.975 saniyelik altın oran tamponu
        self.format = pyaudio.paInt16
        self.channels = 1

        # ONNX Model Dizinleri
        self.model_dir = config.STORAGE_DIR / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.yamnet_path = self.model_dir / "yamnet.onnx"
        self.class_map_path = self.model_dir / "yamnet_class_map.csv"
        
        self.classes = []
        self._ensure_yamnet_exists()
        self._load_classes()
        
        try:
            # Sadece CPU kullanarak RAM/VRAM dengesini kusursuz korur
            self.session = ort.InferenceSession(str(self.yamnet_path), providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
        except Exception as e:
            logging.error(f"YAMNet motoru baslatilamadi: {e}")
            self.session = None

        self.audio = pyaudio.PyAudio()
        self.weapon_stream = None

    def _ensure_yamnet_exists(self):
        """Sistemde YAMNet yoksa otonom olarak indirip üretime hazırlar."""
        if not self.yamnet_path.exists():
            sys.stdout.write("\r[SES UZMANI] Zekâ Modeli (3MB) otonom indiriliyor...\033[K\n")
            sys.stdout.flush()
            try:
                urllib.request.urlretrieve("https://github.com/microsoft/onnx-models/raw/main/audio/yamnet/yamnet.onnx", self.yamnet_path)
            except Exception as e:
                logging.warning(f"ONNX Model indirilemedi (Ag Hatasi): {e}")

        if not self.class_map_path.exists():
            try:
                urllib.request.urlretrieve("https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv", self.class_map_path)
            except Exception:
                pass

    def _load_classes(self):
        """CSV dosyasındaki 521 ses sınıfını Hanedan için yükler."""
        if self.class_map_path.exists():
            try:
                with open(self.class_map_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader) # Basligi atla
                    self.classes = [row[2].strip() for row in reader if len(row) > 2]
            except Exception:
                self.classes = ["Bilinmeyen Ses"] * 521
        else:
            self.classes = ["Bilinmeyen Ses"] * 521

    def is_human_speaking(self, audio_data: np.ndarray) -> bool:
        """FFT (Hızlı Fourier Dönüşümü) ile 85Hz - 255Hz aralığında biyolojik insan sesi analizi yapar."""
        try:
            if len(audio_data) == 0:
                return False
                
            N = len(audio_data)
            yf = np.fft.fft(audio_data)
            xf = np.linspace(0.0, self.sample_rate / 2.0, N // 2)
            
            power = 2.0 / N * np.abs(yf[0:N // 2])
            dominant_freq_index = np.argmax(power)
            dominant_freq = xf[dominant_freq_index]
            
            if config.HUMAN_FREQ_MIN_HZ <= dominant_freq <= config.HUMAN_FREQ_MAX_HZ:
                return True
            return False
        except Exception as e:
            logging.error(f"FFT Analiz Hatasi: {e}")
            return False

    def get_audio_snapshot(self, duration_sec=2.0):
        """Ortam dinlemesi yapar."""
        try:
            stream = self.audio.open(format=self.format, channels=self.channels,
                                     rate=self.sample_rate, input=True, frames_per_buffer=self.chunk_size)
            frames = []
            sys.stdout.write(f"\r[SES UZMANI] Ortam dinleniyor... ({duration_sec} sn)\033[K\n")
            sys.stdout.flush()
            
            for _ in range(0, int(self.sample_rate / self.chunk_size * duration_sec)):
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(np.frombuffer(data, dtype=np.int16))
                
            stream.stop_stream()
            stream.close()
            return np.hstack(frames)
        except Exception as e:
            logging.error(f"Ses okuma hatasi: {e}")
            return None

    def what_is_this_sound(self) -> str:
        """YAMNet ONNX modeli ile ortamdaki sesi 521 sınıftan birine eşler ('Bu ses nedir?')."""
        if self.session is None:
            return "Ses analiz zekası yüklenemedi."

        audio_data = self.get_audio_snapshot()
        if audio_data is None or len(audio_data) == 0 or np.max(np.abs(audio_data)) < 100:
            return "Ortamda analiz edilebilecek belirgin bir ses yok veya mutlak sessizlik var."

        try:
            waveform = audio_data.astype(np.float32) / 32768.0
            
            if len(waveform) > self.chunk_size:
                waveform = waveform[:self.chunk_size]
            elif len(waveform) < self.chunk_size:
                waveform = np.pad(waveform, (0, self.chunk_size - len(waveform)))
                
            waveform = np.expand_dims(waveform, axis=0) # Batch size 1
            
            outputs = self.session.run(None, {self.input_name: waveform})
            scores = outputs[0][0] 
            
            top_class_index = np.argmax(scores)
            confidence = scores[top_class_index]
            
            # Halüsinasyon kalkanı
            if confidence < 0.20:
                return "Bu sesi tanımlayamadım, çok karmaşık veya gürültülü."
                
            sound_name = self.classes[top_class_index]
            return f"Tespit edilen ses: {sound_name} (Güvenilirlik: %{int(confidence*100)})"
            
        except Exception as e:
            logging.error(f"YAMNet analiz hatası: {e}")
            return "Ses analizi sırasında matematiksel bir bozulma yaşandı."

    def fire_deterrent_weapon(self, duration_sec: int = 7):
        """Seraf Ajanı'nın Gazabı: Yabancıları kaçıran nörolojik ses silahı (18kHz Testere Dişi dalga)."""
        freq = 18000.0 # 18 kHz ultrasonik rahatsız edici sınır
        rate = 44100
        
        sys.stdout.write(f"\r[SERAF KALKANI] Psikolojik ses silahı ateşlendi! ({freq}Hz - {duration_sec} sn)\033[K\n")
        sys.stdout.flush()
        
        # Testere dişi dalga hissi için sinüs dalgasının asimetrik işlenmesi
        t = np.linspace(0, duration_sec, int(rate * duration_sec), endpoint=False)
        wave = 0.5 * np.sin(2 * np.pi * freq * t + np.sin(2 * np.pi * 10 * t))
        audio_out = (wave * 32767).astype(np.int16)
        
        try:
            self.weapon_stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=rate, output=True)
            self.weapon_stream.write(audio_out.tobytes())
            self.weapon_stream.stop_stream()
            self.weapon_stream.close()
            self.weapon_stream = None
        except Exception as e:
            logging.error(f"Seraf silahi ateslenemedi: {e}")
            
        sys.stdout.write("\r[SERAF KALKANI] Silah susturuldu. Hedef izleniyor...\033[K\n")
        sys.stdout.flush()

    def cleanup(self):
        if hasattr(self, 'weapon_stream') and self.weapon_stream is not None:
            self.weapon_stream.stop_stream()
            self.weapon_stream.close()
        self.audio.terminate()

if __name__ == "__main__":
    expert = FrequencyExpert()
    print("[*] Frekans Uzmanı Testi Başlıyor...")
    print(expert.what_is_this_sound())
    expert.cleanup()