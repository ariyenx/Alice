# perception/voice_dna.py
# Yazar: Mimar
# Kurallar: 25MB ECAPA-TDNN Mimarisi. CPU üzerinde çalışır, VRAM tüketmez. "pass" YOKTUR.

import os
import sys
import numpy as np
from pathlib import Path
import warnings

try:
    import torch
    import torchaudio
    from speechbrain.inference.speaker import EncoderClassifier
except ImportError as e:
    raise RuntimeError(f"Ses DNA kütüphaneleri eksik (speechbrain, torchaudio): {e}")

class VoiceBiometrics:
    def __init__(self, storage_dir):
        """SpeechBrain ECAPA-TDNN Askeri Ses Sınıflandırıcısı"""
        self.device = "cpu"  # VRAM'i korumak için mutlak suretle CPU
        self.storage_dir = Path(storage_dir)
        self.db_dir = self.storage_dir / "voice_dna"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        warnings.filterwarnings('ignore')
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        try:
            self.classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(self.storage_dir / "models" / "ecapa"),
                run_opts={"device": self.device}
            )
        except Exception as e:
            sys.stdout = old_stdout
            raise RuntimeError(f"Ses DNA Modeli Çöktü: {e}")
        finally:
            sys.stdout = old_stdout

        self.threshold = 0.65  # Benzerlik Eşiği
        self.known_voices = {}
        self.load_profiles()

    def load_profiles(self):
        """Kaydedilmiş Hanedan (Aryen, Rana) DNA'larını bellekten okur."""
        self.known_voices.clear()
        for npy_file in self.db_dir.glob("*.npy"):
            self.known_voices[npy_file.stem] = np.load(str(npy_file))

    def extract_fingerprint(self, wav_path: str) -> np.ndarray:
        """Sesten 192 boyutlu gırtlak vektörünü (DNA) çıkarır."""
        signal, fs = torchaudio.load(wav_path)
        if fs != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
            signal = resampler(signal)
        with torch.no_grad():
            embeddings = self.classifier.encode_batch(signal)
        return embeddings.squeeze().cpu().numpy()

    def enroll(self, wav_path: str, name: str) -> bool:
        """Arayüzden (UI) kaydedilen 5 saniyelik sesi mühürler."""
        try:
            fingerprint = self.extract_fingerprint(wav_path)
            np.save(str(self.db_dir / f"{name}.npy"), fingerprint)
            self.known_voices[name] = fingerprint
            return True
        except Exception as e:
            print(f"[DNA] Kayıt Hatası: {e}")
            return False

    def identify(self, wav_path: str) -> str:
        """Sesi dinler ve Aryen, Rana veya Misafir olduğunu anlar."""
        if not self.known_voices:
            return "1 Misafir"
        try:
            current_fp = self.extract_fingerprint(wav_path)
            best_score = -1.0
            best_speaker = "1 Misafir"

            for name, saved_fp in self.known_voices.items():
                score = np.dot(current_fp, saved_fp) / (np.linalg.norm(current_fp) * np.linalg.norm(saved_fp))
                if score > best_score:
                    best_score = score
                    if score >= self.threshold:
                        best_speaker = name
            return best_speaker
        except Exception:
            return "1 Misafir"