# PicoTutor Constants

LOW_DEPTH = 5  # for 'obvious moves' calculation
LOW_TIME = 0.2  # time limit for 'obvious moves' and first analysis
DEEP_DEPTH = 17  # limit picotutor deep analysis (also used as analysis engine)
LOW_NUM_THREADS = 1  # parallel threads for low
NUM_THREADS = 1  # threads for deep - 1 to save CPU, 2 to have faster analysis
# VALID_ROOT_MOVES must be high enough to find also some bad moves
# but not so high that depth on PI 4 is as low as 5 or LOW_DEPTH
VALID_ROOT_MOVES = 50  # number of multipv best moves
LOW_ROOT_MOVES = 50  # number of obvious multipv root moves

VERY_BAD_MOVE_TH = 250  # difference user to best move ??
BAD_MOVE_TH = 150  # difference user to best move ?
DUBIOUS_TH = 30  # difference user to best move ?!

INACCURACY_TH = 20  # inaccuracy limit - only for PGN comments
ALTERNATIVE_TH = 20  # limit for alternative moves

VERY_GOOD_MOVE_TH = 0  # difference user to best move
GOOD_MOVE_TH = 30  # difference user to best move
INTERESTING_TH = 30  # difference user to best move !?

POS_INCREASE = 50  # for history diffs and ?!
POS_DECREASE = -50  # for history diffs and !?

VERY_GOOD_IMPROVE_TH = 350  # for low_deep_diff
GOOD_IMPROVE_TH = 250  # for low_deep_diff
UNCLEAR_DIFF = 70  # for low_deep_diff unclear position & move

"""
http://www2.eng.cam.ac.uk/~tpl/chess/annotation.html

    Computers and Chess Annotation

    Δ1 -    The difference between move value at min. ply for the current move and best move.

    Δ2 -    The difference between move value at max. ply for the current move and best move.

    ΔS -    The difference between the current move's value at max. and min. ply.

    G1 -    The model's gradient at min. ply

    G2 -    The model's gradient at max. ply

    K - The model's curvature.

    Classification occurs as follows:

    Blunders (?, ??) are characterised as being clearly much worse than the optimal move in a given position. 
    Hence, we define a move as a blunder if both Δ1 and Δ2 are greater than a certain threshold - for example, 
    I have found thresholds of 50 for ? and 150 for ?? to work well in test games.

    # noqa E501
    Exceptional Moves (!, !!) are always ultimately good moves (hence Δ2 must either be small, or, especially 
    in the case of !!, zero), and show improvement with ply (ie. ΔS is positive and, in the case of !!, 
    greater than a positive threshold). We need to take care that the move is not too obviously good - 
    thus we require Δ1 to be greater than a threshold, such that the move was not clearly the best at 
    first glance. We also don't want the move to rapidly become good, as this makes the move's goodness 
    clear to the player without very intensive evaluation - we therefore require the model's curvature 
    to be concave, linear, or at most shallowly convex, otherwise the move's true nature becomes clear 
    at relatively low ply.

    Unclear Moves (?!, !?) need to be both sufficiently good/bad-seeming to warrant a mark, and sufficiently 
    volatile to warrant denotation as being unclear. We detect the apparent initial interest in the move by 
    a high magnitude of G1 - very positive initial gradient makes a move look as though it might be 
    exceptional (!?), while very negative initial gradient makes the move look as 
    though it might be a blunder (?!). We detect the volatility by the curvature - we demand that the 
    curvature be both high in magnitude and acting in the opposite direction to the initial gradient. 
    Finally, we need the max. ply value to be reasonably close to the initial value for the move 
    (ie. the magnitude of ΔS needs to be low) - if it's a lot higher, then the move is better described 
    as exceptional, if a lot lower, the move is more accurately a blunder.



    [Objectively] best move - the move which (as far as can be determined) leads to the best possible position
    Good move - a move which (as far as can be determined) is close to being the objectively best move
    Obvious move - a move which using an n-ply analysis (where n is small) is good
    Easy move - a move which using an n-ply analysis (where n is small) is close to the best move using an n-ply analysis
    Risky move - a move which leads to a much more unclear position
    Double-edged move - leading to a complicated position
    Quiet move - a move which doesn't lead to a more unclear position and doesn't have an immediate threat.

    ! - a move which is much better than the alternatives and not obvious
    !! - a move which is much better than the alternatives and not at all obvious
    ? - a move which is much worse than at least one alternative
    ?? - a blunder: a move which is much worse than at least one alternative, converting a win into a draw/loss or a draw into a loss
    !? - not objectively best, but good for pragmatic reasons.
    ?! - far from objectively best, but maybe good for pragmatic reasons.



    Unclear position - a position where few obvious moves are good.

    Complicated position - a position where some of the obvious moves are good and some bad.

    ###############################################################
    ## 1. bad moves
    ###############################################################

    # Blunder ??
    ##if D1 > VERY_BAD_MOVE_TH and D2 > VERY_BAD_MOVE_TH:
    if best_deep_diff > VERY_BAD_MOVE_TH: ## and best_low_diff > VERY_BAD_MOVE_TH:
    eval_string = '??'

    # Mistake ?
    ##elif D1 > BAD_MOVE_TH and D2 > BAD_MOVE_TH:
    elif best_deep_diff > BAD_MOVE_TH: ## and  best_low_diff  > BAD_MOVE_TH:
    eval_string = '?'

    # Dubious
    elif best_deep_diff > DUBIOUS_TH and abs(deep_low_diff) > UNCLEAR_DIFF and score_hist_diff > POS_INCREASE:
    eval_string = '?!'

    ###############################################################
    ## 2. good moves
    ##############################################################
    eval_string2 = ''

    # very good moves
    if best_deep_diff <= VERY_GOOD_MOVE_TH and deep_low_diff > VERY_GOOD_IMPROVE_TH:
    if best_score == 999 and (best_mate == current_mate):
    pass
    else:
    eval_string2 = '!!'

    # good move
    elif best_deep_diff <= GOOD_MOVE_TH and deep_low_diff > GOOD_IMPROVE_TH:
    eval_string2 = '!'

    ## interesting move
    elif best_deep_diff < INTERESTING_TH and abs(deep_low_diff) > UNCLEAR_DIFF and score_hist_diff < POS_DECREASE:
    eval_string2 = '!?'


"""
