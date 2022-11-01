obooksrv is a chess opening book server that provides opening statistics for specific FENs. 
It reads from a file "opening.data" and starts an HTTP server on port 7777.

The data format is based on the Polyglot opening book format.

Example link to get the data for the starting position as a JSON HTTP response:
http://localhost:7777/query?action=get_book_moves&fen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR%20w%20KQkq%20-%200%201

JSON response (example):

```JSON
{"data": [
{"move":"g1f3","whitewins":30,"draws":49,"blackwins":21,"count":53980},
{"move":"c2c4","whitewins":32,"draws":47,"blackwins":21,"count":40793},
{"move":"e2e4","whitewins":32,"draws":44,"blackwins":24,"count":218543},
{"move":"d2d4","whitewins":32,"draws":47,"blackwins":21,"count":205407},
{"move":"g2g3","whitewins":31,"draws":45,"blackwins":24,"count":4122},
{"move":"b2b3","whitewins":33,"draws":39,"blackwins":28,"count":1248},
{"move":"f2f4","whitewins":28,"draws":34,"blackwins":38,"count":849},
{"move":"b1c3","whitewins":29,"draws":36,"blackwins":35,"count":274},
{"move":"b2b4","whitewins":38,"draws":34,"blackwins":28,"count":171},
{"move":"e2e3","whitewins":30,"draws":30,"blackwins":40,"count":91},
{"move":"a2a3","whitewins":39,"draws":29,"blackwins":32,"count":51},
{"move":"d2d3","whitewins":30,"draws":32,"blackwins":38,"count":53},
{"move":"c2c3","whitewins":31,"draws":40,"blackwins":29,"count":22},
{"move":"g2g4","whitewins":31,"draws":18,"blackwins":51,"count":16}]}
```

* move: chess move in the form source square target square
* whitewins: percentage of white wins for the position
* draws: percentage of draws for the position
* blackwins: percentage of black wins for the position
* count: number of games for the position
