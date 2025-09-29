#!/usr/pkg/bin/python3.12
import socket
import sys
import os
import signal
import argparse
import syslog
import time
import dns.message
import dns.rdatatype
import dns.rrset
import dns.rdata
import dns.rdataclass

# Multicast address/port for mDNS
MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353

# Listen address/port for Unbound
DNS_LISTEN_ADDR = "127.0.0.1"
DNS_LISTEN_PORT = 5533

# Default PID file location
DEFAULT_PID_FILE = "/var/run/mdns-proxy.pid"

# Global flag for graceful shutdown
shutdown_flag = False

# Cache for previous DNS resolutions
resolution_cache = {}

def log_message(message, level=syslog.LOG_INFO):
    """Log message to syslog or stdout depending on daemon mode"""
    if hasattr(log_message, 'use_syslog') and log_message.use_syslog:
        syslog.syslog(level, message)
    else:
        print(message)

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global shutdown_flag
    log_message(f"Received signal {signum}, shutting down gracefully", syslog.LOG_INFO)
    shutdown_flag = True

def create_pid_file(pid_file):
    """Create PID file"""
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        log_message(f"Created PID file: {pid_file}")
    except Exception as e:
        log_message(f"Failed to create PID file {pid_file}: {e}", syslog.LOG_ERR)
        sys.exit(1)

def remove_pid_file(pid_file):
    """Remove PID file"""
    try:
        if os.path.exists(pid_file):
            os.unlink(pid_file)
            log_message(f"Removed PID file: {pid_file}")
    except Exception as e:
        log_message(f"Failed to remove PID file {pid_file}: {e}", syslog.LOG_WARNING)

def create_cached_response(query):
    """Create a response using cached resolution if available"""
    try:
        # Get the question
        question = query.question[0]
        qname = str(question.name)
        qtype = question.rdtype

        # Check if we have a cached resolution for this query
        cache_key = f"{qname}:{qtype}"
        if cache_key not in resolution_cache:
            log_message(f"No cached resolution found for {qname}")
            return None

        # Create response message
        response = dns.message.make_response(query)
        
        # Use the cached answer
        cached_answer = resolution_cache[cache_key]
        response.answer.append(cached_answer)

        return response
    except Exception as e:
        log_message(f"Error creating cached response: {e}", syslog.LOG_ERR)
        return None

def daemonize():
    """Daemonize the process"""
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Parent exits
    except OSError as e:
        log_message(f"First fork failed: {e}", syslog.LOG_ERR)
        sys.exit(1)

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        # Second fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Second parent exits
    except OSError as e:
        log_message(f"Second fork failed: {e}", syslog.LOG_ERR)
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    si = open('/dev/null', 'r')
    so = open('/dev/null', 'a+')
    se = open('/dev/null', 'a+')
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

