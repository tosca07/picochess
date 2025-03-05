#!/usr/bin/env python3

############################################################################
# molli:
# PicoChess engine wrapper for replay/analysis/guess play of games in pgn
# format
# Start with:
# "python3 pgn_engine.py"
#
############################################################################

import sys
import time
import chess
import chess.pgn
import chess.engine
import random
import pygame
from pathlib import Path

###########################################################################################
# UCI Wrapper
###########################################################################################
abc = "abcdefgh"
nn  = "12345678"

is_uci = False
uci_move = ''

log_file          = "pgn_engine-log.txt"
log_file_pgn_info = "pgn_game_info.txt"

engine_name       = "PGN Replay/Analysis Engine V1.0"

game_started     = False
line             = ''

p_pgn_game_file = '/opt/picochess/games/last_game.pgn'
p_engine_path   = '/opt/picochess/engines/aarch64/a-stockf'
p_audio_comment = ''
p_game_sequence = 'backward' ## possible values:  random, forward, backward
##p_pgn_game_file = '/Users/molli/Desktop/games/mate_in_two.pgn'
##p_pgn_game_file = '/Users/molli/Desktop/games/games.pgn'
##p_pgn_game_file = '/Users/molli/Desktop/games/fool.pgn'
##p_engine_path   = '/Users/molli/Documents/stockfish-9-mac/Mac/stockfish-9-bmi2'
##p_audio_comment = '/Users/molli/Desktop/hoerspiel_NwZ.mp3'
flag_audio_playing = False
p_think_time    = 3
think_time      = 0
max_guess       = 0
move_counter    = 0
max_moves       = 0
game_counter    = 0
max_games       = 0
guess_ok        = True
last_line       = ''
last_fen_line   = ''
j               = 0
i               = 0

move_list    = []
game_list    = []
orig_game_list = []
pgn_file     = ''
pgn_game     = None
board        = None
input_board  = None
engine       = None
info_handler = None
info_str     = ''
fen          = ''
l_continue   = True

try:
    log = open(log_file, 'w')
except:
    log = ''
    print("# Could not create log file")

def play_audio():
    global flag_audio_playing

    """Speak out the sound part by using ogg123/play."""
    if not p_audio_comment:
        return

    if Path(p_audio_comment).is_file():
        pygame.mixer.music.load(p_audio_comment)
        pygame.mixer.music.play()
        flag_audio_playing = True
    return


def print2(x):
    global log
    print(x)
    if log:
        log.write("< %s\n" % x)
        log.flush()

def write_log(x):
    global log
    if log:
        log.write("< %s\n" % x)
        log.flush()

def convert_to_uci(move):
    global p_own_color

    if move == 'O-O' or move == 'o-o':
        if p_own_color == 'b':
            uci_move = 'e1g1'
        else:
            uci_move = 'e8g8'
    elif move == 'O-O-O' or move == 'o-o-o':
        if p_own_color == 'b':
            uci_move = 'e1c1'
        else:
            uci_move = 'e8c8'
    else:
        move_fr = move[0:2]
        move_to = move[3:5]

        if move[-1] == 'q'   or move[-1] == 'Q':
            promotion = 'q'
        elif move[-1] == 'b' or move[-1] == 'B':
            promotion = 'b'
        elif move[-1] == 'k' or move[-1] == 'K':
            promotion = 'n'
        elif move[-1] == 'n' or move[-1] == 'N':
             promotion = 'n'
        elif move[-1] == 'r' or move[-1] == 'R':
             promotion = 'r'
        else:
            promotion = ''

        uci_move = move_fr + move_to + promotion
    return(uci_move)

def get_move():
    global is_uci
    global game_started
    global move_counter
    global move_list
    global board
    global ponder_move
    global info_str
    global info_handler
    global think_time
    global engine

    move = ''
    uci_move = ''
    ponder_move = ''
    info_str = ''

    if is_uci and game_started:

        if 'book.pgn' in p_pgn_game_file:
            ## for book test return ABORT to notify that last move wasn't a book move
            uci_move = 'ABORT'
            ponder_move = ''
        elif max_moves == 0 or move_counter > (max_moves-1):
            ## game over
            uci_move = 'ABORT'
            ponder_move = ''
            info_str = 'info depth 999 multipv 1 score cp 999'
        else:

            ## get next move
            move_pgn = move_list[move_counter]
            move_counter = move_counter + 1
            board.push(chess.Move.from_uci(move_pgn))

            if log:
                log.write('get pgn_move: %s\n' % str(move_pgn))
                log.write('new move_counter %s\n' % str(move_counter))

            if think_time > 0:

                move = ''
                ponder_move = ''

                info_str = "info depth 0"

            ponder_move = move ## molli: the ponder move for pico is the current engine move
            ##else:
            ##ponder_move = move_list[move_counter]

            if move_pgn == '0000' or move_pgn == 'ABORT' or move_pgn == '':
                uci_move = 'ABORT'
                ponder_move = ''
            else:
                uci_move = move_pgn

    return (uci_move, ponder_move, info_str)

