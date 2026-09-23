#!/usr/bin/env python3



import sys
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QLabel, QLineEdit,
    QPushButton, QComboBox, QTextEdit, QFrame, QStackedWidget,
    QMessageBox, QCheckBox, QStatusBar
)

DEFAULT_DB = Path(r"D:/JASS_Data/Urdu_Shayari/JASS_Urdu_Shayari.db")


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.con = None

    def connect(self):
        if not self.path.exists():
            raise FileNotFoundError(f"Database not found:\n{self.path}")
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")

    def close(self):
        if self.con:
            self.con.close()

    def poets(self):
        return self.con.execute(
            "SELECT poet, COUNT(*) AS n FROM poems GROUP BY poet ORDER BY poet"
        ).fetchall()

    def stats(self):
        q = self.con.execute
        return {
            "records": q("SELECT COUNT(*) FROM poems").fetchone()[0],
            "complete": q(
                "SELECT COUNT(*) FROM poems WHERE alignment_status='complete'"
            ).fetchone()[0],
            "missing_hi": q(
                "SELECT COUNT(*) FROM poems WHERE alignment_status='missing_hi'"
            ).fetchone()[0],
            "missing_en": q(
                "SELECT COUNT(*) FROM poems WHERE alignment_status='missing_en'"
            ).fetchone()[0],
            "missing_ur": q(
                "SELECT COUNT(*) FROM poems WHERE alignment_status='missing_ur'"
            ).fetchone()[0],
            "poets": q("SELECT COUNT(DISTINCT poet) FROM poems").fetchone()[0],
        }

    def search(self, text="", poet="", status="All"):
        params = []
        where = []

        if text.strip():
            # FTS5 MATCH. Prefix matching is friendly for exploratory searching.
            terms = [
                x.replace('"', ' ').strip()
                for x in text.split()
                if x.strip()
            ]
            if terms:
                match = " AND ".join(f'"{x}"*' for x in terms)
                sql = """
                    SELECT p.*
                    FROM poems_fts f
                    JOIN poems p ON p.id=f.rowid
                    WHERE poems_fts MATCH ?
                """
                params.append(match)
            else:
                sql = "SELECT * FROM poems"
        else:
            sql = "SELECT * FROM poems"

        if poet:
            where.append("p.poet=?" if text.strip() else "poet=?")
            params.append(poet)

        if status != "All":
            where.append(
                "p.alignment_status=?" if text.strip() else "alignment_status=?"
            )
            params.append(status)

        if where:
            sql += " AND " + " AND ".join(where)

        sql += " ORDER BY p.poet, p.filename" if text.strip() else \
               " ORDER BY poet, filename"

        return self.con.execute(sql, params).fetchall()


class StatCard(QFrame):
    def __init__(self, title, value):
        super().__init__()
        self.setObjectName("stat")
        l = QVBoxLayout(self)
        a = QLabel(title)
        a.setObjectName("statTitle")
        b = QLabel(str(value))
        b.setObjectName("statValue")
        l.addWidget(a)
        l.addWidget(b)


class Explorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JASS Urdu Shayari Explorer v1.0")
        self.resize(1500, 900)

        self.db = Database(DEFAULT_DB)
        self.favorites = set()
        self.results = []
        self.current_index = -1

        try:
            self.db.connect()
        except Exception as e:
            QMessageBox.critical(self, "Database error", str(e))
            raise

        self.build_ui()
        self.load_stats()
        self.load_poets()
        self.search_now()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 15, 18, 10)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        title_box = QVBoxLayout()
        title = QLabel("✦ JASS Urdu Shayari Explorer")
        title.setObjectName("title")
        subtitle = QLabel(
            "Multilingual Urdu • Hindi • English literary corpus"
        )
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hl.addLayout(title_box, 1)

        self.db_label = QLabel("●  Database connected")
        self.db_label.setObjectName("connected")
        hl.addWidget(self.db_label)
        root.addWidget(header)

        stats = QHBoxLayout()
        self.stat_records = StatCard("RECORDS", "—")
        self.stat_complete = StatCard("COMPLETE", "—")
        self.stat_partial = StatCard("PARTIAL", "—")
        self.stat_poets = StatCard("POETS", "—")
        for c in (
            self.stat_records, self.stat_complete,
            self.stat_partial, self.stat_poets
        ):
            stats.addWidget(c)
        root.addLayout(stats)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search poet, filename, English, Hindi or Urdu…"
        )
        self.search.returnPressed.connect(self.search_now)
        controls.addWidget(self.search, 1)

        self.poet_combo = QComboBox()
        self.poet_combo.addItem("All poets", "")
        self.poet_combo.currentIndexChanged.connect(self.search_now)
        controls.addWidget(self.poet_combo)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All", "Complete", "Missing Hindi",
                                    "Missing English", "Missing Urdu"])
        self.status_combo.currentIndexChanged.connect(self.search_now)
        controls.addWidget(self.status_combo)

        b = QPushButton("🔎 Search")
        b.clicked.connect(self.search_now)
        controls.addWidget(b)

        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_search)
        controls.addWidget(clear)

        root.addLayout(controls)

        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter, 1)

        # Left: results
        left = QFrame()
        left.setObjectName("panel")
        ll = QVBoxLayout(left)
        lh = QHBoxLayout()
        x = QLabel("POEMS")
        x.setObjectName("section")
        lh.addWidget(x)
        self.result_count = QLabel("0")
        self.result_count.setObjectName("muted")
        lh.addStretch()
        lh.addWidget(self.result_count)
        ll.addLayout(lh)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.open_row)
        ll.addWidget(self.list, 1)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("← Previous")
        self.next_btn = QPushButton("Next →")
        self.prev_btn.clicked.connect(self.previous)
        self.next_btn.clicked.connect(self.next)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        ll.addLayout(nav)
        self.splitter.addWidget(left)

        # Right: reader
        right = QFrame()
        right.setObjectName("panel")
        rl = QVBoxLayout(right)

        self.meta = QLabel("Select a poem")
        self.meta.setObjectName("meta")
        self.meta.setWordWrap(True)
        rl.addWidget(self.meta)

        action = QHBoxLayout()
        self.favorite_btn = QPushButton("☆ Favorite")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        self.copy_btn = QPushButton("Copy current")
        self.copy_btn.clicked.connect(self.copy_current)
        action.addWidget(self.favorite_btn)
        action.addWidget(self.copy_btn)
        action.addStretch()
        rl.addLayout(action)

        self.stack = QStackedWidget()
        self.urdu = self.make_reader("اردو")
        self.hindi = self.make_reader("हिन्दी")
        self.english = self.make_reader("English")
        self.stack.addWidget(self.urdu)
        self.stack.addWidget(self.hindi)
        self.stack.addWidget(self.english)

        tabs = QHBoxLayout()
        for label, index in [("اردو", 0), ("हिन्दी", 1), ("English", 2)]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, i=index: self.set_language(i))
            tabs.addWidget(btn)
            if index == 0:
                btn.setChecked(True)
                self.lang_buttons = []
            self.lang_buttons.append(btn)
        rl.addLayout(tabs)
        rl.addWidget(self.stack, 1)

        # Side-by-side mode
        self.side_btn = QPushButton("▥  Side-by-side")
        self.side_btn.setCheckable(True)
        self.side_btn.clicked.connect(self.toggle_side_by_side)
        rl.addWidget(self.side_btn)

        self.splitter.addWidget(right)
        self.splitter.setSizes([430, 950])

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        self.apply_style()

    def make_reader(self, label):
        box = QTextEdit()
        box.setReadOnly(True)
        box.setAcceptRichText(True)
        box.setPlaceholderText(f"No {label} text available for this record.")
        box.setObjectName("reader")
        return box

    def load_stats(self):
        s = self.db.stats()
        self.stat_records.findChild(QLabel, "statValue").setText(str(s["records"]))
        self.stat_complete.findChild(QLabel, "statValue").setText(str(s["complete"]))
        self.stat_partial.findChild(QLabel, "statValue").setText(
            str(s["records"] - s["complete"])
        )
        self.stat_poets.findChild(QLabel, "statValue").setText(str(s["poets"]))

    def load_poets(self):
        self.poet_combo.blockSignals(True)
        self.poet_combo.clear()
        self.poet_combo.addItem("All poets", "")
        for r in self.db.poets():
            self.poet_combo.addItem(f"{r['poet']}  ({r['n']})", r["poet"])
        self.poet_combo.blockSignals(False)

    def search_now(self):
        status_map = {
            "All": "All",
            "Complete": "complete",
            "Missing Hindi": "missing_hi",
            "Missing English": "missing_en",
            "Missing Urdu": "missing_ur",
        }
        poet = self.poet_combo.currentData() or ""
        status = status_map[self.status_combo.currentText()]
        try:
            self.results = self.db.search(
                self.search.text(), poet, status
            )
        except sqlite3.OperationalError:
            # If an unusual FTS query fails, fall back to LIKE search.
            term = "%" + self.search.text().strip() + "%"
            sql = """
                SELECT * FROM poems
                WHERE (poet LIKE ? OR filename LIKE ?
                       OR english LIKE ? OR hindi LIKE ? OR urdu LIKE ?)
                ORDER BY poet, filename
            """
            self.results = self.db.con.execute(
                sql, (term, term, term, term, term)
            ).fetchall()

        self.list.blockSignals(True)
        self.list.clear()
        for r in self.results:
            flag = "✓" if r["alignment_status"] == "complete" else "⚠"
            fav = " ★" if r["id"] in self.favorites else ""
            item = QListWidgetItem(
                f"{flag}  {r['filename']}{fav}"
            )
            item.setData(Qt.UserRole, r["id"])
            self.list.addItem(item)
        self.list.blockSignals(False)

        self.result_count.setText(str(len(self.results)))
        self.status.showMessage(f"{len(self.results)} records found")

        if self.results:
            self.list.setCurrentRow(
                min(max(self.current_index, 0), len(self.results) - 1)
            )
        else:
            self.clear_reader()

    def clear_search(self):
        self.search.clear()
        self.status_combo.setCurrentIndex(0)
        self.poet_combo.setCurrentIndex(0)
        self.search_now()

    def open_row(self, row):
        if row < 0 or row >= len(self.results):
            self.clear_reader()
            return
        self.current_index = row
        r = self.results[row]

        status = (
            "✓ COMPLETE"
            if r["alignment_status"] == "complete"
            else f"⚠ {r['alignment_status'].replace('_', ' ').upper()}"
        )

        self.meta.setText(
            f"<b>{r['poet']}</b>  •  {r['filename']}  •  "
            f"<span style='color:#78b9ed'>{status}</span>"
        )

        self.set_text(self.urdu, r["urdu"], "rtl")
        self.set_text(self.hindi, r["hindi"], "rtl")
        self.set_text(self.english, r["english"], "ltr")

        self.update_favorite_button(r["id"])

        # Keep current language selection.
        if not self.side_btn.isChecked():
            self.stack.setCurrentIndex(0)

        self.status.showMessage(
            f"Record {row + 1} of {len(self.results)}"
        )

    def set_text(self, widget, text, direction):
        if not text:
            widget.setHtml(
                "<p style='color:#708399'>"
                "No source text available for this language."
                "</p>"
            )
            return

        align = "right" if direction == "rtl" else "left"
        size = "22px" if direction == "rtl" else "19px"
        html = (
            f"<div dir='{direction}' style='text-align:{align};"
            f"font-size:{size}; line-height:1.8; padding:22px;'>"
            f"{self.escape_html(text).replace(chr(10), '<br>')}"
            "</div>"
        )
        widget.setHtml(html)

    @staticmethod
    def escape_html(text):
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )

    def set_language(self, index):
        for i, b in enumerate(self.lang_buttons):
            b.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    def toggle_side_by_side(self, checked):
        if checked:
            self.show_side_by_side()
        else:
            self.stack.setCurrentIndex(0)
            self.side_btn.setText("▥  Side-by-side")

    def show_side_by_side(self):
        if not self.results or self.current_index < 0:
            self.side_btn.setChecked(False)
            return

        # A compact combined reader in the Urdu pane.
        r = self.results[self.current_index]
        parts = [
            ("اردو", r["urdu"], "rtl"),
            ("हिन्दी", r["hindi"], "rtl"),
            ("English", r["english"], "ltr"),
        ]
        chunks = []
        for title, text, direction in parts:
            align = "right" if direction == "rtl" else "left"
            size = "21px" if direction == "rtl" else "18px"
            safe = self.escape_html(text or "—").replace("\n", "<br>")
            chunks.append(
                f"<h2>{title}</h2>"
                f"<div dir='{direction}' style='text-align:{align};"
                f"font-size:{size};line-height:1.75'>{safe}</div><hr>"
            )
        self.urdu.setHtml("".join(chunks))
        self.stack.setCurrentIndex(0)
        self.side_btn.setText("▥  Side-by-side ON")

    def update_favorite_button(self, record_id):
        if record_id in self.favorites:
            self.favorite_btn.setText("★ Unfavorite")
        else:
            self.favorite_btn.setText("☆ Favorite")

    def toggle_favorite(self):
        if self.current_index < 0:
            return
        rid = self.results[self.current_index]["id"]
        if rid in self.favorites:
            self.favorites.remove(rid)
        else:
            self.favorites.add(rid)
        self.update_favorite_button(rid)
        self.search_now()

    def copy_current(self):
        if self.current_index < 0:
            return
        r = self.results[self.current_index]
        text = (
            f"{r['poet']} — {r['filename']}\n\n"
            f"URDU:\n{r['urdu'] or '[missing]'}\n\n"
            f"HINDI:\n{r['hindi'] or '[missing]'}\n\n"
            f"ENGLISH:\n{r['english'] or '[missing]'}"
        )
        QApplication.clipboard().setText(text)
        self.status.showMessage("Current record copied to clipboard")

    def previous(self):
        if self.results:
            self.list.setCurrentRow(max(0, self.current_index - 1))

    def next(self):
        if self.results:
            self.list.setCurrentRow(
                min(len(self.results) - 1, self.current_index + 1)
            )

    def clear_reader(self):
        self.meta.setText("No record selected")
        for w in (self.urdu, self.hindi, self.english):
            w.clear()
        self.favorite_btn.setText("☆ Favorite")

    def closeEvent(self, event):
        self.db.close()
        event.accept()

    def apply_style(self):
        self.setStyleSheet("""
        QWidget {
            background:#09111f;
            color:#e9f1fa;
            font-family:"Segoe UI";
            font-size:14px;
        }
        QFrame#header {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #123c67, stop:1 #1b2850);
            border:1px solid #315f8d;
            border-radius:17px;
        }
        QLabel#title {
            font-size:30px;
            font-weight:800;
            color:#ffffff;
        }
        QLabel#subtitle {
            font-size:15px;
            color:#c2d7ea;
        }
        QLabel#connected {
            color:#83e1ad;
            font-weight:700;
        }
        QFrame#stat {
            background:#101c2c;
            border:1px solid #263c54;
            border-radius:12px;
            padding:8px;
        }
        QLabel#statTitle {
            color:#8299af;
            font-size:11px;
            font-weight:800;
        }
        QLabel#statValue {
            color:#ffffff;
            font-size:25px;
            font-weight:800;
        }
        QFrame#panel {
            background:#0e1928;
            border:1px solid #263b52;
            border-radius:12px;
        }
        QLabel#section {
            color:#a9bfd4;
            font-size:12px;
            font-weight:800;
            letter-spacing:1px;
        }
        QLabel#muted {
            color:#7890a7;
        }
        QLabel#meta {
            background:#111f30;
            border:1px solid #263e57;
            border-radius:9px;
            padding:12px;
            font-size:15px;
        }
        QListWidget {
            background:#0a1422;
            border:0;
            padding:7px;
        }
        QListWidget::item {
            padding:12px 9px;
            border-radius:8px;
            margin:2px 0;
        }
        QListWidget::item:selected {
            background:#19456f;
            color:white;
        }
        QListWidget::item:hover {
            background:#132b45;
        }
        QLineEdit,QComboBox,QTextEdit {
            background:#0b1725;
            border:1px solid #2b425a;
            border-radius:9px;
            padding:9px;
            color:#edf5fd;
        }
        QPushButton {
            background:#142940;
            border:1px solid #31506d;
            border-radius:9px;
            padding:9px 13px;
            color:#eef6ff;
        }
        QPushButton:hover {
            background:#1d466d;
        }
        QPushButton:checked {
            background:#245b8b;
            border-color:#4d8fc2;
        }
        QTextEdit#reader {
            background:#0a1421;
            border:1px solid #233a51;
        }
        QStatusBar {
            background:#07101b;
            color:#8298ad;
        }
        QSplitter::handle {
            background:#07101b;
            width:6px;
        }
        """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JASS Urdu Shayari Explorer")
    app.setStyle("Fusion")
    try:
        win = Explorer()
    except Exception:
        sys.exit(1)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
