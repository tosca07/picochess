PicoChess V3.1
============

* Support of different eboard types (DGT,  Certabo, Chesslink, ChessNut) - this is so cool!

* Different ini-files for retro, modern and favorite engines and corresponding menu entries

* Support of Windows engines (see Dirks S. image via box86 & wine)

* Auto ELO feature for engines supporting the UCI ELO settings

* Web themes: light, dark

* RetroSpeed for mame engines via picochess.ini

* local game and opening book database server which Gerhard added so that we now have this information again provided in the web server 

Internal changes:
* Unified sources for all devices (before we had different sources for the PicochessWeb version  (most important for me)

* Unified translation.py file (new  "web_text" tag for longer texts) eg.: 
if text_id == 'pleasewait': entxt=Dgt.DISPLAY_TEXT(web_text='Reboot: please wait', large_text='please wait', medium_text='pls wait', small_text='wait  ')

* Unified engines.ini (new "web" tag for longer engine names), see attached retro.ini eg.: 
 [mame/academy] 
 name = Mephisto Academy
 small = academ
 medium = Academy
 large = Mep.Academy
 web = Mephisto Academy
 elo = 1980
 levels = 10
 ponder/brain = n
 
* Lots of bug fixes (esp. for analysis mode, PGN information display in web server etc.)

* New (for PicoChessWeb) and alternative (for DGTPI/DGT3000 users) Beep sample sounds instead of internal beeper. For this I have created a new voice  „beeper“  which does not need a voice.ini entry (it is not a voice for announcing moves etc.) because it is activated via menu system ->  sound -> „sample“). This voice folder must be put into the /picochess/talker/en/ folder and consists of different sound samples for various events (eg after computer move has been played etc. You can here some of these sounds in my last video for the no eboard feature). The sound files are part of Gerhards repository but I have put it into my dropbox: https://www.dropbox.com/sh/thii2ty659qm29g/AADaiG_-z3IKavYh9eSvupUla?dl=0

* New "auto" theme option according to sunrise/set and the possibility to change it in the menu

* New no-eboard/web play only mode for playing without an attached eboard via the web server.

* Search nodes like search depth for NN strength restriction for eg. Leela (with node = 1 you can simulate the maia engine etc.)

* Retro speed option is now in menu, automatic restart of the (mame-) engine but keep in mind that you have to start a new game after changing the retro speed because of this engine new start as we have no FEN position setup at the moment (so better change it before starting a new game) 

* PGN Replay/Analysis and Guessing Game engine

i) Correct PGN header information (player names, elo) for the current game in web server. Fully automatic replay, you can define the replay speed in the corresponding uci file by specifying a higher or lower thinking time for the analysis engine). 
[AlphaZero1]
pgn_game_file  = /opt/picochess/engines/pgn_engine/pgn_games/alphazero_stockfish_2018.pgn
pgn_audio_file = /opt/picochess/engines/pgn_engine/pgn_audio/AnnaRudolph_AlphaZeroStockfish.ogg
max_guess= 0
engine_path = /opt/picochess/engines/armv7l/a-stockf
think_time = 1

Pause of audio commentary with II button, pause of fully automatic replay of the game: lever button 

ii) full support of guessing game functions when playing in no-eboard/Web Play mode  (automatic take back of wrong guessed moves, etc.)

* PicoTutor in no-eBoard/WebPlay“ mode

i) Get position evaluation by activating PicoCoach (again) because we can’t lift up and replace a piece (that’s the trigger for the tutor evaluation when playing with an eBoard).

ii) In emulation mode with retro/mame engines: support of automatic take back in case of a blunder (because we can’t take back moves the normal way in case of retro engines)






PicoChess V3.0
============

