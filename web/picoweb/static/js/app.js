// if you don't want the last move of each player side to be "highlighted", set the variable highlight_move to
// HIGHLIGHT_OFF
const HIGHLIGHT_OFF = 0;
const HIGHLIGHT_ON = 1;
var highlight_move = HIGHLIGHT_ON;

const NAG_NULL = 0;
const NAG_GOOD_MOVE = 1;
//"""A good move. Can also be indicated by ``!`` in PGN notation."""
const NAG_MISTAKE = 2;
//"""A mistake. Can also be indicated by ``?`` in PGN notation."""
const NAG_BRILLIANT_MOVE = 3;
//"""A brilliant move. Can also be indicated by ``!!`` in PGN notation."""
const NAG_BLUNDER = 4;
//"""A blunder. Can also be indicated by ``??`` in PGN notation."""
const NAG_SPECULATIVE_MOVE = 5;
//"""A speculative move. Can also be indicated by ``!?`` in PGN notation."""
const NAG_DUBIOUS_MOVE = 6;
//"""A dubious move. Can also be indicated by ``?!`` in PGN notation."""

var simpleNags = {
    '1': '!',
    '2': '?',
    '3': '!!',
    '4': '??',
    '5': '!?',
    '6': '?!',
    '7': '&#9633',
    '8': '&#9632',
    '11': '=',
    '13': '&infin;',
    '14': '&#10866',
    '15': '&#10865',
    '16': '&plusmn;',
    '17': '&#8723',
    '18': '&#43; &minus;',
    '19': '&minus; &#43;',
    '36': '&rarr;',
    '142': '&#8979',
    '146': 'N'
};

var speechAvailable = true
if (typeof speechSynthesis === "undefined") {
    speechAvailable = false
}
if (speechAvailable) {
    var myvoice = "";
    var voices = speechSynthesis.getVoices();
    // for Safari we need to pick an English voice explicitly, otherwise the system default is used
    for (i = 0; i < voices.length; i++) {
        if (voices[i].lang == "en-US") {
            myvoice = voices[i];
            break;
        }
    }
}

function talk(text) {
    if (speechAvailable) {
        var msg = new SpeechSynthesisUtterance(text);
        msg.lang = "en-US";
        if (myvoice != "") {
            msg.voice = myvoice;
        }
        // window.speechSynthesis.speak(msg);
    }
}

talk("Hello, welcome to Picochess!");

function saymove(move, board) {
    var pnames = {
        "p": "pawn",
        "n": "knight",
        "b": "bishop",
        "r": "rook",
        "q": "queen",
        "k": "king",
    };
    talk(pnames[move.piece] + " from " + move.from + " to " + move.to + ".");
    if (move.color == "b") {
        var sidm = "Black";
    } else {
        var sidm = "White";
    }
    if (move.flags.includes("e")) {
        talk("Pawn takes pawn.");
    } else if (move.flags.includes("c")) {
        talk(pnames[move.piece] + " takes " + pnames[move.captured] + ".");
    } else if (move.flags.includes("k")) {
        talk(sidm + " castles kingside.");
    } else if (move.flags.includes("q")) {
        talk(sidm + " castles queenside.");
    }

    if (board.in_checkmate()) {
        talk("Checkmate!");
    } else if (board.in_check()) {
        talk("Check!");
    }
}

const NAG_FORCED_MOVE = 7;
const NAG_SINGULAR_MOVE = 8;
const NAG_WORST_MOVE = 9;
const NAG_DRAWISH_POSITION = 10;
const NAG_QUIET_POSITION = 11;
const NAG_ACTIVE_POSITION = 12;
const NAG_UNCLEAR_POSITION = 13;
const NAG_WHITE_SLIGHT_ADVANTAGE = 14;
const NAG_BLACK_SLIGHT_ADVANTAGE = 15;

//# TODO: Add more constants for example from
//# https://en.wikipedia.org/wiki/Numeric_Annotation_Glyphs

const NAG_WHITE_MODERATE_COUNTERPLAY = 132;
const NAG_BLACK_MODERATE_COUNTERPLAY = 133;
const NAG_WHITE_DECISIVE_COUNTERPLAY = 134;
const NAG_BLACK_DECISIVE_COUNTERPLAY = 135;
const NAG_WHITE_MODERATE_TIME_PRESSURE = 136;
const NAG_BLACK_MODERATE_TIME_PRESSURE = 137;
const NAG_WHITE_SEVERE_TIME_PRESSURE = 138;
const NAG_BLACK_SEVERE_TIME_PRESSURE = 139;

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

var boardStatusEl = $('#BoardStatus'),
    dgtClockStatusEl = $('#DGTClockStatus'),
    dgtClockTextEl = $('#DGTClockText'),
    pgnEl = $('#pgn');
moveListEl = $('#moveList')

var gameHistory, fenHash, currentPosition;
const SERVER_NAME = location.hostname
const OBOCK_SERVER_PREFIX = 'http://' + SERVER_NAME + ':7777';
const GAMES_SERVER_PREFIX = 'http://' + SERVER_NAME + ':7778';

fenHash = {};

currentPosition = {};
currentPosition.fen = START_FEN;

gameHistory = currentPosition;
gameHistory.gameHeader = '';
gameHistory.result = '';
gameHistory.variations = [];

var setupBoardFen = START_FEN;
var dataTableFen = START_FEN;
var chessGameType = 0; // 0=Standard ; 1=Chess960
var computerside = ""; // color played by the computer

function removeHighlights() {
    if (highlight_move == HIGHLIGHT_ON) {
        chessground1.set({ lastMove: [] });
    }
}

function highlightBoard(ucimove, play) {
    if (highlight_move == HIGHLIGHT_ON) {
        var move = ucimove.match(/.{2}/g);
        chessground1.set({ lastMove: [move[0], move[1]] });
    }
}

function removeArrow() {
    chessground1.setShapes([]);
}

function addArrow(ucimove, play) {
    var move = ucimove.match(/.{2}/g);
    var brush = 'green';
    if (play === 'computer') {
        brush = 'yellow';
    }
    if (play === 'review') {
        brush = 'blue';
    }
    var shapes = { orig: move[0], dest: move[1], brush: brush };
    chessground1.setShapes([shapes]);
}

function figurinizeMove(move) {
    if (!move) { return; }
    move = move.replace('N', '&#9816;');
    move = move.replace('B', '&#9815;');
    move = move.replace('R', '&#9814;');
    move = move.replace('K', '&#9812;');
    move = move.replace('Q', '&#9813;');
    move = move.replace('X', '&#9888;'); // error code
    return move;
}

function isLightTheme() {
    var bgcolor = $('body').css("background-color")
    const [r, g, b, a] = bgcolor.match(/[\d\.]+/g).map(Number);
    return r > 127 && g > 127 && b > 127;
}

