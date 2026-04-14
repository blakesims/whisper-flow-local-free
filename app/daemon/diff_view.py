"""
Diff View - 3-way comparison of original, cleaned, and re-processed transcription.

Layout:
  Top row:    Original (left)  |  Cleaned (right)
  Bottom row: Re-processed output (appears after Cmd+Enter)
  Prompt:     Editable prompt panel (toggle with P)

Keys:
  Ctrl+D     - toggle visibility (handled by daemon)
  P          - toggle prompt editor
  Cmd+Enter  - re-process with current prompt, show 3-way diff
  Cmd+S      - save prompt and dismiss
  Escape     - dismiss
"""

import difflib
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit, QPushButton,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QScreen

# Tokyo Night palette
COLORS = {
    'bg': QColor(26, 27, 38, 245),
    'bg_panel': QColor(36, 40, 59),
    'text': QColor(192, 202, 245),
    'text_dim': QColor(86, 95, 137),
    'red_bg': QColor(247, 118, 142, 40),
    'green_bg': QColor(158, 206, 106, 40),
    'red': QColor(247, 118, 142),
    'green': QColor(158, 206, 106),
    'border': QColor(41, 46, 66),
    'blue': QColor(122, 162, 247),
    'purple': QColor(187, 154, 247),
    'orange': QColor(255, 158, 100),
    'yellow': QColor(224, 175, 104),
    'yellow_bg': QColor(224, 175, 104, 40),
}

PANEL_STYLE = """
    QTextEdit {{
        background-color: rgba(36, 40, 59, 255);
        color: {text};
        border: 1px solid rgba(41, 46, 66, 180);
        border-radius: 8px;
        padding: 14px;
        font-size: 15px;
        line-height: 1.5;
        font-family: 'SF Pro Text', 'Helvetica Neue', sans-serif;
        selection-background-color: rgba(122, 162, 247, 80);
    }}
""".format(text=COLORS['text'].name())


