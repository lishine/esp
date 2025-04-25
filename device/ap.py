import _thread
import network
import socket
import time

from log import log
from led import blink_sequence

ap = network.WLAN(network.AP_IF)
AP_IP = "192.168.4.1"  # Define AP IP address


def dns_server():
    """Simple DNS server to redirect all queries to the AP IP"""
    addr = socket.getaddrinfo("0.0.0.0", 53)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow reusing address
    try:
        s.bind(addr)
        log("DNS server started on port 53")
    except OSError as e:
        log(f"Failed to bind DNS server on port 53: {e}")
        return  # Exit thread if bind fails

    while True:
        try:
            data, addr = s.recvfrom(512)
            # Basic DNS query parsing (assuming A record query)
            # Construct a simple DNS response pointing to AP_IP
            # DNS Header: Transaction ID (from query), Flags (Response, Authoritative), QDCOUNT=1, ANCOUNT=1
            # DNS Question: Same as query
            # DNS Answer: Name (compressed), Type A, Class IN, TTL, RDLENGTH=4, RDATA=AP_IP bytes

            # Get Transaction ID from query (first 2 bytes)
            tid = data[:2]

            # Construct response
            response = tid + b"\x81\x80"  # Flags: Response, No error
            response += data[4:6]  # QDCOUNT
            response += data[4:6]  # ANCOUNT (set to QDCOUNT for simplicity)
            response += b"\x00\x00"  # NSCOUNT
            response += b"\x00\x00"  # ARCOUNT

            # Add Question section (copied from query)
            # Find end of question name (null byte)
            qname_end = data.find(b"\x00", 12)
            if qname_end == -1:  # Malformed query? Skip
                log(f"DNS: Malformed query from {addr}")
                continue
            qname_end += 1  # Include the null byte
            response += data[12 : qname_end + 4]  # QNAME, QTYPE, QCLASS

            # Add Answer section
            response += b"\xc0\x0c"  # Pointer to question name (offset 12)
            response += b"\x00\x01"  # Type A
            response += b"\x00\x01"  # Class IN
            response += b"\x00\x00\x00\x3c"  # TTL (60 seconds)
            response += b"\x00\x04"  # RDLENGTH (4 bytes for IPv4)
            response += bytes(map(int, AP_IP.split(".")))  # RDATA (AP IP address)

            s.sendto(response, addr)
            # log(f"DNS query from {addr}, redirected to {AP_IP}") # Optional: logging can be noisy

        except OSError as e:
            log(f"DNS server OS error: {e}")
            # Avoid busy-looping on error
            time.sleep_ms(500)
        except Exception as e:
            log(f"Unexpected DNS server error: {e}")
            time.sleep_ms(500)


def start_ap(essid="DDDEV", password=""):
    """Start the access point with the given ESSID and password"""
    ap.active(True)
    # Ensure IP is static as defined
    ap.ifconfig((AP_IP, "255.255.255.0", AP_IP, AP_IP))
    ap.config(essid=essid, password=password)
    # try:
    #     blink_sequence(count=2)
    # except Exception as e:
    #     log(f"Error during AP start blink: {e}")
    log(f"AP mode activated: {essid}")
    log(f"AP IP address: {ap.ifconfig()[0]}")
    # Start DNS server in a new thread
    # _thread.start_new_thread(dns_server, ())


def get_ap_ip():
    """Get the IP address of the AP interface"""
    # Check if AP is active before getting config
    if ap.active():
        try:
            return ap.ifconfig()[0]
        except Exception as e:
            log(f"Error getting AP IP: {e}")
            return "Error"
    else:
        return "AP_Inactive"
