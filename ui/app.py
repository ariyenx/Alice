# ui/app.py
# Yazar: Mimar
# Kurallar: Çift Tık Pusu Modu, Tam Kapsamlı Klavye, Terminal Temizleme, Otonom Wi-Fi, Merkez Kill-Switch. SIFIR "pass".

import os
import sys
import time
import wave
import subprocess
import datetime
from pathlib import Path

try:
    import pyaudio
    import psutil
    import cv2
    import qrcode
    import numpy as np
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                   QLabel, QPushButton, QStackedWidget, QFrame, QLineEdit, QTextBrowser,
                                   QGridLayout, QSizeGrip, QSizePolicy, QSlider, QListWidget)
    from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QPoint, QEvent, QEasingCurve, QThread, Signal
    from PySide6.QtGui import QColor, QPainter, QPolygonF, QFont, QPixmap, QImage, QPen, QBrush
except ImportError as e:
    sys.exit(f"[KRİTİK HATA] UI Kütüphaneleri eksik. Lütfen kurun: {e}")

sys.path.append(str(Path(__file__).resolve().parent.parent))
try:
    import config
except ImportError as e:
    sys.exit(f"[KRİTİK HATA] Anayasa (config.py) bulunamadı: {e}")

TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# --- ASENKRON AĞ TARAYICI ---
class WifiScannerThread(QThread):
    networks_found = Signal(list)
    error_occurred = Signal(str)
    def run(self):
        try:
            subprocess.run(["nmcli", "dev", "wifi", "rescan"], capture_output=True, timeout=5)
            result = subprocess.run(["nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.error_occurred.emit("Ağ taraması başarısız (Wi-Fi kapalı).")
                return
            nets = {}
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.rsplit(':', 1)
                    if len(parts) == 2 and parts[0].strip():
                        ssid = parts[0].strip(); sig = int(parts[1].strip())
                        if ssid not in nets or sig > nets[ssid]: nets[ssid] = sig
            sorted_nets = [f"{k} (Güç: %{v})" for k, v in sorted(nets.items(), key=lambda item: item[1], reverse=True)]
            self.networks_found.emit(sorted_nets)
        except Exception as e:
            self.error_occurred.emit(f"Sistem Hatası: {str(e)[:30]}")

class WifiConnectThread(QThread):
    connection_result = Signal(str, bool)
    def __init__(self, ssid, password): super().__init__(); self.ssid = ssid; self.password = password
    def run(self):
        try:
            cmd = ["nmcli", "dev", "wifi", "connect", self.ssid]
            if self.password: cmd.extend(["password", self.password])
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0: self.connection_result.emit(f"✅ BAŞARILI: '{self.ssid}' AES kasasına kaydedildi.", True)
            else: self.connection_result.emit(f"❌ BAĞLANTI REDDEDİLDİ: Şifre hatalı veya ağ uzakta.", False)
        except Exception as e: self.connection_result.emit(f"❌ SİSTEM HATASI: {str(e)[:30]}", False)

# --- ASENKRON SES KAYDEDİCİ ---
class VoiceRecordThread(QThread):
    record_finished = Signal(str, bool)
    def __init__(self, name): super().__init__(); self.name = name; self.output_path = f"/tmp/enroll_voice_{self.name}.wav"
    def run(self):
        try:
            chunk = 1024; format_type = pyaudio.paInt16; channels = 1; rate = 16000; record_seconds = 5
            p = pyaudio.PyAudio(); stream = p.open(format=format_type, channels=channels, rate=rate, input=True, frames_per_buffer=chunk)
            frames = [stream.read(chunk, exception_on_overflow=False) for _ in range(0, int(rate / chunk * record_seconds))]
            stream.stop_stream(); stream.close(); p.terminate()
            wf = wave.open(self.output_path, 'wb'); wf.setnchannels(channels); wf.setsampwidth(p.get_sample_size(format_type)); wf.setframerate(rate)
            wf.writeframes(b''.join(frames)); wf.close()
            self.record_finished.emit(self.output_path, True)
        except Exception as e:
            self.record_finished.emit(str(e), False)

# --- TAM KAPSAMLI SÜRÜKLENEBİLİR KLAVYE (ÖZEL KARAKTERLİ) ---
class Klavye(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint); self.setAttribute(Qt.WA_TranslucentBackground); self.setMinimumSize(500, 220); self.resize(550, 260)
        self.target_input = None; self.is_caps = False; self.is_shift = False; self.drag_pos = None; self.layout = QVBoxLayout(self); self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(0)
        self.frame = QFrame(); self.frame.setStyleSheet("background-color: rgba(10, 10, 15, 0.98); border: 1px solid #00E5FF; border-radius: 8px;"); self.frame_layout = QVBoxLayout(self.frame); self.frame_layout.setContentsMargins(5, 5, 5, 5)
        
        header_layout = QHBoxLayout()
        self.header = QLabel("⌨️ SİBER KLAVYE (Sürükle | Boyutlandır)")
        self.header.setStyleSheet("color: #D4AF37; font-size: 11px; font-weight: bold; border-bottom: 1px solid #333; padding: 5px;")
        header_layout.addWidget(self.header)
        close_btn = QPushButton("✖"); close_btn.setFixedSize(25, 25); close_btn.setStyleSheet("QPushButton { color: #FF0000; font-weight: bold; background: transparent; border: none; font-size: 14px;} QPushButton:hover { background: rgba(255,0,0,0.1); }")
        close_btn.clicked.connect(self.hide); header_layout.addWidget(close_btn)
        self.frame_layout.addLayout(header_layout)
        
        self.keys_layout = QGridLayout(); self.keys_layout.setSpacing(3)
        
        self.kb_base = [['1','2','3','4','5','6','7','8','9','0','-','=','/'],['q','w','e','r','t','y','u','i','o','p','ğ','ü'],['a','s','d','f','g','h','j','k','l','ş','i'],['z','x','c','v','b','n','m','ö','ç',',','.']]
        self.kb_shift = [['!','\'','^','+','%','&','/','(',')','=','?','_','-'],['Q','W','E','R','T','Y','U','I','O','P','Ğ','Ü'],['A','S','D','F','G','H','J','K','L','Ş','İ'],['Z','X','C','V','B','N','M','Ö','Ç','<','>']]
        
        self._build_keys(); self.frame_layout.addLayout(self.keys_layout); self.layout.addWidget(self.frame)
        grip_layout = QHBoxLayout(); grip_layout.addStretch(); self.grip = QSizeGrip(self); self.grip.setFixedSize(20, 20); self.grip.setStyleSheet("background: transparent;"); grip_layout.addWidget(self.grip); self.layout.addLayout(grip_layout)

    def _build_keys(self):
        while self.keys_layout.count():
            item = self.keys_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        layout_to_use = self.kb_shift if self.is_shift else self.kb_base

        for r_idx, row in enumerate(layout_to_use):
            for c_idx, key in enumerate(row):
                if self.is_caps and not self.is_shift and key.isalpha():
                    display_key = key.upper()
                elif self.is_caps and self.is_shift and key.isalpha():
                    display_key = key.lower()
                else:
                    display_key = key

                btn = QPushButton(display_key)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); btn.setFocusPolicy(Qt.NoFocus)
                btn.setStyleSheet("QPushButton { background-color: #1a1a1a; color: #ddd; border: 1px solid #333; border-radius: 3px; font-size: 13px; font-weight: bold; padding: 5px; } QPushButton:pressed { background-color: #00E5FF; color: #000; }")
                btn.clicked.connect(lambda checked, k=display_key: self._send_key(k)); self.keys_layout.addWidget(btn, r_idx, c_idx)
        
        bottom_row = len(layout_to_use)
        shift_btn = QPushButton("Shift"); shift_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); shift_btn.setFocusPolicy(Qt.NoFocus); shift_btn.setStyleSheet(f"QPushButton {{ background-color: {'rgba(0,229,255,0.2)' if self.is_shift else '#1a1a1a'}; color: {'#00E5FF' if self.is_shift else '#ddd'}; border: 1px solid {'#00E5FF' if self.is_shift else '#333'}; font-weight: bold; border-radius: 3px; }}"); shift_btn.clicked.connect(self._toggle_shift); self.keys_layout.addWidget(shift_btn, bottom_row, 0, 1, 2)
        caps_btn = QPushButton("Caps"); caps_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); caps_btn.setFocusPolicy(Qt.NoFocus); caps_btn.setStyleSheet(f"QPushButton {{ background-color: {'rgba(0,229,255,0.2)' if self.is_caps else '#1a1a1a'}; color: {'#00E5FF' if self.is_caps else '#ddd'}; border: 1px solid {'#00E5FF' if self.is_caps else '#333'}; font-weight: bold; border-radius: 3px; }}"); caps_btn.clicked.connect(self._toggle_caps); self.keys_layout.addWidget(caps_btn, bottom_row, 2, 1, 2)
        space_btn = QPushButton("Boşluk"); space_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); space_btn.setFocusPolicy(Qt.NoFocus); space_btn.setStyleSheet("QPushButton { background-color: #1a1a1a; color: #ddd; border: 1px solid #333; font-weight: bold; border-radius: 3px; } QPushButton:pressed { background-color: #00E5FF; color: #000; }"); space_btn.clicked.connect(lambda: self._send_key(" ")); self.keys_layout.addWidget(space_btn, bottom_row, 4, 1, 4)
        sil_btn = QPushButton("Sil"); sil_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); sil_btn.setFocusPolicy(Qt.NoFocus); sil_btn.setStyleSheet("QPushButton { background-color: rgba(255,0,0,0.1); color: #FF0000; border: 1px solid #FF0000; font-weight: bold; border-radius: 3px; } QPushButton:pressed { background-color: #FF0000; color: #000; }"); sil_btn.clicked.connect(lambda: self._send_key("BACKSPACE")); self.keys_layout.addWidget(sil_btn, bottom_row, 8, 1, 2)
        enter_btn = QPushButton("Enter"); enter_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); enter_btn.setFocusPolicy(Qt.NoFocus); enter_btn.setStyleSheet("QPushButton { background-color: rgba(0,229,255,0.1); color: #00E5FF; border: 1px solid #00E5FF; font-weight: bold; border-radius: 3px; } QPushButton:pressed { background-color: #00E5FF; color: #000; }"); enter_btn.clicked.connect(lambda: self._send_key("ENTER")); self.keys_layout.addWidget(enter_btn, bottom_row, 10, 1, 2)

    def _toggle_shift(self): self.is_shift = not self.is_shift; self._build_keys()
    def _toggle_caps(self): self.is_caps = not self.is_caps; self._build_keys()
    def _send_key(self, key):
        if not self.target_input: return
        if key == "BACKSPACE": self.target_input.backspace()
        elif key == "ENTER": self.target_input.returnPressed.emit(); self.hide()
        else: self.target_input.insert(key); self.is_shift = False; self._build_keys()
    def set_target(self, line_edit): self.target_input = line_edit
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() < 40: self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept()
    def mouseMoveEvent(self, event):
        if self.drag_pos is not None and event.buttons() == Qt.LeftButton: self.move(event.globalPosition().toPoint() - self.drag_pos)
    def mouseReleaseEvent(self, event): self.drag_pos = None

