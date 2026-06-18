# cognition/chef_agent.py
# Yazar: Mimar
# Kurallar: Hanedan Kan Grubu/Kilo uzerinden RAG destegiyle Diyet ve PDF/Excel Infazi. "pass" YOKTUR.

import os
import sys
import logging
import time
import threading
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
except ImportError:
    SimpleDocTemplate = None

# Anayasa baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

try:
    from memory.dynasty_db import DynastyVault
    from memory.offline_rag import OfflineRAG
except ImportError:
    DynastyVault = None
    OfflineRAG = None

logging.basicConfig(
    filename=config.LOG_DIR / "chef_agent.log",
    level=logging.WARNING,
    format="%(asctime)s - [ŞEF AJANI] - %(message)s"
)

class ChefHealthAgent:
    def __init__(self, vault: DynastyVault, rag: OfflineRAG):
        """
        Hanedan icin Kilo, Kan Grubu ve Uyku verilerini analiz edip
        RAG kutuphanesinden aldigi ilhamla diyet listeleri ve receteler cikarir.
        Uretilen dosyalar 33 dakika sonra sistem tarafindan acimasizca silinir.
        """
        self.vault = vault
        self.rag = rag
        self.temp_dir = config.TEMP_DIR
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        if SimpleDocTemplate is not None:
            self.styles = getSampleStyleSheet()
            self.title_style = ParagraphStyle(
                'CustomTitle',
                parent=self.styles['Heading1'],
                fontName='Helvetica-Bold',
                fontSize=16,
                spaceAfter=14
            )
            self.body_style = ParagraphStyle(
                'CustomBody',
                parent=self.styles['Normal'],
                fontName='Helvetica',
                fontSize=11,
                spaceAfter=10,
                leading=14
            )

    def _schedule_destruction(self, filepath: str):
        """33 Dakika İnfaz Kuralı: Dosya üretildikten tam 33 dk sonra SSD'den kazınır."""
        def destroyer():
            time.sleep(config.FILE_DESTROY_MIN * 60)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    sys.stdout.write(f"\r[SERAF] {Path(filepath).name} süresi dolduğu için imha edildi.\033[K\n")
                    sys.stdout.flush()
                except OSError:
                    pass
        threading.Thread(target=destroyer, daemon=True).start()

    def _clean_tr(self, text: str) -> str:
        """ReportLab Helvetica fontu Türkce karakterleri (ş,ğ,ı vb) desteklemez. 
        Sisteme harici TTF dosyasi bagimsizligi saglamak icin guvenli ASCII haritasina cevirir."""
        char_map = {'ş':'s', 'Ş':'S', 'ğ':'g', 'Ğ':'G', 'ı':'i', 'İ':'I', 'ç':'c', 'Ç':'C', 'ö':'o', 'Ö':'O', 'ü':'u', 'Ü':'U'}
        for tr_char, en_char in char_map.items():
            text = text.replace(tr_char, en_char)
        return text

    def _export_pdf(self, title: str, content_text: str, filename: str) -> str:
        """ReportLab ile içerigi PDF'e isler ve Temp klasorune atar."""
        if SimpleDocTemplate is None:
            logging.error("ReportLab kütüphanesi eksik.")
            return ""
            
        file_path = self.temp_dir / filename
        
        try:
            doc = SimpleDocTemplate(str(file_path), pagesize=A4)
            elements = []
            
            clean_title = self._clean_tr(title)
            elements.append(Paragraph(clean_title, self.title_style))
            elements.append(Spacer(1, 12))
            
            for line in content_text.split('\n'):
                if line.strip():
                    clean_line = self._clean_tr(line)
                    elements.append(Paragraph(clean_line, self.body_style))
                    elements.append(Spacer(1, 6))
            
            # Uyari damgasi
            elements.append(Spacer(1, 24))
            elements.append(Paragraph("UYARI: Bu belge 33 dakika icinde otonom olarak imha edilecektir.", self.body_style))
            
            doc.build(elements)
            self._schedule_destruction(str(file_path))
            sys.stdout.write(f"\r[ŞEF AJANI] PDF Mühürlendi (33dk ömrü var): {filename}\033[K\n")
            sys.stdout.flush()
            return str(file_path)
        except Exception as e:
            logging.error(f"PDF Uretim Hatasi: {e}")
            return ""

    def _export_excel(self, content_text: str, filename: str) -> str:
        """Icerigi satirlar halinde Excel formatina (Pandas ile) cevirir."""
        if pd is None:
            logging.error("Pandas kütüphanesi eksik.")
            return ""
            
        file_path = self.temp_dir / filename
        try:
            lines = [line for line in content_text.split('\n') if line.strip()]
            df = pd.DataFrame({"İçerik Tablosu": lines})
            df.to_excel(str(file_path), index=False)
            self._schedule_destruction(str(file_path))
            sys.stdout.write(f"\r[ŞEF AJANI] Excel Mühürlendi (33dk ömrü var): {filename}\033[K\n")
            sys.stdout.flush()
            return str(file_path)
        except Exception as e:
            logging.error(f"Excel Uretim Hatasi: {e}")
            return ""

    def generate_diet_plan(self, member_name: str, llm_callback, format_type: str = "pdf") -> str:
        """
        Hanedan uyesinin Kan Grubu ve Kilosunu kasadan ceker. 
        RAG'dan diyet arar ve Zihne (LLM'e) emir gonderip donusumu saglar.
        """
        if not self.vault or not self.rag:
            return "Hafıza Kasası veya Kütüphane bağlı değil."
            
        profile = self.vault.get_member_profile(member_name)
        if not profile:
            return f"{member_name} için Hanedan profil verisi bulunamadı."
            
        blood_type = profile.get("blood_type", "Bilinmiyor")
        weight = profile.get("weight", "Bilinmiyor")
        
        sys.stdout.write(f"\r[ŞEF AJANI] {member_name} ({weight}kg, {blood_type} Kan) icin arşiv taranıyor...\033[K\n")
        sys.stdout.flush()
        
        query = f"{blood_type} kan grubu beslenme diyet kilo verme sağlıklı gıdalar"
        rag_context = self.rag.search(query, top_k=5)
        
        system_prompt = (
            f"Sen Hanedanın Aşçısı ve Sağlık Danışmanısın. Üyenin adı: {member_name}. "
            f"Kan Grubu: {blood_type}, Kilosu: {weight} kg.\n"
            f"Arşiv Kütüphanesi Verisi: {rag_context}\n\n"
            f"Görev: Bu verilere göre 7 günlük kısa, net ve bilimsel bir diyet listesi oluştur. "
            f"Sadece listeyi ve rasyonel kısa bir tavsiyeyi yaz. Markdown, yıldız veya kalınlaştırma kullanma."
        )
        
        sys.stdout.write("\r[ZİHİN] LLM diyeti sentezliyor...\033[K\n")
        sys.stdout.flush()
        
        diet_text = llm_callback(system_prompt)
        timestamp = int(time.time())
        filename_base = f"Diyet_{member_name}_{timestamp}"
        
        if format_type.lower() == "excel":
            filepath = self._export_excel(diet_text, f"{filename_base}.xlsx")
            ext = "Excel"
        else:
            filepath = self._export_pdf(f"Alice HIS - {member_name} Beslenme Plani", diet_text, f"{filename_base}.pdf")
            ext = "PDF"
            
        if filepath:
            return f"Beslenme programınız {ext} olarak hazırlandı. QR dosya ağından erişebilirsiniz."
        return "Dosya oluşturulurken donanım yazma hatası meydana geldi."

    def generate_recipe(self, food_name: str, llm_callback, format_type: str = "pdf") -> str:
        """Kutuphaneden yemek yapma tekniklerini cekip recete PDF/Excel cikarir."""
        if not self.rag:
            return "Kütüphane modülü kapalı."
            
        sys.stdout.write(f"\r[ŞEF AJANI] '{food_name}' için arşiv taranıyor...\033[K\n")
        sys.stdout.flush()
        
        query = f"{food_name} nasıl yapılır, tarif, malzemeler, püf noktaları"
        rag_context = self.rag.search(query, top_k=5)
        
        system_prompt = (
            f"Sen usta bir Şefsin. İstenen Yemek: {food_name}.\n"
            f"Arşiv Verisi: {rag_context}\n\n"
            f"Görev: Malzemeleri liste halinde ver. Yapılışını adım adım kısa anlat. "
            f"Sadece metin olarak yanıtla, markdown kullanma."
        )
        
        recipe_text = llm_callback(system_prompt)
        timestamp = int(time.time())
        filename_base = f"Recete_{food_name.replace(' ', '_')}_{timestamp}"
        
        if format_type.lower() == "excel":
            filepath = self._export_excel(recipe_text, f"{filename_base}.xlsx")
            ext = "Excel"
        else:
            filepath = self._export_pdf(f"Özel Reçete: {food_name}", recipe_text, f"{filename_base}.pdf")
            ext = "PDF"
            
        if filepath:
            return f"Reçeteniz {ext} olarak mühürlendi. QR ağından ulaşabilirsiniz."
        return "Reçete oluşturulamadı."

if __name__ == "__main__":
    def dummy_llm(prompt):
        return "Pazartesi: Yulaf, Salata.\nSalı: Et sote.\n(LLM henüz entegre değil, bu bir test yanıtıdır.)"
    
    print("[*] Şef Ajanı Test Ediliyor...")
    chef = ChefHealthAgent(vault=None, rag=None)
    res = chef.generate_recipe("Menemen", dummy_llm, "excel")
    print(res)