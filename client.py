#!/usr/bin/env python3
"""
blackijecky client- uses protocol abstraction

architecture:
- networking lives in protocol.py (udp discovery, tcp, packet formats)
- this file handles the game flow and user interaction only

benefits:
- cleaner code: no socket calls in the client logic
- easier to mock and test
"""

import sys
from protocol import ClientProtocol, Card, calculate_hand_value
from protocol import RESULT_NOT_OVER, RESULT_WIN, RESULT_LOSS, RESULT_TIE

TEAM_NAME = "Python Masters"
NUM_ROUNDS = 3


class BlackijackyClient:
    """client using the protocol layer.

    networking is handled by `ClientProtocol`, so this class just plays the game.
    """

    def __init__(self, team_name: str = TEAM_NAME):
        self.team_name = team_name
        self.num_rounds = NUM_ROUNDS

        # create the protocol handler (it does the networking)
        self.protocol = ClientProtocol()

        # Game state
        self.hand = []
        self.dealer_visible = []
        
        # Statistics
        self.wins = 0
        self.losses = 0
        self.ties = 0

    def get_player_decision(self) -> str:
        """ask the user for hit or stand and return the decision."""
        hand_value = calculate_hand_value(self.hand)

        print(f"\nYour hand: {', '.join(str(card) for card in self.hand)}")
        print(f"Hand value: {hand_value}")

        if hand_value >= 21:
            return "Stand"

        while True:
            decision = input("Do you want to (H)it or (S)tand? ").strip().upper()
            if decision in ['H', 'HIT']:
                return "Hittt"
            elif decision in ['S', 'STAND']:
                return "Stand"
            else:
                print("invalid input. enter H for hit or S for stand.")

    def play_game(self, server_ip: str, tcp_port: int):
        """play the game using the protocol helper.

        use `protocol.connect()`, `protocol.send_decision()` and `protocol.receive_card()`
        for all networking.
        """
        try:
            # connect to the server using the protocol helper
            if not self.protocol.connect(server_ip, tcp_port):
                print("Failed to connect to server")
                return

            # Send request using protocol
            if not self.protocol.send_request(self.num_rounds, self.team_name):
                print("Failed to send game request")
                return

            print(f"Starting {self.num_rounds} rounds of Blackijecky!\n")

            # play each round: receive initial cards, then let player act
            for round_num in range(1, self.num_rounds + 1):
                print(f"\n{'='*50}")
                print(f"ROUND {round_num}/{self.num_rounds}")
                print(f"{'='*50}")

                self.hand = []
                self.dealer_visible = []

                # receive the initial three cards (player card1, player card2, dealer visible)
                for i in range(3):
                    result = self.protocol.receive_card()
                    if not result:
                        print("Failed to receive initial cards")
                        return

                    card, game_result = result

                    if i < 2:  # First 2 cards are player's
                        self.hand.append(card)
                        if i == 0:
                            print(f"Your first card: {card}")
                        else:
                            print(f"Your second card: {card}")
                    else:  # Third card is dealer's visible card
                        self.dealer_visible.append(card)
                        print(f"Dealer's visible card: {card}")

                # player's turn: ask for decisions and send them to server
                while True:
                    decision = self.get_player_decision()

                    # send the decision and wait for an ack
                    if not self.protocol.send_decision(decision):
                        print("failed to send decision")
                        break

                    if decision == "Stand":
                        print("You stand.")
                        break

                    # receive the hit card from server
                    result = self.protocol.receive_card()
                    if not result:
                        print("Failed to receive card")
                        break

                    card, game_result = result
                    self.hand.append(card)

                    print(f"\nYou got: {card}")
                    hand_value = calculate_hand_value(self.hand)
                    print(f"Your hand value: {hand_value}")

                    # Check if player busted (hand > 21)
                    if hand_value > 21:
                        print("\n*** YOU BUST! Dealer wins. ***")
                        self.losses += 1
                        break
                    elif game_result != RESULT_NOT_OVER:
                        # Server sent a result code - round is over
                        break

                # now get the dealer's cards and the final result
                player_value = calculate_hand_value(self.hand)
                if player_value <= 21:
                    print("\n--- Dealer's turn ---")

                    card_count = 0
                    while True:
                        result = self.protocol.receive_card()
                        if not result:
                            break

                        card, game_result = result

                        if game_result == RESULT_NOT_OVER:
                            if card_count == 0:
                                print(f"Dealer reveals hidden card: {card}")
                            else:
                                print(f"Dealer hits: {card}")
                            self.dealer_visible.append(card)
                            card_count += 1
                        else:
                            # final result - this packet includes the last dealer card too
                            if card_count == 0:
                                print(f"Dealer reveals hidden card: {card}")
                            else:
                                print(f"Dealer hits: {card}")
                            self.dealer_visible.append(card)
                            dealer_value = calculate_hand_value(self.dealer_visible)

                            print(f"\n--- Final Hands ---")
                            print(f"Your hand: {', '.join(str(c) for c in self.hand)} (value: {player_value})")
                            print(f"Dealer's hand: {', '.join(str(c) for c in self.dealer_visible)} (value: {dealer_value})")

                            if game_result == RESULT_WIN:
                                print("\n*** YOU WIN! ***")
                                self.wins += 1
                            elif game_result == RESULT_LOSS:
                                print("\n*** DEALER WINS! ***")
                                self.losses += 1
                            elif game_result == RESULT_TIE:
                                print("\n*** TIE! ***")
                                self.ties += 1

                            break

            # Print final statistics
            total_rounds = self.wins + self.losses + self.ties
            win_rate = (self.wins / total_rounds * 100) if total_rounds > 0 else 0
            print(f"\n{'='*50}")
            print(f"Finished playing {total_rounds} rounds, win rate: {win_rate:.1f}%")
            print(f"Wins: {self.wins}, Losses: {self.losses}, Ties: {self.ties}")
            print(f"{'='*50}\n")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.protocol.close()

    def start(self):
        """Start the client - loops forever"""
        print("=" * 60)
        print("  Blackijecky Client")
        print("=" * 60)

        while True:  # Loop forever as per requirements
            # Reset stats for new game
            self.wins = 0
            self.losses = 0
            self.ties = 0
            
            # Ask user for number of rounds
            while True:
                try:
                    rounds_input = input("\nEnter number of rounds to play (1-255): ").strip()
                    self.num_rounds = int(rounds_input)
                    if 1 <= self.num_rounds <= 255:
                        break
                    print("Please enter a number between 1 and 255.")
                except ValueError:
                    print("Invalid input. Please enter a number.")

            # Discover server using protocol
            print("\nClient started, listening for offer requests...")
            
            # Create new protocol for each game session
            self.protocol = ClientProtocol()
            server_info = self.protocol.discover_server(timeout=15.0)

            if not server_info:
                print("Could not find a server. Retrying...")
                continue

            server_ip, tcp_port, server_name = server_info
            print(f"Received offer from {server_ip}, attempting to connect...")

            # Play the game
            self.play_game(server_ip, tcp_port)


def main():
    """Main entry point"""
    team_name = TEAM_NAME

    if len(sys.argv) > 1:
        team_name = sys.argv[1]

    client = BlackijackyClient(team_name=team_name)
    client.start()


if __name__ == '__main__':
    main()
