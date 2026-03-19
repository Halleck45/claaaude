#!/usr/bin/env python3
"""
Claaaude — Claude Code desktop mascot (sprite-based, multi-instance)

INSTALL :
  sudo apt install python3-pyqt5
  python3 claude_mascot.py &

HOOKS (settings.json) :
  Stop             → mkdir -p /tmp/claude_mascot_states && echo done > /tmp/claude_mascot_states/$PPID
  Notification     → mkdir -p /tmp/claude_mascot_states && echo waiting > /tmp/claude_mascot_states/$PPID
  UserPromptSubmit → mkdir -p /tmp/claude_mascot_states && echo working > /tmp/claude_mascot_states/$PPID

CONTRÔLES :
  Clic gauche + glisser  → déplacer la bande verticalement
  Clic droit             → quitter
"""

import sys, os, time, signal, random

# Forcer XWayland — nécessaire pour sticky/above/raise sous Wayland
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (QPainter, QColor, QImage, QPixmap, QFont, QFontMetrics,
                          QPen, QPainterPath, QRegion)

# ── Constantes ───────────────────────────────────────────────────────────────

SPRITE_SIZE = 40
SCALE       = 2
RENDER_SIZE = SPRITE_SIZE * SCALE   # 80
STRIP_H     = 180                   # hauteur bande (bulle 50 + 80 sprite + 20 texte dessous + marge)
TICK_MS     = 40                    # ~25 fps
AUTO_IDLE   = 12                    # s avant retour idle automatique
STATE_DIR   = '/tmp/claude_mascot_states'
STATE_FILE  = '/tmp/claude_mascot_state'  # legacy
ASSETS_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
CHROMAKEY   = QColor(0, 0, 255)
SHEETS      = list(range(101, 112))          # 101..111

STATE_LABELS = {
    'idle':    ('sleeping', QColor(230, 200, 40)),    # jaune
    'working': ('working',  QColor(40, 200, 40)),     # vert
    'ask':     ('ask',      QColor(220, 40, 40)),     # rouge
    'done':    ('done',     QColor(40, 200, 40)),     # vert
}


# ── SpriteAtlas ──────────────────────────────────────────────────────────────

class SpriteAtlas:
    """Charge toutes les sprite sheets, découpe les frames, chromakey, flip, scale."""

    def __init__(self):
        # frames_left[global_index] = QPixmap 80×80 (direction gauche = originale)
        # frames_right[global_index] = QPixmap 80×80 (flipped horizontal)
        self.frames_left: List[QPixmap] = []
        self.frames_right: List[QPixmap] = []
        self._load()

    def _load(self):
        for sheet_num in SHEETS:
            path = os.path.join(ASSETS_DIR, f'{sheet_num}.bmp')
            img = QImage(path)
            if img.isNull():
                # Remplir avec des pixmaps vides si le fichier manque
                for _ in range(16):
                    empty = QPixmap(RENDER_SIZE, RENDER_SIZE)
                    empty.fill(Qt.transparent)
                    self.frames_left.append(empty)
                    self.frames_right.append(empty)
                continue

            # Convertir en ARGB32 pour manipuler la transparence
            img = img.convertToFormat(QImage.Format_ARGB32)

            blue_rgb = CHROMAKEY.rgb() | 0xFF000000  # 0xFF0000FF

            for i in range(16):
                frame = img.copy(i * SPRITE_SIZE, 0, SPRITE_SIZE, SPRITE_SIZE)
                # Chromakey : bleu pur → transparent (pixel par pixel)
                for py in range(frame.height()):
                    for px in range(frame.width()):
                        if frame.pixel(px, py) == blue_rgb:
                            frame.setPixel(px, py, 0)  # ARGB 0 = fully transparent

                # Scale ×2 nearest-neighbor (pixel art net)
                scaled = frame.scaled(RENDER_SIZE, RENDER_SIZE, Qt.IgnoreAspectRatio,
                                      Qt.FastTransformation)
                pix_left = QPixmap.fromImage(scaled)

                # Flip horizontal pour direction droite
                pix_right = QPixmap.fromImage(scaled.mirrored(True, False))

                self.frames_left.append(pix_left)
                self.frames_right.append(pix_right)

    def get(self, sheet: int, frame: int, facing_right: bool) -> QPixmap:
        """Retourne le pixmap pour un sheet (101-111) et frame (0-15)."""
        idx = (sheet - 101) * 16 + frame
        if idx < 0 or idx >= len(self.frames_left):
            return self.frames_left[0]
        return self.frames_right[idx] if facing_right else self.frames_left[idx]


