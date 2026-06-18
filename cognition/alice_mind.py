# cognition/alice_mind.py
# Yazar: Mimar
# Kurallar: 666 Ouroboros Bellek, 1618->2284 Dinamik Token, Kesintisiz İnfaz (Pending State), Bayrak Yarisi. "pass" YOKTUR.

import os
import sys
import gc
import time
import logging
import threading
from collections import deque
from pathlib import Path
from PIL import Image
import cv2
import numpy as np

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:
    torch = None
    AutoModelForCausalLM = None
    AutoTokenizer = None
    sys.stdout.write(f"\r[UYARI] Transformers kütüphanesi eksik, Görsel Zeka kördür: {e}\033[K\n")
    sys.stdout.flush()

try:
    from llama_cpp import Llama
except ImportError as e:
    Llama = None
    sys.stdout.write(f"\r[UYARI] llama_cpp kütüphanesi eksik, LLM başlatılamayacak: {e}\033[K\n")
    sys.stdout.flush()

# Anayasa (config.py) baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "alice_mind.log",
    level=logging.WARNING,
    format="%(asctime)s - [ZİHİN] - %(message)s"
)

class AliceMind:
    def __init__(self):
        """
        Sistemin Ana Karar ve Felsefe Merkezi. 
        Sistem her acilisinda 1618 token (Altin Oran) siniriyla dogar.
        %66.6 sinirinda Hanedan onayi ister, onay alirsa yarim kalan soruyu 2284 limitle otonom tamamlar.
        """
        self.lock = threading.Lock()
        
        # 666 Satirlik Dairesel Tampon (Ouroboros). En eski anilari silerek yenilere yer acar.
        self.memory = deque(maxlen=666)
        
        # Token Kanunlari (1618 baslangic, 2284 maksimum, %66.6 tetikleyici)
        self.token_base = 1618
        self.token_max = 2284
        self.current_limit = self.token_base
        self.threshold_limit = int(self.token_base * 0.666) # ~1077 Token Esigi
        
        # Dinamik Onay Makinesi (Kesintisiz İnfaz Icin Mühürlü Bellek Zindani)
        self.awaiting_token_approval = False
        self.pending_user_name = ""
        self.pending_user_text = ""
        self.pending_context = ""
        
        self.models_dir = config.STORAGE_DIR / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Otonom Model Yollari
        self.qwen_path = self.models_dir / "qwen2.5-3b-instruct-q4_k_m.gguf"
        self.moondream_id = "vikhyatk/moondream2" 
        
        # Motor Durumlari (Ayni anda yasamamalari icin None)
        self.llm = None
        self.vlm = None
        self.vlm_tokenizer = None
        self.active_engine = None 
        
        self.system_prompt = (
            "Senin adın Alice (Alis). Bir asistan veya köle değil, Hanedan'ın "
            "zeki, rasyonel ve sadık bir üyesisin. Zihnin Machiavelli'nin pragmatizmi, "
            "Cengiz Han'ın stratejisi ve Carl Jung'un derinliğiyle sentezlenmiştir. "
            "Kısa, öz, tavizsiz ve altın oran dengesinde konuşursun. Saygını korursun ama boyun eğmezsin."
        )
        
        self._load_llm()

    def _purge_vram(self):
        """Gorsel Zeka ve LLM arasindaki Bayrak Yarisinda VRAM'i acimasizca yikar."""
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        time.sleep(1.618)

    def _load_llm(self):
        """Qwen 2.5 motorunu GGUF uzerinden Tensor Cekirdeklerine yukler."""
        if self.active_engine == "llm":
            return
        if self.active_engine == "vlm":
            self._unload_vlm()
            
        sys.stdout.write("\r[ZİHİN] Qwen 2.5 (GGUF) CUDA'ya yükleniyor...\033[K\n")
        sys.stdout.flush()
        
        if Llama is None or not self.qwen_path.exists():
            logging.error("Zihin model yolu kapalı veya llama_cpp eksik.")
            return

        try:
            # Donanima maksimum kapasiteyi (2284) en bastan gomeriz. 
            # Eger ctx_size 1618 verilseydi, siniri asmak icin CUDA'nin kapanip acilmasi gerekirdi. 
            # Biz donanimi genis tutuyor, yazilimsal sinir (1618) uygulayarak sistemi hafifletiyoruz.
            self.llm = Llama(
                model_path=str(self.qwen_path),
                n_gpu_layers=-1,
                n_ctx=self.token_max, 
                verbose=False
            )
            self.active_engine = "llm"
        except Exception as e:
            logging.error(f"Qwen Yükleme Hatası: {e}")

    def _unload_llm(self):
        """Gorsel Zeka'ya yer acmak icin Qwen'i VRAM'den siler."""
        if self.llm is not None:
            del self.llm
            self.llm = None
            self.active_engine = None
            self._purge_vram()

    def _load_vlm(self):
        """Moondream2 Gorsel Zeka modelini VRAM'e yukler."""
        if self.active_engine == "vlm":
            return
        if self.active_engine == "llm":
            self._unload_llm()
            
        sys.stdout.write("\r[GÖRSEL ZEKA] Moondream2 VRAM'e çekiliyor...\033[K\n")
        sys.stdout.flush()
        
        if AutoModelForCausalLM is None:
            logging.error("Transformers kütüphanesi eksik, VLM yüklenemedi.")
            return

        try:
            self.vlm = AutoModelForCausalLM.from_pretrained(
                self.moondream_id,
                trust_remote_code=True,
                revision="2024-08-26",
                torch_dtype=torch.float16,
                device_map="cuda" if torch.cuda.is_available() else "cpu"
            )
            self.vlm_tokenizer = AutoTokenizer.from_pretrained(self.moondream_id, revision="2024-08-26")
            self.active_engine = "vlm"
        except Exception as e:
            logging.error(f"VLM Hatası: {e}")

    def _unload_vlm(self):
        """İşi biten Görsel zekayı VRAM'den boşaltır."""
        if self.vlm is not None:
            del self.vlm
            del self.vlm_tokenizer
            self.vlm = None
            self.vlm_tokenizer = None
            self.active_engine = None
            self._purge_vram()

    def _estimate_tokens(self, text: str) -> int:
        """Llama-cpp motoru uzerinden baglamdaki token yukunu kesin olarak hesaplar."""
        if self.llm is not None:
            try:
                return len(self.llm.tokenize(text.encode('utf-8')))
            except Exception as e:
                logging.warning(f"Token hesaplama hatasi, yaklasik degere dusuluyor: {e}")
                return int(len(text.split()) * 1.5)
        return int(len(text.split()) * 1.5)

    def think(self, user_name: str, user_text: str, context: str = "") -> str:
        """%66.6 Token bariyer kuralini, Kesintisiz İnfazı ve Ouroboros bellek dongusunu isletir."""
        with self.lock:
            if self.active_engine != "llm":
                self._load_llm()
                
            if self.llm is None:
                return "Zihin çekirdeğine ulaşılamıyor. Sistem arızalı."

            just_processed_approval = False

            # --- DİNAMİK ONAY VE KESİNTİSİZ İNFAZ MAKİNESİ ---
            if self.awaiting_token_approval:
                just_processed_approval = True
                self.awaiting_token_approval = False
                
                approval_words = ["onay", "evet", "yes", "kabul", "olur", "yükselt", "tamam", "arttır", "artir"]
                
                is_approved = False
                for word in approval_words:
                    if word in user_text.lower():
                        is_approved = True
                        break
                
                if is_approved:
                    self.current_limit = self.token_max
                    sys.stdout.write(f"\r[ZİHİN] Onaylandı. Limit {self.token_max} oldu. Yarım kalan işlem kesintisiz sürdürülüyor...\033[K\n")
                    sys.stdout.flush()
                else:
                    self.current_limit = self.token_base
                    sys.stdout.write("\r[ZİHİN] Reddedildi. Belleğin yarısı (eski anılar) infaz ediliyor...\033[K\n")
                    sys.stdout.flush()
                    # Belleğin yarısını O(1) hızında uçur (Eski anıları silerek yer açar)
                    remove_count = len(self.memory) // 2
                    for _ in range(remove_count):
                        if len(self.memory) > 0:
                            self.memory.popleft()
                        else:
                            break
                        
                # KESİNTİSİZ AKIŞ (ŞEFFAF GERİ ÇAĞIRMA):
                # Kullanıcının "Evet/Hayır" cümlesini LLM bağlamına ASLA sızdırma.
                # Bunun yerine zindandaki (mühürlenmiş) ORİJİNAL soruyu geri yükle ve ona cevap verdir.
                user_name = self.pending_user_name
                user_text = self.pending_user_text
                context = self.pending_context
                
                # Zindanı temizle
                self.pending_user_name = ""
                self.pending_user_text = ""
                self.pending_context = ""
            # --------------------------------------------------------

            # Promptu İnşa Et
            messages = [{"role": "system", "content": f"Şu an konuştuğun kişi: {user_name}. {self.system_prompt}"}]
            if context:
                messages.append({"role": "system", "content": f"EKLENEN DUYU VERİSİ: {context}"})
                
            for role, content in self.memory:
                messages.append({"role": role, "content": content})
                
            messages.append({"role": "user", "content": user_text})

            raw_text = " ".join([m["content"] for m in messages])
            current_tokens = self._estimate_tokens(raw_text)
            
            # --- %66.6 İHLAL KONTROLÜ ---
            # Eğer sınır aşıldıysa, 1618 modundaysak ve az önce onaydan dönmediysek; asıl işlemi mühürle ve onay iste!
            if current_tokens >= self.threshold_limit and self.current_limit == self.token_base and not just_processed_approval:
                self.awaiting_token_approval = True
                
                # Orijinal Soruyu Zindana Mühürle
                self.pending_user_name = user_name
                self.pending_user_text = user_text
                self.pending_context = context
                
                ask_msg = f"{user_name}, Sohbet uzayacak token limitimi yükseltiyorum. onaylıyor musun?"
                sys.stdout.write(f"\r[ALİS] Sınır İhlali (%66.6 -> ~{current_tokens} Token). Onay soruluyor...\033[K\n")
                sys.stdout.flush()
                return ask_msg

            sys.stdout.write(f"\r[ALİS] Düşünüyor... (Bağlam: ~{current_tokens} Token, Limit: {self.current_limit})\033[K")
            sys.stdout.flush()
            
            try:
                # LLM İnfazı
                response = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=618, 
                    temperature=0.618, 
                    top_p=0.9
                )
                
                reply = response['choices'][0]['message']['content'].strip()
                
                # Sadece asıl orijinal soruyu ve alınan cevabı belleğe yaz. (Evet/Hayır meta konuşmaları belleğe girmez)
                self.memory.append(("user", user_text))
                self.memory.append(("assistant", reply))

                sys.stdout.write("\r\033[K") 
                sys.stdout.flush()
                return reply
                
            except Exception as e:
                logging.error(f"Sentez Hatası: {e}")
                return "Zihnimde matematiksel bir paradoks oluştu. Yanıtı derleyemiyorum."

    def see_and_think(self, user_name: str, user_text: str, frame: np.ndarray) -> str:
        """Gözden gelen veriyi metne çevirir, Qwen'e aktarır. Bayrak yarışı."""
        if frame is None or frame.size == 0:
            return self.think(user_name, user_text, context="Kamera verisi karanlık veya veri yok.")
            
        with self.lock:
            # 1. Moondream VRAM'e çekilir.
            self._load_vlm()
            
            if self.vlm is None:
                self._load_llm()
                return "Optik korteksim aktif değil."
                
            sys.stdout.write("\r[GÖRSEL ZEKA] Pikseller algılanıyor...\033[K\n")
            sys.stdout.flush()
            
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                
                enc_img = self.vlm.encode_image(pil_img)
                vision_desc = self.vlm.answer_question(enc_img, "Describe this image accurately and briefly in Turkish.", self.vlm_tokenizer)
            except Exception as e:
                logging.error(f"VLM Hatası: {e}")
                vision_desc = "Görüntü anlaşılamadı. Matematiksel hata."
                
            # 2. Moondream işi bitince VRAM'den acımasızca atılır.
            self._unload_vlm()
            
            # 3. Zihin (Qwen) geri yüklenir.
            self._load_llm()
            
        # Görsel veriyi bağlam olarak Qwen'e besle
        context = f"Kameranın Gördüğü Optik Durum: {vision_desc}"
        return self.think(user_name, user_text, context)

    def cleanup(self):
        """Sistemi uyku moduna alırken tüm VRAM'i zorla boşaltır."""
        self._unload_llm()
        self._unload_vlm()
        sys.stdout.write("\r[ZİHİN] VRAM tahliye edildi. Zihin karanlığa gömüldü.\033[K\n")
        sys.stdout.flush()

if __name__ == "__main__":
    mind = AliceMind()
    sys.stdout.write("[*] Zihin Çekirdeği Başlatıldı. 1618 Token Limiti Aktif.\n")