def pub_move():
    global guess_ok
    global move_counter
    global board
    global info_str

    uci_move, ponder_move, info_str = get_move()

    if uci_move != '' and uci_move != 'ABORT' and guess_ok:
    ##board.push(chess.Move.from_uci(uci_move))
    ##uci_move = uci_move
        pass
    else:
        move_counter = move_counter - 1
        uci_move = 'ABORT'
        ponder_move = ''

    if info_str != '':
        print2(info_str)

    result_str = 'bestmove ' + uci_move + ' ponder ' + ponder_move
    print2(result_str)

    if log:
        log.write(info_str)
        log.write(result_str)
        log.write('\nready for next move!\n')
        log.flush()

    guess_ok = True

def get_orig_game_index(find_game):
    global orig_game_list
    found = False
    orig_index = 0
    i = 0

    while not found:
        if orig_game_list[i].headers == find_game.headers:
            orig_index = i
            found = True
        i = i + 1

    ##for game in orig_game_list:
    ##    if game.headers == find_game.headers:
    ##       orig_index = i
    ##   i = i + 1

    return orig_index

def newgame():
    global p_audio_comment
    global game_started
    global p_pgn_game_file
    global log_file_pgn_info
    global p_think_time
    global board
    global input_board
    global move_list
    global move_counter
    global info_handler
    global max_moves
    global pgn_game
    global pgn_file
    global game_list
    global game_counter
    global max_games
    global orig_game_list
    global fen
    global l_continue

    if move_counter <= 1 and game_started and max_moves > 1 and fen == '':
        move_counter = 0
        board       = get_start_pos(board)
        input_board = get_start_pos(input_board)
        return

    result = ''
    problem = ''
    event = ''
    white = ''
    black = ''
    orig_index = 0


    move_counter = 0
    max_moves    = 0
    j            = 0
    move_list    = []

    if game_counter == 0:
    ## reset list to all games
        game_counter = max_games
        game_list = orig_game_list.copy()

    ## get game from remaining games by specified sequence
    if p_game_sequence == 'random':
        game_index   = int(random.randint(0, game_counter - 1))
    elif p_game_sequence == 'forward':
        game_index   =  max_games - game_counter
    elif p_game_sequence == 'backward':
        game_index   =  game_counter - 1
    else:
        game_index   = int(random.randint(0, game_counter - 1))

    if game_index < 0:
        game_index = 0

    if log:
        log.write('game index: %s\n' % str(game_index))

    if l_continue:
        pgn_game = game_list[game_index]

        if 'FEN' in pgn_game.headers:
            fen = pgn_game.headers['FEN']
        else:
            fen = ''

        if 'Event' in pgn_game.headers:
            event = pgn_game.headers['Event']
        else:
            event = ''

        if 'Black' in pgn_game.headers:
            black = pgn_game.headers['Black']
        else:
            black = ''

        if 'White' in pgn_game.headers:
            white = pgn_game.headers['White']
            if 'Mate in' in white:
                problem = white
            else:
                problem = ''
        else:
            white = ''
            problem = ''

        if 'Result' in pgn_game.headers:
            result = pgn_game.headers['Result']
        else:
            result = ''

        if 'WhiteElo' in pgn_game.headers:
            white_elo = pgn_game.headers['WhiteElo']
        else: white_elo = '?'

        if 'BlackElo' in pgn_game.headers:
            black_elo = pgn_game.headers['BlackElo']
        else: black_elo = '?'

        if log:
            log.write('FEN: %s\n' % str(fen))
    ## delete this game from current list
    if l_continue:
        del game_list[game_index]
        game_counter = game_counter - 1


    ## create move list of the new game
    move_counter = 0
    max_moves    = 0

    ## create new game board
    board       = get_start_pos(board)
    input_board = get_start_pos(input_board)

    i = 0
    if l_continue:
        for move in pgn_game.mainline_moves():   ## molli: later mainline_moves() for python-chess 25
            i = i + 1
            move_list.append(move.uci())

    max_moves = i

    if log:
        log.write('Next game no. from PGN: %s\n' % str(game_index))
        log.write('Number of moves: %s\n' % str(max_moves))
        log.flush()

    ## log current pgn game infos for picochess control in main program

    try:
        log_p = open(log_file_pgn_info, 'w')
    except OSError:
        log_p = ''
        print("# Could not create user log file")

    game_started = True

    if p_audio_comment:
        play_audio()

    if log_p:

        if l_continue:
            orig_index = get_orig_game_index(pgn_game)

            if p_pgn_game_file == '/opt/picochess/games/last_game.pgn':
                event = 'LastGame'
            elif '/opt/picochess/games/picochess_game_1.pgn' == p_pgn_game_file:
                event = 'SaveGame_1'
            elif '/opt/picochess/games/picochess_game_2.pgn' == p_pgn_game_file:
                event = 'SaveGame_2'
            elif '/opt/picochess/games/picochess_game_3.pgn' == p_pgn_game_file:
                event = 'SaveGame_3'
            elif 'PicoChess Game' in event:
                event = 'PicoGame' + str(orig_index+1)
            elif 'Online' in event:
                event = 'PicoOnlineGame' + str(orig_index+1)
        else:
            event = 'File-Error'

        log_p.write("PGN_GAME=%s\n" % event)
        log_p.flush()

        log_p.write("PGN_GAME_INDEX=%s\n" % str(orig_index+1))
        log_p.flush()

        log_p.write("PGN_PROBLEM=%s\n" % problem)
        log_p.flush()

        log_p.write("PGN_White=%s\n" % white)
        log_p.flush()

        log_p.write("PGN_Black=%s\n" % black)
        log_p.flush()

        log_p.write("PGN_FEN=%s\n" % fen)
        log_p.flush()

        log_p.write("PGN_RESULT=%s\n" % result)
        log_p.flush()

        log_p.write("PGN_White_ELO=%s\n" % white_elo)
        log_p.flush()

        log_p.write("PGN_Black_ELO=%s\n" % black_elo)
        log_p.flush()

