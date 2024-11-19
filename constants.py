""" Constants to influence behaviour of picochess """
# depending on CPU set 0.05 to 0.5
FLOAT_MSG_WAIT = 0.05  # smaller is more responsive and more CPU intensive

# settings are for engine thinking limits
FLOAT_MAX_ENGINE_TIME = 2.0  # engine max thinking time
FLOAT_MIN_ENGINE_TIME = 0.1  # engine min thinking time
INT_EXPECTED_GAME_LENGTH = 100  # divide thinking time over expected game length

# how long engine should analyse
FLOAT_ANALYSE_HINT_LIMIT = 0.1  # time after each user move (both sides) in ANALYSIS
FLOAT_ANALYSE_PONDER_LIMIT = 0.05 # asking analyse while pondering can be short
FLOAT_MIN_BACKGROUND_TIME = 2.0  # dont update analysis more often than this
