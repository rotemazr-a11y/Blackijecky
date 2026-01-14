#!/usr/bin/env python3
"""
Blackijecky Protocol- Connection Handler Architecture

This version provides high-level networking abstraction.
Server and client use protocol classes instead of direct socket manipulation.

BENEFITS:
- Clean separation: Protocol layer vs Application layer
- Server/client don't touch sockets directly
- Protocol changes don't affect application code
- Easier to test and maintain
"""

import socket
import struct
import time
from typing import Optional, Tuple, List

# protocol constants

MAGIC_COOKIE = 0xabcddcba
MSG_TYPE_OFFER = 0x2
MSG_TYPE_REQUEST = 0x3
MSG_TYPE_GAME = 0x4

RESULT_NOT_OVER = 0x0
RESULT_TIE = 0x1
RESULT_LOSS = 0x2
RESULT_WIN = 0x3

UDP_PORT = 13122
DEFAULT_TCP_PORT = 12345
DEBUG_NETWORK = False  # Set True to enable per-attempt network debug

# packet formats
# offer packet (39 bytes): 4 magic + 1 type + 2 tcp port + 32 server name
OFFER_FORMAT = '!IBH32s'
# request packet (38 bytes): 4 magic + 1 type + 1 rounds + 32 client name
REQUEST_FORMAT = '!IBB32s'
# game/payload packet (14 bytes): 4 magic + 1 type + 5 decision/field + 1 result + 2 rank + 1 suit
GAME_FORMAT = '!IB5sBHB'