# --- ZİHİN KORTEKSİ ---
class AliceTriangle(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(300, 300); self.mode = "sleep"; self.scale_factor = 1.0; self.pulse_dir = 1; self.rotation = 0; self.timer = QTimer(self); self.timer.timeout.connect(self.animate); self.timer.start(50)
    def set_mode(self, mode): self.mode = mode
    def animate(self):
        if self.mode == "sleep":
            self.scale_factor += 0.005 * self.pulse_dir
            if self.scale_factor >= 1.03 or self.scale_factor <= 0.97: self.pulse_dir *= -1
        elif self.mode == "speak":
            self.scale_factor += 0.02 * self.pulse_dir
            if self.scale_factor >= 1.08 or self.scale_factor <= 0.95: self.pulse_dir *= -1
        elif self.mode == "think": self.rotation = (self.rotation + 2) % 360; self.scale_factor = 1.0
        else: self.scale_factor = 1.0
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); cx, cy = self.width() / 2, self.height() / 2; side = 120 * self.scale_factor
        points = [QPoint(int(cx - side), int(cy - side * 0.577)), QPoint(int(cx + side), int(cy - side * 0.577)), QPoint(int(cx), int(cy + side * 1.154))]; poly = QPolygonF([p.toPointF() for p in points])
        color = QColor(0, 229, 255) if self.mode != "sleep" else QColor(68, 68, 68)
        if self.mode == "think": color = QColor(212, 175, 55)
        elif self.mode == "speak": color = QColor(255, 255, 255)
        painter.translate(cx, cy); 
        if self.mode == "think": painter.rotate(self.rotation)
        painter.translate(-cx, -cy); pen = QPen(color); pen.setWidth(2 if self.mode != "speak" else 4); painter.setPen(pen); painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 15))); painter.drawPolygon(poly)