def run_proxy():
    """Main proxy loop"""
    global shutdown_flag

    # Socket for unicast DNS requests (from Unbound)
    dns_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns_sock.bind((DNS_LISTEN_ADDR, DNS_LISTEN_PORT))
    dns_sock.settimeout(1)  # Allow periodic checking of shutdown flag

    # Socket for sending/receiving multicast mDNS
    mdns_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    mdns_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    mdns_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    log_message(f"DNS-mDNS bridge listening on {DNS_LISTEN_ADDR}:{DNS_LISTEN_PORT}")

    while not shutdown_flag:
        try:
            data, addr = dns_sock.recvfrom(4096)
            query = dns.message.from_wire(data)

            # Get the first question
            if len(query.question) == 0:
                continue

            qname = str(query.question[0].name)
            qtype = dns.rdatatype.to_text(query.question[0].rdtype)
            log_message(f"Query for {qname} ({qtype}) from {addr}")

            # Forward only .local. domains to mDNS
            if not qname.endswith(".local."):
                log_message("Non-local query, ignoring")
                continue

            # Forward query to mDNS multicast group
            mdns_sock.sendto(data, (MDNS_ADDR, MDNS_PORT))

            # Wait for a response
            mdns_sock.settimeout(1.0)
            try:
                rdata, _ = mdns_sock.recvfrom(4096)
                response = dns.message.from_wire(rdata)

                # Fix response ID to match the client query
                response.id = query.id

                # Cache the successful resolution
                if len(response.answer) > 0:
                    cache_key = f"{qname}:{query.question[0].rdtype}"
                    resolution_cache[cache_key] = response.answer[0]
                    log_message(f"Cached resolution for {qname}")

                dns_sock.sendto(response.to_wire(), addr)
                log_message(f"Sent mDNS response for {qname} to {addr}")
            except socket.timeout:
                log_message(f"No mDNS reply received for {qname}, checking cache")
                # Try to send cached response
                cached_response = create_cached_response(query)
                if cached_response:
                    dns_sock.sendto(cached_response.to_wire(), addr)
                    log_message(f"Sent cached response for {qname} to {addr}")
                else:
                    log_message(f"No cached response available for {qname}")
            except Exception as mdns_error:
                log_message(f"mDNS error for {qname}: {mdns_error}, checking cache")
                # Try to send cached response on any mDNS error
                cached_response = create_cached_response(query)
                if cached_response:
                    dns_sock.sendto(cached_response.to_wire(), addr)
                    log_message(f"Sent cached response for {qname} to {addr}")
                else:
                    log_message(f"No cached response available for {qname}")

        except socket.timeout:
            # This is expected - allows us to check shutdown_flag periodically
            continue
        except Exception as e:
            log_message(f"Error processing request: {e}", syslog.LOG_ERR)

    # Cleanup
    dns_sock.close()
    mdns_sock.close()
    log_message("DNS-mDNS bridge stopped")

def main():
    global DNS_LISTEN_ADDR, DNS_LISTEN_PORT

    parser = argparse.ArgumentParser(description='DNS-mDNS bridge daemon')
    parser.add_argument('-d', '--daemon', action='store_true',
                       help='Run as daemon')
    parser.add_argument('-p', '--pid-file', default=DEFAULT_PID_FILE,
                       help=f'PID file location (default: {DEFAULT_PID_FILE})')
    parser.add_argument('--listen-addr', default=DNS_LISTEN_ADDR,
                       help=f'Listen address (default: {DNS_LISTEN_ADDR})')
    parser.add_argument('--listen-port', type=int, default=DNS_LISTEN_PORT,
                       help=f'Listen port (default: {DNS_LISTEN_PORT})')

    args = parser.parse_args()

    # Update global variables with command line args
    DNS_LISTEN_ADDR = args.listen_addr
    DNS_LISTEN_PORT = args.listen_port

    if args.daemon:
        # Initialize syslog for daemon mode
        syslog.openlog("mdns-proxy", syslog.LOG_PID, syslog.LOG_DAEMON)
        log_message.use_syslog = True

        log_message("Starting mdns-proxy daemon")

        # Check if already running
        if os.path.exists(args.pid_file):
            try:
                with open(args.pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                # Check if process is still running
                try:
                    os.kill(old_pid, 0)
                    log_message(f"Daemon already running with PID {old_pid}", syslog.LOG_ERR)
                    sys.exit(1)
                except OSError:
                    # Process not running, remove stale PID file
                    os.unlink(args.pid_file)
            except (ValueError, IOError):
                # Invalid PID file, remove it
                try:
                    os.unlink(args.pid_file)
                except:
                    pass

        # Daemonize
        daemonize()

        # Create PID file after daemonizing
        create_pid_file(args.pid_file)

        # Set up signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)

        try:
            run_proxy()
        finally:
            remove_pid_file(args.pid_file)
            syslog.closelog()
    else:
        # Foreground mode
        log_message.use_syslog = False

        # Set up signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        try:
            run_proxy()
        except KeyboardInterrupt:
            log_message("Interrupted by user")

if __name__ == "__main__":
    main()
