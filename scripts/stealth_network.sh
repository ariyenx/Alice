#!/bin/bash
# ALICE HİS - Ağ Hayalet Modu ve Bluetooth İnfazı
# Yazar: Mimar
# Kurallar: Intel Bluetooth rfkill kalkanı, mDNS susturma, UFW ICMP (Ping) Drop. "pass" YOKTUR.

set -e

echo "[*] Seraf Ag Hayalet Modu Baslatiliyor..."

# 1. Intel Bluetooth İletişimini ve Servisini Acımasızca Katlet
echo "[*] Intel Bluetooth Radyosu bloklaniyor..."
sudo systemctl stop bluetooth || true
sudo systemctl disable bluetooth || true
sudo rfkill block bluetooth || true

# 2. Avahi Daemon (mDNS) Kapatılması (.local yayınını engeller)
echo "[*] mDNS (Avahi) yayini kesiliyor (Ağda isim zikretmeyecek)..."
sudo systemctl stop avahi-daemon || true
sudo systemctl disable avahi-daemon || true

# 3. ICMP (Ping) Yutma (Drop) Protokolü
echo "[*] Ping (ICMP Echo) istekleri cekirdek ve UFW uzerinden yutuluyor (Drop)..."

# Çekirdek seviyesi (Sysctl)
SYSCTL_CONF="/etc/sysctl.d/99-stealth.conf"
echo "net.ipv4.icmp_echo_ignore_all = 1" | sudo tee $SYSCTL_CONF > /dev/null
echo "net.ipv4.icmp_echo_ignore_broadcasts = 1" | sudo tee -a $SYSCTL_CONF > /dev/null
sudo sysctl -p $SYSCTL_CONF > /dev/null

# Güvenlik Duvarı (UFW) seviyesi
UFW_BEFORE_RULES="/etc/ufw/before.rules"
if [ -f "$UFW_BEFORE_RULES" ]; then
    # UFW before.rules icinde ok-icmp echo-request satirini ACCEPT'ten DROP'a cevir
    sudo sed -i 's/-A ufw-before-input -p icmp --icmp-type echo-request -j ACCEPT/-A ufw-before-input -p icmp --icmp-type echo-request -j DROP/g' $UFW_BEFORE_RULES
    sudo ufw reload > /dev/null 2>&1
fi

# 4. Geçersiz Paket Düşürme (Nmap Stealth taramalarını boşa çıkarmak için)
sudo iptables -A INPUT -m conntrack --ctstate INVALID -j DROP || true

echo "[+] Mükemmel İnfaz. Hayalet Modu Aktif. Jetson artik ağ taramalarında YOK hükmündedir."