# ── Animation ────────────────────────────────────────────────────────────────

@dataclass
class Animation:
    """Définit une séquence d'animation."""
    frames: List[Tuple[int, int, int]]  # [(sheet, frame_idx, durée_ticks), ...]
    speed: float = 1.5                  # px/tick mouvement horizontal
    loop: bool = True                   # boucle infinie ?
    max_loops: int = 0                  # 0 = infini (si loop=True)

# Animations par état
ANIM_IDLE = Animation(
    frames=[(101, 0, 15), (101, 1, 15)],
    speed=0.0,    # dort sur place
    loop=True,
)

ANIM_WORKING = Animation(
    frames=[(101, 3, 5), (101, 4, 5), (101, 5, 5), (101, 6, 5)],
    speed=6.0,
    loop=True,
)

ANIM_ASK = Animation(
    frames=[
        (105, 8, 8), (105, 9, 8), (105, 10, 8),
    ],
    speed=0.0,   # sur place
    loop=True,
)

ANIM_DONE = Animation(
    frames=[
        (108, 7, 4), (108, 8, 4), (108, 9, 4), (108, 10, 4),
        (108, 11, 4), (108, 12, 4), (108, 13, 4), (108, 14, 4),
    ],
    speed=6.0,
    loop=True,
    max_loops=3,
)

ANIM_GRABBED_A = Animation(frames=[(103, 2, 8), (103, 3, 8), (103, 4, 8)], speed=0.0, loop=True)
ANIM_GRABBED_B = Animation(frames=[(103, 5, 8), (103, 6, 8), (103, 7, 8)], speed=0.0, loop=True)
ANIM_GRABBED_C = Animation(frames=[(103, 14, 10), (103, 15, 10)], speed=0.0, loop=True)
ANIM_GRABBED_D = Animation(frames=[(104, 2, 8), (104, 3, 8)], speed=0.0, loop=True)
ANIM_GRABBED_E = Animation(frames=[(105, 0, 8), (105, 1, 8), (105, 2, 8), (105, 3, 8), (105, 4, 8), (105, 5, 8), (105, 6, 8)], speed=0.0, loop=True)
ANIM_GRABBED_F = Animation(frames=[(106, 5, 8)], speed=0.0, loop=True)
ANIM_GRABBED_G = Animation(frames=[(107, 1, 8), (107, 2, 8), (107, 3, 8), (107, 4, 8)], speed=0.0, loop=True)
ANIM_GRABBED_H = Animation(frames=[(107, 7, 8), (107, 8, 8), (107, 9, 8), (107, 10, 8)], speed=0.0, loop=True)
GRAB_ANIMS = [
    ANIM_GRABBED_A, ANIM_GRABBED_B, ANIM_GRABBED_C, ANIM_GRABBED_D,
    ANIM_GRABBED_E, ANIM_GRABBED_F, ANIM_GRABBED_G, ANIM_GRABBED_H,
]

# ── Dream animations (idle sheep, every 3-5 min) ────────────────────────────

DREAM_MIN_TICKS = int(180 * 1000 / TICK_MS)   # 3 min
DREAM_MAX_TICKS = int(300 * 1000 / TICK_MS)   # 5 min

DREAM_MOVE_NONE  = 'none'
DREAM_MOVE_CROSS = 'cross'   # horizontal L→R across screen, 1.5 s
DREAM_MOVE_FALL  = 'fall'    # diagonal fall ↘→↙, 1.5 s

ANIM_DREAM_A = Animation(
    frames=[(109, 0, 8), (109, 1, 8), (109, 2, 8)],
    speed=0.0, loop=True, max_loops=3,
)
ANIM_DREAM_B = Animation(
    frames=[(106, 8, 8), (106, 9, 8), (106, 10, 8)],
    speed=0.0, loop=True, max_loops=3,
)
ANIM_DREAM_CROSS = Animation(
    frames=[(108, i, 4) for i in range(16)],
    speed=0.0, loop=False,
)
ANIM_DREAM_FALL = Animation(
    frames=[(109, i, 6) for i in range(6, 16)],
    speed=0.0, loop=False,
)