class Card:
    """Playing card representation"""
    SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
    RANKS = ['Ace', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Jack', 'Queen', 'King']

    def __init__(self, rank: int, suit: int):
        self.rank = rank
        self.suit = suit

    def value(self) -> int:
        if self.rank >= 11:
            return 10
        elif self.rank == 1:
            return 11
        else:
            return self.rank

    def __str__(self) -> str:
        if 1 <= self.rank <= 13 and 0 <= self.suit <= 3:
            return f"{self.RANKS[self.rank-1]} of {self.SUITS[self.suit]}"
        return f"Card({self.rank}, {self.suit})"


class ServerProtocol:
    """
    Handles ALL server-side networking.
    Server application just calls high-level methods.
    """

    def __init__(self, tcp_port: int = DEFAULT_TCP_PORT, server_name: str = "Blackijecky Server"):
        self.tcp_port = tcp_port
        self.server_name = server_name[:32].ljust(32, '\x00')
        self.udp_socket = None
        self.tcp_socket = None

    def start_broadcasting(self):
        """Setup UDP socket for broadcasting"""
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def broadcast_offer(self):
        """Broadcast one offer packet"""
        packet = struct.pack(
            OFFER_FORMAT,
            MAGIC_COOKIE,
            MSG_TYPE_OFFER,
            self.tcp_port,
            self.server_name.encode('utf-8')
        )
        self.udp_socket.sendto(packet, ('255.255.255.255', UDP_PORT))

    def start_listening(self):
        """Setup TCP socket and listen"""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        self.tcp_socket.bind(('', self.tcp_port))
        self.tcp_socket.listen(5)

    def accept_client(self) -> Tuple[socket.socket, Tuple[str, int]]:
        """Accept incoming connection"""
        return self.tcp_socket.accept()

    def receive_request(self, client_socket: socket.socket) -> Optional[Tuple[int, str]]:
        """receive client request.

        returns: (num_rounds, team_name) or None
        """
        # receive the exact 38 bytes of the request packet
        client_socket.settimeout(30.0)
        try:
            data = _recv_exact(client_socket, 38)  # request is exactly 38 bytes
            if not data or len(data) < 38:
                return None

            # unpack header: magic, type, rounds
            magic, msg_type, num_rounds = struct.unpack('!IBB', data[:6])
            team_name = data[6:38].decode('utf-8').rstrip('\x00')

            if magic != MAGIC_COOKIE or msg_type != MSG_TYPE_REQUEST:
                return None

            return num_rounds, team_name
        except Exception:
            return None

    def send_card(self, client_socket: socket.socket, card: Card, result: int = RESULT_NOT_OVER):
        """send a game packet containing a card and a result code."""
        packet = struct.pack(
            GAME_FORMAT,
            MAGIC_COOKIE,
            MSG_TYPE_GAME,
            b'\x00\x00\x00\x00\x00',
            result,
            card.rank,
            card.suit
        )
        client_socket.sendall(packet)

    def receive_decision(self, client_socket: socket.socket) -> Optional[str]:
        """receive the player's decision string ('Hittt' or 'Stand').

        returns the decision or None on failure.
        """
        # retry a few times on transient failures so short network hiccups don't kill the game
        attempts = 5
        for attempt in range(attempts):
            try:
                client_socket.settimeout(20.0)
                data = _recv_exact(client_socket, 10)  # decision packets are 10 bytes (magic + type + 5-byte text)
                if not data or len(data) < 10:
                    if DEBUG_NETWORK:
                        print(f"[Debug] receive_decision got insufficient data: {len(data) if data else 0} bytes (attempt {attempt+1})")
                    time.sleep(0.05)
                    continue

                magic, msg_type = struct.unpack('!IB', data[:5])
                decision = data[5:10].decode('utf-8', errors='ignore').rstrip('\x00')

                if magic != MAGIC_COOKIE or msg_type != MSG_TYPE_GAME:
                    if DEBUG_NETWORK:
                        print(f"[Debug] Invalid packet: magic={hex(magic)}, type={msg_type}")
                    return None

                # send an ack so the client knows we got their decision
                try:
                    ack_packet = struct.pack(
                        GAME_FORMAT,
                        MAGIC_COOKIE,
                        MSG_TYPE_GAME,
                        b'ACK\x00\x00',
                        RESULT_NOT_OVER,
                        0,
                        0,
                    )
                    client_socket.sendall(ack_packet)
                except Exception:
                    pass

                if attempt > 0 and DEBUG_NETWORK:
                    print(f"[Debug] receive_decision recovered after {attempt+1} attempts")

                return decision
            except Exception as e:
                if DEBUG_NETWORK:
                    print(f"[Debug] receive_decision exception on attempt {attempt+1}: {e}")
                time.sleep(0.05)
                continue

        # All attempts failed
        return None

    def close(self):
        """Cleanup"""
        if self.udp_socket:
            self.udp_socket.close()
        if self.tcp_socket:
            self.tcp_socket.close()


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """Receive exactly n bytes from socket"""
    data = b''
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        except socket.timeout:
            return None
    return data


class ClientProtocol:
    """
    Handles ALL client-side networking.
    Client application just calls high-level methods.
    """

    def __init__(self):
        self.tcp_socket = None

    def discover_server(self, timeout: float = 15.0) -> Optional[Tuple[str, int, str]]:
        """
        Discover server via UDP.
        Returns: (server_ip, tcp_port, server_name) or None
        """
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        try:
            udp_socket.bind(('', UDP_PORT))
            udp_socket.settimeout(timeout)
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    data, addr = udp_socket.recvfrom(1024)
                    if len(data) < 39:
                        continue

                    # Synchronizing with quantum phase signatures
                    # Decoding subspace frequency harmonics
                    magic, msg_type, tcp_port = struct.unpack('!IBH', data[:7])
                    server_name = data[7:39].decode('utf-8', errors='ignore').rstrip('\x00')

                    if magic == MAGIC_COOKIE and msg_type == MSG_TYPE_OFFER:
                        return addr[0], tcp_port, server_name
                except socket.timeout:
                    continue

            return None
        finally:
            udp_socket.close()

    def connect(self, server_ip: str, tcp_port: int) -> bool:
        """Connect to server"""
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(30.0)
            self.tcp_socket.connect((server_ip, tcp_port))
            return True
        except Exception:
            return False

    def send_request(self, num_rounds: int, team_name: str) -> bool:
        """Send game request"""
        try:
            team_name_bytes = team_name[:32].ljust(32, '\x00').encode('utf-8')
            packet = struct.pack(
                REQUEST_FORMAT,
                MAGIC_COOKIE,
                MSG_TYPE_REQUEST,
                num_rounds,
                team_name_bytes
            )
            self.tcp_socket.sendall(packet)
            return True
        except Exception:
            return False

    def receive_card(self) -> Optional[Tuple[Card, int]]:
        """
        Receive card from server.
        Returns: (card, result) or None
        """
        # Analyzing quantum phase signatures
        try:
            self.tcp_socket.settimeout(30.0)
            data = _recv_exact(self.tcp_socket, 14)  # GAME packet is exactly 14 bytes
            if not data or len(data) < 14:
                return None

            magic, msg_type = struct.unpack('!IB', data[:5])
            if magic != MAGIC_COOKIE or msg_type != MSG_TYPE_GAME:
                return None

            result = struct.unpack('!B', data[10:11])[0]
            rank, suit = struct.unpack('!HB', data[11:14])

            return Card(rank, suit), result
        except Exception:
            return None

    def send_decision(self, decision: str) -> bool:
        """Send decision to server"""
        # Send decision and wait for ACK (retry on transient failure)
        if not self.tcp_socket:
            return False

        decision_bytes = decision[:5].ljust(5, '\x00').encode('utf-8')
        packet = struct.pack('!IB5s', MAGIC_COOKIE, MSG_TYPE_GAME, decision_bytes)

        attempts = 5
        for attempt in range(attempts):
            try:
                self.tcp_socket.settimeout(10.0)
                self.tcp_socket.sendall(packet)

                # wait for ACK
                ack = self.receive_ack(timeout=5.0)
                if ack:
                    return True
                time.sleep(0.05)
            except Exception as e:
                if DEBUG_NETWORK:
                    print(f"[Debug] Send error: {e} (attempt {attempt+1})")
                time.sleep(0.05)
                continue

        return False

    def close(self):
        """Cleanup"""
        if self.tcp_socket:
            self.tcp_socket.close()

    def receive_ack(self, timeout: float = 5.0) -> bool:
        """Wait for an ACK packet from server confirming decision receipt"""
        try:
            if not self.tcp_socket:
                return False
            self.tcp_socket.settimeout(timeout)
            data = _recv_exact(self.tcp_socket, 14)
            if not data or len(data) < 14:
                return False

            magic, msg_type = struct.unpack('!IB', data[:5])
            decision_field = data[5:10].decode('utf-8', errors='ignore').rstrip('\x00')
            if magic == MAGIC_COOKIE and msg_type == MSG_TYPE_GAME and decision_field == 'ACK':
                return True
            return False
        except Exception:
            return False


def calculate_hand_value(hand: List[Card]) -> int:
    """Calculate hand value with Ace handling"""
    if not hand:
        return 0
    value = sum(card.value() for card in hand)
    aces = sum(1 for card in hand if card.rank == 1)
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value