class DiffView(QWidget):
    """
    Floating diff window with 3-way comparison and inline prompt editor.
    """

    reprocess_requested = Signal(str)  # emits the new prompt text

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._prompt_visible = False
        self._reprocess_visible = False
        self._original_text = ""
        self._cleaned_text = ""
        self._reprocessed_text = ""

        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumSize(900, 450)

        self._container = QWidget(self)
        self._container.setStyleSheet("""
            QWidget {
                background-color: rgba(26, 27, 38, 245);
                border-radius: 12px;
                border: 1px solid rgba(41, 46, 66, 180);
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(20, 16, 20, 20)
        self._container_layout.setSpacing(10)

        # ── Header ──
        header = QHBoxLayout()
        title = QLabel("Transcript Diff")
        title.setStyleSheet(f"color: {COLORS['blue'].name()}; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        self._hint = QLabel("P = prompt  |  \u2318\u21A9 = re-process  |  \u2318S = save & close")
        self._hint.setStyleSheet(f"color: {COLORS['text_dim'].name()}; font-size: 12px; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._hint)
        self._container_layout.addLayout(header)

        # ── Top row: Original | Cleaned ──
        top_panels = QHBoxLayout()
        top_panels.setSpacing(12)

        # Original
        left_layout = QVBoxLayout()
        left_label = QLabel("Original")
        left_label.setStyleSheet(f"color: {COLORS['red'].name()}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self._left_text = QTextEdit()
        self._left_text.setReadOnly(True)
        self._left_text.setStyleSheet(PANEL_STYLE)
        left_layout.addWidget(left_label)
        left_layout.addWidget(self._left_text)
        top_panels.addLayout(left_layout)

        # Cleaned
        right_layout = QVBoxLayout()
        right_label = QLabel("Cleaned")
        right_label.setStyleSheet(f"color: {COLORS['green'].name()}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self._right_text = QTextEdit()
        self._right_text.setReadOnly(True)
        self._right_text.setStyleSheet(PANEL_STYLE)
        right_layout.addWidget(right_label)
        right_layout.addWidget(self._right_text)
        top_panels.addLayout(right_layout)

        self._container_layout.addLayout(top_panels)

        # ── Stats ──
        self._stats = QLabel("")
        self._stats.setStyleSheet(f"color: {COLORS['text_dim'].name()}; font-size: 13px; border: none; background: transparent;")
        self._container_layout.addWidget(self._stats)

        # ── Bottom row: Re-processed (hidden until Cmd+Enter) ──
        self._reprocess_panel = QWidget()
        self._reprocess_panel.setVisible(False)
        reprocess_layout = QVBoxLayout(self._reprocess_panel)
        reprocess_layout.setContentsMargins(0, 0, 0, 0)
        reprocess_layout.setSpacing(4)

        reprocess_label = QLabel("Re-processed")
        reprocess_label.setStyleSheet(f"color: {COLORS['yellow'].name()}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self._reprocess_text = QTextEdit()
        self._reprocess_text.setReadOnly(True)
        self._reprocess_text.setStyleSheet(PANEL_STYLE)
        self._reprocess_text.setMaximumHeight(160)
        self._reprocess_stats = QLabel("")
        self._reprocess_stats.setStyleSheet(f"color: {COLORS['text_dim'].name()}; font-size: 12px; border: none; background: transparent;")

        reprocess_layout.addWidget(reprocess_label)
        reprocess_layout.addWidget(self._reprocess_text)
        reprocess_layout.addWidget(self._reprocess_stats)

        self._container_layout.addWidget(self._reprocess_panel)

        # ── Prompt editor (hidden until P) ──
        self._prompt_panel = QWidget()
        self._prompt_panel.setVisible(False)
        prompt_layout = QVBoxLayout(self._prompt_panel)
        prompt_layout.setContentsMargins(0, 8, 0, 0)
        prompt_layout.setSpacing(8)

        prompt_header = QHBoxLayout()
        prompt_label = QLabel("Prompt")
        prompt_label.setStyleSheet(f"color: {COLORS['purple'].name()}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        prompt_hint = QLabel("{text} = transcription placeholder")
        prompt_hint.setStyleSheet(f"color: {COLORS['text_dim'].name()}; font-size: 11px; border: none; background: transparent;")
        prompt_header.addWidget(prompt_label)
        prompt_header.addStretch()
        prompt_header.addWidget(prompt_hint)
        prompt_layout.addLayout(prompt_header)

        self._prompt_editor = QTextEdit()
        self._prompt_editor.setMinimumHeight(160)
        self._prompt_editor.setMaximumHeight(220)
        self._prompt_editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(36, 40, 59, 255);
                color: {COLORS['text'].name()};
                border: 1px solid {COLORS['purple'].name()};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                font-family: 'SF Mono', 'Menlo', monospace;
                selection-background-color: rgba(187, 154, 247, 80);
            }}
        """)
        prompt_layout.addWidget(self._prompt_editor)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._save_btn = QPushButton("\u2318S  Save & Close")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(86, 95, 137, 150);
                color: {COLORS['text'].name()};
                border: none;
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(86, 95, 137, 220);
            }}
        """)
        self._save_btn.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self._save_btn)

        btn_row.addSpacing(10)

        self._rerun_btn = QPushButton("\u2318\u21A9  Re-process")
        self._rerun_btn.setCursor(Qt.PointingHandCursor)
        self._rerun_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['purple'].name()};
                color: {COLORS['bg'].name()};
                border: none;
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['blue'].name()};
            }}
        """)
        self._rerun_btn.clicked.connect(self._on_rerun_clicked)
        btn_row.addWidget(self._rerun_btn)

        prompt_layout.addLayout(btn_row)

        self._container_layout.addWidget(self._prompt_panel)

    # ── Public API ──

    def show_diff(self, original: str, processed: str):
        """Display the 2-way diff (original vs cleaned)."""
        self._original_text = original
        self._cleaned_text = processed
        self._reprocessed_text = ""

        self._left_text.clear()
        self._right_text.clear()

        orig_words = original.split()
        proc_words = processed.split()
        matcher = difflib.SequenceMatcher(None, orig_words, proc_words)
        self._render_two_way(self._left_text, self._right_text, matcher, orig_words, proc_words)

        # Stats
        removed = len(orig_words) - len(proc_words)
        pct = (removed / len(orig_words) * 100) if orig_words else 0
        self._stats.setText(
            f"{len(orig_words)} words \u2192 {len(proc_words)} words  "
            f"\u2022  {removed} removed  "
            f"\u2022  {pct:.0f}% reduction"
        )

        # Hide re-process panel (fresh diff)
        self._reprocess_panel.setVisible(False)
        self._reprocess_visible = False

        # Load prompt if editor is empty
        if not self._prompt_editor.toPlainText().strip():
            self._load_current_prompt()

        self._position_on_screen()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_3way(self, original: str, previous: str, new: str):
        """Display all three: original, previous cleaned, and new re-processed."""
        self._original_text = original
        self._cleaned_text = previous
        self._reprocessed_text = new

        # Top row stays the same
        self._left_text.clear()
        self._right_text.clear()
        orig_words = original.split()
        prev_words = previous.split()
        matcher = difflib.SequenceMatcher(None, orig_words, prev_words)
        self._render_two_way(self._left_text, self._right_text, matcher, orig_words, prev_words)

        # Top stats
        removed = len(orig_words) - len(prev_words)
        pct = (removed / len(orig_words) * 100) if orig_words else 0
        self._stats.setText(
            f"{len(orig_words)} words \u2192 {len(prev_words)} words  "
            f"\u2022  {removed} removed  "
            f"\u2022  {pct:.0f}% reduction"
        )

        # Bottom row: re-processed output with 3-way highlights
        self._reprocess_text.clear()
        new_words = new.split()
        self._render_reprocessed(self._reprocess_text, orig_words, prev_words, new_words)

        # Re-process stats: compare new vs previous
        delta = len(prev_words) - len(new_words)
        direction = "shorter" if delta > 0 else "longer" if delta < 0 else "same length"
        self._reprocess_stats.setText(
            f"Re-processed: {len(new_words)} words  "
            f"\u2022  {abs(delta)} words {direction} than previous"
        )

        self._reprocess_panel.setVisible(True)
        self._reprocess_visible = True

        self._position_on_screen()
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Rendering ──

    def _render_two_way(self, left: QTextEdit, right: QTextEdit, matcher, a_words, b_words):
        """Render a 2-way word diff into two text panels."""
        lc = left.textCursor()
        rc = right.textCursor()

        fmt_normal = QTextCharFormat()
        fmt_normal.setForeground(COLORS['text'])
        fmt_del = QTextCharFormat()
        fmt_del.setForeground(COLORS['red'])
        fmt_del.setBackground(COLORS['red_bg'])
        fmt_add = QTextCharFormat()
        fmt_add.setForeground(COLORS['green'])
        fmt_add.setBackground(COLORS['green_bg'])

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                t = ' '.join(a_words[i1:i2]) + ' '
                lc.insertText(t, fmt_normal)
                rc.insertText(t, fmt_normal)
            elif tag == 'delete':
                lc.insertText(' '.join(a_words[i1:i2]) + ' ', fmt_del)
            elif tag == 'insert':
                rc.insertText(' '.join(b_words[j1:j2]) + ' ', fmt_add)
            elif tag == 'replace':
                lc.insertText(' '.join(a_words[i1:i2]) + ' ', fmt_del)
                rc.insertText(' '.join(b_words[j1:j2]) + ' ', fmt_add)

        left.moveCursor(QTextCursor.Start)
        right.moveCursor(QTextCursor.Start)

    def _render_reprocessed(self, panel: QTextEdit, orig_words, prev_words, new_words):
        """Render inline diff: previous vs new, with red strikethrough for removed and green for added."""
        cursor = panel.textCursor()

        fmt_normal = QTextCharFormat()
        fmt_normal.setForeground(COLORS['text'])

        fmt_removed = QTextCharFormat()
        fmt_removed.setForeground(COLORS['red'])
        fmt_removed.setBackground(COLORS['red_bg'])
        fmt_removed.setFontStrikeOut(True)

        fmt_added = QTextCharFormat()
        fmt_added.setForeground(COLORS['green'])
        fmt_added.setBackground(COLORS['green_bg'])

        # Diff previous output vs new output
        matcher = difflib.SequenceMatcher(None, prev_words, new_words)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                cursor.insertText(' '.join(new_words[j1:j2]) + ' ', fmt_normal)
            elif tag == 'delete':
                # Words in previous but removed in new — show as strikethrough
                cursor.insertText(' '.join(prev_words[i1:i2]) + ' ', fmt_removed)
            elif tag == 'insert':
                # Words added in new — show as green
                cursor.insertText(' '.join(new_words[j1:j2]) + ' ', fmt_added)
            elif tag == 'replace':
                # Show old as strikethrough red, new as green
                cursor.insertText(' '.join(prev_words[i1:i2]) + ' ', fmt_removed)
                cursor.insertText(' '.join(new_words[j1:j2]) + ' ', fmt_added)

        panel.moveCursor(QTextCursor.Start)

    # ── Prompt management ──

    def _load_current_prompt(self):
        from app.core.post_processor import PROMPT_FILE, PostProcessor
        if PROMPT_FILE.exists():
            self._prompt_editor.setPlainText(PROMPT_FILE.read_text().strip())
        else:
            self._prompt_editor.setPlainText(PostProcessor.DEFAULT_PROMPT.strip())

    def _save_prompt(self):
        """Save prompt to disk."""
        prompt = self._prompt_editor.toPlainText().strip()
        if not prompt:
            return
        from app.core.post_processor import PROMPT_FILE, CONFIG_DIR
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PROMPT_FILE.write_text(prompt)

    def _toggle_prompt_editor(self):
        self._prompt_visible = not self._prompt_visible
        self._prompt_panel.setVisible(self._prompt_visible)
        if self._prompt_visible:
            self._load_current_prompt()
            self._prompt_editor.setFocus()
        self._position_on_screen()

    # ── Actions ──

    def _on_rerun_clicked(self):
        prompt = self._prompt_editor.toPlainText().strip()
        if not prompt or '{text}' not in prompt:
            self._rerun_btn.setText("Missing {text} placeholder!")
            QTimer.singleShot(2000, self._reset_rerun_btn)
            return

        self._rerun_btn.setText("Processing...")
        self._rerun_btn.setEnabled(False)
        # Don't save prompt — only Cmd+S saves. Pass it through for this run.
        self.reprocess_requested.emit(prompt)

    def _on_save_clicked(self):
        self._save_prompt()
        self.hide()

    def _reset_rerun_btn(self):
        self._rerun_btn.setText("\u2318\u21A9  Re-process")
        self._rerun_btn.setEnabled(True)

    # ── Layout ──

    def _position_on_screen(self):
        screen = QScreen.availableGeometry(self.screen())
        w = min(1100, int(screen.width() * 0.7))
        # Grow vertically based on visible panels
        base_h = 480
        if self._reprocess_visible:
            base_h += 200
        if self._prompt_visible:
            base_h += 300
        h = min(base_h, int(screen.height() * 0.85))
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)

    # ── Key handling ──

    def keyPressEvent(self, event):
        mods = event.modifiers()
        key = event.key()

        # Cmd+Enter: re-process (works even when in prompt editor)
        if key in (Qt.Key_Return, Qt.Key_Enter) and mods & Qt.ControlModifier:
            self._on_rerun_clicked()
            return

        # Cmd+S: save prompt and dismiss
        if key == Qt.Key_S and mods & Qt.ControlModifier:
            self._on_save_clicked()
            return

        # Don't intercept other keys when typing in prompt editor
        if self._prompt_editor.hasFocus():
            super().keyPressEvent(event)
            return

        if key == Qt.Key_Escape:
            self.hide()
        elif key == Qt.Key_P:
            self._toggle_prompt_editor()
        else:
            super().keyPressEvent(event)