DREAM_ANIMS = [
    (ANIM_DREAM_A, DREAM_MOVE_NONE),
    (ANIM_DREAM_B, DREAM_MOVE_NONE),
    (ANIM_DREAM_CROSS, DREAM_MOVE_CROSS),
    (ANIM_DREAM_FALL, DREAM_MOVE_FALL),
]

STATE_ANIMS = {
    'idle':    ANIM_IDLE,
    'working': ANIM_WORKING,
    'ask':     ANIM_ASK,
    'done':    ANIM_DONE,
}


# ── AnimationPlayer ──────────────────────────────────────────────────────────

class AnimationPlayer:
    """Gère le frame courant et avance au tick."""

    def __init__(self, anim: Animation):
        self.anim = anim
        self.frame_idx = 0       # index dans anim.frames
        self.ticks_left = anim.frames[0][2] if anim.frames else 1
        self.loops_done = 0
        self.finished = False

    def tick(self):
        if self.finished:
            return
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            self.frame_idx += 1
            if self.frame_idx >= len(self.anim.frames):
                if self.anim.loop:
                    self.loops_done += 1
                    if self.anim.max_loops > 0 and self.loops_done >= self.anim.max_loops:
                        self.finished = True
                        self.frame_idx = len(self.anim.frames) - 1
                        return
                    self.frame_idx = 0
                else:
                    self.finished = True
                    self.frame_idx = len(self.anim.frames) - 1
                    return
            self.ticks_left = self.anim.frames[self.frame_idx][2]

    def current_frame(self) -> Tuple[int, int]:
        """Retourne (sheet, frame_index)."""
        f = self.anim.frames[self.frame_idx]
        return f[0], f[1]

    def play(self, anim: Animation):
        """Démarre une nouvelle animation."""
        self.anim = anim
        self.frame_idx = 0
        self.ticks_left = anim.frames[0][2] if anim.frames else 1
        self.loops_done = 0
        self.finished = False


# ── Sheep ────────────────────────────────────────────────────────────────────