[![Join the chat at https://gitter.im/picochess/Lobby](https://badges.gitter.im/picochess/Lobby.svg)](https://gitter.im/picochess/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Stand alone chess computer based on [Raspberry Pi](http://www.raspberrypi.org/) and [DGT electronic chess board](http://www.dgtprojects.com/index.php/products/electronic-boards).

See [installation instructions](http://docs.picochess.org/en/latest/installation.html), [manual](http://docs.picochess.org), and [website](http://www.picochess.org).


This is an enhancement of the last main picochess version 09N and includes changes of my version 1.0, 2.01 and 3.0

IMPORTANT:
-------------------------------------------------------------------------------------------
This repository is only for code reference - it won't be a fully 3.1 working version because of the github restrictions (25MB each file and less than 100 files in one folder) so don't expect to be able to use this repository as a working picochess version because a lot of (non source) files are missing for a working V3 (eg. voice samples for V3 features, audio example samples for the replay of games using my pgn_engine or the mame emulator framework).
Further than that the software quality is no longer good - I used the "sledge hammer" in order to achieve some features and lots of global variables & functions are used. I started as an absolute python beginner almost 2 years ago so I would implement some features completly different today.

Installation:
-------------------------------------------------------------------------------------------
In addition to the standard Picochess set-up (see the Picochess 09N documentation) you need to do the following installation/modification steps:

- install audio lib pygame: sudo apt-get install python3-pygame
- Install telnet: sudo apt-get install telnet (don’t know if this is already installed by default)
- BERSERK: sudo pip3 install berserk (evtl. for the lichess client)
- mame emulator:  -- set Memory Split Factor >= 64GB
                  -- install the  packages  needed: sudo apt-get install git build-essential libsdl2-dev libsdl2-ttf-dev libfontconfig-dev qt5-  default
- Modification for the windows ssh comunication thanks to help of the community: I removed spur and paramiko: sudo pip3 uninstall spursudo pip3 uninstall paramiko, then updated them to their latest versions (spur-0.3.21 and paramiko-2.7.1): sudo pip3 install spur,sudo pip3 install paramiko, I then renamed /usr/local/lib/python3.7/dist-packages/spur/ssh.py as ssh.py0321 and placed the version with windows support (as suggested by Hasnul - thanks!) from the spur folder here: https://github.com/tfromme/spur.py 

-  python-chess bugfix modification for tournament  time controls:
Python Chess is installed on my system: /usr/local/lib/python3.7/dist-packages/chess
in file uci.py (for tournament setting):

def go 
...
Bug fix:
 if movestogo is not None and int(movestogo) > 0:
Instead of
 if movestogo is not None and movestogo > 0:


You can find more information in these follwong threads:

1. The hardware I use: https://groups.google.com/g/picochess/c/jC-EEwEd15M 

2. More about the features of the PicoChess V3 software: https://groups.google.com/g/picochess/c/HM2Dtzt6gic

3. More about my „enhanced uci engine“ concept which allows to easily integrate my PGN replay engine and online engines: https://groups.google.com/g/picochess/c/czHRxH9HLw4

4. The thread for the V3 image for the Raspebrry Pi (DGTPI and nonDGTPI versions):
https://groups.google.com/g/picochess/c/SpNFpp2Scw4


This is the (probably incomplete) change log of all changes from 1.0 on up to 3.0

Personal Picochess Versions Change Log
-------------------------------------------------------------------------------------------
 The following enhancements to the 0.9N version have been implemented:
        0.  Version set to 1.0 (finally ;-)
        1.  Voice announcements even if time < 1 minute
        2.  Possibility to continue playing even if one player runs out of time
        3.  Pre-Moves: Computer and user moves can be done in rapid sequence
            (no need to wait for registration of computer move). Even the
            own move could be played before computer move - it doesn't matter
        4.  New flexible ponder mode: no more checks if valid moves, position can
            be setup without any restrictions (of course it must be a legal one)
            Makes analysis and playing differenet variants much easier
        5.  Remote mode working again (without room handling, see menue.py)

-------------------------------------------------------------------------------------------
        6.  Version set to 2.0
        7.  Framework for adding (more or less funny) speech comments based on
            various events
        8.  Rolling display of time/score/depth/hintmove in Ponder On or Normal Mode
        9.  Continue directly after start with an interrupted game if board still shows
            last position by reading the last games pgn file
        10. New cool training mode with training options (with big thanks to Wilhelm!!!)
        11. Configuration parameters for all 1.00/2.00 enhancements in picochess.ini
        12. Various bug fixes (eg. pressing the outer buttons for quick restart
            instead of shutdown like it was intended, calc. error in evaluation)
            Again: big thanks to Wilhelm!
        13. Renaming of the play modes! Now we have:
            New mode name                                         Old mode name
            a5 NORMAL (rolling info display off by default)       NORMAL
            b5 PONDER ON (rolling info display on by default)     BRAIN
            c5 MOVE HINT                                          ANALYSIS
            d5 EVAL.SCORE                                         KIBITZ
            e5 OBSERVE                                            OBSERVE
            f5 ANALYSIS (flexible option on by default)           PONDER
            g5 TRAINING (this is new in 2.00)                       -
            h5 REMOTE (working again from 1.00 on)                REMOTE

-------------------------------------------------------------------------------------------
        14. Version set to 2.01
        15. Added possibility to change voice volume via menu and picochess.ini

-------------------------------------------------------------------------------------------
        16. Version set to 3.0 (a really big one ;-)
            I think most of the enhancements only make sense running on a Revelation II (or at least
            a DGTPI with better display capabilities. Especially on a Revelation II it is really fun
            to read game comments or the opening name etc. while this is exhausting on a DGTPI and awful
            on a standalone DGT Clock with its 8 chars)
            Some features (like tournament control or PicoTutor) even wouldn't correctly work on stand
            alone clocks together with picochess because the display can not show the correct time control
            setting.
            Furthermore additional libraries must be installed, a bug must be fixed in the python-chess
            code itself(!) for the tournament control option and you need additional engines for some
            of the new feature (don't ask me where to get them or where you can get an image etc.)
            !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            !!! Keep in mind: I did these enhancements in this Personal Version for my own pleasure
            !!! in order to have fun & play with picochess on my Revelation 2 - so it might be not
            !!! your cup of tea...
            !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        17. Support for Online Engines
             - Switch to Online Mode if online engine is choosen (engine name starts with
               Prefix 'Online')
             - Time control settings are taken from the online server challenge and are
               applied automatically as current time control settings#
             - Clocks start after first white and black moves. After this the player's time already
               starts with the annoucement of the best move and no longer when
               the computer move has been done by the user (other than that no real sync with server
               times has been implemented)
             - Online decrement: In order to better "sync" picochess times with online server times#
               you can subtract X seconds after each own move from your remaining game time in
               picochess.ini, default value is 0.9s
             - additional online info messages (login, seeking, opponent name, game result)
             - new online seek in case of 'start new game' event
             - Online move is automatically played in case of white = online opponent and clock starts
             - last move is published to online engine in case of game ending to inform the online
               server
             - online player names in pgn file(s) instead of engine or pico user name only
             - Online engines won't be saved in picochess.ini as last engine
             - picochess.ini "Online decrement" parameter can be overwritten in online uci files via parameter
               OnlineDecrement (just add "[DEFAULT]  OnlineDecrement = X"
             - still work in progress (don't ask me when they are ready to play...):
               - basic FICS online engine (for this TELNET must have been installed, default!?)
               - very basic lichess online engine (for this the BESERK package must have been installed)
       18. (Better) support for MAME emulated chess engines
             - requirement: new SDL libraries (probably different for BUSTER)
                            and Q5 library must have been installed
             - newer mame/mess versions do need BUSTER!
             - longer startup time for mame engines necessary, voice/sound end messages from mame engine
               last ending move is published to emulator engine in case of game end for specific engines
             - "engine setup" message because of longer initializing phase of mame chess engines
             - support for pico timecontrol setting in uci file settings according to mame engine levels
               (just define the UCI parameter PicoTimeControl X Y Z in your level settings) and time is set
               automatically after choosing a level
             - When switching back to non mame engine time settings are reset to last setting before it has been
               eventually changed by the uci setting (default time setting can be defined in picochess.ini
               via parameter def-timectrl when having a mame engine as last engine after startup)
             - automatic reset of the original time control settings after choosing a non mame/mess engine
             - mame engine should not be saved as last used engine on a DGTPI because of possible clock problems when
               starting mame engine directly after boot (very strange maybe a sync problem with dgtpicom lib!?)
       19. Finally: practical support of remote engines and local engines at the same time(!)
             - IMPORTANT! For windows server access an update of the spur and paraminko packages and a
               modification of the spur package are necessary (ssh.py must be replaced from a different repository)
             - name in engine.ini must start with prefix 'remote_'
             - implemented via standard ssh connection, just add the remote login infos
               in the corresponding parameters of picochess.ini and your remote engine in engines.ini
               and make sure SSH server is running on your remote computer (default on MacOS)
       20. Automatic takeback mode (only for mame engines) in case of a blunder move with active PicoTutor
            (PicoWatcher must be switched on)
             - Normally taking back moves when using mame engine is not possible so this is a nice feature for
               beginners (like me ;-) who often play against mame engines.
             - only the last blunder move can be taken back when using mame (of course this restriction is not
               valid for other native uci engines!)
       21. Bugfix: Set correct (old) engine (name) in case of engine error (very important for
                     new remote/online engines which sould easily fail if server is not available)
       22. Taking back moves: Now the next move which could be taken back is shown in display and
             in long notation format (good for old people like me ;-)
       23. After start up and new game events the current chosen engine is shown in the display
            (setting in display menu & config parameter in picochess.ini)
       24. Support for correct remaining game times for continued games from version 2 (finally!)
       25. Synthesized voice support for moves in WebServer (unfortunately works only in desktop
            browsers and in Android Firefox browser): Big thanks to Martin (author of the ingenious
            TuroChamp python engine) and deletion of the non working remote room button functionality
            Of course you can still use the remote play mode functionality (re)introduced since 2.0 and
            the new handling of remote engines)
       26. Replay of PGN games (semi automatic) via new engine
            - Semi automatic replay of saved pgn games with hint move/score evaluation by an analysis engine
              for a specific thinking period (time settings will be changed according to uci file and changed
              back automatically)
            - "Guess that move" game option for white or black (switch "guessing" sides by pressing the lever)
            - Additionally this pgn replay mode can be used to train opening books when setting
              an empty pgn file with name 'Book Test' and choosing a specific book in menu: just try and play
              a move you think belongs to the chosen book opening (makes more sense when you create specific books
              with a specific theme or famous player moves)
            - Furthermore an audio comment file for the pgn file can be specified and will be automatically
              played during the pgn game replay and can be manually started and stopped during the match
              (I did this because I have a (german) genious radio play "Nahrungsaufnahme während der Zeitnotphase"
               which is playing in real time during a tournament game. Now I can listen to the radio play and
               watch the game at the same time with picochess - how cool is that!?
            - PGN Replay engine settings won't be saved in picochess.ini as last engine 
        27. Enhancement of supported tags in pgn file: opening eco code, pico remaining times, pico time
            control setting
        28. For online-, emulation- and pgn-mode: Automatically switch off opening books (setting "no book"
            as book option)
        29. Override pgn location from picochess.ini in case the parameter 'location' is set to
            something different than 'auto' (you can use this if you always get a wrong auto location).
        30. Basic chess tutor functionality (even in case the choosen engine does not support
            score & hint moves like almost all mame emulated engines) with the following 3
            functions (disabled in Online mode)
            a) Pico Watcher (checks your moves and returns ??, ?, !?, ?!, !, !!)
               You can change the control limits for the evalutations in file picotutor_constants.py
            b) Pico Coach (gives position score and move hint(s) - just lift a piece and put it back into
               the same position)
            c) Pico Opening Explorer (displays current opening name (alternative) independet of the
               used opening book
        31. Tournament time control settings:
            Possible time control settings in picochess v3.0:
            time = m, time = g i, time = n g i  or time = n g1 i g2
            Examples:
            time = ... 7   (time per move, eg. m = 7 seconds)
                       5 0 (game time, eg. Blitz g = 5 min. and 0 seconds increment)
                       5 3 (game time g= 5 min. plus I = 3 sec. increment)
            Tournament time control settings: n moves in g1 minutes (plus I increment seconds) and rest
            of the game in g2 minutes
            time = ...
            new:   40 5 0 (n = 40 moves in g = 5 minutes)
            new:   40 5 3 ((n = 40 moves in g= 5 minutes with I = 3s Fischer inc.)
            new:   40 60 0 30 (n = 40 moves in g1 = 90 minutes, I = 0 seconds increment and rest of the game in g2 = 30 minutes)
            **************
            * Important: *
            **************
            for this a python-chess bug in 22.1 version must have been fixed to support the
            movestogo go command option correctly!
            If you have a higher python version look there (eg. 3.7 on BUSTER)
            (in file /usr/local/lib/python3.7/dist-packages/chess/uci.py:
             line 949  original:   if movestogo is not None and movestogo > 0:
                       changed to: if movestogo is not None and int(movestogo) > 0:
             That was not so easy to figure out...)
        32. Possibility to directly play an alternative move for the engine on the board after the engine move
            has been displayed in NORMAL mode (like in TRAINING mode or the DGT CENTAUR chess computer)
            (setting in menu and config para)
        33. Menu for saving, reading and continuing a game from pgn files (yes, finally!)
            *** IMPORTANT ***
            In order to load and continue a saved game you will need to use the webserver in order to set up
            the correct starting position of the game. For this you must open the webserver page BEFORE
            you read and restore the game or if not just use the sync button!
        34. Display of the book opening name(s) (function of the PicoTutor)
        35. New time control setting: Support of a specific max. search depth (with a fixed
            countdown movetime of 11:11 (unfortunately counting up the clock is not possible)
        36. Support of written game comments like it used to be in Boris or Sargon 2.5 MGS old chess computers
        37. Display of pgn event, players & result when loading an existing game
        38. Enhancements of REV2 and webserver display of moves/evaluation/depth/score
        39. Display of „new position“ message in case of analysis mode and user sets up
            a new position instead of playing an legal move (or in case he plays an illegal
            move which is seen as a new position)
        40. Removed use of vorbis ogg player because of audio play conflicts with sound from
            mame chess engines in picotalker.py and OS update problems and missing start/stop/pause
            functions(now pygame.mixer is used instead), see <https://www.pygame.org/docs/ref/mixer.html>
            install additional lib via: "sudo apt-get install python3-pygame"
        50. Three new voices (one with commentary): Daniel (eng.), Boris (eng. with commentary)
            and Gust (german). Additinal voice samples (eng./german) for the new picochess V3.0
            feature which can be put additionally in all existing voice folders
        51. Specific 'set pieces' sound (no voice) so you hear when something wrong with the board position
        52. Set opponent pgn player to 'Player B' instead of engine name and user name ro 'Player A'
            in case of 'Observe Mode'
        53. No more searchmoves in UCI 'go' command for the engine in case normal moves (exception:
            Alternative moves), otherwise this might cause problems with the use of internal
            engine books etc.(thanks to Rasmus for the hint)
        54. BugFix for Buster: Change of voice volume working again (big thanks to Wilhelm!)
        55. New (Fischer) "simulated" median move time levels: 5s, 10s, 15s, 20s, 30s, 60s, 90s
            (thanks to the schachcomputer.info Forum for this idea!)
        56. New "favorite engines" options: It is nice to have all 60 and more engines installed
            but it is a pain to select one out of these many engines...
            => new Favorite menu to keep your main and most often used engine separately.
               just put your favorite engines into the favorite.ini file liek you would do for the
               main engine list in engine.ini and put it in the correct egine directory - that's it
               *** IMPORTANT ***
               Engines in favorite.ini must also appear in engines.ini!!!
        57. BugFix: Continue game/load saved game and play in opposite board direction fixed
        58. Support of engine subfolders: you can now organize your engines in subfolders
            within the main engine folder (just specify the subfolder path in engines.ini in
            in front of the filename eg. [MAME/mm5] where MAME is a subfolder within the armv7l
            folder (thanks to Wilhelm for supporting the correct engine startup loading procedure!)
        59. Fix for the strange clock times reset "bug" when playing without a clock with just a board,
            PI and the webserver. With the voice move announcements of the webserver in V3.0 we even
            don't have to look at the webserver screen when playing... (thanks to Marcel Swidde for
            the fix in the picochess google groups forum)
        60. Position correction message after the "Set pieces" error message occurs the second time:
            assuming that you are lost and don't know where to put the piece to its correct position,
            picochess will tell you what is wrong and how to correct (if you have your PI hooked up
            into your WLAN you could just check the correct position with the webserver board display
            by just pressing the Sync button of the webserver).
            Picochess will stop the clocks and check its internal game position against the external
            DGT board position and will display two kind of correction messages:
            - Put w N f3 (=> put white night on f3)
            - Clear h5 (=> remove piece from h5)
            This will continue as long as the correct position has been set up.
