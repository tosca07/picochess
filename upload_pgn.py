# upload_handler.py

import os
import base64
import pam
import tornado.web

from utilities import Observable
from dgt.api import Event


UPLOAD_DIR = "/opt/picochess/games"
FIXED_FILENAME = "picochess_game_1.pgn"
FIXED_PATH = os.path.join(UPLOAD_DIR, FIXED_FILENAME)

os.makedirs(UPLOAD_DIR, exist_ok=True)


class UploadHandler(tornado.web.RequestHandler):
    def prepare(self):
        auth_header = self.request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            self.request_auth()
            return

        try:
            auth_decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = auth_decoded.split(":", 1)
        except Exception:
            self.request_auth()
            return

        if not pam.pam().authenticate(username, password):
            self.request_auth()
            return

        self.current_user = username

    def request_auth(self):
        self.set_status(401)
        self.set_header("WWW-Authenticate", 'Basic realm="Upload Area"')
        self.finish("Authentication required")

    async def post(self):
        if not hasattr(self, "current_user"):
            return  # Auth failed

        if "file" not in self.request.files:
            self.set_status(400)
            self.finish("No file uploaded")
            return

        fileinfo = self.request.files["file"][0]
        original_name = fileinfo["filename"]

        # Check if uploaded file is a PGN file (by name)
        if not original_name.lower().endswith(".pgn"):
            self.set_status(400)
            self.finish("Only .pgn files are allowed.")
            return

        try:
            with open(FIXED_PATH, "wb") as f:
                f.write(fileinfo["body"])
                event = Event.READ_GAME(pgn_filename="picochess_game_1.pgn")
                await Observable.fire(event)
        except Exception as e:
            self.set_status(500)
            self.finish(f"Failed to save file: {str(e)}")
            return

        self.write(f"User '{self.current_user}' uploaded '{original_name}' and it was saved as Game 1.")
