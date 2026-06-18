# main.py
# Yazar: Mimar
# Kurallar: Ses DNA, MAC Taraması, Otonom Uyanış, Termal Kalkan. SIFIR "pass".

import os
import sys
import time
import threading
import traceback
import gc

try:
    import torch
except ImportError as e:
    sys.exit(f"[KRİTİK HATA] PyTorch bulunamadı: {e}")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    from perception.voice_dna import VoiceBiometrics
    from network.cyber_tracker import CyberTracker
    from perception.stt_tts import AudioInterface
    from cognition.alice_mind import AliceMind
    from hardware.camera import YoloCamera
    from hardware.iot_thermal import ThermalController
except ImportError as e:
    sys.exit(f"[KRİTİK HATA] Modüller yüklenemedi: {e}")

class AliceOrchestrator:
    def __init__(self):
        sys.stdout.write("[MİMAR]: Alice Edge OS Çekirdeği Başlatılıyor...\n")
        self.is_running = True
        self.is_awake = False
        self.active_user = "1 Misafir"
        self.last_interaction_time = time.time()
        self.vram_cleared = False
        
        self.speech_lock = threading.Lock()
        self.is_speaking = False

        try:
            self.physical = ThermalController()
            sys.stdout.write("[DONANIM]: Termal sensörler aktif.\n")
        except Exception as e:
            self.physical = None
            sys.stdout.write(f"[HATA]: Termal kontrolcü başlatılamadı: {e}\n")

        try:
            self.camera = YoloCamera()
            if hasattr(self.camera, 'disable_heavy_face_recognition'):
                self.camera.disable_heavy_face_recognition()
            sys.stdout.write("[DONANIM]: Şahin Gözü devrede. Yüz tanıma optimize edildi.\n")
        except Exception as e:
            self.camera = None
            sys.stdout.write(f"[HATA]: Kamera sensörü başlatılamadı: {e}\n")

        try:
            self.comm = AudioInterface()
            sys.stdout.write("[ALGI]: STT/TTS motorları hazır.\n")
        except Exception as e:
            self.comm = None
            sys.stdout.write(f"[HATA]: STT/TTS Motoru çöktü: {e}\n")

        try:
            self.voice_dna = VoiceBiometrics(config.STORAGE_DIR)
            sys.stdout.write("[ALGI]: Ses DNA motoru CPU üzerinde mühürlendi.\n")
        except Exception as e:
            self.voice_dna = None
            sys.stdout.write(f"[HATA]: Ses Biyometrisi başlatılamadı: {e}\n")

        try:
            self.cyber_tracker = CyberTracker(config.STORAGE_DIR)
            sys.stdout.write("[AĞ]: Siber Gözcü (MAC Radarı) hazır.\n")
        except Exception as e:
            self.cyber_tracker = None
            sys.stdout.write(f"[HATA]: Siber Gözcü başlatılamadı: {e}\n")

        try:
            self.mind = AliceMind()
            sys.stdout.write("[BİLİŞSEL]: LLM Zihin Çekirdeği hazır.\n")
        except Exception as e:
            self.mind = None
            sys.stdout.write(f"[HATA]: Zihin motoru başlatılamadı: {e}\n")

        self.core_thread = threading.Thread(target=self._cognitive_loop, daemon=True)
        self.thermal_thread = threading.Thread(target=self._thermal_loop, daemon=True)

    def start(self):
        if self.camera:
            self.camera.start()
        self.core_thread.start()
        self.thermal_thread.start()
        sys.stdout.write("\n[MİMAR]: ALİCE PUSUDA BEKLİYOR.\n")
        
        while self.is_running:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                sys.stdout.write(f"[KRİTİK HATA]: Ana thread kesintisi: {e}\n")

    def stop(self):
        sys.stdout.write("\n[MİMAR]: Kıyamet Protokolü tetiklendi. Sistem kapatılıyor...\n")
        self.is_running = False
        if self.camera:
            self.camera.stop()
        if self.mind:
            self.mind.clear_vram()
        sys.exit(0)

    def safe_speak(self, text: str):
        if not text or not self.comm:
            return
        with self.speech_lock:
            self.is_speaking = True
            try:
                self.comm.speak(text)
            except Exception as e:
                sys.stdout.write(f"[HATA]: Konuşma başarısız: {e}\n")
            finally:
                self.is_speaking = False
        self.last_interaction_time = time.time()
        self.vram_cleared = False

    def interrupt(self):
        if self.comm:
            self.comm.stop_audio()
        if self.mind:
            self.mind.interrupt()
        self.is_awake = False
        sys.stdout.write("[SİSTEM] İnfaz durduruldu. Pusu moduna dönüldü.\n")

    def _clear_vram(self):
        try:
            if self.mind:
                self.mind.clear_vram()
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            self.vram_cleared = True
            sys.stdout.write("[SİSTEM] 33 Saniye Kuralı: VRAM temizlendi.\n")
        except Exception as e:
            sys.stdout.write(f"[VRAM HATASI]: {e}\n")

    def _process_command(self, cmd: str):
        self.last_interaction_time = time.time()
        self.vram_cleared = False
        if self.mind:
            reply = self.mind.think("Hanedan_Terminal", cmd)
            self.safe_speak(reply)
        else:
            sys.stdout.write("[HATA] Zihin motoru çevrimdışı.\n")

    def _cognitive_loop(self):
        wav_path = "/tmp/alice_cmd.wav"
        while self.is_running:
            try:
                if not self.comm:
                    time.sleep(1)
                    continue

                if not self.is_awake and not self.vram_cleared and (time.time() - self.last_interaction_time > 33):
                    self._clear_vram()

                if not self.is_awake:
                    if self.comm.listen_for_wakeword():
                        self.is_awake = True
                        self.last_interaction_time = time.time()
                        self.vram_cleared = False
                else:
                    sys.stdout.write("\r[ALICE]: Dinleniyor...\033[K\n")
                    text = self.comm.record_and_transcribe(wav_path, timeout_sec=5)
                    
                    if not text:
                        self.is_awake = False
                        continue

                    self.last_interaction_time = time.time()
                    speaker = "1 Misafir"
                    if self.voice_dna and os.path.exists(wav_path):
                        speaker = self.voice_dna.identify(wav_path)
                    
                    self.active_user = speaker
                    greeting = ""
                    if speaker in ["Aryen", "Rana"]:
                        is_device_home = False
                        if self.cyber_tracker:
                            is_device_home = self.cyber_tracker.is_device_home(speaker)
                        
                        if is_device_home:
                            greeting = f"Merhaba {speaker}, siber ağda cihazını doğruladım."
                        else:
                            greeting = f"Merhaba {speaker}."
                    
                    if greeting:
                        self.safe_speak(greeting)

                    sys.stdout.write(f"\n[DURUM]: Konuşan ({speaker}) | Emir: {text}\n")

                    if self.mind:
                        secret_context = f"[SİSTEM GİZLİ NOTU: Seninle konuşan kişi {speaker}. Cevaplarında ona saygıyla ve ismiyle hitap et.]"
                        reply = self.mind.think(speaker, text, context=secret_context)
                        self.safe_speak(reply)
                    else:
                        self.safe_speak("Zihin motoruma ulaşılamıyor.")

                    self.is_awake = False

            except Exception as e:
                sys.stdout.write(f"[ÇEKİRDEK İSTİSNASI]: {e}\n")
                traceback.print_exc()
                self.is_awake = False
                time.sleep(1)

    def _thermal_loop(self):
        while self.is_running:
            try:
                if self.physical:
                    temp = self.physical.get_max_temperature()
                    if temp >= 80.0:
                        sys.stdout.write(f"[KRİTİK UYARI] Isı {temp}°C'ye ulaştı! Acil soğutma.\n")
                        self.safe_speak("Termal sınırlar aşıldı. Zihinsel faaliyetleri askıya alıyorum.")
                        self._clear_vram()
                        time.sleep(60)
            except Exception as e:
                sys.stdout.write(f"[TERMAL SENSÖR HATASI]: {e}\n")
            time.sleep(10)