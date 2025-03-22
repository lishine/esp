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


def extract_domain_from_dns_query(data):
    """Extract the domain name from a DNS query packet"""
    try:
        # Skip the header (12 bytes)
        domain_parts = []
        i = 12
        while i < len(data):
            length = data[i]
            if length == 0:
                break
            part = data[i + 1 : i + 1 + length].decode("utf-8")
            domain_parts.append(part)
            i += length + 1
        return ".".join(domain_parts)
    except Exception:
        return "unknown_domain"


def dns_server():
    """DNS server for AP mode - acts as a captive portal by responding to all DNS queries with the AP's IP"""
    udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udps.bind(("", 53))
    ap_ip = "192.168.4.1"
    log(f"DNS server started - redirecting all queries to {ap_ip}")

    # Apple-specific domains that need special handling
    apple_domains = [
        "captive.apple.com",
        "www.apple.com",
        "apple.com",
        "appleiphonecell.com",
        "itools.info",
        "ibook.info",
        "airport.us",
        "thinkdifferent.us",
    ]

    while True:
        try:
            data, addr = udps.recvfrom(512)
            domain = extract_domain_from_dns_query(data)

            # Log the domain being queried
            if any(apple_domain in domain for apple_domain in apple_domains):
                log(f"Apple domain DNS query: {domain}")

            # Respond to all DNS queries with the AP's IP to create a captive portal effect
            response = make_dns_response(data, ap_ip)
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
