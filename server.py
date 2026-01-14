#!/usr/bin/env python3
"""
blackijecky server- uses protocol abstraction

architecture:
- networking lives in protocol.py (udp, tcp, packet formats)
- this file only deals with game logic and printing

benefits:
- simpler code: no socket calls here
- easy to test: you can mock protocol functions
"""

import threading
import time
import random
import socket
from protocol import ServerProtocol, Card, calculate_hand_value
from protocol import RESULT_NOT_OVER, RESULT_WIN, RESULT_LOSS, RESULT_TIE

TCP_PORT = 12345
SERVER_NAME = "Blackijecky Server"


class Deck:
    """Manages card deck"""
    def __init__(self):
        self.cards = []
        self.reset()

    def reset(self):
        self.cards = [Card(rank, suit) for rank in range(1, 14) for suit in range(4)]
        random.shuffle(self.cards)

    def deal(self) -> Card:
        if not self.cards:
            self.reset()
        return self.cards.pop()


class BlackjackGame:
    """Manages game state"""
    def __init__(self, num_rounds: int):
        self.deck = Deck()
        self.num_rounds = num_rounds
        self.current_round = 0
        self.player_hand = []
        self.dealer_hand = []

    def start_new_round(self):
        self.current_round += 1
        self.player_hand = [self.deck.deal(), self.deck.deal()]
        self.dealer_hand = [self.deck.deal(), self.deck.deal()]
        return self.player_hand, self.dealer_hand[0]

    def player_hit(self) -> Card:
        card = self.deck.deal()
        self.player_hand.append(card)
        return card

    def dealer_play(self):
        dealer_cards = []
        while calculate_hand_value(self.dealer_hand) < 17:
            card = self.deck.deal()
            self.dealer_hand.append(card)
            dealer_cards.append(card)
        return dealer_cards

    def determine_winner(self) -> int:
        player_value = calculate_hand_value(self.player_hand)
        dealer_value = calculate_hand_value(self.dealer_hand)

        if player_value > 21:
            return RESULT_LOSS
        elif dealer_value > 21:
            return RESULT_WIN
        elif player_value > dealer_value:
            return RESULT_WIN
        elif player_value < dealer_value:
            return RESULT_LOSS
        else:
            return RESULT_TIE


class BlackijackyServer:
    """server using the protocol layer.

    no socket code here — networking is handled by `ServerProtocol`.
    """

    def __init__(self, tcp_port: int = TCP_PORT, server_name: str = SERVER_NAME):
        # Create protocol handler (handles ALL networking)
        self.protocol = ServerProtocol(tcp_port, server_name)
        self.running = False

    def broadcast_offers(self):
        """udp broadcast loop. calls protocol.broadcast_offer() once a second."""
        self.protocol.start_broadcasting()

        while self.running:
            self.protocol.broadcast_offer()
            time.sleep(1)

    def handle_client(self, client_socket, client_address):
        """handle a single client session (runs in its own thread).

        use protocol.send_card() and protocol.receive_decision() for networking.
        """
        try:
            # receive the initial request (rounds + team name)
            request = self.protocol.receive_request(client_socket)
            if not request:
                return

            num_rounds, team_name = request

            # build a short label so logs show which client is which
            conn_label = f"{team_name}@{client_address[0]}:{client_address[1]}"
            def log(msg: str):
                print(f"[Client: {conn_label}] {msg}")

            log(f"Connected for {num_rounds} rounds")

            # Play game
            game = BlackjackGame(num_rounds)

            for round_num in range(1, num_rounds + 1):
                log(f"\nRound {round_num}/{num_rounds}")

                # start round: deal cards and show them in the log
                player_cards, dealer_visible_card = game.start_new_round()
                log(f"player's cards: {player_cards[0]}, {player_cards[1]}")
                log(f"dealer's visible card: {dealer_visible_card}")
                log(f"dealer's hidden card: {game.dealer_hand[1]}")

                # send the player's two cards and the dealer visible card
                # small sleeps help avoid packet coalescing on some systems
                self.protocol.send_card(client_socket, player_cards[0])
                time.sleep(0.1)
                self.protocol.send_card(client_socket, player_cards[1])
                time.sleep(0.1)
                self.protocol.send_card(client_socket, dealer_visible_card)

                # player's turn: wait for decisions from the client
                while True:
                    # Receive decision using protocol
                    decision = self.protocol.receive_decision(client_socket)
                    if not decision:
                        log("player decision not received (timed out or disconnected)")
                        break

                    log(f"player decision: {decision}")

                    if decision.startswith('Stand'):
                        break
                    elif decision.startswith('Hittt'):
                        card = game.player_hit()

                        log(f"player hits: {card}")

                        player_value = calculate_hand_value(game.player_hand)
                        log(f"player hand value: {player_value}")

                        if player_value > 21:
                            log(f"player lost (over 21)")
                            self.protocol.send_card(client_socket, card, RESULT_LOSS)
                            time.sleep(0.2)  # Give client time to process
                            break
                        else:
                            self.protocol.send_card(client_socket, card, RESULT_NOT_OVER)

                # dealer's turn: reveal hidden card then hit as needed
                player_value = calculate_hand_value(game.player_hand)
                if player_value <= 21:
                    log(f"dealer's turn...")

                    # dealer hits according to rules (hit until 17 or more)
                    dealer_cards = game.dealer_play()

                    # Send hidden card and any additional hits EXCEPT the last card
                    if dealer_cards:
                        # dealer hit at least once - reveal hidden card first
                        log(f"dealer reveals hidden card: {game.dealer_hand[1]}")
                        self.protocol.send_card(client_socket, game.dealer_hand[1], RESULT_NOT_OVER)
                        time.sleep(0.1)

                        # send all hit cards except the last one; last one comes with the final result
                        for i in range(len(dealer_cards) - 1):
                            log(f"dealer hits: {dealer_cards[i]}")
                            self.protocol.send_card(client_socket, dealer_cards[i], RESULT_NOT_OVER)
                            time.sleep(0.1)

                        final_card = dealer_cards[-1]
                        log(f"dealer hits: {final_card}")
                    else:
                        # dealer didn't hit - the hidden card will be the final card
                        final_card = game.dealer_hand[1]
                        log(f"dealer reveals hidden card: {final_card}")

                    result = game.determine_winner()
                    dealer_value = calculate_hand_value(game.dealer_hand)

                    log(f"final - player: {player_value}, dealer: {dealer_value}")

                    if result == RESULT_WIN:
                        log(f"Player wins!")
                    elif result == RESULT_LOSS:
                        log(f"Dealer wins!")
                    else:
                        log(f"Tie!")

                    # send final card with the round result
                    self.protocol.send_card(client_socket, final_card, result)
                
                # Small delay between rounds to ensure synchronization
                time.sleep(0.3)

            log(f"Game complete with {team_name}")

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def start(self):
        """Start server"""
        self.running = True

        # Get local IP address
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = '127.0.0.1'

        # Start UDP broadcast thread
        udp_thread = threading.Thread(target=self.broadcast_offers, daemon=True)
        udp_thread.start()

        # Start TCP server using protocol
        self.protocol.start_listening()
        print(f"Server started, listening on IP address {local_ip}")

        try:
            while self.running:
                # Accept client using protocol
                client_socket, client_address = self.protocol.accept_client()

                # Handle in thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.protocol.close()


def main():
    server = BlackijackyServer(tcp_port=TCP_PORT, server_name=SERVER_NAME)
    server.start()


if __name__ == '__main__':
    main()
