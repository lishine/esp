import socket
import _thread
import network

from log import log
from led import blink


def make_dns_response(data, ip_addr):
    """Create a simple DNS response packet"""
    packet = bytearray(32)
    packet[0] = data[0]
    packet[1] = data[1]
    packet[2] = 0x81
    packet[3] = 0x80
    packet[4] = 0x00
    packet[5] = 0x01
    packet[6] = 0x00
    packet[7] = 0x01
    packet[12:] = data[12:]
    packet.extend(
        bytearray(
            [
                0xC0,
                0x0C,  # Name pointer
                0x00,
                0x01,  # Type A
                0x00,
                0x01,  # Class IN
                0x00,
                0x00,
                0x00,
                0x0A,  # TTL (10 seconds)
                0x00,
                0x04,  # Data length
            ]
        )
    )
    packet.extend(bytes(map(int, ip_addr.split("."))))
    return packet


def dns_server():
    """DNS server for AP mode"""
    udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udps.bind(("", 53))
    while True:
        try:
            data, addr = udps.recvfrom(512)
            response = make_dns_response(data, "192.168.4.1")
            udps.sendto(response, addr)
        except Exception as e:
            log(f"DNS Error: {e}")


ap = network.WLAN(network.AP_IF)


def start_ap(essid="DDDEV", password=""):
    """Start the access point with the given ESSID and password"""
    ap.active(True)
    ap.config(essid=essid, password=password)
    blink(2)
    log(f"AP mode activated: {essid}")
    log(f"AP IP address: {ap.ifconfig()[0]}")

    _thread.start_new_thread(dns_server, ())


def get_ap_ip():
    """Get the IP address of the AP interface"""
    return ap.ifconfig()[0]
