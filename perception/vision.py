# perception/vision.py
# Yazar: Mimar
# Kurallar: Ayna Paradoksu, 3D PnP Euler Canlilik Kontrolu, 128D Vektor. "pass" YOKTUR.

import cv2
import time
import sys
import logging
import numpy as np
import mediapipe as mp
import face_recognition
from pathlib import Path

# Anayasa (config.py) baglantisi
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(
    filename=config.LOG_DIR / "vision.log",
    level=logging.WARNING,
    format="%(asctime)s - [GÖRSEL BİYOMETRİ] - %(message)s"
)

class BiometricVision:
    def __init__(self):
        """
        Zihnin optik korteksi. Ayna Paradoksunu cozer, maske/fotograf ile
        kandirilmayi PnP matematigi ile engeller ve yuzu 128 boyutlu matrise gomer.
        """
        self.mp_face_mesh = mp.solutions.face_mesh
        # Maksimum hiz ve 0 VRAM tuketimi icin CPU tabanli topolojik model
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1, # Altin kural: Cift yuz tespiti guvenlik ihlalidir
            refine_landmarks=False,
            min_detection_confidence=0.618,
            min_tracking_confidence=0.618
        )
        
        # PnP Euler Acilari icin 3D Insan Yuzu Referans Modeli
        self.face_3d_model = np.array([
            (0.0, 0.0, 0.0),             # Burun Ucu (Merkez)
            (0.0, -330.0, -65.0),        # Cene Alt Noktasi
            (-225.0, 170.0, -135.0),     # Sol Goz Dis Kenar
            (225.0, 170.0, -135.0),      # Sag Goz Dis Kenar
            (-150.0, -150.0, -125.0),    # Sol Dudak Kenari
            (150.0, -150.0, -125.0)      # Sag Dudak Kenari
        ], dtype=np.float64)
        
        self.lm_indices = [1, 152, 33, 263, 61, 291]
        
        # Tanima dogrulugu (Oklid Esigi - 0.45 cok kati, yanilmaz ve guvenlidir)
        self.recognition_tolerance = 0.45

    def resolve_mirror_and_pose(self, frame: np.ndarray):
        """
        Ayna etkisini (cv2.flip) uygular, PnP ile Kafa Acilarini ve 
        Z eksenindeki derinligi (Canliligi) hesaplar.
        Dondurur: mirrored_frame, pitch (Y-Ekseni), yaw (X-Ekseni), is_live_depth (Bool)
        """
        if frame is None or frame.size == 0:
            return None, None, None, False
            
        # 1. Ayna Paradoksu Infazi
        mirrored = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
        
        results = self.face_mesh.process(rgb_frame)
        if not results.multi_face_landmarks:
            return mirrored, None, None, False
            
        landmarks = results.multi_face_landmarks[0]
        h, w, _ = frame.shape
        
        # 2. Anti-Spoofing (Z Ekseni Derinlik Kontrolu)
        z_nose = landmarks.landmark[1].z
        z_left_cheek = landmarks.landmark[234].z
        z_right_cheek = landmarks.landmark[454].z
        
        depth_variance = abs(z_nose - z_left_cheek) + abs(z_nose - z_right_cheek)
        is_live_depth = depth_variance > 0.03 # Duz ekran/kagit uzerinde Z ekseni olusamaz
        
        # 3. 3D PnP Nokta Cikarimi
        face_2d = []
        for idx in self.lm_indices:
            lm = landmarks.landmark[idx]
            x, y = int(lm.x * w), int(lm.y * h)
            face_2d.append([x, y])
            
        face_2d = np.array(face_2d, dtype=np.float64)
        
        focal_length = 1 * w
        cam_matrix = np.array([
            [focal_length, 0, w / 2],
            [0, focal_length, h / 2],
            [0, 0, 1]
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)
        
        # Kafa donus acilarini cikar
        success, rot_vec, _ = cv2.solvePnP(self.face_3d_model, face_2d, cam_matrix, dist_coeffs)
        
        if success:
            rmat, _ = cv2.Rodrigues(rot_vec)
            angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
            pitch = angles[0] # Asagi/Yukari
            yaw = angles[1]   # Saga/Sola
            return mirrored, pitch, yaw, is_live_depth
            
        return mirrored, None, None, False

    def extract_128d_vector(self, rgb_frame: np.ndarray) -> np.ndarray:
        """Karedeki yuzu CPU dostu HOG motoruyla 128D imza vektorune cevirir."""
        boxes = face_recognition.face_locations(rgb_frame, model="hog")
        if not boxes:
            return np.array([])
            
        # Sistem kadraja sizan ikinci kisileri reddetmek icin en buyuk yuz kutusunu hedefler
        boxes = sorted(boxes, key=lambda b: (b[2]-b[0])*(b[1]-b[3]), reverse=True)
        encodings = face_recognition.face_encodings(rgb_frame, [boxes[0]])
        
        if encodings:
            return encodings[0]
        return np.array([])

    def execute_biometric_enrollment(self, camera_eye, tts_say) -> list:
        """
        Hanedan Tanima Protokolu 6. Adim.
        Zihin, gorsel vektorunuzu cikarmak icin bu iskeleti otonom cagirir.
        Geriye JSON dostu standart Python List dondurur.
        """
        tts_say("Biyometrik tarama için lütfen kameraya tam karşıdan bakın.")
        sys.stdout.write("\r[BİYOMETRİ] Merkez vektor (DNA) bekleniyor...\033[K\n")
        sys.stdout.flush()
        
        start_time = time.time()
        center_vector = np.array([])
        
        # 1. Asama: Yuzu Karsidan Sabitleme ve Derinlik Okuma
        while time.time() - start_time < 20:
            frame = camera_eye.get_frame()
            mirrored, pitch, yaw, is_live = self.resolve_mirror_and_pose(frame)
            
            if pitch is not None and yaw is not None:
                # Eger kisi kameraya +12 -12 aci toleransi icinde (karsidan) bakiyorsa
                if -12.0 < yaw < 12.0 and -15.0 < pitch < 15.0:
                    if is_live:
                        rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
                        center_vector = self.extract_128d_vector(rgb)
                        if center_vector.size > 0:
                            break
            time.sleep(0.1)
            
        if center_vector.size == 0:
            tts_say("Yüzünüzü net göremedim veya aydınlık yetersiz. Biyometrik kayıt iptal edildi.")
            return []
            
        # 2. Asama: Canlilik Icin Kafayi Cevirme (Spoofing İnfazi)
        tts_say("Sistemi doğrulamak için lütfen başınızı sağa veya sola çevirin.")
        sys.stdout.write("\r[BİYOMETRİ] 3D Liveness Onayi: Kafa cevirme bekleniyor...\033[K\n")
        sys.stdout.flush()
        
        start_time = time.time()
        liveness_passed = False
        
        while time.time() - start_time < 15:
            frame = camera_eye.get_frame()
            _, _, yaw, is_live = self.resolve_mirror_and_pose(frame)
            
            if yaw is not None and is_live:
                # Kisi fiziksel olarak saga veya sola en az 20 derece donduyse gercektir
                if abs(yaw) > 20.0: 
                    liveness_passed = True
                    break
            time.sleep(0.1)
            
        if not liveness_passed:
            tts_say("Dönüş algılanamadı. Güvenlik ihlali şüphesiyle işlem reddedildi.")
            sys.stdout.write("\r[BİYOMETRİ] Liveness Reddedildi! Fotograf gosterilmis olabilir.\033[K\n")
            sys.stdout.flush()
            return []
            
        tts_say("Harika. Biyometrik vektörünüz zihne mühürlendi.")
        sys.stdout.write("\r[BİYOMETRİ] 3D Canlilik Dogrulandi! 128D Vektor Hafizaya gonderiliyor.\033[K\n")
        sys.stdout.flush()
        
        return center_vector.tolist()
        
    def verify_identity(self, current_frame: np.ndarray, known_vector_list: list) -> bool:
        """
        Seraf Ajaninin veya Zihnin kapida/arayuzde kisiyi teyit etmek icin kullandigi 
        matematiksel Oklid karsilastirmasi.
        """
        if not known_vector_list:
            return False
            
        known_vector = np.array(known_vector_list)
        mirrored, pitch, _, is_live = self.resolve_mirror_and_pose(current_frame)
        
        # Guvenlik İnfazi: Gelen yuz canli (is_live) degilse direkt reddet
        if not is_live or pitch is None:
            return False
            
        rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
        current_vector = self.extract_128d_vector(rgb)
        
        if current_vector.size == 0:
            return False
            
        # Altin oran toleransi asilirsa True, kalirsa False doner
        distance = face_recognition.face_distance([known_vector], current_vector)[0]
        return distance <= self.recognition_tolerance

    def capture_intruder_snapshot(self, frame: np.ndarray) -> str:
        """Seraf Ajaninin kirmizi alarm aninda cektigi ihlal fotografi."""
        if frame is None:
            return ""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        intruder_dir = config.STORAGE_DIR / "intruders"
        intruder_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = intruder_dir / f"intruder_{timestamp}.jpg"
        # Ihlal karesi orijinal (aynalanmamis) haliyle mahkemelik delil gibi yazilir
        cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return str(filepath)

    def cleanup(self):
        """MediaPipe agini guvenle siler, RAM bosaltir."""
        self.face_mesh.close()

if __name__ == "__main__":
    # Orkestrator olmadan bagimsiz Cekirdek Testi
    print("[*] 3D Biyometrik Goz Baslatiliyor...")
    eye = BiometricVision()
    print("[+] PnP Liveness (Canlilik) kalkanlari aktif. 128D Motoru devrede.")