var bookDataTable = $('#BookTable').DataTable({
    'processing': false,
    'paging': false,
    'info': false,
    'searching': false,
    'sScrollY': '168px',
    'order': [
        [1, 'desc']
    ],
    'columnDefs': [{
        className: 'dt-center zero-border-right bookMoves',
        'targets': 0
    }, {
        className: 'dt-right zero-border-right',
        'targets': 1
    }],
    'ajax': {
        'url': OBOCK_SERVER_PREFIX + '/query',
        'dataSrc': 'data',
        'data': function (d) {
            d.action = 'get_book_moves';
            d.fen = dataTableFen;
        }
    },
    'columns': [
        {
            data: 'move',
            render: function (data, type, row) {
                if (currentPosition) {
                    var tmp_board = new Chess(currentPosition.fen, chessGameType);
                    move = tmp_board.move({ from: data.slice(0, 2), to: data.slice(2, 4), promotion: data.slice(4) });
                    if (move) {
                        return figurinizeMove(move.san);
                    }
                }
                return data;
            }
        },
        { data: 'count', render: $.fn.dataTable.render.number(',', '.') },
        {
            data: 'draws',
            render: function (data, type, row) { return "" },
            createdCell: function (td, cellData, rowData, row, col) {
                var canvas = jQuery("<canvas id=\"white_draws_black\"></canvas>");
                canvas.appendTo(jQuery(td));

                ctx = $(canvas).get(0).getContext("2d");
                ctx.fillStyle = '#bfbfbf'; // border color for dark theme
                if (isLightTheme()) {
                    // border color for light theme
                    ctx.fillStyle = '#4f4f4f';
                }
                ctx.fillRect(0, 0, 300, 150); // border
                var height = 130;
                var maxWidth = 298;
                var top = 10
                whiteWins = rowData['whitewins']
                whiteWidth = maxWidth * whiteWins / 100;
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(1, top, whiteWidth, height); // white wins
                draws = cellData;
                if ((100 - whiteWins - draws) == 1) { // take care of rounding errors
                    draws++;
                }
                drawsWidth = maxWidth * draws / 100;
                ctx.fillStyle = '#bfbfbf';
                ctx.fillRect(whiteWidth + 1, top, drawsWidth, height); // draws
                ctx.fillStyle = '#000000';
                ctx.fillRect(whiteWidth + drawsWidth + 1, top, maxWidth - whiteWidth - drawsWidth, height); // black wins
            },
        },
    ]
});

var gameDataTable = $('#GameTable').DataTable({
    'processing': false,
    'paging': false,
    'info': false,
    'searching': false,
    'sScrollY': '168px',
    'ordering': false,
    'select': { items: 'row', style: 'single', toggleable: false },
    'columnDefs': [{
        className: 'result',
        'targets': 2
    }],
    'ajax': {
        'url': GAMES_SERVER_PREFIX + '/query',
        'dataSrc': 'data',
        'data': function (d) {
            d.action = 'get_games';
            d.fen = dataTableFen;
        },
        'error': function (xhr, error, thrown) {
            console.warn(xhr);
        }
    },
    'columns': [
        { data: 'white' },
        { data: 'black' },
        { data: 'result', render: function (data, type, row) { return data.replace('1/2-1/2', '\u00BD'); } },
        { data: 'event' }
    ]
});

gameDataTable.on('select', function (e, dt, type, indexes) {
    var data = gameDataTable.rows(indexes).data().pluck('pgn')[0].split("\n");
    loadGame(data);
    updateStatus();
    removeHighlights();
});

// do not pick up pieces if the game is over
// only pick up pieces for the side to move
function createGamePointer() {
    var tmpGame;

    if (currentPosition && currentPosition.fen) {
        tmpGame = new Chess(currentPosition.fen, chessGameType);
    }
    else {
        tmpGame = new Chess(setupBoardFen, chessGameType);
    }
    return tmpGame;
}

