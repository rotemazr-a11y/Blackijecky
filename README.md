# Blackijecky - Network Blackjack Game

Team: **Python Masters**

This is our implementation of a simple blackjack game over the network. The server broadcasts offers via UDP, and clients connect over TCP to play.

## How to Run

### Start the Server

```bash
python3 server.py
```

You'll see:
```
Server started, listening on IP address 192.168.1.5
```

The server will keep running until you press Ctrl+C.

### Start the Client

```bash
python3 client.py
```

Or with a custom team name:
```bash
python3 client.py "Your Team Name"
```

The client asks you how many rounds you want to play, then automatically finds the server and starts playing.

## What's Inside

**protocol.py** - All the networking stuff (UDP discovery, TCP connections, packet formats)
**server.py** - The game server (deals cards, runs the dealer logic)
**client.py** - The player client (gets input from you, shows the game)

## How It Works

1. **Server** broadcasts "I'm here!" messages on UDP port 13122
2. **Client** listens for these broadcasts and finds the server
3. Client connects to server via TCP
4. They play blackjack for the number of rounds you chose
5. Client shows you win/loss stats at the end
6. Client goes back to step 1 and looks for a server again (runs forever)

## The Protocol

We use binary packets with a magic cookie (0xabcddcba) to make sure packets are valid.

**Offer packet (UDP, 39 bytes)**
- Server tells clients where to connect (IP + TCP port + server name)

**Request packet (TCP, 38 bytes)**
- Client asks to play X rounds and sends team name

**Game packet (TCP, 14 bytes)**
- Used for everything during the game:
  - Sending cards (rank 1-13, suit 0-3)
  - Sending player decisions ("Hittt" or "Stand")
  - Sending results (win/loss/tie)

## Game Rules

Basic blackjack rules:
- You get 2 cards, dealer shows 1 card
- You can Hit (get another card) or Stand (stop)
- If you go over 21, you lose immediately
- If you stand, dealer plays: hits until 17 or higher
- Whoever is closer to 21 without going over wins
- Aces count as 11 (or 1 if you'd bust)
- Face cards (J, Q, K) count as 10

## Example Game

```

  Blackijecky Client

Enter number of rounds to play (1-255): 3

Client started, listening for offer requests...
Received offer from 192.168.1.5, attempting to connect...
Starting 3 rounds of Blackijecky!


ROUND 1/3

Your first card: 7 of Hearts
Your second card: 9 of Clubs
Dealer's visible card: King of Diamonds

Your hand: 7 of Hearts, 9 of Clubs
Hand value: 16
Do you want to (H)it or (S)tand? s
You stand.

--- Dealer's turn ---
Dealer reveals hidden card: 6 of Spades
Dealer hits: 5 of Hearts

--- Final Hands ---
Your hand: 7 of Hearts, 9 of Clubs (value: 16)
Dealer's hand: King of Diamonds, 6 of Spades, 5 of Hearts (value: 21)

*** YOU LOSE! ***

...


Finished playing 3 rounds, win rate: 33.3%
Wins: 1, Losses: 2, Ties: 0

```

## Features

- Works with any other team's client or server (we follow the protocol spec)
- Handles multiple clients at the same time (uses threads)
- Retries on network errors (good for crowded networks)
- No busy-waiting (won't use much CPU)
- Runs on multiple clients on same computer (uses SO_REUSEPORT)

## Configuration

You can change these if you want:

**server.py:**
```python
TCP_PORT = 12345                    # What port to listen on
SERVER_NAME = "Blackijecky Server"  # Your server's name
```

**client.py:**
```python
TEAM_NAME = "Python Masters"  # Your team name
```

**protocol.py:**
```python
DEBUG_NETWORK = False  # Set to True to see debug messages
```

## Requirements

- Python 3
- No extra packages needed (uses standard library)
- Works on Linux, Mac, and Windows

## Notes

- The client asks for rounds each time it connects
- Both server and client run forever until you manually stop them
- If you lose connection, the client will automatically look for a server again
- The protocol has some retry logic to handle packet loss on busy networks
