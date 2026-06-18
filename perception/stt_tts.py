# perception/stt_tts.py
# Yazar: Mimar
# Kurallar: openWakeWord (15MB RAM Uyanis), Silero VAD (Insan Sesi Tespiti), Faster-Whisper. Hata yutma YOKTUR.

import os
import sys
import time
import logging
import threading
import wave
import subprocess
from pathlib import Path
import numpy as np
import pyaudio

try:
    import torch
    from faster_whisper import WhisperModel
    import openwakeword
    from openwakeword.model import Model as WakeWordModel
except ImportError as e:
    raise RuntimeError(f"Ses algı kütüphaneleri eksik (torch/faster_whisper/openwakeword): {e}")

try:
    from TTS.api import TTS
except ImportError as e:
    raise RuntimeError(f"TTS kütüphanesi eksik: {e}")

# Anayasa baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "stt_tts.log",
    level=logging.WARNING,
    format="%(asctime)s - [İLETİŞİM] - %(message)s"
)

class CommunicationCore:
    def __init__(self):
        """Zihnin Kulaklari ve Agzi. VAD ve WakeWord kalkanlariyla donatilmistir."""
        self.temp_dir = config.TEMP_DIR
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        
        self.models_dir = config.STORAGE_DIR / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.audio = pyaudio.PyAudio()
        self.sample_rate = 16000
        self.chunk_size = 1280 
        self.format = pyaudio.paInt16
        self.channels = 1
        
        sys.stdout.write("\r[KULAK] Silero VAD (İnsan Sesi Filtresi) çekiliyor...\033[K\n")
        sys.stdout.flush()
        try:
            self.vad_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', trust_repo=True)
            self.vad_model.eval()
        except Exception as e:
            raise RuntimeError(f"Silero VAD Modeli çekilemedi: {e}")

        sys.stdout.write("\r[KULAK] openWakeWord CPU Kalkanı aktif ediliyor...\033[K\n")
        sys.stdout.flush()
        try:
            openwakeword.utils.download_models()
            model_path = self.models_dir / "alis.onnx"
            if model_path.exists():
                self.wake_model = WakeWordModel(wakeword_models=[str(model_path)], inference_framework="onnx")
                self.wake_key = "alis"
            else:
                # Ozel model yoksa otonom olarak Alexa yedegine gecer
                self.wake_model = WakeWordModel(wakeword_models=["alexa"], inference_framework="onnx")
                self.wake_key = "alexa"
        except Exception as e:
            raise RuntimeError(f"WakeWord kalkanı çöktü: {e}")

        sys.stdout.write("\r[KULAK] STT (faster-whisper) CUDA'ya yükleniyor...\033[K\n")
        sys.stdout.flush()
        try:
            self.stt_model = WhisperModel("small", device="cuda" if torch.cuda.is_available() else "cpu", compute_type="float16")
        except Exception as e:
            raise RuntimeError(f"Whisper CUDA yüklenemedi: {e}")

        sys.stdout.write("\r[AĞIZ] TTS Motoru (Türkçe VITS) başlatılıyor...\033[K\n")
        sys.stdout.flush()
        try:
            self.tts_model = TTS(model_name="tts_models/tr/f_boun/vits", progress_bar=False, gpu=torch.cuda.is_available())
        except Exception as e:
            raise RuntimeError(f"TTS başlatılamadı: {e}")

    def _is_human_voice(self, audio_chunk: bytes) -> bool:
        """Silero VAD motoruyla sesteki insan girtlagi yuzdesini cikarir."""
        try:
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            tensor_chunk = torch.from_numpy(audio_float32)
            
            with torch.no_grad():
                vad_prob = self.vad_model(tensor_chunk, self.sample_rate).item()
            return vad_prob > 0.5 
        except Exception as e:
            logging.error(f"VAD Matematik Hatası: {e}")
            return False

    def wait_for_wake_word(self, speech_lock: threading.Lock) -> bool:
        """Uyku aninda GPU'yu dinlendirip sadece CPU'da WakeWord bekler."""
        stream = None
        try:
            stream = self.audio.open(format=self.format, channels=self.channels,
                                     rate=self.sample_rate, input=True,
                                     frames_per_buffer=self.chunk_size)
            
            sys.stdout.write(f"\r[ALİS] Uyku Modu. Uyanış kelimesi ({self.wake_key}) bekleniyor...\033[K\n")
            sys.stdout.flush()

            while True:
                with speech_lock:
                    is_speaking = getattr(speech_lock, "is_speaking", False)
                if is_speaking:
                    stream.read(self.chunk_size, exception_on_overflow=False)
                    continue

                data = stream.read(self.chunk_size, exception_on_overflow=False)
                
                # CPU israfini engellemek icin once sesin insan olup olmadigini (VAD) sorar
                if self._is_human_voice(data):
                    audio_np = np.frombuffer(data, dtype=np.int16)
                    prediction = self.wake_model.predict(audio_np)
                    
                    for mdl_name, score in prediction.items():
                        if score > 0.5:
                            sys.stdout.write(f"\r[KULAK] Uyanış kelimesi tespit edildi (Güven: %{int(score*100)})\033[K\n")
                            sys.stdout.flush()
                            return True
        except Exception as e:
            raise RuntimeError(f"WakeWord okuma döngüsü çöktü: {e}")
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()

    def listen_and_transcribe(self, timeout_sec: int = 15) -> str:
        """Silero VAD ile sadece insani dinler. Motor sesi gelirse gozardi eder."""
        stream = None
        try:
            stream = self.audio.open(format=self.format, channels=self.channels,
                                     rate=self.sample_rate, input=True,
                                     frames_per_buffer=self.chunk_size)
            
            sys.stdout.write("\r[ALİS] Dinliyorum (VAD Kalkanı Aktif)...\033[K\n")
            sys.stdout.flush()

            frames = []
            has_started_speaking = False
            silence_start_time = 0.0
            start_time = time.time()
            silence_limit_sec = 1.618 

            while True:
                if not has_started_speaking and (time.time() - start_time) > timeout_sec:
                    break

                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    is_human = self._is_human_voice(data)

                    if not has_started_speaking:
                        if is_human:
                            has_started_speaking = True
                            frames.append(data)
                            sys.stdout.write("\r[KULAK] İnsan sesi (VAD) algılandı, kayıt başladı...\033[K\n")
                            sys.stdout.flush()
                    else:
                        frames.append(data)
                        if not is_human:
                            if silence_start_time == 0.0:
                                silence_start_time = time.time()
                            elif time.time() - silence_start_time > silence_limit_sec:
                                break 
                        else:
                            silence_start_time = 0.0 

                except IOError:
                    continue

        except Exception as e:
            raise RuntimeError(f"Mikrofon kayıt hatası: {e}")
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()

        if not has_started_speaking or len(frames) == 0:
            return ""

        temp_wav = self.temp_dir / "temp_listen.wav"
        try:
            with wave.open(str(temp_wav), 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(frames))

            sys.stdout.write("\r[ZİHİN] Sesten metne çevriliyor...\033[K\n")
            sys.stdout.flush()
            
            segments, _ = self.stt_model.transcribe(str(temp_wav), beam_size=5, language="tr", condition_on_previous_text=False)
            text = " ".join([segment.text for segment in segments]).strip()
            
            if temp_wav.exists():
                os.remove(str(temp_wav))
                
            if text:
                sys.stdout.write(f"\r[SİZ] {text}\033[K\n")
                sys.stdout.flush()
            return text
        except Exception as e:
            raise RuntimeError(f"Whisper CUDA İnfaz Hatası: {e}")

    def speak(self, text: str):
        if not text:
            return
            
        sys.stdout.write(f"\r[ALİS] {text}\033[K\n")
        sys.stdout.flush()

        with self.lock:
            temp_out = self.temp_dir / "temp_speak.wav"
            try:
                self.tts_model.tts_to_file(text=text, file_path=str(temp_out))
                subprocess.run(["aplay", "-q", str(temp_out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if temp_out.exists():
                    os.remove(str(temp_out))
            except Exception as e:
                raise RuntimeError(f"TTS Oynatma Hatası: {e}")

    def cleanup(self):
        self.audio.terminate()