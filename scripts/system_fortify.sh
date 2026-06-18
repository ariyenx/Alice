#!/bin/bash
# ALICE HİS - Sistem Zırhlandırma ve Çekirdek Güvenlik Protokolü
# Yazar: Mimar
# Kurallar: 4GB Swap (Altın Oran), USB Uyku Engeli, Kali Hibritleri, Seraf Tırpanı.

set -e

echo "[*] Hanedan İletişim Sistemi (HİS) Zırhlandırma Protokolü Başlatılıyor..."

# 1. Jetson Maximum Performans ve Altın Oran Swap Tahsisi (8GB RAM -> 4GB Swap)
echo "[*] Güç Modu Max (nvpmodel -m 0) ve Jetson Clocks aktif ediliyor..."
sudo nvpmodel -m 0 || true
sudo jetson_clocks || true

SWAP_SIZE="4G"
SWAP_FILE="/swapfile"
if ! swapon --show | grep -q "$SWAP_FILE"; then
    echo "[*] $SWAP_SIZE Swap alanı oluşturuluyor..."
    sudo fallocate -l $SWAP_SIZE $SWAP_FILE
    sudo chmod 600 $SWAP_FILE
    sudo mkswap $SWAP_FILE
    sudo swapon $SWAP_FILE
    echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab
else
    echo "[+] Swap alanı zaten mevcut."
fi

# 2. Konum ve Zaman Senkronizasyonu (IP/NTP)
echo "[*] Zaman Bilinci: Europe/Istanbul..."
sudo timedatectl set-timezone Europe/Istanbul
sudo timedatectl set-ntp true

# 3. Kali Ağ Güvenliği Hibrit Araçları ve Temel Bağımlılıklar
echo "[*] Ağ güvenliği ve Hanedan MAC tarama araçları kuruluyor..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    nmap arp-scan aircrack-ng macchanger \
    ufw fail2ban \
    v4l-utils alsa-utils i2c-tools \
    python3-pip ffmpeg sox

# 4. Güvenlik Duvarı (UFW) Acımasız Modu
echo "[*] UFW (Seraf Kalkanı) Aktifleştiriliyor..."
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
# Gelecekteki QR Wi-Fi Dosya Transfer API'si için Port İzni
sudo ufw allow 8000/tcp
sudo ufw --force enable

# 5. USB Bekçisi: Donanım Düşmesini Çekirdekten Engelleme
echo "[*] USB Uyku Modu (Autosuspend) Kapatılıyor..."
UDEV_RULE="/etc/udev/rules.d/usb-power.rules"
echo 'ACTION=="add", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"' | sudo tee $UDEV_RULE > /dev/null
echo 'ACTION=="add", SUBSYSTEM=="usb", TEST=="power/autosuspend", ATTR{power/autosuspend}="-1"' | sudo tee -a $UDEV_RULE > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

# 6. Seraf Kapanış Tırpanı (TMP ve LOG Yok Etme - Kural 12)
echo "[*] Seraf Kapanış Temizleyicisi (Systemd) Kuruluyor..."
SERAPH_SERVICE="/etc/systemd/system/seraph-cleanup.service"
sudo tee $SERAPH_SERVICE > /dev/null << 'EOF'
[Unit]
Description=Seraph Agent - Tmp and Log Reaper
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c "rm -rf /tmp/* /var/log/*.log /var/log/syslog /var/log/auth.log /var/tmp/*"
TimeoutSec=0

[Install]
WantedBy=shutdown.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable seraph-cleanup.service

echo "[+] Zırhlandırma Tamamlandı. Sistem Hanedan için hazır."
echo "[!] Uyarı: Log ve Tmp dosyaları sistem kapandığında Seraf tarafından acımasızca silinecektir."