function stripFen(fen) {
    var strippedFen = fen.replace(/\//g, '');
    strippedFen = strippedFen.replace(/ /g, '');
    return strippedFen;
}

String.prototype.trim = function () {
    return this.replace(/\s*$/g, '');
};

function WebExporter(columns) {
    this.lines = [];
    this.columns = columns;
    this.current_line = '';
    this.flush_current_line = function () {
        if (this.current_line) {
            this.lines.append(this.current_line.trim());
            this.current_line = '';
        }
    };

    this.write_token = function (token) {
        if (this.columns && this.columns - this.current_line.length < token.length) {
            this.flush_current_line();
        }
        this.current_line += token;
    };

    this.write_line = function (line) {
        this.flush_current_line();
        this.lines.push(line.trim());
    };

    this.start_game = function () { };

    this.end_game = function () {
        this.write_line();
    };

    this.start_headers = function () { };

    this.end_headers = function () {
        this.write_line();
    };

    this.start_variation = function () {
        this.write_token('<span class="gameVariation"> [ ');
    };

    this.end_variation = function () {
        this.write_token(' ] </span>');
    };

    this.put_starting_comment = function (comment) {
        this.put_comment(comment);
    };

    this.put_comment = function (comment) {
        this.write_token('<span class="gameComment"><a href="#" class="comment"> ' + comment + ' </a></span>');
    };

    this.put_nags = function (nags) {
        if (nags) {
            nags = nags.sort();

            for (var i = 0; i < nags.length; i++) {
                this.put_nag(nags[i]);
            }
        }
    };

    this.put_nag = function (nag) {
        var int_nag = parseInt(nag);
        if (simpleNags[int_nag]) {
            this.write_token(" " + simpleNags[int_nag] + " ");
        }
        else {
            this.write_token("$" + String(nag) + " ");
        }
    };

    this.put_fullmove_number = function (turn, fullmove_number, variation_start) {
        if (turn === 'w') {
            this.write_token(String(fullmove_number) + ". ");
        }
        else if (variation_start) {
            this.write_token(String(fullmove_number) + "... ");
        }
    };

    this.put_move = function (board, m) {
        var old_fen = board.fen();
        var tmp_board = new Chess(old_fen, chessGameType);
        var out_move = tmp_board.move(m);
        var fen = tmp_board.fen();
        var stripped_fen = stripFen(fen);
        if (!out_move) {
            console.warn('put_move error');
            console.log(board.ascii());
            console.log(board.moves());
            console.log(tmp_board.ascii());
            console.log(m);
            out_move = { 'san': 'X' + m.from + m.to };
        }
        this.write_token('<span class="gameMove' + (board.fullmove_number) + '"><a href="#" class="fen" data-fen="' + fen + '" id="' + stripped_fen + '"> ' + figurinizeMove(out_move.san) + ' </a></span>');
    };

    this.put_result = function (result) {
        this.write_token(result + " ");
    };

    // toString override
    this.toString = function () {
        if (this.current_line) {
            var tmp_lines = this.lines.slice(0);
            tmp_lines.push(this.current_line.trim());

            return tmp_lines.join("\n").trim();
        }
        else {
            return this.lines.join("\n").trim();
        }
    };
}

function PgnExporter(columns) {
    this.lines = [];
    this.columns = columns;
    this.current_line = "";
    this.flush_current_line = function () {
        if (this.current_line) {
            this.lines.append(this.current_line.trim());
            this.current_line = "";
        }
    };

    this.write_token = function (token) {
        if (this.columns && this.columns - this.current_line.length < token.length) {
            this.flush_current_line();
        }
        this.current_line += token;
    };

    this.write_line = function (line) {
        this.flush_current_line();
        this.lines.push(line.trim());
    };

    this.start_game = function () { };

    this.end_game = function () {
        this.write_line();
    };

    this.start_headers = function () { };

    this.put_header = function (tagname, tagvalue) {
        this.write_line("[{0} \"{1}\"]".format(tagname, tagvalue));
    };

    this.end_headers = function () {
        this.write_line();
    };

    this.start_variation = function () {
        this.write_token("( ");
    };

    this.end_variation = function () {
        this.write_token(") ");
    };

    this.put_starting_comment = function (comment) {
        this.put_comment(comment);
    };

    this.put_comment = function (comment) {
        this.write_token("{ " + comment.replace("}", "").trim() + " } ");
    };

    this.put_nags = function (nags) {
        if (nags) {
            nags = nags.sort();

            for (var i = 0; i < nags.length; i++) {
                this.put_nag(nags[i]);
            }
        }
    };

    this.put_nag = function (nag) {
        this.write_token("$" + String(nag) + " ");
    };

    this.put_fullmove_number = function (turn, fullmove_number, variation_start) {
        if (turn === 'w') {
            this.write_token(String(fullmove_number) + ". ");
        }
        else if (variation_start) {
            this.write_token(String(fullmove_number) + "... ");
        }
    };

    this.put_move = function (board, m) {
        var tmp_board = new Chess(board.fen(), chessGameType);
        var out_move = tmp_board.move(m);
        if (!out_move) {
            console.warn('put_move error');
            console.log(tmp_board.ascii());
            console.log(m);
            out_move = { 'san': 'X' + m.from + m.to };
        }
        this.write_token(out_move.san + " ");
    };

    this.put_result = function (result) {
        this.write_token(result + " ");
    };

    // toString override
    this.toString = function () {
        if (this.current_line) {
            var tmp_lines = this.lines.slice(0);
            tmp_lines.push(this.current_line.trim());

            return tmp_lines.join("\n").trim();
        }
        else {
            return this.lines.join("\n").trim();
        }
    };
}

function exportGame(root_node, exporter, include_comments, include_variations, _board, _after_variation) {
    if (_board === undefined) {
        _board = new Chess(root_node.fen, chessGameType);
    }

    // append fullmove number
    if (root_node.variations && root_node.variations.length > 0) {
        _board.fullmove_number = Math.ceil(root_node.variations[0].half_move_num / 2);

        var main_variation = root_node.variations[0];
        exporter.put_fullmove_number(_board.turn(), _board.fullmove_number, _after_variation);
        exporter.put_move(_board, main_variation.move);
        if (include_comments) {
            exporter.put_nags(main_variation.nags);
            // append comment
            if (main_variation.comment) {
                exporter.put_comment(main_variation.comment);
            }
        }
    }

    // Then export sidelines.
    if (include_variations && root_node.variations) {
        for (var j = 1; j < root_node.variations.length; j++) {
            var variation = root_node.variations[j];
            exporter.start_variation();

            if (include_comments && variation.starting_comment) {
                exporter.put_starting_comment(variation.starting_comment);
            }
            exporter.put_fullmove_number(_board.turn(), _board.fullmove_number, true);

            exporter.put_move(_board, variation.move);

            if (include_comments) {
                // Append NAGs.
                exporter.put_nags(variation.nags);

                // Append the comment.
                if (variation.comment) {
                    exporter.put_comment(variation.comment);
                }
            }
            // Recursively append the next moves.
            _board.move(variation.move);
            exportGame(variation, exporter, include_comments, include_variations, _board, false);
            _board.undo();

            // End variation.
            exporter.end_variation();
        }
    }

    // The mainline is continued last.
    if (root_node.variations && root_node.variations.length > 0) {
        main_variation = root_node.variations[0];

        // Recursively append the next moves.
        _board.move(main_variation.move);
        _after_variation = (include_variations && (root_node.variations.length > 1));
        exportGame(main_variation, exporter, include_comments, include_variations, _board, _after_variation);
        _board.undo();
    }
}

function writeVariationTree(dom, gameMoves, gameHistoryEl) {
    $(dom).html(gameHistoryEl.gameHeader + '<div class="gameMoves">' + gameMoves + ' <span class="gameResult">' + gameHistoryEl.result + '</span></div>');
}

// update the board position after the piece snap
// for castling, en passant, pawn promotion
function updateCurrentPosition(move, tmpGame) {
    var foundMove = false;
    if (currentPosition && currentPosition.variations) {
        for (var i = 0; i < currentPosition.variations.length; i++) {
            if (move.san === currentPosition.variations[i].move.san) {
                currentPosition = currentPosition.variations[i];
                foundMove = true;
            }
        }
    }
    if (!foundMove) {
        var __ret = addNewMove({ 'move': move }, currentPosition, tmpGame.fen());
        currentPosition = __ret.node;
        var exporter = new WebExporter();
        exportGame(gameHistory, exporter, true, true, undefined, false);
        writeVariationTree(pgnEl, exporter.toString(), gameHistory);
    }
}

var updateStatus = function () {
    var status = '';
    $('.fen').unbind('click', goToGameFen).one('click', goToGameFen);

    var moveColor = 'White';
    var tmpGame = createGamePointer();
    var fen = tmpGame.fen();

    var strippedFen = stripFen(fen);

    // squares for dark mode
    var whiteSquare = 'fa-square-o'
    var blackSquare = 'fa-square'
    if (isLightTheme()) {
        // squares for light mode
        whiteSquare = 'fa-square';
        blackSquare = 'fa-square-o';
    }
    if (tmpGame.turn() === 'b') {
        moveColor = 'Black';
        $('#sidetomove').html("<i class=\"fa " + whiteSquare + " fa-lg\"></i>");
    }
    else {
        $('#sidetomove').html("<i class=\"fa " + blackSquare + " fa-lg\"></i>");
    }

    // checkmate?
    if (tmpGame.in_checkmate() === true) {
        status = moveColor + ' (mate)';
    }
    // draw?
    else if (tmpGame.in_draw() === true) {
        status = moveColor + ' (draw)';
    }
    // game still on
    else {
        status = moveColor;
        // check?
        if (tmpGame.in_check() === true) {
            status += ' (check)';
        }
    }

    boardStatusEl.html(status);
    if (window.analysis) {
        analyze(true);
    }

    dataTableFen = fen;


    if ($('#' + strippedFen).position()) {
        moveListEl.scrollTop(0);
        var element = $('#' + strippedFen);
        var y_position = element.position().top;
        moveListEl.scrollTop(y_position);
        $(".fen").each(function () {
            $(this).removeClass('text-warning');
        });
        element.addClass('text-warning');
    }

    bookDataTable.ajax.reload();
    gameDataTable.ajax.reload();
};

function toDests(chess) {
    var dests = {};
    chess.SQUARES.forEach(function (s) {
        var ms = chess.moves({ square: s, verbose: true });
        if (ms.length)
            dests[s] = ms.map(function (m) { return m.to; });
    });
    return dests;
}

function toColor(chess) {
    return (chess.turn() === 'w') ? 'white' : 'black';
}

var onSnapEnd = async function (source, target) {
    stopAnalysis();
    var tmpGame = createGamePointer();

    if (!currentPosition) {
        currentPosition = {};
        currentPosition.fen = tmpGame.fen();
        gameHistory = currentPosition;
        gameHistory.gameHeader = '<h4>Player (-) vs Player (-)</h4><h5>Board game</h5>';
        gameHistory.result = '*';
    }

    var move = await getMove(tmpGame, source, target);

    updateCurrentPosition(move, tmpGame);
    updateChessGround();
    $.post('/channel', {
        action: 'move', fen: currentPosition.fen, source: source, target: target,
        promotion: move.promotion ? move.promotion : ''
    }, function (data) { });
    updateStatus();
};

async function promotionDialog(ucimove) {
    var move = ucimove.match(/.{2}/g);
    var source = move[0];
    var target = move[1];

    var tmpGame = createGamePointer();
    var move = await getMove(tmpGame, source, target);
    if (move !== null) {
        $.post('/channel', {
            action: 'promotion', fen: currentPosition.fen, source: source, target: target,
            promotion: move.promotion ? move.promotion : ''
        }, function (data) { });
    }
}

async function getMove(game, source, target) {
    let promotion = null
    if (isPromotion(game.get(source), target)) {
        chessground1.set({ animation: { enabled: false } })
        promotion = await getUserPromotion(target)
        chessground1.set({ animation: { enabled: true } })
    }

    return game.move({
        from: source,
        to: target,
        promotion: promotion
    });
}

function updateChessGround() {
    var tmpGame = createGamePointer();

    chessground1.set({
        fen: currentPosition.fen,
        turnColor: toColor(tmpGame),
        movable: {
            color: toColor(tmpGame),
            dests: toDests(tmpGame)
        }
    });
}

function playOtherSide() {
    return onSnapEnd;
}

var cfg3 = {
    movable: {
        color: 'white',
        free: false,
        dests: toDests(Chess())
    }
};

var chessground1 = new Chessground(document.getElementById('board'), cfg3);

chessground1.set({
    movable: { events: { after: playOtherSide() } }
});

$(window).resize(function () {
    chessground1.redrawAll();
});

function addNewMove(m, current_position, fen, props) {
    var node = {};
    node.variations = [];

    node.move = m.move;
    node.previous = current_position;
    node.nags = [];
    if (props) {
        if (props.comment) {
            node.comment = props.comment;
        }
        if (props.starting_comment) {
            node.starting_comment = props.starting_comment;
        }
    }

    if (current_position && current_position.previous) {
        node.half_move_num = node.previous.half_move_num + 1;
    }
    else {
        node.half_move_num = 1;
    }
    node.fen = fen;
    if ($.isEmptyObject(fenHash)) {
        fenHash['first'] = node.previous;
        node.previous.fen = setupBoardFen;
    }
    fenHash[node.fen] = node;
    if (current_position) {
        if (!current_position.variations) {
            current_position.variations = [];
        }
        current_position.variations.push(node);
    }
    return { node: node, position: current_position };
}

function loadGame(pgn_lines) {
    fenHash = {};

    var curr_fen;
    if (currentPosition) {
        curr_fen = currentPosition.fen;
    }
    else {
        curr_fen = START_FEN;
    }

    gameHistory.previous = null;
    currentPosition = {};
    var current_position = currentPosition;
    gameHistory = current_position;

    var game_body_regex = /(%.*?[\n\r])|(\{[\s\S]*?\})|(\$[0-9]+)|(\()|(\))|(\*|1-0|0-1|1\/2-1\/2)|([NBKRQ]?[a-h]?[1-8]?[\-x]?[a-h][1-8](?:=?[nbrqNBRQ])?[\+]?|--|O-O(?:-O)?|0-0(?:-0)?)|([\?!]{1,2})/g;
    var game_header_regex = /\[([A-Za-z0-9]+)\s+\"(.*)\"\]/;

    var line;
    var parsed_headers = false;
    var game_headers = {};
    var game_body = '';
    for (var j = 0; j < pgn_lines.length; j++) {
        line = pgn_lines[j];
        // Parse headers first, then game body
        if (!parsed_headers) {
            if ((result = game_header_regex.exec(line)) !== null) {
                game_headers[result[1]] = result[2];
            }
            else {
                parsed_headers = true;
            }
        }
        if (parsed_headers) {
            game_body += line + "\n";
        }
    }

    var tmpGame;
    if ('FEN' in game_headers && 'SetUp' in game_headers) {
        if ('Variant' in game_headers && 'Chess960' === game_headers['Variant']) {
            chessGameType = 1; // values from chess960.js
        } else {
            chessGameType = 0;
        }
        tmpGame = new Chess(game_headers['FEN'], chessGameType);
        setupBoardFen = game_headers['FEN'];
    }
    else {
        tmpGame = new Chess();
        setupBoardFen = START_FEN;
        chessGameType = 0;
    }

    var board_stack = [tmpGame];
    var variation_stack = [current_position];
    var last_board_stack_index;
    var last_variation_stack_index;

    var in_variation = false;
    var starting_comment = '';

    var result;
    var lastmove;
    while ((result = game_body_regex.exec(game_body)) !== null) {

        var token = result[0];
        var comment;

        if (token === '1-0' || token === '0-1' || token === '1/2-1/2' || token === '*') {
            game_headers['Result'] = token;
        }
        else if (token[0] === '{') {
            last_variation_stack_index = variation_stack.length - 1;

            comment = token.substring(1, token.length - 1);
            comment = comment.replace(/\n|\r/g, " ");

            if (in_variation || !variation_stack[last_variation_stack_index].previous) {
                if (variation_stack[last_variation_stack_index].comment) {
                    variation_stack[last_variation_stack_index].comment = variation_stack[last_variation_stack_index].comment + " " + comment;
                }
                else {
                    variation_stack[last_variation_stack_index].comment = comment;
                }
                comment = undefined;
            }
            else {
                if (starting_comment.length > 0) {
                    comment = starting_comment + " " + comment;
                }
                starting_comment = comment;
                comment = undefined;
            }
        }
        else if (token === '(') {
            last_board_stack_index = board_stack.length - 1;
            last_variation_stack_index = variation_stack.length - 1;

            if (variation_stack[last_variation_stack_index].previous) {
                variation_stack.push(variation_stack[last_variation_stack_index].previous);
                last_variation_stack_index += 1;
                board_stack.push(Chess(variation_stack[last_variation_stack_index].fen));
                in_variation = false;
            }
        }
        else if (token === ')') {
            if (variation_stack.length > 1) {
                variation_stack.pop();
                board_stack.pop();
            }
        }
        else if (token[0] === '$') {
            variation_stack[variation_stack.length - 1].nags.push(token.slice(1));
        }
        else if (token === '?') {
            variation_stack[variation_stack.length - 1].nags.push(NAG_MISTAKE);
        }
        else if (token === '??') {
            variation_stack[variation_stack.length - 1].nags.push(NAG_BLUNDER);
        }
        else if (token === '!') {
            variation_stack[variation_stack.length - 1].nags.push(NAG_GOOD_MOVE);
        }
        else if (token === '!!') {
            variation_stack[variation_stack.length - 1].nags.push(NAG_BRILLIANT_MOVE);
        }
        else if (token === '!?') {
            variation_stack[variation_stack.length - 1].nags.push(NAG_SPECULATIVE_MOVE);
        }
        else if (token === '?!') {
            variation_stack[variation_stack.length - 1].nags.push(NAG_DUBIOUS_MOVE);
        }
        else {
            last_board_stack_index = board_stack.length - 1;
            last_variation_stack_index = variation_stack.length - 1;

            var preparsed_move = token;
            var move = board_stack[last_board_stack_index].move(preparsed_move, { sloppy: true });
            in_variation = true;
            if (move === null) {
                console.log('Unparsed move:');
                console.log(preparsed_move);
                console.log('Fen: ' + board_stack[last_board_stack_index].fen());
                console.log('faulty line: ' + line);
                console.log('Chess960: ' + chessGameType)
            }

            var props = {};
            if (comment) {
                props.comment = comment;
                comment = undefined;
            }
            if (starting_comment) {
                props.starting_comment = starting_comment;
                starting_comment = '';
            }
            lastmove = move;

            var __ret = addNewMove({ 'move': move }, variation_stack[last_variation_stack_index], board_stack[last_board_stack_index].fen(), props);
            variation_stack[last_variation_stack_index] = __ret.node;
        }
    }
    if (computerside == "" || (computerside != "" && lastmove.color != computerside)) {
        var tmp_board = new Chess(currentPosition.fen, chessGameType);
        saymove(lastmove, tmp_board); // announce user move
    }
    fenHash['last'] = fenHash[tmpGame.fen()];

    if (curr_fen === undefined) {
        currentPosition = fenHash['first'];
    }
    else {
        currentPosition = fenHash[curr_fen];
    }
    setHeaders(game_headers);
    $('.fen').unbind('click', goToGameFen).one('click', goToGameFen);
}

function getFullGame() {
    var gameHeader = getPgnGameHeader(gameHistory.originalHeader);
    if (gameHeader.length <= 1) {
        gameHistory.originalHeader = {
            'White': '*',
            'Black': '*',
            'Event': '?',
            'Site': '?',
            'Date': '?',
            'Round': '?',
            'Result': '*',
            'BlackElo': '-',
            'WhiteElo': '-',
            'Time': '00:00:00'
        };
        gameHeader = getPgnGameHeader(gameHistory.originalHeader);
    }

    var exporter = new PgnExporter();
    exportGame(gameHistory, exporter, true, true, undefined, false);
    var exporterContent = exporter.toString();
    return gameHeader + exporterContent;
}

function getPgnGameHeader(h) {
    var gameHeaderText = '';
    for (var key in h) {
        // hasOwnProperty ensures that inherited properties are not included
        if (h.hasOwnProperty(key)) {
            var value = h[key];
            gameHeaderText += "[" + key + " \"" + value + "\"]\n";
        }
    }
    gameHeaderText += "\n";
    return gameHeaderText;
}

function getWebGameHeader(h) {
    var gameHeaderText = '';
    gameHeaderText += '<h4>' + h.White + ' (' + h.WhiteElo + ') vs ' + h.Black + ' (' + h.BlackElo + ')</h4>';
    gameHeaderText += '<h5>' + h.Event + ', ' + h.Site + ' ' + h.Date + '</h5>';
    return gameHeaderText;
}

function download() {
    var content = getFullGame();
    var dl = document.createElement('a');
    dl.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(content));
    dl.setAttribute('download', 'game.pgn');
    document.body.appendChild(dl);
    dl.click();
}

function newBoard(fen) {
    stopAnalysis();

    currentPosition = {};
    currentPosition.fen = fen;

    setupBoardFen = fen;
    gameHistory = currentPosition;
    gameHistory.gameHeader = '';
    gameHistory.result = '';
    gameHistory.variations = [];

    updateChessGround();
    updateStatus();
    removeHighlights();
    removeArrow();
}

function clockButton0() {
    $.post('/channel', { action: 'clockbutton', button: 0 }, function (data) { });
}

function clockButton1() {
    $.post('/channel', { action: 'clockbutton', button: 1 }, function (data) { });
}

function clockButton2() {
    $.post('/channel', { action: 'clockbutton', button: 2 }, function (data) { });
}

function clockButton3() {
    $.post('/channel', { action: 'clockbutton', button: 3 }, function (data) { });
}

function clockButton4() {
    $.post('/channel', { action: 'clockbutton', button: 4 }, function (data) { });
}

function toggleLeverButton() {
    $('#leverDown').toggle();
    $('#leverUp').toggle();
    var button = 0x40;
    if ($('#leverDown').is(':hidden')) {
        button = -0x40;
    }
    $.post('/channel', { action: 'clockbutton', button: button }, function (data) { });
}

function clockButtonPower() {
    $.post('/channel', { action: 'clockbutton', button: 0x11 }, function (data) { });
}

function goToPosition(fen) {
    stopAnalysis();
    currentPosition = fenHash[fen];
    if (!currentPosition) {
        return false;
    }
    updateChessGround();
    updateStatus();
    return true;
}

function goToGameFen() {
    var fen = $(this).attr('data-fen');
    goToPosition(fen);
    removeHighlights();
}

function goToStart() {
    removeHighlights();
    stopAnalysis();
    currentPosition = gameHistory;
    updateChessGround();
    updateStatus();
}

function goToEnd() {
    removeHighlights();
    stopAnalysis();
    if (fenHash.last) {
        currentPosition = fenHash.last;
        updateChessGround();
    }
    updateStatus();
}

function goForward() {
    removeHighlights();
    stopAnalysis();
    if (currentPosition && currentPosition.variations[0]) {
        currentPosition = currentPosition.variations[0];
        if (currentPosition) {
            updateChessGround();
        }
    }
    updateStatus();
}

function goBack() {
    removeHighlights();
    stopAnalysis();
    if (currentPosition && currentPosition.previous) {
        currentPosition = currentPosition.previous;
        updateChessGround();
    }
    updateStatus();
}

function boardFlip() {
    chessground1.toggleOrientation();
}

function receive_message(wsevent) {
    console.log("received message: " + wsevent.data);
    var msg_obj = $.parseJSON(wsevent.data);
    console.log(msg_obj.event);
    console.log(msg_obj);
    console.log(' ');
}

function formatEngineOutput(line) {
    if (line.search('depth') > 0 && line.search('currmove') < 0) {
        var analysis_game = new Chess();
        var start_move_num = 1;
        if (currentPosition && currentPosition.fen) {
            analysis_game.load(currentPosition.fen, chessGameType);
            start_move_num = getCountPrevMoves(currentPosition) + 1;
        }

        var output = '';
        var tokens = line.split(" ");
        var depth_index = tokens.indexOf('depth') + 1;
        var depth = tokens[depth_index];
        var score_index = tokens.indexOf('score') + 1;

        var multipv_index = tokens.indexOf('multipv');
        var multipv = 0;
        if (multipv_index > -1) {
            multipv = Number(tokens[multipv_index + 1]);
        }

        var token = tokens[score_index];
        var score = '?';
        if (token === 'mate') {
            score = '#' + tokens[score_index + 1];
        }
        else if (tokens[score_index + 1]) {
            score = (tokens[score_index + 1] / 100.0).toFixed(2);
            if (analysis_game.turn() === 'b') {
                score *= -1;
            }
            if (token === 'lowerbound') {
                score = '>' + score;
            }
            if (token === 'upperbound') {
                score = '<' + score;
            }
        }

        var pv_index = tokens.indexOf('pv') + 1;

        var pv_out = tokens.slice(pv_index);
////////////////////////////////////////////////////////////////////////////////////////
        var MAX_PV_MOVES = 8;                        // *** Limita PV max 8 movimientos.
        pv_out = pv_out.slice(0, MAX_PV_MOVES);
        var first_move = pv_out[0];
        for (var i = 0; i < pv_out.length; i++) {
            var from = pv_out[i].slice(0, 2);
            var to = pv_out[i].slice(2, 4);
            var promotion = '';
            if (pv_out[i].length === 5) {
                promotion = pv_out[i][4];
            }
            if (promotion) {
                var mv = analysis_game.move(({ from: from, to: to, promotion: promotion }));
            } else {
                analysis_game.move(({ from: from, to: to }));
            }
        }

        var history = analysis_game.history();
        window.engine_lines['import_pv_' + multipv] = { score: score, depth: depth, line: history };

        var turn_sep = '';
        if (start_move_num % 2 === 0) {
            turn_sep = '..';
        }

// Determinar clase de puntuacion
        var scoreClass = 'score-display';
        var numericScore = parseFloat(score);
        if (String(score).includes('#')) {
            scoreClass += ' score-mate';
        } else if (numericScore > 0) {
            scoreClass += ' score-positive';
        } else if (numericScore < 0) {
            scoreClass += ' score-negative';
        }

        output = '<div class="list-group-item">';
        output += '<div class="analysis-line-compact">';
        
// Puntuacion (siempre en relacion al blanco)
        if (score !== null) {
            output += '<span class="' + scoreClass + '">' + score + '</span>';
        }
        
// Primer movimiento destacado
        if (history.length > 0) {
            var firstMoveText = '';
            if ((start_move_num) % 2 === 1) {
                firstMoveText += Math.floor((start_move_num + 1) / 2) + '. ';
            } else {
                firstMoveText += Math.floor((start_move_num + 1) / 2) + '... ';
            }
            firstMoveText += figurinizeMove(history[0]);
            output += '<span class="first-move">' + firstMoveText + '</span>';
        }
        
// Continuacion de la linea (mas discreta)
        if (history.length > 1) {
            var continuationText = '';
            for (i = 1; i < history.length; ++i) {
                if ((start_move_num + i) % 2 === 1) {
                    continuationText += Math.floor((start_move_num + i + 1) / 2) + '. ';
                }
                continuationText += figurinizeMove(history[i]) + ' ';
            }
            output += '<span class="continuation-moves">' + continuationText.trim() + '</span>';
        }
        
// Profundidad al final
        output += '<span class="depth-display">d' + depth + '</span>';
        
        output += '</div></div>';

        analysis_game = null;
        return { line: output, pv_index: multipv };
    }
    else if (line.search('currmove') < 0 && line.search('time') < 0) {
        return line;
    }
}
////////////////////////////////////////////////////////////////////////////////////////

function multiPvIncrease() {
    if (window.stockfish) {
        window.multipv += 1;

        if (window.stockfish) {
            window.stockfish.postMessage('setoption name multipv value ' + window.multipv);
            if (window.analysis) {
                window.stockfish.postMessage('stop');
                window.stockfish.postMessage('go infinite');
            }
            else {
                $('#engineMultiPVStatus').html(window.multipv + (window.multipv > 1 ? ' lines' : ' line'));
            }
        }

        var new_div_str = "<div id=\"pv_" + window.multipv + "\"  style=\"margin-top: 0px; margin-left: 12px; margin-bottom: 3vh;\"></div>";
        $("#pv_output").append(new_div_str);

        if (!window.StockfishModule) {
            // Need to restart web worker as its not Chrome
            stopAnalysis();
            analyze(true);
        }
    }
}

function multiPvDecrease() {
    if (window.multipv > 1) {
        $('#pv_' + window.multipv).remove();

        window.multipv -= 1;
        if (window.stockfish) {
            window.stockfish.postMessage('setoption name multipv value ' + window.multipv);
            if (window.analysis) {
                window.stockfish.postMessage('stop');
                window.stockfish.postMessage('go infinite');
            }
            else {
                $('#engineMultiPVStatus').html(window.multipv + (window.multipv > 1 ? ' lines' : ' line'));
            }
        }

        if (!window.StockfishModule) {
            // Need to restart web worker as its not Chrome
            stopAnalysis();
            analyze(true);
        }
    }
}

function importPv(multipv) {
    stopAnalysis();
    var tmpGame = createGamePointer();
    var line = window.engine_lines['import_pv_' + multipv].line;
    for (var i = 0; i < line.length; ++i) {
        var text_move = line[i];
        var move = tmpGame.move(text_move);
        if (move) {
            updateCurrentPosition(move, tmpGame);
        } else {
            console.warn('import_pv error');
            console.log(tmpGame.ascii());
            console.log(text_move);
            break;
        }
    }
    updateChessGround();
    updateStatus();
}

function analyzePressed() {
    analyze(false);
}

function stockfishPNACLModuleDidLoad() {
    window.StockfishModule = document.getElementById('stockfish_module');
    window.StockfishModule.postMessage('uci');
    $('#analyzeBtn').prop('disabled', false);
}

function handleCrash(event) {
    console.warn('Nacl Module crash handler method');
    console.warn(event);
    loadNaclStockfish();
}

function handleMessage(event) {
    var output = formatEngineOutput(event.data);
    if (output && output.pv_index && output.pv_index > 0) {
        $('#pv_' + output.pv_index).html(output.line);
    }
    $('#engineMultiPVStatus').html(window.multipv + (window.multipv > 1 ? ' lines' : ' line'));
}

function loadNaclStockfish() {
    var listener = document.getElementById('listener');
    listener.addEventListener('load', stockfishPNACLModuleDidLoad, true);
    listener.addEventListener('message', handleMessage, true);
    listener.addEventListener('crash', handleCrash, true);
}

function stopAnalysis() {
    if (!window.StockfishModule) {
        if (window.stockfish) {
            window.stockfish.terminate();
        }
    } else {
        try {
            window.StockfishModule.postMessage('stop');
        }
        catch (err) {
            console.warn(err);
        }
    }
}

function getCountPrevMoves(node) {
    if (node.previous) {
        return getCountPrevMoves(node.previous) + 1;
    } else {
        return 0;
    }
}

function getPreviousMoves(node, format) {
    format = format || 'raw';

    if (node.previous) {
        var san = '';
        if (format === 'san') {
            if (node.half_move_num % 2 === 1) {
                san += Math.floor((node.half_move_num + 1) / 2) + ". "
            }
            san += node.move.san;
        }
        else {
            san += node.move.from + node.move.to + (node.move.promotion ? node.move.promotion : '');
        }
        return getPreviousMoves(node.previous, format) + ' ' + san;
    } else {
        return '';
    }
}

function analyze(position_update) {
    if (!position_update) {
        if ($('#AnalyzeText').text() === 'Analyze') {
            window.analysis = true;
            $('#AnalyzeText').text('Stop');
        }
        else {
            $('#AnalyzeText').text('Analyze');
            stopAnalysis();
            window.analysis = false;
            $('#engineStatus').html('');
            return;
        }
    }
    var moves;
    if (currentPosition === undefined) {
        moves = '';
    }
    else {
        moves = getPreviousMoves(currentPosition);
    }
    if (!window.StockfishModule) {
        window.stockfish = new Worker('/static/js/stockfish.js');
        window.stockfish.onmessage = function (event) {
            handleMessage(event);
        };
    }
    else {
        if (!window.stockfish) {
            window.stockfish = StockfishModule;
        }
    }

    var startpos = 'startpos';
    if (setupBoardFen !== START_FEN) {
        startpos = 'fen ' + setupBoardFen;
    }
    window.stockfish.postMessage('position ' + startpos + ' moves ' + moves);
    window.stockfish.postMessage('setoption name multipv value ' + window.multipv);
    window.stockfish.postMessage('go infinite');
}

function updateDGTPosition(data) {
    if (!goToPosition(data.fen) || data.play === 'reload') {
        loadGame(data['pgn'].split("\n"));
        goToPosition(data.fen);
    }
}

function goToDGTFen() {
    $.get('/dgt', { action: 'get_last_move' }, function (data) {
        if (data) {
            updateDGTPosition(data);
            highlightBoard(data.move, data.play);
            addArrow(data.move, data.play);
        }
        else {
            data.fen = START_FEN
            updateDGTPosition(data);
            highlightBoard(data.move, data.play);
            addArrow(data.move, data.play);
        }
    }).fail(function (jqXHR, textStatus) {
        dgtClockStatusEl.html(textStatus);
    });
}

function setTitle(data) {
    window.ip_info = data;
    var ip = '';
    if (window.ip_info.ext_ip) {
        ip += ' IP: ' + window.ip_info.ext_ip;
    }
    var version = '';
    if (window.ip_info.version) {
        version = window.ip_info.version;
    } else if (window.system_info.version) {
        version = window.system_info.version;
    }
    document.title = 'Webserver Picochess ' + version + ip;
}

// copied from loadGame()
function setHeaders(data) {
    if ('FEN' in data && 'SetUp' in data) {
        if ('Variant' in data && 'Chess960' === data['Variant']) {
            chessGameType = 1; // values from chess960.js
        } else {
            chessGameType = 0;
        }
    }
    gameHistory.gameHeader = getWebGameHeader(data);
    gameHistory.result = data.Result;
    gameHistory.originalHeader = data;
    var exporter = new WebExporter();
    exportGame(gameHistory, exporter, true, true, undefined, false);
    writeVariationTree(pgnEl, exporter.toString(), gameHistory);
}

function getAllInfo() {
    $.get('/info', { action: 'get_system_info' }, function (data) {
        window.system_info = data;
    }).fail(function (jqXHR, textStatus) {
        dgtClockStatusEl.html(textStatus);
    });
    $.get('/info', { action: 'get_ip_info' }, function (data) {
        setTitle(data);
    }).fail(function (jqXHR, textStatus) {
        dgtClockStatusEl.html(textStatus);
    });
    $.get('/info', { action: 'get_headers' }, function (data) {
        setHeaders(data);
    }).fail(function (jqXHR, textStatus) {
        dgtClockStatusEl.html(textStatus);
    });
    $.get('/info', { action: 'get_clock_text' }, function (data) {
        dgtClockTextEl.html(data);
    }).fail(function (jqXHR, textStatus) {
        console.warn(textStatus);
        dgtClockStatusEl.html(textStatus);
    });
}

$('#flipOrientationBtn').on('click', boardFlip);
$('#backBtn').on('click', goBack);
$('#fwdBtn').on('click', goForward);
$('#startBtn').on('click', goToStart);
$('#endBtn').on('click', goToEnd);

$('#DgtSyncBtn').on('click', goToDGTFen);
if (location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
    $('#downloadBtn').hide()
} else {
    $('#downloadBtn').on('click', download);
}

$('#analyzeBtn').on('click', analyzePressed);

// disable plus/minus analysis on device as this currently causes the engine to load multiple times
if (location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
    $('#analyzePlus').hide()
    $('#analyzeMinus').hide()
} else {
    $('#analyzePlus').on('click', multiPvIncrease);
    $('#analyzeMinus').on('click', multiPvDecrease);
}

$('#ClockBtn0').on('click', clockButton0);
$('#ClockBtn1').on('click', clockButton1);
$('#ClockBtn2').on('click', clockButton2);
$('#ClockBtn3').on('click', clockButton3);
$('#ClockBtn4').on('click', clockButton4);
$('#ClockLeverBtn').on('click', toggleLeverButton);

$("#ClockBtn0").mouseup(function () {
    btn = $(this);
    setTimeout(function () { btn.blur(); }, 100);
})
$("#ClockBtn1").mouseup(function () {
    btn = $(this);
    setTimeout(function () { btn.blur(); }, 100);
})
$("#ClockBtn2").mouseup(function () {
    btn = $(this);
    setTimeout(function () { btn.blur(); }, 100);
})
$("#ClockBtn3").mouseup(function () {
    btn = $(this);
    setTimeout(function () { btn.blur(); }, 100);
})
$("#ClockBtn4").mouseup(function () {
    btn = $(this);
    setTimeout(function () { btn.blur(); }, 100);
})
$("#ClockLeverBtn").mouseup(function () {
    btn = $(this);
    setTimeout(function () { btn.blur(); }, 100);
})

$(function () {
    getAllInfo();

    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        updateStatus();
    });
    window.engine_lines = {};
    window.multipv = 1;

    $(document).keydown(function (e) {
        if (e.keyCode === 39) { // right arrow
            if (e.ctrlKey) {
                $('#endBtn').click();
            } else {
                $('#fwdBtn').click();
            }
            return true;
        }
    });

    $(document).keydown(function (e) {
        if (e.keyCode === 37) { // left arrow
            if (e.ctrlKey) {
                $('#startBtn').click();
            } else {
                $('#backBtn').click();
            }
        }
        return true;
    });
    updateStatus();

    window.WebSocket = window.WebSocket || window.MozWebSocket || false;
    if (!window.WebSocket) {
        alert('No WebSocket Support');
    }
    else {
        var ws = new WebSocket('ws://' + location.host + '/event');
        // Process messages from picochess
        ws.onmessage = function (e) {
            var data = JSON.parse(e.data);
            switch (data.event) {
                case 'Fen':
                    pickPromotion(null) // reset promotion dialog if still showing
                    updateDGTPosition(data);
                    if (data.play === 'reload') {
                        removeHighlights();
                    }
                    if (data.play === 'user') {
                        highlightBoard(data.move, 'user');
                    }
                    if (data.play === 'review') {
                        highlightBoard(data.move, 'review');
                    }
                    break;
                case 'Game':
                    newBoard(data.fen);
                    break;
                case 'Message':
                    boardStatusEl.html(data.msg);
                    break;
                case 'Clock':
                    dgtClockTextEl.html(data.msg);
                    break;
                case 'Status':
                    // dgtClockStatusEl.html(data.msg);
                    break;
                case 'Light':
                    var tmp_board = new Chess(currentPosition.fen, chessGameType);
                    var tmp_move = tmp_board.move(data.move, { sloppy: true });
                    if (tmp_move !== null) {
                        computerside = tmp_move.color;
                        saymove(tmp_move, tmp_board);
                        highlightBoard(data.move, 'computer');
                        addArrow(data.move, 'computer');
                    }
                    break;
                case 'Clear':
                    break;
                case 'Header':
                    setHeaders(data['headers']);
                    break;
                case 'Title':
                    setTitle(data['ip_info']);
                    break;
                case 'Broadcast':
                    boardStatusEl.html(data.msg);
                    break;
                case 'PromotionDlg':
                    // for e-boards that do not feature piece recognition
                    promotionDialog(data.move);
                default:
                    console.warn(data);
            }
        };
        ws.onclose = function () {
            dgtClockStatusEl.html('closed');
        };
    }

    if (navigator.mimeTypes['application/x-pnacl'] !== undefined) {
        $('#analyzeBtn').prop('disabled', true);
        loadNaclStockfish();
    }

    $.fn.dataTable.ext.errMode = 'throw';
});