def push_uci_move(uci_move):
    if log:
        log.write('Received an uci move: %s\n' % uci_move)
        log.flush()

def get_start_pos(board):
    global fen

    if fen:
        board = chess.Board()
        board.set_fen(fen)
        return board
    else:
        board = chess.Board()
        return board

def set_move_counter_from_fen(last_move):
    global input_board
    global move_counter
    global board
    global max_moves
    s_board = None

    current_move = ''
    found = False
    s_board = get_start_pos(s_board)

    count = 0

    while not(found) and count < max_moves:
        fen1 = s_board.fen()
        fen2 = input_board.fen()
        if count == 0:
            current_move = ''
        else:
            current_move = move_list[count-1]
        if log:
            log.write('Input last move: %s\n' % str(last_move))
            log.write('Current search move: %s\n' % str(current_move))

        if fen1 == fen2 and str(last_move) == str(current_move):
            found = True

            if log:
                log.write('Found FEN position in game\n')
                log.write('Old move_counter: %s\n' % str(move_counter))
                log.write('New move_counter: %s\n' % str(count))
                log.flush()
            move_counter = count
            board = input_board

        move = move_list[count]
        s_board.push(chess.Move.from_uci(move))
        count = count + 1

    return(found)

###############################################################
# Main program loop: process input string (line)
###############################################################

pygame.mixer.init()

