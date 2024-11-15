""" Constants to influence behaviour of picochess """
# depending on CPU set 0.05 to 0.5
FLOAT_MSG_WAIT = 0.05  # smaller is more responsive and more CPU intensive

# settings are for engine thinking limits
FLOAT_MAX_ENGINE_TIME = 2.0  # engine max thinking time
FLOAT_MIN_ENGINE_TIME = 0.1  # engine min thinking time
INT_EXPECTED_GAME_LENGTH = 100  # divide thinking time over expected game length

# how long to ponder or brain
FLOAT_PONDERING_LIMIT = 0.5  # long value will force user to wait while entering moves
FLOAT_BRAIN_LIMIT = 0.5
