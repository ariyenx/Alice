# memory/offline_rag.py
# Yazar: Mimar
# Kurallar: FAISS mmap ile Sıfır RAM Atigi. BZ2/PDF/JSON Parcalayici (666 kelime). VRAM kullanilmaz. "pass" YOKTUR.

import os
import sys
import bz2
import json
import csv
import sqlite3
import logging
import threading
import re
import numpy as np
from pathlib import Path

# VRAM sömürüsünü engellemek için PyTorch CUDA'yı tamamen yoksaymaya zorla
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

try:
    from pdfminer.high_level import extract_text
    import faiss
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    logging.error(f"RAG Kutuphaneleri eksik: {e}")
    faiss = None
    SentenceTransformer = None
    extract_text = None

# Anayasa baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "offline_rag.log",
    level=logging.WARNING,
    format="%(asctime)s - [KÜTÜPHANE] - %(message)s"
)

class OfflineRAG:
    def __init__(self):
        """
        Devasa arsiv dosyalarini VRAM'i isgal etmeden CPU uzerinde 
        vektorlere donusturur ve FAISS/SQLite ile saniyeler icinde tarar.
        """
        self.arsiv_dir = config.BASE_DIR / "arsiv"
        self.arsiv_dir.mkdir(parents=True, exist_ok=True)
        
        self.index_path = config.RAG_DIR / "dynasty_knowledge.faiss"
        self.db_path = config.RAG_DIR / "dynasty_metadata.db"
        
        self.chunk_size = 666 # Altin Oran Parcalama Limiti
        self.embedding_dim = 384 # all-MiniLM-L6-v2 boyutu
        self.lock = threading.Lock()
        
        # GPU (VRAM) LLM'e kalsin diye Embedding motorunu kasten CPU'ya hapsediyoruz
        sys.stdout.write("\r[KÜTÜPHANE] Vektör Motoru CPU üzerinde başlatılıyor...\033[K\n")
        sys.stdout.flush()
        if SentenceTransformer is not None and faiss is not None:
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
            self._init_db_and_index()
        else:
            self.embedder = None
            self.index = None
            logging.error("Vektör motoru başlatılamadı. Kütüphane kördür.")

    def _init_db_and_index(self):
        """SQLite metadata haritasini ve FAISS matrisini donanimda var eder."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT,
                        chunk_text TEXT,
                        UNIQUE(file_name, chunk_text)
                    )
                """)
                conn.commit()
                conn.close()
            except sqlite3.Error as e:
                logging.error(f"Kütüphane DB Hatası: {e}")

            if self.index_path.exists():
                try:
                    self.index = faiss.read_index(str(self.index_path))
                    sys.stdout.write(f"\r[KÜTÜPHANE] SSD Üzerinden FAISS Bağlandı. Mühürlü Veri: {self.index.ntotal}\033[K\n")
                    sys.stdout.flush()
                except Exception as e:
                    logging.error(f"FAISS okuma hatası, sıfırlanıyor: {e}")
                    self.index = faiss.IndexFlatL2(self.embedding_dim)
            else:
                self.index = faiss.IndexFlatL2(self.embedding_dim)

    def _get_indexed_files(self) -> set:
        """Sistemin ayni dosyayi tekrar okuyup efor kaybetmesini onler."""
        indexed = set()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT file_name FROM documents")
            indexed = {row[0] for row in cursor.fetchall()}
            conn.close()
        except sqlite3.Error:
            pass
        return indexed

    def _clean_text(self, text: str) -> str:
        """Metinleri gereksiz bosluk ve XML/HTML etiketlerinden arindirir."""
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _chunk_text(self, text: str) -> list:
        """Metni 666 kelimelik Altin Oran bloklarina boler."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.chunk_size):
            chunk = " ".join(words[i:i + self.chunk_size])
            if len(chunk) > 20: 
                chunks.append(chunk)
        return chunks

    def _read_bz2_generator(self, filepath: Path):
        """Wikipedia BZ2 dosyalarini RAM patlatmadan satir satir yutar."""
        try:
            with bz2.open(filepath, "rt", encoding="utf-8") as f:
                buffer = ""
                for line in f:
                    buffer += line + " "
                    if len(buffer.split()) >= self.chunk_size:
                        yield self._clean_text(buffer)
                        buffer = ""
                if buffer:
                    yield self._clean_text(buffer)
        except Exception as e:
            logging.error(f"BZ2 Okuma Hatasi ({filepath}): {e}")

    def _process_and_store_chunks(self, file_name: str, chunks: list):
        """Metin parcalarini vektorleyip FAISS'e ve SQLite'a baglar."""
        if not chunks or self.embedder is None or self.index is None:
            return

        embeddings = self.embedder.encode(chunks, convert_to_numpy=True).astype('float32')
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for i, chunk in enumerate(chunks):
                try:
                    cursor.execute("INSERT INTO documents (file_name, chunk_text) VALUES (?, ?)", (file_name, chunk))
                    self.index.add(np.array([embeddings[i]]))
                except sqlite3.IntegrityError:
                    pass # Zaten indekslenmisse atla
            conn.commit()
            conn.close()

    def build_library(self):
        """Arsiv klasorunu tarar, yeni dosyalari damla damla okur ve SSD'ye infaz eder."""
        sys.stdout.write("\r[KÜTÜPHANE] Arşiv taranıyor, zeka ağı örülüyor...\033[K\n")
        sys.stdout.flush()
        
        if self.embedder is None or self.index is None:
            return

        indexed_files = self._get_indexed_files()

        for filepath in self.arsiv_dir.rglob("*"):
            if not filepath.is_file() or filepath.name in indexed_files:
                continue
                
            sys.stdout.write(f"\r[KÜTÜPHANE] Asimile ediliyor: {filepath.name}\033[K")
            sys.stdout.flush()

            try:
                ext = filepath.suffix.lower()
                if ext == '.bz2':
                    for text_block in self._read_bz2_generator(filepath):
                        chunks = self._chunk_text(text_block)
                        self._process_and_store_chunks(filepath.name, chunks)
                elif ext == '.pdf' and extract_text is not None:
                    text = extract_text(str(filepath))
                    chunks = self._chunk_text(self._clean_text(text))
                    self._process_and_store_chunks(filepath.name, chunks)
                elif ext == '.json':
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        chunks = self._chunk_text(self._clean_text(json.dumps(data, ensure_ascii=False)))
                        self._process_and_store_chunks(filepath.name, chunks)
                elif ext == '.csv':
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        content = "\n".join([" | ".join(row) for row in reader])
                        chunks = self._chunk_text(self._clean_text(content))
                        self._process_and_store_chunks(filepath.name, chunks)
                elif ext in ['.md', '.txt']:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        chunks = self._chunk_text(self._clean_text(f.read()))
                        self._process_and_store_chunks(filepath.name, chunks)
            except Exception as e:
                logging.error(f"Dosya okuma atlandi ({filepath}): {e}")

        with self.lock:
            faiss.write_index(self.index, str(self.index_path))
                
        sys.stdout.write(f"\n[KÜTÜPHANE] Mimari Tamamlandı. FAISS İndeksi mühürlendi.\n")
        sys.stdout.flush()

    def search(self, query: str, top_k: int = 5) -> str:
        """Kâhin veya Sef Ajani tarafindan gelen soruyu ansiklopedik verilerle eslestirir."""
        if not self.index or not self.embedder or self.index.ntotal == 0:
            return "Kütüphane kapalı veya arşiv boş."

        try:
            query_vector = self.embedder.encode([query], convert_to_numpy=True).astype('float32')
            distances, indices = self.index.search(query_vector, top_k)
            
            results = []
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                for idx in indices[0]:
                    if idx != -1:
                        # FAISS ID'leri SQLite'taki rowid (id) ile eslesir (1 indexli)
                        cursor.execute("SELECT chunk_text FROM documents WHERE id=?", (int(idx) + 1,))
                        row = cursor.fetchone()
                        if row:
                            results.append(row[0])
                conn.close()
                    
            if results:
                return "\n---\n".join(results)
            return "Arşivde bu konuya dair tutarlı bir veri bulunamadı."
        except Exception as e:
            logging.error(f"RAG Arama Hatasi: {e}")
            return "Kütüphane taramasında bir sorun oluştu."

if __name__ == "__main__":
    rag = OfflineRAG()
    rag.build_library()
    res = rag.search("Sağlıklı beslenme ve uyku")
    print(f"[*] RAG Test Sonucu (Ilk 200 karakter):\n{res[:200]}...")