while True:

    line = ''

    sys.stdout.flush()

    try:
        line = input()
    except KeyboardInterrupt:    # XBoard sends Control-C characters, so these must be caught
        if not is_uci:
            pass        #   Otherwise Python would quit.

    mstart_t = int(time.time())

    if line:
        if log:
            log.write('*** ' + line + '\n')
            log.flush()
        if line == 'quit':
            if flag_audio_playing:
                pygame.mixer.music.stop()

            if is_uci and p_pgn_game_file and pgn_file != '' and game_started:
                pgn_file.close()

                game_started = False
            is_uci = False
            sys.exit(0)
        elif line == 'new':
            newgame()
        elif line == 'uci':
            if is_uci and game_started and p_audio_comment:
                if flag_audio_playing:
                    if log:
                        log.write("pause audio\n")
                        log.flush()
                    pygame.mixer.music.pause()
                    flag_audio_playing = False
                else:
                    pygame.mixer.music.unpause()
                    flag_audio_playing = True
                    if log:
                        log.write("continue audio\n")
                        log.flush()

            is_uci = True

            print2("id name %s" % engine_name)
            print2("id author Molli")
            print2("option name pgn_game_file type string default /opt/picochess/games/last_game.pgn")
            print2("option name game_sequence type string default random")
            print2("option name pgn_audio_file type string default ")
            print2("option name max_guess type spin default 0 min 0 max 10")
            print2("option name engine_path type string default /opt/picochess/engines/aarch64/a-stockf")
            print2("option name think_time type spin default 3 min 0 max 60")
            print2("uciok")

        elif line == 'ucinewgame':
            newgame()

        elif 'position startpos moves' in line:
            mm = line.split()[3:]

            input_board = chess.Board()

            for mo in mm:   ## get last move and set current position
                input_board.push(chess.Move.from_uci(mo))
                last_move = mo

            if log:
                log.write("input move %s\n" % last_move)
                log.write("game_started %s\n" % game_started)
                log.flush()

            guess_ok = set_move_counter_from_fen(last_move)

            if game_started:
                push_uci_move(last_move)

        elif 'position startpos' in line:
            input_board = chess.Board()
            move_counter = 0
            ##game_started = True

            if log:
                log.write("position startpos ready\n")
                log.flush()

        elif 'position fen' in line:
            ##game_started = True
            if line == last_fen_line:
                if log:
                    log.write("WARNING: input fen (double)")
                    log.flush()
            last_fen_line = line

            if line.split()[6] == 'moves':	# Shredder FEN
                line = ' '.join(line.split()[:6] + ['0', '1'] + line.split()[6:])
            ff = line.split()[2:8]
            mm = line.split()[9:]
            ff = ' '.join(ff)

            last_move = ''

            input_board = chess.Board(ff)

            for mo in mm:   ## get last move and set current position
                input_board.push(chess.Move.from_uci(mo))
                last_move = mo

            if log:
                log.write("input move %s\n" % last_move)
                log.flush()

            if last_move != '':
                guess_ok = set_move_counter_from_fen(last_move)
                push_uci_move(last_move)

        elif 'setoption name pgn_audio_file value' in line:
            p_audio_comment = str(line.split()[4])
            print2("# pgn_audio_file: %s" %  p_audio_comment)

        elif 'setoption name pgn_game_file value' in line:
            p_pgn_game_file = str(line.split()[4])
            print2("# pgn_game_file: %s" %  p_pgn_game_file)

        elif 'setoption name game_sequence value' in line:
            p_game_sequence = str(line.split()[4])
            print2("# game sequence: %s" %  p_game_sequence)

        elif 'setoption name engine_path value' in line:
            p_engine_path = str(line.split()[4])
            print2("# engine_path: %s" %  p_engine_path)

        elif 'setoption name think_time value' in line:
            p_think_time = int(line.split()[4])
            print2("# think_time: %s" %  p_think_time)

        elif 'setoption name max_guess value' in line:
            max_guess = int(line.split()[4])
            print2("# max_guess: %s" %  max_guess)

        elif line == 'isready':
            j = 0
            ## load pgn file
            if p_pgn_game_file:
                l_continue = True
                try:
                    pgn_file = open(p_pgn_game_file)
                except OSError:
                    l_continue = False
                    print2("# Error: opening file %s"  %  p_pgn_game_file)

                if l_continue:
                    while True:
                        game = chess.pgn.read_game(pgn_file)
                        if game == None:
                            break
                        j=j+1
                        max_games = j
                        game_list.append(game)

                orig_game_list = game_list.copy()
                if max_games > 0:
                    game_counter = max_games

                if log:
                    log.write('Game(s) from PGN file loaded.\n')
                    log.write('max_games %s\n' % str(max_games))
                    log.write('game_counter %s\n' % str(game_counter))
                    log.flush()

            ##start engine
            if p_engine_path != '' and p_think_time > 0:

                think_time = p_think_time * 1000

            if is_uci:
                print2("id name %s" % engine_name)
                print2("readyok")

        elif 'setboard' in line:
            pass

        elif line[:2] == 'go':
            if log:
                log.write('pgn_engine go called')
            pub_move()

        elif line == 'force':
            if is_uci:
                pub_move()

        elif line == 'stop':
            ## if pygame.mixer.music.get_busy():
            if flag_audio_playing:
                pygame.mixer.music.pause()
                flag_audio_playing = False
            else:
                pygame.mixer.music.unpause()
                flag_audio_playing = True

            if log:
                log.write("Stop audio\n")
                log.flush()

        elif line == '?':
            print("move", uci_move)
            if log:
                log.write("move %s\n" % uci_move)
                log.flush()
        else:
            if len(line) == 4 and is_uci and game_started:
                if line[0] in abc and line[2] in abc and line[1] in nn and line[3] in nn:
                    move = line
                    push_uci_move(move) ## just for testing