class Sheep:
    """Un mouton sprite avec position, direction, état et animation."""

    def __init__(self, sw: int, atlas: SpriteAtlas, pid: int = 0):
        self.sw = sw
        self.atlas = atlas
        self.pid = pid
        self.x = float(random.randint(60, sw - 60))
        self.dir = random.choice([-1, 1])   # -1 = gauche, 1 = droite
        self.state = 'idle'
        self.label = ''           # texte affiché au-dessus du mouton
        self.ask_message = ''     # texte de la bulle (état ask)
        self._done_handled = False
        self.player = AnimationPlayer(ANIM_IDLE)
        # Dream system
        self.y_offset = 0.0
        self._dreaming = False
        self._dream_movement = DREAM_MOVE_NONE
        self._dream_saved_x = 0.0
        self._dream_saved_dir = 1
        self._dream_dx = 0.0
        self._dream_dy = 0.0
        self._dream_timer = random.randint(DREAM_MIN_TICKS, DREAM_MAX_TICKS)
        self._update_label()

    def set_state(self, new_state: str, message: str = ''):
        # "waiting for your input" = Claude a fini, pas une question
        if new_state == 'ask' and message and 'waiting for your input' in message.lower():
            new_state = 'done'
            message = ''
        # Raccourcir les messages de permission
        elif new_state == 'ask' and message and 'permission' in message.lower():
            message = 'needs your permission'
        # Toute autre question → simplifier
        elif new_state == 'ask' and message:
            message = 'What do you want?'
        if new_state == self.state and message == self.ask_message:
            return
        # Ignorer 'done' si on a déjà fini la roulade (retour idle)
        if new_state == 'done' and self._done_handled:
            return
        self._cancel_dream()
        self._done_handled = (new_state == 'idle' and self._done_handled)
        if new_state != self.state:
            anim = STATE_ANIMS.get(new_state, ANIM_IDLE)
            self.player.play(anim)
        self.state = new_state
        self.ask_message = message if new_state == 'ask' else ''
        self._update_label()

    def _update_label(self):
        """Construit le label texte + dossier (le cercle coloré est dessiné séparément)."""
        verb, _color = STATE_LABELS.get(self.state, ('idle', QColor(230, 200, 40)))
        folder = self._get_cwd()
        if folder:
            self.label = f'{verb} - {folder}'
        else:
            self.label = verb

    def _get_cwd(self) -> str:
        """Lit le répertoire de travail du process Claude via /proc."""
        if self.pid <= 0:
            return ''
        try:
            cwd = os.readlink(f'/proc/{self.pid}/cwd')
            return os.path.basename(cwd)
        except OSError:
            return ''

    def update(self):
        self.player.tick()

        # Mouvement horizontal
        speed = self.player.anim.speed
        if speed > 0:
            self.x += speed * self.dir
            self._wrap()

        # Si l'animation 'done' est terminée, retour idle
        if self.state == 'done' and self.player.finished:
            self._done_handled = True
            self.set_state('idle')

        # Dream system — idle sheep play a random animation every 3-5 min
        if self.state == 'idle' and not self._dreaming and self.player.anim is ANIM_IDLE:
            self._dream_timer -= 1
            if self._dream_timer <= 0:
                self._start_dream()
        if self._dreaming:
            self.x += self._dream_dx
            self.y_offset += self._dream_dy
            if self.player.finished:
                self._cancel_dream()
                self.player.play(ANIM_IDLE)

    def _wrap(self):
        margin = RENDER_SIZE // 2
        if self.x > self.sw + margin:
            self.x = float(-margin)
        elif self.x < -margin:
            self.x = float(self.sw + margin)

    def _start_dream(self):
        anim, movement = random.choice(DREAM_ANIMS)
        self._dreaming = True
        self._dream_movement = movement
        self._dream_saved_x = self.x
        self._dream_saved_dir = self.dir
        self.y_offset = 0.0
        total_ticks = sum(f[2] for f in anim.frames)
        if movement == DREAM_MOVE_CROSS:
            self.x = float(-RENDER_SIZE)
            self.dir = 1
            self._dream_dx = (self.sw + RENDER_SIZE * 2) / total_ticks
            self._dream_dy = 0.0
        elif movement == DREAM_MOVE_FALL:
            self.y_offset = float(-(STRIP_H - 40))
            self.dir = -1
            self._dream_dx = -(self.sw * 0.3) / total_ticks
            self._dream_dy = (STRIP_H - 40) / total_ticks
        else:
            self._dream_dx = 0.0
            self._dream_dy = 0.0
        self.player.play(anim)

    def _cancel_dream(self):
        if not self._dreaming:
            return
        self._dreaming = False
        self.x = self._dream_saved_x
        self.dir = self._dream_saved_dir
        self.y_offset = 0.0
        self._dream_timer = random.randint(DREAM_MIN_TICKS, DREAM_MAX_TICKS)

    def draw(self, painter: QPainter, y_base: int):
        sheet, frame = self.player.current_frame()
        facing_right = self.dir > 0
        pix = self.atlas.get(sheet, frame, facing_right)
        cx = int(self.x)
        sprite_x = cx - RENDER_SIZE // 2
        sprite_y = y_base - RENDER_SIZE + int(self.y_offset)
        painter.drawPixmap(sprite_x, sprite_y, pix)

        # Label SOUS le mouton : cercle coloré + texte
        if self.label:
            font = QFont('Sans', 7)
            font.setBold(True)
            painter.setFont(font)
            fm = QFontMetrics(font)

            _verb, color = STATE_LABELS.get(self.state, ('idle', QColor(230, 200, 40)))
            circle_r = 5
            text_y = y_base + 14  # sous le sprite
            tw = fm.horizontalAdvance(self.label)
            total_w = circle_r * 2 + 4 + tw  # cercle + gap + texte
            start_x = cx - total_w // 2

            # Cercle coloré
            painter.setPen(QPen(QColor(40, 40, 40), 1))
            painter.setBrush(color)
            painter.drawEllipse(start_x, text_y - circle_r - fm.ascent() // 2,
                                circle_r * 2, circle_r * 2)
            painter.setBrush(Qt.NoBrush)

            # Texte après le cercle
            tx = start_x + circle_r * 2 + 4
            # Contour blanc pour lisibilité
            painter.setPen(QPen(QColor(255, 255, 255, 220)))
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                painter.drawText(tx + dx, text_y + dy, self.label)
            # Texte noir
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(tx, text_y, self.label)

        # Bulle pour l'état ask (au-dessus du mouton)
        if self.state == 'ask':
            self._draw_bubble(painter, cx, sprite_y)

    def hit_region(self, y_base: int) -> QRegion:
        """Retourne la zone cliquable du mouton (sprite + label dessous + bulle)."""
        cx = int(self.x)
        sprite_y = y_base - RENDER_SIZE
        # Zone : bulle éventuelle au-dessus + sprite + label en dessous (+20px)
        top = sprite_y - 70 if self.state == 'ask' else sprite_y
        bottom = y_base + 20
        return QRegion(cx - RENDER_SIZE, top, RENDER_SIZE * 2, bottom - top)

    def _draw_bubble(self, painter: QPainter, cx: int, sprite_y: int):
        """Dessine une bulle de parole au-dessus du mouton."""
        from PyQt5.QtCore import QRectF
        text = self.ask_message.strip() if self.ask_message else '?'
        if len(text) > 80:
            text = text[:77] + '...'

        font = QFont('Sans', 8)
        painter.setFont(font)
        fm = QFontMetrics(font)
        padding = 6
        max_bw = 250

        # Calculer la taille avec word wrap
        text_rect = fm.boundingRect(0, 0, max_bw - padding * 2, 0,
                                    Qt.AlignLeft | Qt.TextWordWrap, text)
        bw = text_rect.width() + padding * 2 + 4
        bh = text_rect.height() + padding * 2 + 2

        # Centrer sur le mouton, clamper aux bords
        bx = max(2, min(cx - bw // 2, self.sw - bw - 2))
        by = sprite_y - bh - 10

        # Bulle blanche arrondie
        painter.setPen(QPen(QColor(60, 60, 60), 2))
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawRoundedRect(bx, by, bw, bh, 8, 8)

        # Petite pointe vers le mouton
        tail = QPainterPath()
        tail_x = max(bx + 10, min(cx, bx + bw - 10))
        tail.moveTo(tail_x - 5, by + bh)
        tail.lineTo(tail_x, by + bh + 7)
        tail.lineTo(tail_x + 5, by + bh)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawPath(tail)
        painter.setPen(QPen(QColor(60, 60, 60), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(tail_x - 5, by + bh, tail_x, by + bh + 7)
        painter.drawLine(tail_x, by + bh + 7, tail_x + 5, by + bh)

        # Texte
        painter.setPen(QPen(QColor(40, 40, 40)))
        painter.drawText(QRectF(bx + padding, by + padding,
                                bw - padding * 2, bh - padding * 2),
                         Qt.AlignCenter | Qt.TextWordWrap, text)


# ── SheepWindow ──────────────────────────────────────────────────────────────

class SheepWindow(QWidget):
    def __init__(self):
        super().__init__()
        screen = QApplication.primaryScreen().geometry()
        self.sw = screen.width()
        self.sh = screen.height()

        self.setGeometry(0, self.sh - STRIP_H, self.sw, STRIP_H)
        self.setWindowFlags(Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint |
                            Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.atlas = SpriteAtlas()

        # pid → Sheep
        self.sheep_map: Dict[int, Sheep] = {}
        # Mouton idle par défaut (pid=0)
        self.default_sheep = Sheep(self.sw, self.atlas)
        self.default_sheep.set_state('idle')

        self._last_mt_legacy = 0.0   # pour compat ancien fichier
        self._dragged_sheep = None
        self._drag_offset_x = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

        self.show()
        self._set_sticky()

    # ── boucle ───────────────────────────────────────────────────────────────

    def _tick(self):
        self._poll_states()
        # Update tous les moutons (sauf celui en cours de drag)
        for sheep in self.sheep_map.values():
            if sheep is self._dragged_sheep:
                sheep.player.tick()
            else:
                sheep.update()
        if not self.sheep_map:
            if self.default_sheep is self._dragged_sheep:
                self.default_sheep.player.tick()
            else:
                self.default_sheep.update()
        # Re-raise toutes les 2s pour rester au-dessus
        self._raise_counter = getattr(self, '_raise_counter', 0) + 1
        if self._raise_counter >= 50:  # 50 ticks × 40ms = 2s
            self._raise_counter = 0
            self.raise_()
        self._update_mask()
        self.update()

    def _poll_states(self):
        """Scanne le répertoire d'états multi-instance."""
        active_pids = set()

        # Nouveau format : répertoire
        if os.path.isdir(STATE_DIR):
            try:
                for name in os.listdir(STATE_DIR):
                    path = os.path.join(STATE_DIR, name)
                    if not os.path.isfile(path):
                        continue
                    try:
                        pid = int(name)
                    except ValueError:
                        continue

                    # Vérifier si le process existe encore
                    if not self._process_alive(pid):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        continue

                    active_pids.add(pid)

                    # Lire l'état (format: "state" ou "ask:message")
                    try:
                        raw = open(path).read().strip()
                    except OSError:
                        continue
                    message = ''
                    if raw.startswith('ask:'):
                        state = 'ask'
                        message = raw[4:]
                    else:
                        state = raw
                    if state not in ('idle', 'working', 'ask', 'done'):
                        continue

                    # Créer ou mettre à jour le mouton
                    if pid not in self.sheep_map:
                        sheep = Sheep(self.sw, self.atlas, pid=pid)
                        self.sheep_map[pid] = sheep
                    self.sheep_map[pid].set_state(state, message)
            except OSError:
                pass

        # Compat ancien format : fichier unique
        elif os.path.exists(STATE_FILE):
            try:
                mt = os.path.getmtime(STATE_FILE)
                if mt > self._last_mt_legacy:
                    self._last_mt_legacy = mt
                    state = open(STATE_FILE).read().strip()
                    if state in ('idle', 'working', 'waiting', 'done'):
                        active_pids.add(-1)
                        if -1 not in self.sheep_map:
                            self.sheep_map[-1] = Sheep(self.sw, self.atlas)
                        self.sheep_map[-1].set_state(state)
            except OSError:
                pass

        # Supprimer les moutons dont le PID a disparu
        gone = set(self.sheep_map.keys()) - active_pids
        for pid in gone:
            del self.sheep_map[pid]

    @staticmethod
    def _process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _update_mask(self):
        """Met à jour le masque d'entrée : seuls les moutons sont cliquables."""
        y_base = STRIP_H - 28
        region = QRegion()
        sheep_list = list(self.sheep_map.values()) if self.sheep_map else [self.default_sheep]
        for sheep in sheep_list:
            region = region.united(sheep.hit_region(y_base))
        self.setMask(region)

    # ── rendu ────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        y_base = STRIP_H - 28   # sol (laisse marge en bas)

        if self.sheep_map:
            for sheep in self.sheep_map.values():
                sheep.draw(p, y_base)
        else:
            self.default_sheep.draw(p, y_base)

        p.end()

    # ── souris ───────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            y_base = STRIP_H - 28
            sheep_list = list(self.sheep_map.values()) if self.sheep_map else [self.default_sheep]
            for sheep in sheep_list:
                if sheep.hit_region(y_base).contains(e.pos()):
                    self._dragged_sheep = sheep
                    self._drag_offset_x = e.x() - int(sheep.x)
                    sheep._cancel_dream()
                    sheep._pre_drag_state = sheep.state
                    sheep.player.play(random.choice(GRAB_ANIMS))
                    break
        elif e.button() == Qt.RightButton:
            QApplication.quit()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._dragged_sheep is not None:
            self._dragged_sheep.x = float(e.x() - self._drag_offset_x)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._dragged_sheep is not None:
                anim = STATE_ANIMS.get(self._dragged_sheep._pre_drag_state, ANIM_IDLE)
                self._dragged_sheep.player.play(anim)
            self._dragged_sheep = None

    def _set_sticky(self):
        """Afficher sur tous les workspaces + toujours au-dessus via wmctrl."""
        try:
            import subprocess
            wid = hex(int(self.winId()))
            devnull = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Sticky = tous les workspaces
            subprocess.Popen(['wmctrl', '-i', '-r', wid, '-b', 'add,sticky'], **devnull)
            # Above = toujours au-dessus (survit au alt-tab)
            subprocess.Popen(['wmctrl', '-i', '-r', wid, '-b', 'add,above'], **devnull)
            # Skip taskbar + skip pager = invisible dans alt-tab
            subprocess.Popen(['wmctrl', '-i', '-r', wid, '-b', 'add,skip_taskbar'], **devnull)
            subprocess.Popen(['wmctrl', '-i', '-r', wid, '-b', 'add,skip_pager'], **devnull)
        except FileNotFoundError:
            pass


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # Ctrl+C fonctionne
    app = QApplication(sys.argv)
    win = SheepWindow()
    sys.exit(app.exec_())
