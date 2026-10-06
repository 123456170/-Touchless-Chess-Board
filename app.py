import streamlit as st
import chess
import time
import math
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None

try:
    import mediapipe as mp
except Exception:
    mp = None


st.set_page_config(
    page_title="Touchless Chess Board",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

BOARD_PX = 640
STATUS_PX = 96
IMG_W = BOARD_PX
IMG_H = BOARD_PX + STATUS_PX
SQ = BOARD_PX // 8

HOLD_SECONDS = 0.5
RESIGN_HOLD_SECONDS = 2.0
RESIGN_CONFIRM_WINDOW = 3.0

LIGHT = (238, 238, 210)
DARK = (118, 150, 86)

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS

PIECE_UNICODE = {
    "K": "♔",
    "Q": "♕",
    "R": "♖",
    "B": "♗",
    "N": "♘",
    "P": "♙",
    "k": "♚",
    "q": "♛",
    "r": "♜",
    "b": "♝",
    "n": "♞",
    "p": "♟",
}

PROMOTION_CHOICES = [
    ("queen", chess.QUEEN),
    ("rook", chess.ROOK),
    ("bishop", chess.BISHOP),
    ("knight", chess.KNIGHT),
]

PROMO_NAME_TO_CHESS = {name: piece for name, piece in PROMOTION_CHOICES}
PROMO_CHESS_TO_NAME = {piece: name for name, piece in PROMOTION_CHOICES}

PROMO_UNICODE = {
    chess.WHITE: {
        "queen": "♕",
        "rook": "♖",
        "bishop": "♗",
        "knight": "♘",
    },
    chess.BLACK: {
        "queen": "♛",
        "rook": "♜",
        "bishop": "♝",
        "knight": "♞",
    },
}

BOX_W = 112
BOX_H = 112
GAP = 18
TOTAL_PROMO_W = 4 * BOX_W + 3 * GAP
PROMO_START_X = (IMG_W - TOTAL_PROMO_W) // 2
PROMO_Y_BOARD = (BOARD_PX - BOX_H) // 2

PROMO_RECTS_BOARD = {}
_x = PROMO_START_X
for _name, _ in PROMOTION_CHOICES:
    PROMO_RECTS_BOARD[_name] = (_x, PROMO_Y_BOARD, _x + BOX_W, PROMO_Y_BOARD + BOX_H)
    _x += BOX_W + GAP

MODES = [
    "Auto Demo",
    "Mouse / Touch Board",
    "Touchless Webcam",
]


# ----------------------------------------------------------------------------
# Demo script
# ----------------------------------------------------------------------------

DEMO_SCRIPT = [
    {"kind": "msg", "text": "Live touchless chess demo starting.", "duration": 1.2},
    {"kind": "board", "fen": "startpos", "duration": 0.5},
    {"kind": "msg", "text": "Concept: point to select, hold 0.5s, point again to move.", "duration": 1.3},

    {"kind": "msg", "text": "Point at e2 to select White's pawn.", "duration": 0.9},
    {"kind": "point", "square": "e2", "duration": 0.8},
    {"kind": "msg", "text": "Legal destinations are highlighted by python-chess.", "duration": 1.0},
    {"kind": "point", "square": "e4", "duration": 0.8},

    {"kind": "msg", "text": "Black to move. Point at e7.", "duration": 0.8},
    {"kind": "point", "square": "e7", "duration": 0.8},
    {"kind": "point", "square": "e5", "duration": 0.8},

    {"kind": "msg", "text": "White develops the knight: g1 to f3.", "duration": 0.9},
    {"kind": "point", "square": "g1", "duration": 0.8},
    {"kind": "point", "square": "f3", "duration": 0.8},

    {"kind": "msg", "text": "Black develops the knight: b8 to c6.", "duration": 0.9},
    {"kind": "point", "square": "b8", "duration": 0.8},
    {"kind": "point", "square": "c6", "duration": 0.8},

    {"kind": "msg", "text": "Illegal attempt: e4 pawn cannot advance to occupied e5.", "duration": 1.2},
    {"kind": "point", "square": "e4", "duration": 0.8},
    {"kind": "point", "square": "e5", "duration": 0.8},

    {"kind": "msg", "text": "Recover and play a legal bishop move: f1 to c4.", "duration": 1.0},
    {"kind": "point", "square": "f1", "duration": 0.8},
    {"kind": "point", "square": "c4", "duration": 0.8},

    {"kind": "msg", "text": "Loading a scripted check position.", "duration": 1.0},
    {"kind": "board", "fen": "4k3/8/8/7Q/8/8/8/4K3 b - - 0 1", "duration": 0.6},
    {"kind": "msg", "text": "Check! Banner is driven directly by board.is_check().", "duration": 1.8},

    {"kind": "msg", "text": "Loading pawn promotion position.", "duration": 1.0},
    {"kind": "board", "fen": "k7/4P3/8/8/8/8/8/4K3 w - - 0 1", "duration": 0.6},
    {"kind": "point", "square": "e7", "duration": 0.8},
    {"kind": "point", "square": "e8", "duration": 0.8},
    {"kind": "msg", "text": "Promotion required. Point at Queen.", "duration": 1.2},
    {"kind": "promo", "piece": "queen", "duration": 0.8},

    {"kind": "msg", "text": "Resign gesture demo: fist held for 2 seconds.", "duration": 1.2},
    {"kind": "board", "fen": "startpos", "duration": 0.5},
    {"kind": "fist", "duration": 2.2},
    {"kind": "msg", "text": "Confirmation required within 3 seconds. Repeat fist.", "duration": 0.3},
    {"kind": "fist", "duration": 2.2},

    {"kind": "msg", "text": "Demo complete. Switch to Mouse/Touch or Touchless Webcam.", "duration": 2.0},
]


# ----------------------------------------------------------------------------
# Font helper
# ----------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    for name in ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass

    return ImageFont.load_default()


def draw_centered_text(draw, xy, text, font, fill, stroke_fill=None):
    try:
        if stroke_fill is not None:
            draw.text(
                xy,
                text,
                font=font,
                fill=fill,
                anchor="mm",
                stroke_width=2,
                stroke_fill=stroke_fill,
            )
        else:
            draw.text(xy, text, font=font, fill=fill, anchor="mm")
    except TypeError:
        draw.text(xy, text, font=font, fill=fill)


# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------

def init_session():
    defaults = {
        "board": chess.Board(),
        "selected": None,
        "legal_targets": set(),
        "promotion_pending": None,
        "promotion_cursor": None,
        "cursor_square": None,
        "cursor_progress": 0.0,
        "cursor_gesture": None,
        "game_over": False,
        "result_text": "",
        "status_message": "White to move",
        "history": [],
        "log": [],
        "last_move": None,
        "mode": "Auto Demo",
        "demo_active": True,
        "demo_index": 0,
        "demo_action": None,
        "demo_action_started": 0.0,
        "camera_active": False,
        "cap": None,
        "mp_hands": None,
        "touch_frame": None,
        "touch_error": "",
        "hand_dwell": {"key": None, "started": None},
        "dwell_cooldown_until": 0.0,
        "resign_hold_start": None,
        "resign_armed": False,
        "resign_window_deadline": None,
        "resign_requires_release": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ----------------------------------------------------------------------------
# Logging and state helpers
# ----------------------------------------------------------------------------

def log(message: str):
    entry = f"{datetime.now().strftime('%H:%M:%S')} — {message}"
    st.session_state.log.append(entry)
    st.session_state.log = st.session_state.log[-40:]


def clear_selection():
    st.session_state.selected = None
    st.session_state.legal_targets = set()
    st.session_state.promotion_pending = None
    st.session_state.promotion_cursor = None


def reset_resign_arm():
    st.session_state.resign_hold_start = None
    st.session_state.resign_armed = False
    st.session_state.resign_window_deadline = None
    st.session_state.resign_requires_release = False


def arm_resign(now: float):
    st.session_state.resign_armed = True
    st.session_state.resign_window_deadline = now + RESIGN_CONFIRM_WINDOW
    st.session_state.resign_requires_release = True
    st.session_state.status_message = "Resign armed. Repeat fist within 3 seconds."
    log("Resign armed. Confirmation required.")


def confirm_resign_expired(now: float):
    reset_resign_arm()
    st.session_state.status_message = "Resign confirmation expired."
    log("Resign confirmation expired.")


def do_resign():
    if st.session_state.game_over:
        return

    winner = "Black" if st.session_state.board.turn == chess.WHITE else "White"
    st.session_state.game_over = True
    st.session_state.result_text = f"{winner} wins by resignation"
    st.session_state.status_message = st.session_state.result_text
    clear_selection()
    reset_resign_arm()
    log(st.session_state.result_text)


def complete_resign_hold(now: float):
    """
    Used by demo and mouse/accessibility resign button.
    First hold arms resignation, second hold within window confirms.
    """
    if st.session_state.game_over:
        return

    if st.session_state.resign_armed:
        if (
            st.session_state.resign_window_deadline is not None
            and now <= st.session_state.resign_window_deadline
        ):
            do_resign()
        else:
            confirm_resign_expired(now)
            arm_resign(now)
    else:
        arm_resign(now)


def update_fist_hold(now: float) -> float:
    """
    Real-time webcam fist handler.

    Behavior:
    - Fist for 2s arms resignation.
    - Hand must release fist.
    - Second fist for 2s confirms if it starts within the 3s window.
    """
    if st.session_state.game_over:
        return 0.0

    if st.session_state.resign_armed and st.session_state.resign_requires_release:
        return 0.0

    if st.session_state.resign_hold_start is None:
        if (
            st.session_state.resign_armed
            and st.session_state.resign_window_deadline is not None
            and now > st.session_state.resign_window_deadline
        ):
            confirm_resign_expired(now)

        st.session_state.resign_hold_start = now
        return 0.0

    elapsed = now - st.session_state.resign_hold_start
    progress = min(1.0, elapsed / RESIGN_HOLD_SECONDS)

    if elapsed >= RESIGN_HOLD_SECONDS:
        if st.session_state.resign_armed:
            do_resign()
        else:
            arm_resign(now)

        st.session_state.resign_hold_start = None
        return 0.0

    return progress


# ----------------------------------------------------------------------------
# Chess helpers
# ----------------------------------------------------------------------------

def get_legal_targets(board: chess.Board, from_square: int):
    return {
        move.to_square
        for move in board.legal_moves
        if move.from_square == from_square
    }


def set_terminal(text: str):
    st.session_state.game_over = True
    st.session_state.result_text = text
    st.session_state.status_message = text
    clear_selection()
    log(text)


def update_game_status():
    board = st.session_state.board

    if st.session_state.game_over:
        return

    if board.is_checkmate():
        winner = "Black" if board.turn == chess.WHITE else "White"
        set_terminal(f"Checkmate! {winner} wins.")
        return

    if board.is_stalemate():
        set_terminal("Stalemate. Draw.")
        return

    if board.is_insufficient_material():
        set_terminal("Draw by insufficient material.")
        return

    if hasattr(board, "is_seventyfive_moves") and board.is_seventyfive_moves():
        set_terminal("Draw by seventy-five-move rule.")
        return

    if hasattr(board, "is_fivefold_repetition") and board.is_fivefold_repetition():
        set_terminal("Draw by fivefold repetition.")
        return

    if board.is_game_over():
        result = board.result()
        set_terminal(f"Game over. Result: {result}")
        return

    if board.is_check():
        st.session_state.status_message = "Check!"
    else:
        turn = "White" if board.turn == chess.WHITE else "Black"
        st.session_state.status_message = f"{turn} to move"


def reset_board(fen: str = "startpos"):
    try:
        if fen in ("startpos", "", None):
            board = chess.Board()
        else:
            board = chess.Board(fen)
    except Exception:
        board = chess.Board()

    st.session_state.board = board
    st.session_state.game_over = False
    st.session_state.result_text = ""
    st.session_state.history = []
    st.session_state.last_move = None
    clear_selection()
    reset_resign_arm()
    update_game_status()


def new_game():
    reset_board("startpos")
    log("New game started from the initial position.")


def attempt_move(from_square: int, to_square: int):
    board = st.session_state.board

    legal_moves_for_pair = [
        move
        for move in board.legal_moves
        if move.from_square == from_square and move.to_square == to_square
    ]

    if not legal_moves_for_pair:
        clear_selection()
        log("Illegal destination ignored.")
        return

    promotion_moves = [move for move in legal_moves_for_pair if move.promotion]

    if promotion_moves:
        st.session_state.selected = None
        st.session_state.legal_targets = set()
        st.session_state.promotion_pending = (from_square, to_square)
        st.session_state.promotion_cursor = None
        st.session_state.status_message = "Promotion required. Choose queen, rook, bishop, or knight."
        log("Pawn promotion required.")
        return

    move = legal_moves_for_pair[0]
    san = board.san(move)
    board.push(move)

    st.session_state.last_move = (from_square, to_square)
    st.session_state.history.append(san)
    clear_selection()
    log(f"Played {san}.")
    update_game_status()


def complete_promotion(piece_type: int):
    pending = st.session_state.promotion_pending
    if not pending:
        return

    board = st.session_state.board
    from_square, to_square = pending
    move = chess.Move(from_square, to_square, promotion=piece_type)

    if not board.is_legal(move):
        st.session_state.promotion_pending = None
        clear_selection()
        log("Illegal promotion ignored.")
        return

    san = board.san(move)
    board.push(move)

    st.session_state.last_move = (from_square, to_square)
    st.session_state.history.append(san)
    clear_selection()
    log(f"Promoted with {san}.")
    update_game_status()


def handle_tap(square: int):
    if st.session_state.game_over:
        return

    if st.session_state.promotion_pending:
        return

    board = st.session_state.board
    selected = st.session_state.selected
    piece = board.piece_at(square)

    if selected is not None and square == selected:
        clear_selection()
        log("Selection cleared by pointing at the selected piece again.")
        return

    if selected is not None and square in st.session_state.legal_targets:
        attempt_move(selected, square)
        return

    if piece is not None and piece.color == board.turn:
        st.session_state.selected = square
        st.session_state.legal_targets = get_legal_targets(board, square)
        log(f"Selected {chess.square_name(square)}.")
        return

    if selected is not None:
        clear_selection()
        log("Selection cleared by pointing at a non-highlighted square.")


# ----------------------------------------------------------------------------
# Demo engine
# ----------------------------------------------------------------------------

def toggle_demo():
    st.session_state.demo_active = not st.session_state.demo_active


def reset_demo():
    release_camera()
    st.session_state.camera_active = False
    st.session_state.demo_index = 0
    st.session_state.demo_action = None
    st.session_state.demo_action_started = 0.0
    st.session_state.demo_active = True
    st.session_state.log = []
    reset_board("startpos")
    log("Demo restarted.")


def demo_tick(now: float):
    if not st.session_state.demo_active:
        st.session_state.cursor_square = None
        st.session_state.cursor_progress = 0.0
        st.session_state.cursor_gesture = None
        st.session_state.promotion_cursor = None
        return

    if st.session_state.demo_index >= len(DEMO_SCRIPT):
        st.session_state.demo_active = False
        st.session_state.cursor_square = None
        st.session_state.cursor_progress = 0.0
        st.session_state.cursor_gesture = None
        st.session_state.promotion_cursor = None
        st.session_state.status_message = "Demo complete."
        log("Demo complete.")
        return

    action = st.session_state.demo_action

    if action is None:
        action = DEMO_SCRIPT[st.session_state.demo_index]
        st.session_state.demo_action = action
        st.session_state.demo_action_started = now

        st.session_state.cursor_square = None
        st.session_state.cursor_progress = 0.0
        st.session_state.cursor_gesture = None
        st.session_state.promotion_cursor = None

        kind = action["kind"]

        if kind == "msg":
            st.session_state.status_message = action["text"]
            log(action["text"])

        elif kind == "board":
            reset_board(action["fen"])
            log(f"Loaded position: {action['fen']}")

        elif kind == "point":
            st.session_state.cursor_square = chess.parse_square(action["square"])

        elif kind == "promo":
            st.session_state.promotion_cursor = action["piece"]

        elif kind == "fist":
            st.session_state.cursor_gesture = "fist"

        return

    elapsed = now - st.session_state.demo_action_started
    duration = float(action.get("duration", 1.0))
    kind = action["kind"]

    if kind == "point":
        st.session_state.cursor_progress = min(1.0, elapsed / HOLD_SECONDS)
    elif kind == "promo":
        st.session_state.cursor_progress = min(1.0, elapsed / HOLD_SECONDS)
    elif kind == "fist":
        st.session_state.cursor_progress = min(1.0, elapsed / RESIGN_HOLD_SECONDS)
    else:
        st.session_state.cursor_progress = 0.0

    if elapsed >= duration:
        if kind == "point":
            handle_tap(chess.parse_square(action["square"]))
        elif kind == "promo":
            complete_promotion(PROMO_NAME_TO_CHESS[action["piece"]])
        elif kind == "fist":
            complete_resign_hold(now)

        st.session_state.demo_index += 1
        st.session_state.demo_action = None
        st.session_state.cursor_square = None
        st.session_state.cursor_progress = 0.0
        st.session_state.cursor_gesture = None
        st.session_state.promotion_cursor = None


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def square_to_xy(square: int):
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    x = file * SQ
    y = STATUS_PX + (7 - rank) * SQ
    return x, y


def render_board_image():
    board = st.session_state.board

    img = Image.new("RGB", (IMG_W, IMG_H), (15, 23, 42))
    d = ImageDraw.Draw(img)

    # Base board and pieces
    for rank in range(7, -1, -1):
        for file in range(8):
            square = chess.square(file, rank)
            x = file * SQ
            y = STATUS_PX + (7 - rank) * SQ

            color = LIGHT if (file + rank) % 2 == 0 else DARK
            d.rectangle([x, y, x + SQ - 1, y + SQ - 1], fill=color)

            piece = board.piece_at(square)
            if piece is not None:
                symbol = PIECE_UNICODE.get(piece.symbol(), "?")
                if piece.color == chess.WHITE:
                    fill = (255, 255, 255)
                    stroke = (25, 25, 25)
                else:
                    fill = (25, 25, 25)
                    stroke = (240, 240, 240)

                draw_centered_text(
                    d,
                    (x + SQ // 2, y + SQ // 2),
                    symbol,
                    load_font(54),
                    fill,
                    stroke,
                )

    # Coordinate labels
    for i, file_char in enumerate("abcdefgh"):
        d.text((i * SQ + 5, IMG_H - 18), file_char, font=load_font(14), fill=(226, 232, 240))

    for r in range(8):
        d.text((5, STATUS_PX + r * SQ + 4), str(8 - r), font=load_font(14), fill=(226, 232, 240))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    last_move = st.session_state.last_move
    selected = st.session_state.selected
    legal_targets = st.session_state.legal_targets
    cursor_square = st.session_state.cursor_square
    cursor_progress = st.session_state.cursor_progress

    check_square = None
    if board.is_check() and not st.session_state.game_over:
        check_square = board.king(board.turn)

    for rank in range(7, -1, -1):
        for file in range(8):
            square = chess.square(file, rank)
            x, y = square_to_xy(square)

            if last_move and square in last_move:
                od.rectangle([x, y, x + SQ, y + SQ], fill=(59, 130, 246, 65))

            if square == selected:
                od.rectangle(
                    [x + 4, y + 4, x + SQ - 4, y + SQ - 4],
                    outline=(250, 204, 21, 255),
                    width=6,
                )

            if square in legal_targets:
                od.ellipse(
                    [x + SQ // 4, y + SQ // 4, x + 3 * SQ // 4, y + 3 * SQ // 4],
                    fill=(34, 197, 94, 135),
                    outline=(22, 163, 74, 255),
                    width=3,
                )

            if check_square is not None and square == check_square:
                od.rectangle(
                    [x + 3, y + 3, x + SQ - 3, y + SQ - 3],
                    outline=(239, 68, 68, 255),
                    width=6,
                )

    if cursor_square is not None:
        x, y = square_to_xy(cursor_square)
        od.rectangle(
            [x + 5, y + 5, x + SQ - 5, y + SQ - 5],
            outline=(34, 211, 238, 255),
            width=5,
        )

        if cursor_progress > 0:
            od.arc(
                [x + 14, y + 14, x + SQ - 14, y + SQ - 14],
                start=-90,
                end=-90 + int(360 * cursor_progress),
                fill=(250, 204, 21, 255),
                width=6,
            )

    if st.session_state.promotion_pending:
        od.rectangle([0, STATUS_PX, IMG_W, IMG_H], fill=(2, 6, 23, 155))

        for name, rect in PROMO_RECTS_BOARD.items():
            x1, y1, x2, y2 = rect
            y1 += STATUS_PX
            y2 += STATUS_PX

            is_hover = st.session_state.promotion_cursor == name
            fill = (250, 204, 21, 235) if is_hover else (248, 250, 252, 225)

            od.rectangle(
                [x1, y1, x2, y2],
                fill=fill,
                outline=(15, 23, 42, 255),
                width=4,
            )

    if st.session_state.cursor_gesture == "fist":
        od.rectangle([0, STATUS_PX, IMG_W, IMG_H], fill=(239, 68, 68, 75))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    # Status bar
    d.rectangle([0, 0, IMG_W, STATUS_PX], fill=(15, 23, 42))

    turn = "White" if board.turn == chess.WHITE else "Black"

    if st.session_state.game_over:
        headline = st.session_state.result_text
        headline_color = (248, 113, 113)
    elif st.session_state.resign_armed:
        headline = "Resign armed — repeat fist within 3s"
        headline_color = (251, 191, 36)
    elif board.is_check():
        headline = "Check!"
        headline_color = (248, 113, 113)
    else:
        headline = st.session_state.status_message or f"{turn} to move"
        headline_color = (226, 232, 240)

    d.text(
        (16, 16),
        "Touchless Chess • python-chess legal-move engine",
        font=load_font(18),
        fill=(148, 163, 184),
    )
    d.text((16, 48), headline, font=load_font(28), fill=headline_color)

    # Promotion labels
    if st.session_state.promotion_pending:
        d.text(
            (IMG_W // 2, PROMO_Y_BOARD + STATUS_PX - 38),
            "Promote pawn to:",
            font=load_font(26),
            fill=(255, 255, 255),
            anchor="mm",
        )

        for name, rect in PROMO_RECTS_BOARD.items():
            x1, y1, x2, y2 = rect
            y1 += STATUS_PX
            y2 += STATUS_PX
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            symbol = PROMO_UNICODE[board.turn][name]
            draw_centered_text(d, (cx, cy - 8), symbol, load_font(56), (15, 23, 42))
            d.text((cx, y2 - 20), name.title(), font=load_font(16), fill=(15, 23, 42), anchor="mm")

    # Fist progress
    if st.session_state.cursor_gesture == "fist":
        bar_width = int((IMG_W - 80) * st.session_state.cursor_progress)
        d.rectangle([40, IMG_H - 34, 40 + bar_width, IMG_H - 18], fill=(250, 204, 21))
        d.text(
            (IMG_W // 2, IMG_H - 62),
            "Fist held: resign",
            font=load_font(22),
            fill=(255, 255, 255),
            anchor="mm",
        )

    return img


# ----------------------------------------------------------------------------
# Touchless / MediaPipe helpers
# ----------------------------------------------------------------------------

def release_camera():
    if st.session_state.get("cap") is not None:
        try:
            st.session_state.cap.release()
        except Exception:
            pass
        st.session_state.cap = None

    if st.session_state.get("mp_hands") is not None:
        try:
            st.session_state.mp_hands.close()
        except Exception:
            pass
        st.session_state.mp_hands = None

    st.session_state.touch_frame = None


def start_camera():
    st.session_state.camera_active = True
    st.session_state.touch_error = ""


def stop_camera():
    st.session_state.camera_active = False
    release_camera()


def get_board_rect(frame_shape):
    h, w = frame_shape[:2]
    bs = min(int(w * 0.62), int(h * 0.82))
    bx = (w - bs) // 2
    by = max(10, int(h * 0.08))

    if by + bs > h:
        by = max(0, h - bs - 10)

    return bx, by, bs


def detect_hand(frame_rgb):
    if mp is None or st.session_state.mp_hands is None:
        return {"gesture": "none"}

    results = st.session_state.mp_hands.process(frame_rgb)

    if not results.multi_hand_landmarks:
        return {"gesture": "none"}

    landmarks = results.multi_hand_landmarks[0]
    h, w = frame_rgb.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in landmarks.landmark]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    wrist = pts[0]

    def extended(tip_idx, pip_idx):
        return dist(pts[tip_idx], wrist) > dist(pts[pip_idx], wrist) * 1.08

    index_extended = extended(8, 6)
    middle_extended = extended(12, 10)
    ring_extended = extended(16, 14)
    pinky_extended = extended(20, 18)

    if index_extended and not middle_extended and not ring_extended and not pinky_extended:
        return {"gesture": "point", "tip": pts[8]}

    if not index_extended and not middle_extended and not ring_extended and not pinky_extended:
        return {"gesture": "fist", "tip": pts[8]}

    return {"gesture": "open", "tip": pts[8]}


def map_point_to_target(frame_shape, tip):
    bx, by, bs = get_board_rect(frame_shape)

    if not (bx <= tip[0] < bx + bs and by <= tip[1] < by + bs):
        return None

    px = int((tip[0] - bx) * BOARD_PX / bs)
    py = int((tip[1] - by) * BOARD_PX / bs)

    if st.session_state.promotion_pending:
        for name, rect in PROMO_RECTS_BOARD.items():
            x1, y1, x2, y2 = rect
            if x1 <= px < x2 and y1 <= py < y2:
                return ("promo", PROMO_NAME_TO_CHESS[name])
        return None

    if 0 <= px < BOARD_PX and 0 <= py < BOARD_PX:
        file = px // SQ
        rank = 8 - (py // SQ)

        if 0 <= file < 8 and 0 <= rank < 8:
            return ("square", chess.square(file, rank))

    return None


def update_hand_dwell(target, now: float) -> float:
    hd = st.session_state.hand_dwell
    cooldown = st.session_state.get("dwell_cooldown_until", 0.0)

    if now < cooldown:
        hd["key"] = None
        hd["started"] = None
        return 0.0

    if target is None:
        hd["key"] = None
        hd["started"] = None
        return 0.0

    key = f"{target[0]}:{target[1]}"

    if hd.get("key") != key:
        hd["key"] = key
        hd["started"] = now
        return 0.0

    elapsed = now - hd["started"]
    progress = min(1.0, elapsed / HOLD_SECONDS)

    if elapsed >= HOLD_SECONDS:
        if target[0] == "square":
            handle_tap(target[1])
        else:
            complete_promotion(target[1])

        hd["key"] = None
        hd["started"] = None
        st.session_state.dwell_cooldown_until = now + 0.6
        return 0.0

    return progress


def compose_touch_frame(frame_rgb, board_img, hand, target, progress):
    if cv2 is None:
        return frame_rgb

    frame = frame_rgb.copy()
    bx, by, bs = get_board_rect(frame.shape)

    board_only = board_img.crop((0, STATUS_PX, IMG_W, IMG_H)).resize((bs, bs), RESAMPLE)
    frame[by:by + bs, bx:bx + bs] = np.array(board_only)

    if hand and hand.get("tip"):
        tip = (int(hand["tip"][0]), int(hand["tip"][1]))
        gesture = hand.get("gesture", "none")

        if gesture == "point":
            color = (34, 211, 238)
        elif gesture == "fist":
            color = (239, 68, 68)
        else:
            color = (148, 163, 184)

        cv2.circle(frame, tip, 16, color, 2)
        cv2.circle(frame, tip, 5, color, -1)

        if progress > 0:
            cv2.ellipse(
                frame,
                tip,
                (28, 28),
                0,
                270,
                int(270 + 360 * progress),
                (250, 204, 21),
                4,
            )

    gesture_text = f"Gesture: {(hand or {}).get('gesture', 'none')}"
    cv2.putText(
        frame,
        gesture_text,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
    )

    if st.session_state.game_over:
        status_text = st.session_state.result_text
    elif st.session_state.resign_armed:
        status_text = "Resign armed — repeat fist"
    elif st.session_state.board.is_check():
        status_text = "Check!"
    else:
        status_text = st.session_state.status_message

    cv2.putText(
        frame,
        str(status_text)[:52],
        (12, frame.shape[0] - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
    )

    return frame


def touchless_tick(now: float):
    st.session_state.touch_frame = None

    if not st.session_state.camera_active:
        return

    if cv2 is None or mp is None:
        st.session_state.touch_error = (
            "OpenCV and MediaPipe are required for live touchless mode. "
            "Install dependencies and restart the app. Auto Demo and Mouse modes still work."
        )
        st.session_state.camera_active = False
        return

    if st.session_state.cap is None:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            st.session_state.touch_error = "Unable to open webcam. Check permissions and camera index."
            st.session_state.camera_active = False
            return
        st.session_state.cap = cap

    if st.session_state.mp_hands is None:
        st.session_state.mp_hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    ok, frame = st.session_state.cap.read()

    if not ok:
        st.session_state.touch_error = "Webcam frame read failed."
        st.session_state.camera_active = False
        release_camera()
        return

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    hand = detect_hand(frame_rgb)
    gesture = hand.get("gesture", "none")

    target = None
    progress = 0.0

    if gesture == "point":
        st.session_state.resign_hold_start = None
        target = map_point_to_target(frame_rgb.shape, hand["tip"])
        progress = update_hand_dwell(target, now)

    elif gesture == "fist":
        st.session_state.hand_dwell = {"key": None, "started": None}
        progress = update_fist_hold(now)

    else:
        st.session_state.hand_dwell = {"key": None, "started": None}
        st.session_state.resign_hold_start = None
        st.session_state.resign_requires_release = False

    if target and target[0] == "square":
        st.session_state.cursor_square = target[1]
        st.session_state.promotion_cursor = None
    elif target and target[0] == "promo":
        st.session_state.cursor_square = None
        st.session_state.promotion_cursor = PROMO_CHESS_TO_NAME.get(target[1])
    else:
        st.session_state.cursor_square = None
        if gesture != "fist":
            st.session_state.promotion_cursor = None

    st.session_state.cursor_gesture = "fist" if gesture == "fist" else None
    st.session_state.cursor_progress = progress

    board_img = render_board_image()
    st.session_state.touch_frame = compose_touch_frame(frame_rgb, board_img, hand, target, progress)


# ----------------------------------------------------------------------------
# UI bodies
# ----------------------------------------------------------------------------

def _realtime_body():
    now = time.time()

    if st.session_state.mode != "Auto Demo":
        st.session_state.demo_active = False

    if st.session_state.mode != "Touchless Webcam" and st.session_state.camera_active:
        stop_camera()

    if st.session_state.mode == "Auto Demo":
        demo_tick(now)
    elif st.session_state.mode == "Touchless Webcam":
        touchless_tick(now)

    left, right = st.columns([2, 1])

    with left:
        if st.session_state.mode == "Touchless Webcam" and st.session_state.touch_frame is not None:
            st.image(st.session_state.touch_frame, channels="RGB", use_container_width=True)
        else:
            st.image(render_board_image(), use_container_width=True)

    with right:
        st.subheader("Live state")

        if st.session_state.game_over:
            st.error(st.session_state.result_text)
        elif st.session_state.resign_armed:
            st.warning("Resign armed. Repeat the fist gesture within 3 seconds.")
        elif st.session_state.board.is_check():
            st.warning("Check!")
        else:
            st.info(st.session_state.status_message)

        board = st.session_state.board
        turn = "White" if board.turn == chess.WHITE else "Black"
        selected_name = chess.square_name(st.session_state.selected) if st.session_state.selected else "—"
        legal_count = len(st.session_state.legal_targets)

        st.markdown(f"**Turn:** {turn}")
        st.markdown(f"**Selected:** {selected_name}")
        st.markdown(f"**Legal destinations:** {legal_count}")

        if st.session_state.mode == "Auto Demo":
            c1, c2 = st.columns(2)
            c1.button(
                "Pause demo" if st.session_state.demo_active else "Resume demo",
                key="demo_toggle",
                on_click=toggle_demo,
                use_container_width=True,
            )
            c2.button("Restart demo", key="demo_restart", on_click=reset_demo, use_container_width=True)

        elif st.session_state.mode == "Touchless Webcam":
            c1, c2 = st.columns(2)

            if not st.session_state.camera_active:
                c1.button("Start webcam", key="start_cam", on_click=start_camera, use_container_width=True)
            else:
                c1.button("Stop webcam", key="stop_cam", on_click=stop_camera, use_container_width=True)

            c2.button("New game", key="new_game_rt", on_click=new_game, use_container_width=True)

            if cv2 is None or mp is None:
                st.warning("OpenCV/MediaPipe unavailable. Install dependencies for live hand pointing.")

            if st.session_state.touch_error:
                st.error(st.session_state.touch_error)

            st.markdown(
                """
                **Gesture rules**
                - Index-only point: select/move after 0.5s dwell.
                - Fist for 2s: arm resignation.
                - Release, then fist again within 3s: confirm resignation.
                """
            )

        with st.expander("Activity log", expanded=True):
            if not st.session_state.log:
                st.write("No events yet.")
            else:
                for entry in reversed(st.session_state.log[-15:]):
                    st.markdown(f"- {entry}")

        with st.expander("Engine FEN"):
            st.code(board.fen(), language=None)


def _mouse_body():
    now = time.time()

    if st.session_state.camera_active:
        stop_camera()

    st.session_state.demo_active = False
    st.session_state.cursor_square = None
    st.session_state.cursor_progress = 0.0
    st.session_state.cursor_gesture = None
    st.session_state.promotion_cursor = None

    st.image(render_board_image(), use_container_width=True)

    board = st.session_state.board

    if st.session_state.game_over:
        st.error(st.session_state.result_text)
        st.button("New game", key="new_game_mouse_over", on_click=new_game, use_container_width=True)
        return

    if board.is_check():
        st.warning("Check!")

    if st.session_state.resign_armed:
        st.warning("Resign armed. Press resign again within 3 seconds to confirm.")

    if st.session_state.promotion_pending:
        st.subheader("Choose promotion piece")
        cols = st.columns(4)

        for i, (name, piece_type) in enumerate(PROMOTION_CHOICES):
            if cols[i].button(name.title(), key=f"promo_{name}", use_container_width=True):
                complete_promotion(piece_type)

        return

    st.subheader("Click a square")
    st.caption("Clicking emulates a completed 0.5-second point dwell.")

    for rank in range(7, -1, -1):
        cols = st.columns(8)

        for file in range(8):
            square = chess.square(file, rank)
            name = chess.square_name(square)
            piece = board.piece_at(square)

            if piece is None:
                label = "·"
            else:
                label = PIECE_UNICODE.get(piece.symbol(), "?")

            if cols[file].button(
                label,
                key=f"board_{name}",
                help=name,
                use_container_width=True,
            ):
                handle_tap(square)

    c1, c2 = st.columns([1, 3])

    if c1.button(
        "Resign current player",
        key="resign_mouse",
        use_container_width=True,
    ):
        complete_resign_hold(now)

    if c2.button("New game", key="new_game_mouse", on_click=new_game, use_container_width=True):
        pass


# ----------------------------------------------------------------------------
# Fragment wiring
# ----------------------------------------------------------------------------

if hasattr(st, "fragment"):
    try:
        realtime_fragment = st.fragment(run_every=0.12)(_realtime_body)
    except Exception:
        realtime_fragment = st.fragment()(_realtime_body)

    try:
        mouse_fragment = st.fragment()(_mouse_body)
    except Exception:
        mouse_fragment = _mouse_body
else:
    realtime_fragment = _realtime_body
    mouse_fragment = _mouse_body


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    init_session()

    st.title("♟️ Touchless Chess Board")
    st.caption(
        "Point to select, hold for 0.5 seconds, then point again to move. "
        "python-chess enforces legal moves, check, promotion, and terminal game states."
    )

    mode = st.selectbox("Interaction mode", MODES, key="mode")

    if mode == "Mouse / Touch Board":
        mouse_fragment()
    else:
        realtime_fragment()

    st.divider()
    st.caption(
        "No API key required. The app starts in Auto Demo mode and immediately plays a realistic "
        "touchless-style demonstration with legal-move validation, check, promotion, and resign confirmation."
    )


if __name__ == "__main__":
    main()