# --- ANA İŞLETİM SİSTEMİ ARAYÜZÜ ---
class AliceEdgeOS(QMainWindow):
    def __init__(self, orchestrator=None):
        super().__init__()
        self.orc = orchestrator
        self.setWindowTitle("Alice Edge OS V10.0 (Kusursuz İnfaz)")
        self.setFixedSize(1024, 600)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setStyleSheet("background-color: #030303; color: #E0E0E0; font-family: 'Segoe UI', Tahoma, sans-serif;")
        
        self.terminal_logs = []
        self.goz_history = []
        self.active_camera_process = False
        self.active_tani_name = ""
        self.telemetry_error_logged = False
        
        self.keyboard = Klavye(self)
        self.keyboard.hide()
        
        self._build_ui()
        self._start_system_loops()
        
        # Pusu Modu Zamanlayıcısı
        self.is_screensaver_active = False
        self.idle_timeout_ms = 60000 
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.activate_screensaver)
        self.idle_timer.start(self.idle_timeout_ms)
        
        QApplication.instance().installEventFilter(self)
        self.log_terminal("sys", "Alice Edge AI OS Çekirdek Başlatıldı. Çift Tık Pusu devrede.")

    def mouseDoubleClickEvent(self, event):
        """Çift Tıklama ile anında Pusu (Ekran Koruyucu) Moduna Geçiş"""
        if event.button() == Qt.LeftButton:
            self.activate_screensaver()
            self.log_terminal("sys", "Çift tıklama ile manuel Pusu moduna geçildi.")
        super().mouseDoubleClickEvent(event)

    def _build_ui(self):
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget); self.main_layout = QGridLayout(self.central_widget); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)

        self.top_bar = QFrame(); self.top_bar.setFixedHeight(30); self.top_bar.setStyleSheet("background: #0a0a0f; border-bottom: 1px solid #222;"); top_layout = QHBoxLayout(self.top_bar); top_layout.setContentsMargins(15, 0, 15, 0)
        self.lbl_location = QLabel("📍 Yalıkavak, Türkiye"); self.lbl_date = QLabel(""); self.lbl_time = QLabel(""); self.lbl_time.setStyleSheet("color: #FFF; font-weight: bold;"); self.lbl_alarm = QLabel("🔔 Alarm: Yok"); self.lbl_alarm.setStyleSheet("color: #D4AF37; font-weight: bold; margin-right: 15px; border-right: 1px solid #333; padding-right: 15px;"); self.lbl_alarm.hide()
        for lbl in [self.lbl_location, self.lbl_date, self.lbl_time]: lbl.setStyleSheet(lbl.styleSheet() + " color: #E0E0E0; font-size: 11px;"); top_layout.addWidget(lbl); if lbl != self.lbl_time: top_layout.addWidget(QLabel("  |  ", styleSheet="color: #444;"))
        top_layout.addStretch(); top_layout.addWidget(self.lbl_alarm)
        self.btn_top_wifi = QPushButton("📶 Ağ Aranıyor..."); self.btn_top_wifi.setStyleSheet("QPushButton { background: transparent; color: #00E5FF; font-weight: bold; border: none; font-size: 11px; padding: 4px; } QPushButton:hover { color: #FFF; }"); self.btn_top_wifi.setCursor(Qt.PointingHandCursor); self.btn_top_wifi.clicked.connect(lambda: self.nav_to(7)); top_layout.addWidget(self.btn_top_wifi); self.main_layout.addWidget(self.top_bar, 0, 0, 1, 3)

        self.left_bar = QFrame(); self.left_bar.setFixedWidth(85); self.left_bar.setStyleSheet("background: #050505; border-right: 1px solid #1a1a1a;"); left_layout = QVBoxLayout(self.left_bar); left_layout.setContentsMargins(10, 15, 10, 15); left_layout.setSpacing(15)
        self.nav_btns = []; menus = [("💠\nMerkez", 0), ("🛡️\nGüvenli", 1), ("⚕️\nSağlık", 2), ("🧬\nHanedan", 3), ("⚙️\nAyarlar", 4), ("⏻\nGüç", 5)]
        for txt, idx in menus: btn = QPushButton(txt); btn.setFixedSize(65, 60); btn.setStyleSheet("QPushButton { background: transparent; color: #777; border: 1px solid transparent; border-radius: 8px; font-size: 10px; font-weight: bold; } QPushButton:checked { color: #00E5FF; border: 1px solid rgba(0,229,255,0.3); background: rgba(0,229,255,0.05); }"); btn.setCheckable(True); btn.clicked.connect(lambda ch, i=idx: self.nav_to(i)); left_layout.addWidget(btn); self.nav_btns.append(btn)
        left_layout.addStretch(); self.btn_mudahale = QPushButton("🛑\nMüdahale"); self.btn_mudahale.setFixedSize(65, 60); self.btn_mudahale.setStyleSheet("QPushButton { color: #FF0000; font-size: 10px; font-weight: bold; background: rgba(255,0,0,0.05); border: 1px solid rgba(255,0,0,0.2); border-radius: 8px; } QPushButton:hover { background: rgba(255,0,0,0.2); border-color: #FF0000; }"); self.btn_mudahale.clicked.connect(self.execute_barge_in); left_layout.addWidget(self.btn_mudahale); self.main_layout.addWidget(self.left_bar, 1, 0, 1, 1)

        self.stack = QStackedWidget(); self.main_layout.addWidget(self.stack, 1, 1, 1, 1)
        self.page_merkez = QWidget(); m_layout = QVBoxLayout(self.page_merkez); m_layout.setAlignment(Qt.AlignCenter); self.alice = AliceTriangle(); m_layout.addWidget(self.alice)
        self.lbl_status = QLabel("ALİCE PUSUDA BEKLİYOR"); self.lbl_status.setStyleSheet("color: #666; font-size: 12px; letter-spacing: 5px; margin-top: 20px; font-weight:bold;"); self.lbl_status.setAlignment(Qt.AlignCenter); m_layout.addWidget(self.lbl_status); self.stack.addWidget(self.page_merkez)

        # PANELLER DOLDURULDU
        self.stack.addWidget(self.create_panel("🛡️ GÜVENLİ PROTOKOLÜ", self.build_guvenlik())) # 1
        self.stack.addWidget(self.create_panel("⚕️ SAĞLIK PROTOKOLÜ", self.build_saglik())) # 2
        self.stack.addWidget(self.create_panel("🧬 HANEDAN TANI PROTOKOLÜ", self.build_hanedan())) # 3
        self.stack.addWidget(self.create_panel("⚙️ DONANIM AYARLARI", self.build_ayarlar())) # 4
        self.stack.addWidget(self.create_panel("⏻ GÜÇ YÖNETİMİ", self.build_guc())) # 5
        self.stack.addWidget(self.create_panel("📊 DERİN SİSTEM ANALİZİ", self.build_derin_sistem())) # 6
        self.stack.addWidget(self.create_panel("📶 SİBER AĞ YÖNETİMİ (Wi-Fi)", self.build_wifi_panel())) # 7

        self.right_bar = QFrame(); self.right_bar.setFixedWidth(280); self.right_bar.setStyleSheet("background: #050505; border-left: 1px solid #222;"); right_layout = QVBoxLayout(self.right_bar); right_layout.setContentsMargins(15, 15, 15, 15); right_layout.setSpacing(10)
        right_layout.addWidget(QLabel("<span style='color:#777; font-size:11px; font-weight:bold; letter-spacing:1px;'>👁️ GÖZ</span>")); self.lbl_goz_list = QLabel("Kamera Taranıyor..."); self.lbl_goz_list.setStyleSheet("font-family: 'Courier New'; font-size: 10px; color: #aaa; line-height: 1.5;"); right_layout.addWidget(self.lbl_goz_list)
        right_layout.addWidget(QLabel("<span style='color:#777; font-size:11px; font-weight:bold; letter-spacing:1px; margin-top:10px;'>🖥️ SİSTEM</span>")); self.btn_sys_card = QPushButton(); self.btn_sys_card.setStyleSheet("QPushButton { background: rgba(0,0,0,0.5); border: 1px solid #333; border-radius: 8px; text-align: left; padding: 10px; font-family: 'Courier New'; font-size: 11px; color: #ddd; line-height: 1.5;} QPushButton:hover { border-color: #D4AF37; }"); self.btn_sys_card.clicked.connect(lambda: self.nav_to(6)); right_layout.addWidget(self.btn_sys_card)
        right_layout.addSpacing(10); self.fixed_vizor = QLabel("<div style='font-size:24px; margin-bottom:5px;'>🔳</div>BEKLEMEDE"); self.fixed_vizor.setAlignment(Qt.AlignCenter); self.fixed_vizor.setFixedSize(250, 160); self.fixed_vizor.setStyleSheet("border: 1px dashed #333; color: #444; border-radius: 8px; font-size: 12px; font-weight:bold; letter-spacing: 2px; background: #000; padding:10px; box-sizing:border-box;"); right_layout.addWidget(self.fixed_vizor)
        right_layout.addStretch(); right_layout.addWidget(QLabel("<span style='color:#555; font-size:9px; font-weight:bold;'>AKTİF DOSYALAR (7s Kalan)</span>")); self.lbl_files = QLabel("📄 Diyet_Aryen_7G.pdf\n📄 Rapor_Rana_Uyku.pdf"); self.lbl_files.setStyleSheet("color: #00E5FF; font-size: 10px; line-height: 1.5;"); right_layout.addWidget(self.lbl_files); self.main_layout.addWidget(self.right_bar, 1, 2, 1, 1)

        self.bottom_bar = QFrame(); self.bottom_bar.setFixedHeight(35); self.bottom_bar.setStyleSheet("background: #0A0A0F; border-top: 1px solid #222;"); bot_layout = QHBoxLayout(self.bottom_bar); bot_layout.setContentsMargins(15, 0, 15, 0)
        self.btn_term_toggle = QPushButton("[ >_ TERMİNAL ]"); self.btn_term_toggle.setStyleSheet("background: transparent; color: #777; font-family: 'Courier New'; font-size: 12px; font-weight: bold; border: none;"); self.btn_term_toggle.clicked.connect(self.toggle_terminal); bot_layout.addWidget(self.btn_term_toggle); bot_layout.addStretch(); bot_layout.addWidget(QLabel("<span style='color:#444; font-size:9px; font-weight:bold;'>ALICE EDGE AI OS V10.0</span>")); self.main_layout.addWidget(self.bottom_bar, 2, 0, 1, 3)

        self.term_panel = QFrame(self.central_widget); self.term_panel.setGeometry(85, 600, 1024 - 85 - 280, 260); self.term_panel.setStyleSheet("background: rgba(4,4,6,0.98); border-top: 1px solid #00E5FF; border-right: 1px solid #222; border-top-right-radius: 10px;"); term_layout = QVBoxLayout(self.term_panel); term_layout.setContentsMargins(0, 0, 0, 0); term_layout.setSpacing(0)
        
        # --- ARAMA VE TEMİZLEME KUTUSU EKLENDİ ---
        search_box = QFrame(); search_box.setStyleSheet("background: #000; border-bottom: 1px solid #222; padding: 8px;"); s_layout = QHBoxLayout(search_box); s_layout.setContentsMargins(0,0,0,0)
        self.term_search = QLineEdit(); self.term_search.setPlaceholderText("🔍 Loglarda Ara (Anında Filtrele)..."); self.term_search.setStyleSheet("background: transparent; color: #D4AF37; border: none; font-family: 'Courier New'; font-size: 11px;"); self.term_search.textChanged.connect(self.render_terminal); self.term_search.installEventFilter(self); s_layout.addWidget(self.term_search)
        
        self.btn_clear_term = QPushButton("🗑️ TEMİZLE")
        self.btn_clear_term.setStyleSheet("background: rgba(255,0,0,0.1); color: #FF0000; border: 1px solid #FF0000; border-radius: 3px; font-weight: bold; font-family: 'Courier New'; font-size: 10px; padding: 2px 8px;")
        self.btn_clear_term.clicked.connect(self.clear_terminal)
        s_layout.addWidget(self.btn_clear_term)
        term_layout.addWidget(search_box)

        self.term_text = QTextBrowser(); self.term_text.setReadOnly(True); self.term_text.setStyleSheet("background: transparent; border: none; font-family: 'Courier New'; font-size: 11px; padding: 10px;"); term_layout.addWidget(self.term_text)
        
        cmd_box = QFrame(); cmd_box.setStyleSheet("background: #000; border-top: 1px solid #333; padding: 8px;"); c_layout = QHBoxLayout(cmd_box); c_layout.setContentsMargins(0,0,0,0); c_layout.addWidget(QLabel("<span style='color:#D4AF37; font-family:Courier New; font-weight:bold;'>~</span>")); self.term_input = QLineEdit(); self.term_input.setPlaceholderText("Emir girin..."); self.term_input.setStyleSheet("background: transparent; color: #00FF00; border: none; font-family: 'Courier New'; font-size: 11px;"); self.term_input.installEventFilter(self); self.term_input.returnPressed.connect(self.process_command); c_layout.addWidget(self.term_input); term_layout.addWidget(cmd_box)
        
        self.anim_term = QPropertyAnimation(self.term_panel, b"geometry"); self.anim_term.setDuration(300); self.anim_term.setEasingCurve(QEasingCurve.OutCubic); self.is_term_open = False
        self.nav_to(0)

    # --- PUSU MODU YÖNETİMİ ---
    def reset_idle_timer(self):
        self.idle_timer.start(self.idle_timeout_ms)
        if self.is_screensaver_active:
            self.deactivate_screensaver()

    def activate_screensaver(self):
        if self.is_screensaver_active: return
        self.is_screensaver_active = True
        self.top_bar.hide(); self.left_bar.hide(); self.right_bar.hide(); self.bottom_bar.hide()
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == 0)
        self.stack.setCurrentIndex(0)
        if self.is_term_open: self.toggle_terminal()
        if self.keyboard.isVisible(): self.keyboard.hide()
        self.lbl_status.hide(); self.alice.set_mode("sleep")

    def deactivate_screensaver(self):
        if not self.is_screensaver_active: return
        self.is_screensaver_active = False
        self.top_bar.show(); self.left_bar.show(); self.right_bar.show(); self.bottom_bar.show(); self.lbl_status.show()

    def eventFilter(self, source, event):
        if event.type() in [QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.TouchBegin, QEvent.KeyPress]:
            self.reset_idle_timer()
            
        if event.type() == QEvent.MouseButtonPress:
            if source in [getattr(self, 'term_search', None), getattr(self, 'term_input', None), getattr(self, 'wifi_pwd_input', None)]:
                self.keyboard.set_target(source)
                if not self.keyboard.isVisible():
                    x_offset = 450 if source != getattr(self, 'wifi_pwd_input', None) else 480
                    y_offset = 150 if source != getattr(self, 'wifi_pwd_input', None) else 50
                    self.keyboard.move(self.geometry().x() + x_offset, self.geometry().y() + y_offset); self.keyboard.show()
        return super().eventFilter(source, event)

    # --- EKSİKSİZ PANEL İNŞALARI ---
    def create_panel(self, title, content_widget):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(30, 30, 30, 30); header_layout = QHBoxLayout(); header = QLabel(title); header.setStyleSheet("color: #D4AF37; font-size: 14px; font-weight: bold; letter-spacing: 2px;"); close = QPushButton("✕"); close.setFixedSize(20, 20); close.setStyleSheet("QPushButton { color: #888; font-weight: bold; border: none; background: transparent; font-size: 16px; } QPushButton:hover { color: #FF0000; }"); close.clicked.connect(lambda: self.nav_to(0)); header_layout.addWidget(header); header_layout.addStretch(); header_layout.addWidget(close); l.addLayout(header_layout); line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #333;"); l.addWidget(line); l.addWidget(content_widget); l.addStretch(); return w

    def build_wifi_panel(self):
        w = QWidget(); l = QVBoxLayout(w); top_h = QHBoxLayout(); top_h.addWidget(QLabel("<span style='color:#888; font-size:12px;'>Çevredeki Ağlar:</span>")); self.btn_scan_wifi = QPushButton("🔄 Yenile / Tara"); self.btn_scan_wifi.setStyleSheet("background: #111; color: #00E5FF; border: 1px solid #00E5FF; padding: 5px 15px; border-radius: 4px; font-weight:bold;"); self.btn_scan_wifi.clicked.connect(self.scan_wifi_networks); top_h.addStretch(); top_h.addWidget(self.btn_scan_wifi); l.addLayout(top_h); self.wifi_list_widget = QListWidget(); self.wifi_list_widget.setStyleSheet("QListWidget { background: #000; border: 1px solid #333; border-radius: 5px; padding: 5px; color: #ddd; font-size: 12px; font-weight: bold; } QListWidget::item { padding: 10px; border-bottom: 1px dashed #222; } QListWidget::item:selected { background: rgba(0,229,255,0.1); color: #00E5FF; border-left: 3px solid #00E5FF; }"); self.wifi_list_widget.itemClicked.connect(self._wifi_item_clicked); l.addWidget(self.wifi_list_widget); inp_l = QHBoxLayout(); self.wifi_pwd_input = QLineEdit(); self.wifi_pwd_input.setPlaceholderText("Seçili ağın şifresini girin (Klavye açılacaktır)..."); self.wifi_pwd_input.setEchoMode(QLineEdit.Password); self.wifi_pwd_input.setStyleSheet("background: #111; color: #D4AF37; border: 1px solid #333; padding: 10px; border-radius: 5px; font-size: 12px; font-family: 'Courier New';"); self.wifi_pwd_input.installEventFilter(self); self.wifi_pwd_input.returnPressed.connect(self.connect_wifi); inp_l.addWidget(self.wifi_pwd_input); self.btn_connect_wifi = QPushButton("BAĞLAN"); self.btn_connect_wifi.setStyleSheet("background: #111; color: #00E5FF; border: 1px solid #00E5FF; padding: 10px 20px; border-radius: 5px; font-weight:bold;"); self.btn_connect_wifi.clicked.connect(self.connect_wifi); inp_l.addWidget(self.btn_connect_wifi); l.addLayout(inp_l); self.lbl_wifi_status = QLabel("Durum: Ağları taramak için butona basın."); self.lbl_wifi_status.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 5px;"); self.lbl_wifi_status.setAlignment(Qt.AlignCenter); l.addWidget(self.lbl_wifi_status); return w

    def build_guvenlik(self):
        w = QWidget(); l = QVBoxLayout(w); self.btn_sec_toggle = QPushButton("DURUM: PASİF (Açmak için dokun)"); self.btn_sec_toggle.setStyleSheet("padding: 20px; font-size: 12px; font-weight: bold; background: #111; color: #ddd; border: 1px solid #333; border-radius: 5px;"); self.btn_sec_toggle.clicked.connect(self.toggle_seraf); l.addWidget(self.btn_sec_toggle); self.lbl_sec_report = QLabel("<div style='color:#D4AF37; margin-bottom:5px; border-bottom:1px solid #222; padding-bottom:5px;'>📋 GEÇMİŞ İHLAL RAPORU</div>21:05 - Kapı sensörü tetiklendi.<br>02:14 - Radar tespiti (Kediler)"); self.lbl_sec_report.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 15px; background: #050505; border: 1px solid #333; padding: 15px; border-radius: 5px; line-height: 1.6;"); l.addWidget(self.lbl_sec_report); return w

    def build_saglik(self):
        w = QWidget(); l = QVBoxLayout(w); l.setSpacing(10); row1 = QHBoxLayout()
        for txt in ["GÜNLÜK UYKU", "HAFTALIK UYKU"]: b = QPushButton(txt); b.setStyleSheet("padding: 20px; background: #111; color: #ddd; border: 1px solid #333; border-radius: 5px; font-weight: bold;"); b.clicked.connect(lambda ch, t=txt: self.execute_health(t)); row1.addWidget(b)
        l.addLayout(row1); row2 = QHBoxLayout()
        for txt in ["7 GÜNLÜK BESLENME", "33 GÜNLÜK BESLENME"]: b = QPushButton(txt); b.setStyleSheet("padding: 20px; background: #111; color: #ddd; border: 1px solid #333; border-radius: 5px; font-weight: bold;"); b.clicked.connect(lambda ch, t=txt: self.execute_health(t)); row2.addWidget(b)
        l.addLayout(row2); line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #222; margin: 10px 0;"); l.addWidget(line); row3 = QHBoxLayout()
        b_qr = QPushButton("📄 RAPOR OKUT (QR)"); b_qr.setStyleSheet("padding: 15px; background: rgba(0,229,255,0.1); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 5px; font-weight: bold;"); b_qr.clicked.connect(lambda: self.show_qr()); row3.addWidget(b_qr)
        b_ses = QPushButton("🔊 SESLİ ÖZET"); b_ses.setStyleSheet("padding: 15px; background: #111; color: #ddd; border: 1px solid #333; border-radius: 5px; font-weight: bold;"); b_ses.clicked.connect(lambda: self.log_terminal('alice', 'Raporunuzu sesli özetliyorum: Gece kalp ritminiz Altın Oranda stabildi.')); row3.addWidget(b_ses); l.addLayout(row3); return w

    def build_hanedan(self):
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(QLabel("<span style='color:#888; font-size:12px;'>128D Yüz Taraması ve Ses DNA mühürlemesi için kimlik seçin:</span>"))
        btn_row = QHBoxLayout()
        self.hanedan_btns = []
        for name in ["Aryen", "Rana", "1 Misafir"]:
            b = QPushButton(name); b.setStyleSheet("padding: 15px; background: #111; color: #FFF; border: 1px solid #333; border-radius: 5px; font-weight: bold;"); b.clicked.connect(lambda ch, n=name, btn=b: self.start_tani(n, btn)); self.hanedan_btns.append(b); btn_row.addWidget(b)
        l.addLayout(btn_row)

        self.voice_enroll_panel = QFrame(); self.voice_enroll_panel.hide(); v_layout = QVBoxLayout(self.voice_enroll_panel)
        self.lbl_voice_text = QLabel("Lütfen şu metni okuyun:\n\n'Alice, ben Hanedan üyesi [İsim]. Sesimi ve varlığımı sistemin çekirdeğine mühürle.'")
        self.lbl_voice_text.setStyleSheet("color: var(--cyber-blue); font-size: 14px; font-style: italic; background: rgba(0,229,255,0.05); padding: 15px; border: 1px dashed var(--cyber-blue); border-radius: 5px; text-align: center;"); self.lbl_voice_text.setAlignment(Qt.AlignCenter); self.lbl_voice_text.setWordWrap(True); v_layout.addWidget(self.lbl_voice_text)
        self.btn_record_voice = QPushButton("🎤 SESİMİ KAYDET VE MÜHÜRLE (5 Saniye)"); self.btn_record_voice.setStyleSheet("padding: 15px; background: #111; color: var(--gold); border: 1px solid var(--gold); border-radius: 5px; font-weight: bold; font-size: 14px;"); self.btn_record_voice.clicked.connect(self.record_voice_dna); v_layout.addWidget(self.btn_record_voice)
        l.addWidget(self.voice_enroll_panel); return w

    def build_ayarlar(self):
        w = QWidget(); l = QGridLayout(w); l.setSpacing(10)
        self.btn_wifi_tg = QPushButton("Wi-Fi Kalkanı: AÇIK"); self.btn_wifi_tg.setStyleSheet("padding: 15px; font-weight:bold; background: rgba(0,229,255,0.1); color: #00E5FF; border: 1px solid #00E5FF; border-radius:5px;"); self.btn_wifi_tg.clicked.connect(self.toggle_wifi); l.addWidget(self.btn_wifi_tg, 0, 0)
        self.btn_bt = QPushButton("Bluetooth: KAPALI"); self.btn_bt.setStyleSheet("padding: 15px; font-weight:bold; background: #111; color: #ddd; border: 1px solid #333; border-radius:5px;"); self.btn_bt.clicked.connect(self.toggle_bt); l.addWidget(self.btn_bt, 0, 1)
        self.btn_cam = QPushButton("Kamera Lensi: AÇIK"); self.btn_cam.setStyleSheet("padding: 15px; font-weight:bold; background: rgba(0,229,255,0.1); color: #00E5FF; border: 1px solid #00E5FF; border-radius:5px;"); self.btn_cam.clicked.connect(self.toggle_camera_hardware); l.addWidget(self.btn_cam, 1, 0)
        self.btn_mqtt = QPushButton("Oda Işıkları (MQTT): AÇIK"); self.btn_mqtt.setStyleSheet("padding: 15px; font-weight:bold; background: rgba(0,229,255,0.1); color: #00E5FF; border: 1px solid #00E5FF; border-radius:5px;"); self.btn_mqtt.clicked.connect(self.toggle_lights); l.addWidget(self.btn_mqtt, 1, 1)

        vol_widget = QWidget(); vol_layout = QVBoxLayout(vol_widget); vol_layout.setContentsMargins(0, 0, 0, 0); self.lbl_vol = QLabel("Ses Seviyesi: %75"); self.lbl_vol.setStyleSheet("color:#aaa; font-size:11px; font-weight:bold;"); vol_layout.addWidget(self.lbl_vol); self.slider_vol = QSlider(Qt.Horizontal); self.slider_vol.setRange(0, 100); self.slider_vol.setValue(75); self.slider_vol.setStyleSheet("QSlider::groove:horizontal { border: 1px solid #333; height: 8px; background: #111; border-radius: 4px; } QSlider::handle:horizontal { background: #00E5FF; width: 18px; margin: -5px 0; border-radius: 9px; }"); self.slider_vol.valueChanged.connect(self.set_sys_volume); vol_layout.addWidget(self.slider_vol); l.addWidget(vol_widget, 2, 0)

        bri_widget = QWidget(); bri_layout = QVBoxLayout(bri_widget); bri_layout.setContentsMargins(0, 0, 0, 0); self.lbl_bri = QLabel("Ekran Parlaklığı: %90"); self.lbl_bri.setStyleSheet("color:#aaa; font-size:11px; font-weight:bold;"); bri_layout.addWidget(self.lbl_bri); self.slider_bri = QSlider(Qt.Horizontal); self.slider_bri.setRange(10, 100); self.slider_bri.setValue(90); self.slider_bri.setStyleSheet("QSlider::groove:horizontal { border: 1px solid #333; height: 8px; background: #111; border-radius: 4px; } QSlider::handle:horizontal { background: #D4AF37; width: 18px; margin: -5px 0; border-radius: 9px; }"); self.slider_bri.valueChanged.connect(self.set_sys_brightness); bri_layout.addWidget(self.slider_bri); l.addWidget(bri_widget, 2, 1)
        return w

    def build_guc(self):
        w = QWidget(); l = QHBoxLayout(w); l.setSpacing(15)
        for txt, act, col in [("💤 UYKU", "suspend", "#ddd"), ("🔄 YENİDEN BAŞLAT", "reboot", "#ddd"), ("🛑 KAPAT", "poweroff", "#FF0000")]:
            b = QPushButton(txt); bg = "rgba(255,0,0,0.1)" if act == "poweroff" else "#111"; border = "#FF0000" if act == "poweroff" else "#333"; b.setStyleSheet(f"padding: 25px; font-size: 14px; font-weight:bold; background: {bg}; color: {col}; border: 1px solid {border}; border-radius: 5px;"); b.clicked.connect(lambda ch, a=act: self.system_power_action(a)); l.addWidget(b)
        return w

    def build_derin_sistem(self):
        w = QWidget(); l = QVBoxLayout(w); 
        deep_html = """
        <div style="font-family:'Courier New'; color:#00FF00; font-size:12px; background:#000; border:1px solid #222; border-radius:5px; padding:15px; display:flex; flex-direction:column; gap:8px;">
            <div style="color:#E0E0E0; border-bottom: 1px dashed #333; padding-bottom: 5px;">OS: Ubuntu 20.04.6 LTS | Jetpack 5.1.2 [L4T 35.4.1] - Jetson Orin Nano (8GB)</div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top:10px;">
                <div>
                    <div style="color:#D4AF37; margin-bottom:4px;">[ CPU Çekirdek Yükleri ]</div>
                    <div>CPU 1: [||||||····] 62%</div><div>CPU 2: [|||·······] 34%</div>
                    <div>CPU 3: [|||||·····] 51%</div><div>CPU 4: [|·········] 12%</div>
                    <div>CPU 5: [||||||||··] 88%</div><div>CPU 6: [||········] 21%</div>
                </div>
                <div>
                    <div style="color:#D4AF37; margin-bottom:4px;">[ GPU & Tensor Çekirdekleri ]</div>
                    <div>GPU Yükü : [||||······] 45%</div><div>Tensor   : [||········] 20%</div>
                    <div style="margin-top:8px; color:#aaa;">NVENC: KAPALI<br>NVDEC: KAPALI</div>
                </div>
            </div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px; border-top: 1px dashed #333; padding-top: 8px; margin-top:10px;">
                <div>
                    <div style="color:#D4AF37; margin-bottom:4px;">[ Bellek Durumu ]</div>
                    <div>RAM  : 2.1 GB / 8.0 GB</div><div>SWAP : 0.4 GB / 4.0 GB</div>
                    <div>VRAM : 3.4 GB (Qwen+YOLO)</div>
                </div>
                <div>
                    <div style="color:#D4AF37; margin-bottom:4px;">[ Termal Sensörler ]</div>
                    <div>CPU-therm : <span style="color:#0F0;">42.5°C</span></div>
                    <div>GPU-therm : <span style="color:#0F0;">44.1°C</span></div>
                </div>
            </div>
            <div style="color:#555; text-align:right; margin-top:15px; font-size:9px;">*Veriler jtop ve psutil üzerinden okunmaktadır.</div>
        </div>
        """
        self.lbl_deep_sys = QLabel(deep_html)
        l.addWidget(self.lbl_deep_sys); return w

    # --- SİSTEM DÖNGÜLERİ ---
    def _start_system_loops(self):
        self.t_clock = QTimer(self); self.t_clock.timeout.connect(self.update_telemetry); self.t_clock.start(1000); self.update_telemetry()
        self.t_cam = QTimer(self); self.t_cam.timeout.connect(self.update_camera_feed)
        self.t_net = QTimer(self); self.t_net.timeout.connect(self.check_current_wifi); self.t_net.start(5000); self.check_current_wifi()

    def check_current_wifi(self):
        try:
            res = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], capture_output=True, text=True, timeout=2)
            active_ssid = "Bağlı Değil"
            if res.returncode == 0:
                for line in res.stdout.strip().split('\n'):
                    if line.startswith("yes:") or line.startswith("evet:") or line.startswith("*"):
                        parts = line.split(':'); 
                        if len(parts) >= 2: active_ssid = parts[1].strip(); break
            if active_ssid != "Bağlı Değil": self.btn_top_wifi.setText(f"📶 {active_ssid}"); self.btn_top_wifi.setStyleSheet("background: transparent; color: #00FF00; font-weight: bold; border: none; font-size: 11px; padding: 4px;")
            else: self.btn_top_wifi.setText("📶 Ağ Yok"); self.btn_top_wifi.setStyleSheet("background: transparent; color: #FF0000; font-weight: bold; border: none; font-size: 11px; padding: 4px;")
        except Exception as e:
            if not self.telemetry_error_logged: self.log_terminal("sys", f"Wi-Fi okuma hatası: {str(e)[:50]}"); self.telemetry_error_logged = True

    def scan_wifi_networks(self):
        self.wifi_list_widget.clear(); self.wifi_list_widget.addItem("Siber Ağlar Taranıyor... Lütfen Bekleyin."); self.btn_scan_wifi.setEnabled(False); self.lbl_wifi_status.setText("Tarama başladı..."); self.lbl_wifi_status.setStyleSheet("color: #D4AF37;"); QApplication.processEvents()
        self.scanner = WifiScannerThread(); self.scanner.networks_found.connect(self._on_scan_complete); self.scanner.error_occurred.connect(self._on_scan_error); self.scanner.start()

    def _on_scan_complete(self, networks):
        self.wifi_list_widget.clear(); self.btn_scan_wifi.setEnabled(True)
        if not networks: self.wifi_list_widget.addItem("Ağ bulunamadı veya Wi-Fi kapalı."); self.lbl_wifi_status.setText("Tarama başarısız."); self.lbl_wifi_status.setStyleSheet("color: #FF0000;"); return
        for net in networks: self.wifi_list_widget.addItem(net)
        self.lbl_wifi_status.setText(f"{len(networks)} ağ bulundu."); self.lbl_wifi_status.setStyleSheet("color: #00FF00;")

    def _on_scan_error(self, err_msg):
        self.wifi_list_widget.clear(); self.btn_scan_wifi.setEnabled(True); self.wifi_list_widget.addItem(err_msg); self.lbl_wifi_status.setText("Hata oluştu."); self.lbl_wifi_status.setStyleSheet("color: #FF0000;")

    def _wifi_item_clicked(self, item):
        self.wifi_pwd_input.clear(); self.keyboard.set_target(self.wifi_pwd_input); self.keyboard.move(self.geometry().x() + 450, self.geometry().y() + 100); self.keyboard.show()

    def connect_wifi(self):
        selected = self.wifi_list_widget.currentItem()
        if not selected or "Ağ bulunamadı" in selected.text() or "Taranıyor" in selected.text() or "Hata" in selected.text(): self.lbl_wifi_status.setText("Lütfen listeden geçerli bir ağ seçin!"); self.lbl_wifi_status.setStyleSheet("color: #FF0000;"); return
        ssid = selected.text().split(" (Güç:")[0].strip(); pwd = self.wifi_pwd_input.text().strip()
        self.lbl_wifi_status.setText(f"[{ssid}] ağına bağlanılıyor. AES Kasasına yazılıyor..."); self.lbl_wifi_status.setStyleSheet("color: #D4AF37;"); self.log_terminal("sys", f"Wi-Fi bağlantı isteği: {ssid}"); self.keyboard.hide(); self.btn_connect_wifi.setEnabled(False)
        self.connector = WifiConnectThread(ssid, pwd); self.connector.connection_result.connect(self._on_connect_complete); self.connector.start()

    def _on_connect_complete(self, msg, success):
        self.btn_connect_wifi.setEnabled(True); self.lbl_wifi_status.setText(msg)
        if success: self.lbl_wifi_status.setStyleSheet("color: #00FF00;"); self.wifi_pwd_input.clear(); self.check_current_wifi(); self.log_terminal("sys", msg); QTimer.singleShot(2000, lambda: self.nav_to(0))
        else: self.lbl_wifi_status.setStyleSheet("color: #FF0000;"); self.log_terminal("sys", f"Ağ bağlantı hatası: {msg}")

    def update_telemetry(self):
        now = datetime.datetime.now(); self.lbl_time.setText(now.strftime("%H:%M:%S")); self.lbl_date.setText(f"{now.day} {TR_MONTHS[now.month]} {now.year}")
        try:
            cpu_pct = psutil.cpu_percent(percpu=True); avg_cpu = sum(cpu_pct)/len(cpu_pct) if cpu_pct else 0
            ram = psutil.virtual_memory(); disk = psutil.disk_usage('/')
            temp = 42.0; 
            if self.orc and hasattr(self.orc, "physical") and getattr(self.orc, "physical", None): temp = self.orc.physical.get_max_temperature()
            temp_color = "#FF0000" if temp > 75 else "#00FF00"
            self.btn_sys_card.setText(f"CPU: %{int(avg_cpu)} | RAM: {ram.used / (1024**3):.1f}G\nISI: <span style='color:{temp_color};'>{temp:.1f}°C</span>\nSSD: %{int(disk.percent)}")
            
            if self.orc and hasattr(self.orc, "camera") and getattr(self.orc, "camera", None):
                targets = self.orc.camera.get_live_targets()
                if targets and "temiz" not in targets.lower() and "kapalı" not in targets.lower():
                    t_str = f"<span style='color:#D4AF37;'>[{now.strftime('%H:%M:%S')}]</span> <span>{targets.split(',')[0]}</span>"
                    if len(self.goz_history) == 0 or self.goz_history[0] != t_str: self.goz_history.insert(0, t_str); self.goz_history.pop() if len(self.goz_history) > 3 else None; self.lbl_goz_list.setText("<br>".join(self.goz_history))

            if self.orc:
                if getattr(self.orc, 'is_awake', False) and self.is_screensaver_active: self.reset_idle_timer()
                lock = getattr(self.orc, 'speech_lock', None)
                is_spk = False
                if lock:
                    with lock: is_spk = getattr(self.orc, "is_speaking", False)
                else: is_spk = getattr(self.orc, "is_speaking", False)

                if is_spk:
                    self.alice.set_mode("speak"); 
                    if not self.is_screensaver_active: self.lbl_status.setText("KONUŞUYOR..."); self.lbl_status.setStyleSheet("color: #FFFFFF;")
                elif getattr(self.orc, "awaiting_token_approval", False) or (hasattr(self.orc, 'mind') and getattr(self.orc, 'mind', None) and getattr(self.orc.mind, "active_engine", "") == "llm"):
                    self.alice.set_mode("think"); 
                    if not self.is_screensaver_active: self.lbl_status.setText("ZİHİN HESAPLIYOR..."); self.lbl_status.setStyleSheet("color: #D4AF37;")
                elif getattr(self.orc, 'is_awake', False):
                    self.alice.set_mode("listen"); 
                    if not self.is_screensaver_active: self.lbl_status.setText("SİZİ DİNLİYORUM EFENDİM"); self.lbl_status.setStyleSheet("color: #00E5FF;")
                else:
                    self.alice.set_mode("sleep"); 
                    if not self.is_screensaver_active: self.lbl_status.setText("ALİCE PUSUDA BEKLİYOR"); self.lbl_status.setStyleSheet("color: #666;")
        except Exception as e: self.log_terminal("sys", f"Telemetri uyarısı: {str(e)[:50]}")

    def nav_to(self, index):
        if index == 0:
            self.active_camera_process = False; 
            if hasattr(self, 't_cam'): self.t_cam.stop()
            if hasattr(self, 'voice_enroll_panel'): self.voice_enroll_panel.hide()
            self.fixed_vizor.setText("<div style='font-size:24px; margin-bottom:5px;'>🔳</div>BEKLEMEDE"); self.fixed_vizor.setStyleSheet("border: 1px dashed #333; color: #444; border-radius: 8px; font-size: 12px; font-weight:bold; letter-spacing: 2px; background: #000;")
            if self.is_term_open: self.toggle_terminal()
            if self.keyboard.isVisible(): self.keyboard.hide()
            self.alice.set_mode("sleep")
            if not self.is_screensaver_active: self.lbl_status.setText("ALİCE PUSUDA BEKLİYOR"); self.lbl_status.setStyleSheet("color: #666;")
        for i, btn in enumerate(self.nav_btns): btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
        if index == 7: self.scan_wifi_networks()

    def toggle_terminal(self):
        self.is_term_open = not self.is_term_open; end_y = 600 - 260 - 35 if self.is_term_open else 600; self.anim_term.setEndValue(QRect(85, end_y, 1024 - 85 - 280, 260)); self.anim_term.start()
        if self.is_term_open: self.btn_term_toggle.setStyleSheet("background: transparent; color: #00E5FF; font-family: 'Courier New'; font-size: 12px; font-weight: bold; border: none;")
        else: self.btn_term_toggle.setStyleSheet("background: transparent; color: #777; font-family: 'Courier New'; font-size: 12px; font-weight: bold; border: none;"); self.keyboard.hide()

    def clear_terminal(self):
        self.terminal_logs.clear()
        self.term_text.setHtml("")
        self.term_search.clear()
        self.log_terminal("sys", "Terminal ekranı Mimarın emriyle temizlendi.")

    def log_terminal(self, sender, text):
        if sender == "alice": html = f"<div style='margin-bottom:4px;'><span style='color:#FF0000; font-weight:bold;'>[Alice]:</span> <span style='color:#00FF00;'>{text}</span></div>"
        elif sender == "hanedan": html = f"<div style='margin-bottom:4px;'><span style='color:#00E5FF; font-weight:bold;'>[Hanedan]:</span> <span style='color:#FFFFFF;'>{text}</span></div>"
        else: html = f"<div style='margin-bottom:4px;'><span style='color:#777777;'>> {text}</span></div>"
        self.terminal_logs.append(html); 
        if len(self.terminal_logs) > 100: self.terminal_logs.pop(0)
        self.render_terminal()

    def render_terminal(self):
        filter_text = self.term_search.text().lower()
        content = "".join([log for log in self.terminal_logs if filter_text in log.lower() or not filter_text])
        self.term_text.setHtml(content); scroll_bar = self.term_text.verticalScrollBar(); scroll_bar.setValue(scroll_bar.maximum())

    def process_command(self):
        cmd = self.term_input.text().strip(); self.term_input.clear(); 
        if not cmd: return
        self.log_terminal("hanedan", cmd); lower_cmd = cmd.lower()
        if "alarm kur" in lower_cmd:
            parts = lower_cmd.split("alarm kur")
            if len(parts) > 1 and parts[1].strip():
                time_str = parts[1].strip(); self.lbl_alarm.setText(f"🔔 Alarm: {time_str}"); self.lbl_alarm.show(); self.log_terminal("sys", f"Sistem saati kuruldu: {time_str}"); self.log_terminal("alice", "Emriniz zihnime mühürlendi efendim.")
        elif self.orc: getattr(self.orc, '_process_command', lambda x: None)(cmd)
        self.keyboard.hide()

    def set_sys_volume(self):
        val = self.slider_vol.value(); self.lbl_vol.setText(f"Ses Seviyesi: %{val}")
        try: subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{val}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception as e: self.log_terminal("sys", f"Ses donanımı hatası: {str(e)[:50]}")

    def set_sys_brightness(self):
        val = self.slider_bri.value(); self.lbl_bri.setText(f"Ekran Parlaklığı: %{val}")
        try:
            res = subprocess.run(["brightnessctl", "set", f"{val}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if res.returncode != 0: subprocess.run("xrandr --output $(xrandr | grep ' connected' | awk '{print $1}') --brightness " + str(val/100.0), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception as e: self.log_terminal("sys", f"Parlaklık hatası: {str(e)[:50]}")

    def toggle_wifi(self):
        try:
            subprocess.run(["rfkill", "toggle", "wifi"], check=False); is_active = "AÇIK" not in self.btn_wifi_tg.text()
            self.btn_wifi_tg.setText(f"Wi-Fi Kalkanı: {'AÇIK' if is_active else 'KAPALI'}"); self.btn_wifi_tg.setStyleSheet(f"padding: 15px; font-weight:bold; border-radius:5px; background: {'rgba(0,229,255,0.1)' if is_active else '#111'}; color: {'#00E5FF' if is_active else '#ddd'}; border: 1px solid {'#00E5FF' if is_active else '#333'};")
        except Exception as e: self.log_terminal("sys", f"Wi-Fi modül hatası: {str(e)[:50]}")

    def toggle_bt(self):
        try:
            subprocess.run(["rfkill", "toggle", "bluetooth"], check=False); is_active = "AÇIK" not in self.btn_bt.text()
            self.btn_bt.setText(f"Bluetooth: {'AÇIK' if is_active else 'KAPALI'}"); self.btn_bt.setStyleSheet(f"padding: 15px; font-weight:bold; border-radius:5px; background: {'rgba(0,229,255,0.1)' if is_active else '#111'}; color: {'#00E5FF' if is_active else '#ddd'}; border: 1px solid {'#00E5FF' if is_active else '#333'};")
        except Exception as e: self.log_terminal("sys", f"Bluetooth modül hatası: {str(e)[:50]}")

    def toggle_camera_hardware(self):
        is_active = "AÇIK" not in self.btn_cam.text()
        if is_active:
            self.btn_cam.setText("Kamera Lensi: AÇIK"); self.btn_cam.setStyleSheet("padding: 15px; font-weight:bold; background: rgba(0,229,255,0.1); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 5px;")
            if self.orc and hasattr(self.orc, "camera") and getattr(self.orc, "camera", None): self.orc.camera.start()
        else:
            self.btn_cam.setText("Kamera Lensi: KAPALI"); self.btn_cam.setStyleSheet("padding: 15px; font-weight:bold; background: #111; color: #ddd; border: 1px solid #333; border-radius: 5px;")
            if self.orc and hasattr(self.orc, "camera") and getattr(self.orc, "camera", None): self.orc.camera.stop()
            self.fixed_vizor.setText("<div style='font-size:24px; margin-bottom:5px;'>🔳</div>BEKLEMEDE"); self.fixed_vizor.setStyleSheet("border: 1px dashed #333; color: #444; border-radius: 8px; font-size: 12px; font-weight:bold; letter-spacing: 2px; background: #000; padding:10px; box-sizing:border-box;")

    def toggle_lights(self):
        try:
            if self.orc and hasattr(self.orc, 'physical') and getattr(self.orc, "physical", None): self.orc.physical.trigger_relay("alice/home/light/main", {"state": "TOGGLE"})
        except Exception as e: self.log_terminal("sys", f"Işık rölesi hatası: {str(e)[:50]}")

    def system_power_action(self, action):
        if self.orc: self.orc.stop()
        try:
            if action == "suspend": subprocess.run(["systemctl", "suspend"], check=False)
            elif action == "reboot": subprocess.run(["reboot"], check=False)
            elif action == "poweroff": subprocess.run(["poweroff"], check=False)
        except Exception as e: self.log_terminal("sys", f"Sistem gücü hatası: {str(e)[:50]}")
        QApplication.quit()

    def execute_health(self, mode):
        self.log_terminal("sys", f"Sağlık Protokolü mühürlendi: {mode}")
        if self.orc: getattr(self.orc, 'safe_speak', lambda x: None)(f"{mode.replace(chr(10), ' ')} döngüsünü başlatıyorum efendim.")

    def show_qr(self):
        self.nav_to(0)
        try:
            if qrcode is not None:
                qr = qrcode.QRCode(box_size=5, border=2); qr.add_data("Alice_Edge_Rapor_Sifreli_Baglanti"); qr.make(fit=True); img = qr.make_image(fill_color="black", back_color="white").convert("RGBA"); qim = QImage(img.tobytes("raw", "RGBA"), img.size[0], img.size[1], QImage.Format_RGBA8888)
                self.fixed_vizor.setPixmap(QPixmap.fromImage(qim).scaled(self.fixed_vizor.size(), Qt.KeepAspectRatio)); self.fixed_vizor.setStyleSheet("border: 1px solid #D4AF37; background: #FFF; border-radius: 8px;")
        except Exception as e: self.log_terminal("sys", f"QR Kod oluşturulamadı: {str(e)[:50]}")

    def start_tani(self, name, btn):
        if "KAPALI" in getattr(self, 'btn_cam', QPushButton()).text(): 
            self.log_terminal("sys", "Kamera Lensi kapalı. Optik tarama başlatılamaz.")
            return
        self.nav_to(0)
        for b in self.hanedan_btns: b.setStyleSheet("padding: 15px; background: #111; color: #FFF; border: 1px solid #333; border-radius: 5px; font-weight: bold;")
        btn.setStyleSheet("padding: 15px; background: rgba(0,229,255,0.2); color: #00E5FF; border: 1px solid #00E5FF; border-radius: 5px; font-weight: bold;")
        self.active_camera_process = True
        self.active_tani_name = name
        self.fixed_vizor.setStyleSheet("border: 1px solid #00E5FF; border-radius: 8px; background: rgba(0,229,255,0.05); color: #00E5FF;")
        self.fixed_vizor.setText(f"<div style='font-size:30px; margin-bottom:5px;'>📷</div><div style='font-weight:bold;'>TANI: {name}</div><div style='font-size:9px; color:#aaa; margin-top:5px;'>128D Yüz Taranıyor...</div>")
        self.t_cam.start(100)
        if name in ["Aryen", "Rana"]:
            self.lbl_voice_text.setText(f"Lütfen şu metni sesli okuyun:\n\n'Alice, ben Hanedan üyesi {name}. Sesimi ve varlığımı sistemin çekirdeğine mühürle.'")
            self.voice_enroll_panel.show(); self.btn_record_voice.setText("🎤 SESİMİ KAYDET VE MÜHÜRLE (5 Saniye)"); self.btn_record_voice.setEnabled(True)
        else: self.voice_enroll_panel.hide()

    def record_voice_dna(self):
        if not getattr(self, 'active_tani_name', None) or self.active_tani_name not in ["Aryen", "Rana"]: return
        self.btn_record_voice.setEnabled(False); self.btn_record_voice.setText("🔴 KAYDEDİLİYOR... Konuşun (5sn)"); self.btn_record_voice.setStyleSheet("padding: 15px; background: rgba(255,0,0,0.1); color: #FF0000; border: 1px solid #FF0000; border-radius: 5px; font-weight: bold; font-size: 14px;")
        QApplication.processEvents()
        self.voice_recorder = VoiceRecordThread(self.active_tani_name); self.voice_recorder.record_finished.connect(self._on_voice_recorded); self.voice_recorder.start()

    def _on_voice_recorded(self, wav_path, success):
        self.btn_record_voice.setEnabled(True)
        if success:
            self.btn_record_voice.setText("🧬 Ses DNA Çıkarılıyor..."); QApplication.processEvents()
            try:
                if getattr(self.orc, 'comm', None) and hasattr(self.orc.comm, 'voice_dna') and getattr(self.orc.comm, 'voice_dna', None):
                    enroll_res = self.orc.comm.voice_dna.enroll(wav_path, self.active_tani_name)
                    if enroll_res:
                        self.btn_record_voice.setText("✅ Ses DNA'sı Mühürlendi.")
                        self.btn_record_voice.setStyleSheet("padding: 15px; background: rgba(0,255,0,0.1); color: #00FF00; border: 1px solid #00FF00; border-radius: 5px; font-weight: bold; font-size: 14px;")
                        self.log_terminal("sys", f"{self.active_tani_name} için Ses Vektörü AES kasasına mühürlendi.")
                        if self.orc: getattr(self.orc, 'safe_speak', lambda x: None)(f"Ses vektörünüz çekirdeğe mühürlendi {self.active_tani_name}.")
                    else: self.btn_record_voice.setText("❌ Ses Mühürleme Hatası.")
                else:
                    self.log_terminal("sys", "UYARI: Ses DNA modülü aktif değil. Dosya oluşturuldu.")
                    self.btn_record_voice.setText("✅ Ses Dosyası Alındı (DNA Yok)")
            except Exception as e:
                self.log_terminal("sys", f"Kayıt işleme hatası: {str(e)[:50]}")
        else:
            self.btn_record_voice.setText("🎙️ Kayıt Hatası! Tekrar Dene")
            self.log_terminal("sys", f"Mikrofon Hatası: {wav_path}")
        QTimer.singleShot(3000, lambda: self.btn_record_voice.setText("🎤 SESİMİ KAYDET VE MÜHÜRLE (5 Saniye)"))
        QTimer.singleShot(3000, lambda: self.btn_record_voice.setStyleSheet("padding: 15px; background: #111; color: var(--gold); border: 1px solid var(--gold); border-radius: 5px; font-weight: bold; font-size: 14px;"))

    def toggle_seraf(self):
        armed = False
        try:
            if self.orc and hasattr(self.orc, "camera") and getattr(self.orc, "camera", None):
                armed = not self.orc.camera.security_armed; self.orc.camera.arm_security(armed); getattr(self.orc, "radar", type('obj', (object,), {'arm_security_mode': lambda x: None})).arm_security_mode(armed)
            if armed:
                self.btn_sec_toggle.setText("DURUM: AKTİF (İhlal İnfazı Bekleniyor)")
                self.btn_sec_toggle.setStyleSheet("padding: 20px; font-size: 12px; font-weight: bold; background: rgba(255,0,0,0.1); color: #FF0000; border: 1px solid #FF0000; border-radius: 5px;")
                self.log_terminal("sys", "Seraf Güvenlik Kalkanı AKTİF.")
            else:
                self.btn_sec_toggle.setText("DURUM: PASİF (Açmak için dokun)")
                self.btn_sec_toggle.setStyleSheet("padding: 20px; font-size: 12px; font-weight: bold; background: #111; color: #ddd; border: 1px solid #333; border-radius: 5px;")
                self.log_terminal("sys", "Seraf Güvenlik Kalkanı PASİF.")
        except Exception as e:
            self.log_terminal("sys", f"Seraf kalkanı hatası: {str(e)[:50]}")

    def execute_barge_in(self):
        self.log_terminal("sys", "ACİL MÜDAHALE: Alice donanımsal olarak susturuldu."); if self.orc: getattr(self.orc, 'interrupt', lambda: None)()

def run_ui(orchestrator_instance):
    app = QApplication(sys.argv); window = AliceEdgeOS(orchestrator_instance); window.show(); sys.exit(app.exec())

if __name__ == "__main__":
    run_ui(None)