# get_games.tcl

Using tcscid, the get_games.tcl script listens on port 7778 and searches a scid database for a specific FEN.
It returns the first 5 games containing the FEN in the sort order of the scid database itself.
If you want a specific sort order (e.g. sorted by combined ELO rating) you need to sort the scid database.

Example link to get games data for the starting position as a JSON HTTP response:
http://localhost:7778/?action=get_games&fen=rnbqkbnr%2Fpppppppp%2F8%2F8%2F8%2F8%2FPPPPPPPP%2FRNBQKBNR+w+KQkq+-+0+1

JSON response (example):

```JSON
{
    "data": [{
        "white": "Carlsen, M. (wh) (2848)",
        "black": "Aronian, L. (bl) (2815)",
        "result": "1-0",
        "event": "2012, 4th London Chess Classic",
        "pgn": "[Event \"4th London Chess Classic\"]\n[Site \"London ENG\"]\n[Date \"2012.12.02\"]\n[Round \"2.1\"]\n[White \"Carlsen, M. (wh)\"]\n[Black \"Aronian, L. (bl)\"]\n[Result \"1-0\"]\n[WhiteElo \"2848\"]\n[BlackElo \"2815\"]\n[ECO \"C77\"]\n\n1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.d3 b5 6.Bb3 Bc5 7.Nc3 O-O 8.Nd5 Nxd5 9.Bxd5 Rb8 10.O-O Ne7 11.Nxe5 Nxd5 12.exd5 Re8 13.d4 Bf8 14.b3 Bb7 15.c4 d6 16.Nf3 Qf6 17.Be3 Bc8 18.Qd2 Qg6 19.Kh1 h6 20.Rac1 Be7 21.Ng1 Bg5 22.Bxg5 Qxg5 23.Rfd1 bxc4 24.bxc4 Qxd2 25.Rxd2 a5 26.h3 Rb4 27.Nf3 Bf5 28.c5 Kf8 29.Nh2 Reb8 30.Ng4 Rb1 31.Rxb1 Rxb1+ 32.Kh2 a4 33.Ne3 Bg6 34.Kg3 Rb4 35.Kf3 Ke7 36.Ke2 Kd7 37.f3 Rb5 38.Nd1 Rb4 39.c6+ Kc8 40.Nc3 f6 41.Ke3 Rc4 42.Ne2 a3 43.h4 Rb4 44.g4 Rb1 45.h5 Bh7 46.f4 f5 47.g5 Rh1 48.Ng3 Rh3 49.Kf3 hxg5 50.fxg5 g6 51.Re2 Kd8 52.hxg6 Bxg6 53.Re6 Bf7 54.g6 Bg8 55.g7 f4 56.Kxf4 Rh2 57.Nf5 Rxa2 58.Rf6 Re2 59.Rf8+ 1-0\n"
    }, {
        "white": "Aronian, L. (wh) (2802)",
        "black": "Carlsen, M. (bl) (2861)",
        "result": "1/2-1/2",
        "event": "2013, 75th Tata Steel GpA",
        "pgn": "[Event \"75th Tata Steel GpA\"]\n[Site \"Wijk aan Zee NED\"]\n[Date \"2013.01.13\"]\n[Round \"2.4\"]\n[White \"Aronian, L. (wh)\"]\n[Black \"Carlsen, M. (bl)\"]\n[Result \"1/2-1/2\"]\n[WhiteElo \"2802\"]\n[BlackElo \"2861\"]\n[ECO \"E90\"]\n\n1.d4 Nf6 2.c4 g6 3.Nc3 Bg7 4.e4 d6 5.Nf3 O-O 6.h3 Nc6 7.d5 Nb4 8.Be2 e6 9.Be3 Re8 10.Nd2 a5 11.O-O Bd7 12.Re1 b6 13.Rc1 Kh8 14.a3 Na6 15.Qc2 e5 16.Rb1 Ng8 17.b4 f5 18.Nb5 Bh6 19.Bxh6 Nxh6 20.exf5 gxf5 21.f4 exf4 22.Qc3+ Kg8 23.Bh5 Nf7 24.Rxe8+ Qxe8 25.Qf6 Qf8 26.Bxf7+ Qxf7 27.Qg5+ Qg7 28.Qxf4 axb4 29.axb4 Re8 30.Nd4 Qe5 31.Qg5+ Qg7 32.N2f3 Qxg5 33.Nxg5 Kg7 34.Nge6+ Kf6 35.Rf1 Bxe6 36.Nxe6 h5 37.g4 hxg4 38.hxg4 Nxb4 39.Rxf5+ Kg6 40.Nf4+ Kg7 41.g5 c6 42.Kf2 cxd5 43.cxd5 Re5 44.Ne6+ Kg6 45.Rf6+ Kh5 46.Kf3 Re3+ 1/2-1/2\n"
    }, {
        "white": "Carlsen, M. (wh) (2835)",
        "black": "Aronian, L. (bl) (2825)",
        "result": "0-1",
        "event": "2012, 7th Tal Mem Blitz",
        "pgn": "[Event \"7th Tal Mem Blitz\"]\n[Site \"Moscow RUS\"]\n[Date \"2012.06.07\"]\n[Round \"2\"]\n[White \"Carlsen, M. (wh)\"]\n[Black \"Aronian, L. (bl)\"]\n[Result \"0-1\"]\n[WhiteElo \"2835\"]\n[BlackElo \"2825\"]\n[ECO \"C65\"]\n\n1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.d4 exd4 5.O-O a6 6.Bxc6 dxc6 7.Nxd4 Be7 8.f3 O-O 9.Be3 Nd7 10.Nc3 Ne5 11.Qe2 Bb4 12.Nd1 c5 13.Nb3 c4 14.Nd4 c5 15.Nf5 Bxf5 16.exf5 Re8 17.Nf2 Nc6 18.Ne4 Nd4 19.Bxd4 Qxd4+ 20.Kh1 Qxb2 21.a3 Ba5 22.Rab1 Qe5 23.Rxb7 Qxf5 24.Qxc4 Qe6 25.Qxc5 Bd8 26.Qd4 Be7 27.Rb6 Qa2 28.c4 Qxa3 29.c5 a5 30.Ra1 Rad8 31.Nd6 Bf6 32.Rxa3 Bxd4 33.Nxe8 Bxc5 34.Rd6 Rxe8 0-1\n"
    }, {
        "white": "Carlsen, M. (wh) (2835)",
        "black": "Aronian, L. (bl) (2825)",
        "result": "1/2-1/2",
        "event": "2012, 7th Mikhail Tal Memorial",
        "pgn": "[Event \"7th Mikhail Tal Memorial\"]\n[Site \"Moscow RUS\"]\n[Date \"2012.06.14\"]\n[Round \"6\"]\n[White \"Carlsen, M. (wh)\"]\n[Black \"Aronian, L. (bl)\"]\n[Result \"1/2-1/2\"]\n[WhiteElo \"2835\"]\n[BlackElo \"2825\"]\n[ECO \"C67\"]\n\n1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.O-O Nxe4 5.d4 Nd6 6.Bxc6 dxc6 7.dxe5 Nf5 8.Qxd8+ Kxd8 9.Nc3 Ke8 10.b3 Be6 11.Bb2 Bb4 12.Ne2 Bd5 13.Ne1 h5 14.Nd3 Be7 15.Nef4 Rh6 16.c4 Be4 17.Rad1 g5 18.Rfe1 Bxd3 19.Nxd3 b5 20.c5 Ng7 21.b4 a5 22.a3 Ne6 23.g3 g4 24.Kg2 Rg6 25.Nf4 Rg5 26.Bc1 Rf5 27.h3 gxh3+ 28.Nxh3 axb4 29.axb4 Ra4 30.Bd2 Ra3 31.f4 h4 32.Re3 Rxe3 33.Bxe3 hxg3 34.Kxg3 Rh5 35.Bf2 f5 36.exf6 Bxf6 37.Kg4 Rxh3 38.Kxh3 Nxf4+ 39.Kg4 Nd5 40.Bd4 Kf7 41.Kf5 Ne7+ 42.Ke4 Bxd4 43.Kxd4 Ke6 44.Re1+ Kd7 45.Ke5 Nd5 46.Re4 Kc8 47.Ke6 Nc3 48.Rh4 Nd5 49.Rd4 Kd8 50.Rg4 Kc8 51.Rh4 Kb7 52.Kd7 Nf6+ 53.Kd8 Nd5 54.Rg4 Kb8 55.Rd4 Kb7 56.Kd7 Nc3 57.Ke6 Kc8 58.Rd3 Nd5 59.Rd4 Nc3 60.Rd3 Nd5 1/2-1/2\n"
    }, {
        "white": "Carlsen, M. (wh) (2843)",
        "black": "Aronian, L. (bl) (2816)",
        "result": "1/2-1/2",
        "event": "2012, 5th Final Masters",
        "pgn": "[Event \"5th Final Masters\"]\n[Site \"Bilbao ESP\"]\n[Date \"2012.09.28\"]\n[Round \"4\"]\n[White \"Carlsen, M. (wh)\"]\n[Black \"Aronian, L. (bl)\"]\n[Result \"1/2-1/2\"]\n[WhiteElo \"2843\"]\n[BlackElo \"2816\"]\n[ECO \"C65\"]\n\n1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 4.d3 Bc5 5.Bxc6 dxc6 6.Nbd2 Be6 7.O-O Bd6 8.b3 Nd7 9.Nc4 Bxc4 10.bxc4 O-O 11.Rb1 b6 12.g3 f5 13.exf5 Rxf5 14.Qe2 Nc5 15.Be3 Ne6 16.Nd2 Qf6 17.Qg4 Rf8 18.Ne4 Qf7 19.a4 h5 20.Qe2 Be7 21.a5 Qg6 22.axb6 axb6 23.Kh1 Rf3 24.Rbe1 Bb4 25.Ra1 Qg4 26.Qd1 Qh3 27.Bf4 Bc3 28.Qxf3 Bxa1 29.Qg2 Qf5 30.Bd2 Bd4 31.h3 Bc5 32.Bc3 Be7 33.Re1 b5 34.Kg1 b4 35.Bb2 Bd6 36.h4 Be7 37.Kh2 Ra8 38.Ra1 Rxa1 39.Bxa1 Nc5 40.Nd2 Bf6 41.Bb2 b3 42.Nxb3 Nxb3 43.cxb3 Qxd3 44.Qxc6 Qc2 45.Qe8+ Kh7 46.Qxh5+ Kg8 47.Qe8+ Kh7 48.Qh5+ 1/2-1/2\n"
    }]
}```

## Installation

Download the source of Scid vs. PC (tar.gz), extract it and build the software:

```shell
apt-get install build-essential tk-dev
./configure
make
```

Copy the executable tcscid to the folder /opt/picochess/gamesdb/:

```shell
cp tcscid /opt/picochess/gamesdb/
```

### Dependencies

You can remove all build dependencies and built software. In that case, make sure to install libtcl:

```shell
apt-get install libtcl8.6
```

### Start

Place a scid database named 'games' with its three files (games.sg4, games.si4, games.sn4) in the /opt/picochess/gamesdb/ folder.

Run the start.sh script to start the server.

To automatically start the server on system startup create a systemd service configuration:

/etc/systemd/system/gamesdb.service:

```INI
[Unit]
Description=Games server
After=multi-user.target

[Service]
Type=simple
ExecStart=/opt/picochess/gamesdb/start.sh
ExecStop=/usr/bin/pkill -f tcscid
WorkingDirectory=/opt/picochess/gamesdb

[Install]
WantedBy=graphical.target
```

Enable the service:

```shell
systemctl enable gamesdb.service
```