// promotion code taken from https://github.com/thinktt/chessg
function isPromotion(squareState, toSquare) {
    if (squareState.type !== 'p') return false
    if (toSquare.includes('8') || toSquare.includes('1')) return true
    return false
}

function html() {
    arguments[0] = { raw: arguments[0] };
    return String.raw(...arguments);
}

let setPromotion = null
async function getUserPromotion(toSquare) {
    const column = toSquare[0]
    const offSetMap = {
        'a': 0,
        'b': 12.5,
        'c': 25,
        'd': 37.5,
        'e': 50,
        'f': 62.5,
        'g': 75,
        'h': 87.5,
    }
    const leftOffset = offSetMap[column]

    let color = 'black'
    let queenTop = 87.5
    let topOffsetIncrement = -12.5

    if (toSquare.includes('8')) {
        color = 'white'
        queenTop = 0
        topOffsetIncrement = 12.5
    }

    const knightTop = queenTop + topOffsetIncrement
    const roookTop = knightTop + topOffsetIncrement
    const bishopTop = roookTop + topOffsetIncrement

    const promoChoiceHtml = html`
    <div class="promotion-overlay cg-wrap">
    <square onclick="pickPromotion('q')" style="top:${queenTop}%; left: ${leftOffset}%">
        <piece class="queen ${color}"></piece>
    </square>
    <square onclick="pickPromotion('n')" style="top:${knightTop}%; left: ${leftOffset}%">
        <piece class="knight ${color}"></piece>
    </square>
    <square onclick="pickPromotion('r')" style="top:${roookTop}%; left: ${leftOffset}%">
        <piece class="rook ${color}"></piece>
    </square>
    <square onclick="pickPromotion('b')" style="top:${bishopTop}%; left: ${leftOffset}%">
        <piece class="piece bishop ${color}"></piece>
    </square>
    </div>
    `

    const boardContainerEl = document.querySelector('.board-container')
    boardContainerEl.insertAdjacentHTML('beforeend', promoChoiceHtml)

    const piece = await new Promise(resolve => setPromotion = resolve)

    boardContainerEl.removeChild(document.querySelector('.promotion-overlay'))
    return piece
}

function pickPromotion(piece) {
    if (setPromotion) setPromotion(piece)
}

window.pickPromotion = pickPromotion
