lappend auto_path json
package require json::write

source wapp.tcl

if {$argc < 2} {
    puts "Usage: ./tcscid wapp_get_games.tcl --server <port>"
    puts "Example: ./tcscid wapp_get_games.tcl --server 7778"
    exit
}

proc search {fen} {
    puts stderr "searching for $fen"
    set TIME_start [clock clicks -milliseconds]

    set search_result ""

    # initialize board position with the FEN
    if [catch {set fenOk [sc_game startBoard $fen]}] {
        # invalid FEN
        puts stderr "Invalid FEN <$fen>"
        append search_result "{\"data\":\[\]}"
        return $search_result
    }

    sc_search board 2 E False False

    append search_result "{\"data\":\["
    # initialize gameNum with the first game in the filter
    set gameNum [sc_filter first]
    set i 0
    set MAX_GAMES 50
    while {$gameNum != 0 && $i < $MAX_GAMES} {
        incr i
        # load game
        sc_game load $gameNum
        # set gameNum to the next game in the filter
        set gameNum [sc_filter next]

        set white [sc_game tags get White]
        set black [sc_game tags get Black]
        set year [sc_game tags get Year]
        set event [sc_game tags get Event]
        set result [sc_game tags get Result]
        set whiteElo [sc_game tags get WhiteElo]
        set blackElo [sc_game tags get BlackElo]
        # the following tags are currently not used
        #set site [sc_game tags get Site]
        #set date [sc_game tags get Date]

        switch $result {
            1 {
                set result 1-0
            }
            0 {
                set result 0-1
            }
            = {
                set result 1/2-1/2
            }
            default {
                set result *
            }
        }
        if {$whiteElo == 0} {
            set whiteElo ""
        } else {
            set whiteElo ($whiteElo)
        }
        if {$blackElo == 0} {
            set blackElo ""
        } else {
            set blackElo ($blackElo)
        }
        # game information as JSON
        append search_result "{"
        append search_result "\"white\":\"$white $whiteElo\",\"black\":\"$black $blackElo\",\"result\":\"$result\",\"event\":\"$year, $event\","
        append search_result "\"pgn\":"
        append search_result [::json::write string [sc_game pgn]]
        append search_result "}"
        if {$gameNum != 0 && $i < $MAX_GAMES} {
            append search_result ",\n"
        } else {
            append search_result "\n"
        }
    }
    append search_result "]}"

    set TIME_taken [expr [clock clicks -milliseconds] - $TIME_start]
    puts stderr "search took $TIME_taken ms"
    return $search_result
}

set baseName games
puts "Opening database $baseName"
if [catch {set baseNum [sc_base open -readonly $baseName]}] {
    puts "Error: could not open database $baseName"
    exit
}

proc wapp-default {} {
    wapp-allow-xorigin-params
    wapp-reply-extra Access-Control-Allow-Origin *
    if {[wapp-param-exists action] && [wapp-param action]=="get_games" && [wapp-param-exists fen]} {
        wapp-trim {[search [wapp-param fen]]}
    } else {
        wapp-trim "{}"
    }
}
wapp-start $argv

sc_base close $baseNum
