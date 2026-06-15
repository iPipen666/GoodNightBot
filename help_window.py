"""help_window.py — окно справки GoodNightBot.

Структура: Toplevel без системного заголовка, EDGE-рамка, NIGHT-фон, Canvas-шапка
с перетаскиванием + ✕, Canvas-вкладки (сегмент-тоггл), скролл-область с аккордеонами,
поле поиска по всем разделам. Полностью локализуемо: всё через ht(key).

Использование:
    import help_window
    hw = help_window.open_help(root)  # открыть
    hw.set_language("en-US")          # live-смена языка
"""
import os
import json
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import theme as T
import i18n

HERE = os.path.dirname(os.path.abspath(__file__))
_HI18N_PATH = os.path.join(HERE, "help_i18n.json")

# ─── загрузка help_i18n.json ───
try:
    _HI18N = json.load(open(_HI18N_PATH, encoding="utf-8"))
except Exception:
    _HI18N = {}

# ширина окна помощи
HELP_W = 600


def ht(key, locale=None):
    """Строка справки по ключу. Фолбэк: locale -> en-US -> ru-RU -> key.
    Никогда не возвращает пустую строку (используется ключ как последний фолбэк)."""
    d = _HI18N.get(key)
    if not isinstance(d, dict):
        return key
    if locale is None:
        locale = _cur_lang()
    s = d.get(locale) or d.get("en-US") or d.get("ru-RU")
    return s if s else key


def _cur_lang():
    """Текущий lang_main из config.json (через i18n._lang())."""
    try:
        return i18n._lang()
    except Exception:
        return "ru-RU"


# ─── структура контента ───────────────────────────────────────────────────────
# SECTIONS: список секций. Каждая секция: (section_key, tab_i18n_key, [topics])
# topic: (topic_key, title_key, what_key, how_key, why_key)
# Добавить тему = добавить строки в help_i18n.json + строку в _TOPICS нужной секции.

_SECTIONS = [
    (
        "quickstart",
        "tab_quickstart",
        [
            ("qs_launch",  "qs_launch_title",  "qs_launch_what",  "qs_launch_how",  "qs_launch_why"),
            ("qs_stop",    "qs_stop_title",    "qs_stop_what",    "qs_stop_how",    "qs_stop_why"),
            ("qs_modes",   "qs_modes_title",   "qs_modes_what",   "qs_modes_how",   "qs_modes_why"),
        ],
    ),
    (
        "farming",
        "tab_farming",
        [
            ("fm_what",    "fm_what_title",    "fm_what_what",    "fm_what_how",    "fm_what_why"),
            ("fm_log",     "fm_log_title",     "fm_log_what",     "fm_log_how",     "fm_log_why"),
            ("fm_mail",    "fm_mail_title",    "fm_mail_what",    "fm_mail_how",    "fm_mail_why"),
            ("fm_popups",  "fm_popups_title",  "fm_popups_what",  "fm_popups_how",  "fm_popups_why"),
        ],
    ),
    (
        "merge",
        "tab_merge",
        [
            ("mg_grades",   "mg_grades_title",   "mg_grades_what",   "mg_grades_how",   "mg_grades_why"),
            ("mg_rules",    "mg_rules_title",    "mg_rules_what",    "mg_rules_how",    "mg_rules_why"),
            ("mg_lock",     "mg_lock_title",     "mg_lock_what",     "mg_lock_how",     "mg_lock_why"),
            ("mg_forbidden","mg_forbidden_title","mg_forbidden_what","mg_forbidden_how","mg_forbidden_why"),
        ],
    ),
    (
        "knowledgebase",
        "tab_knowledgebase",
        [
            ("kb_overview", "kb_overview_title", "kb_overview_what", "kb_overview_how", "kb_overview_why"),
            ("kb_search",   "kb_search_title",   "kb_search_what",   "kb_search_how",   "kb_search_why"),
            ("kb_detail",   "kb_detail_title",   "kb_detail_what",   "kb_detail_how",   "kb_detail_why"),
            ("kb_lang",     "kb_lang_title",     "kb_lang_what",     "kb_lang_how",     "kb_lang_why"),
        ],
    ),
    (
        "settings",
        "tab_settings",
        [
            ("set_behavior",   "set_behavior_title",   "set_behavior_what",   "set_behavior_how",   "set_behavior_why"),
            ("set_ocr",        "set_ocr_title",        "set_ocr_what",        "set_ocr_how",        "set_ocr_why"),
            ("set_humanlike",  "set_humanlike_title",  "set_humanlike_what",  "set_humanlike_how",  "set_humanlike_why"),
            ("set_politeness", "set_politeness_title", "set_politeness_what", "set_politeness_how", "set_politeness_why"),
            ("set_mail",       "set_mail_title",       "set_mail_what",       "set_mail_how",       "set_mail_why"),
            ("set_lang",       "set_lang_title",       "set_lang_what",       "set_lang_how",       "set_lang_why"),
            ("set_custom",     "set_custom_title",     "set_custom_what",     "set_custom_how",     "set_custom_why"),
        ],
    ),
    (
        "troubleshoot",
        "tab_troubleshoot",
        [
            ("ts_window",      "ts_window_title",      "ts_window_what",      "ts_window_how",      "ts_window_why"),
            ("ts_ocr",         "ts_ocr_title",         "ts_ocr_what",         "ts_ocr_how",         "ts_ocr_why"),
            ("ts_covered",     "ts_covered_title",     "ts_covered_what",     "ts_covered_how",     "ts_covered_why"),
            ("ts_calibration", "ts_calibration_title", "ts_calibration_what", "ts_calibration_how", "ts_calibration_why"),
            ("about_bot",      "about_bot_title",      "about_bot_what",      "about_bot_how",      "about_bot_why"),
            ("about_support",  "about_support_title",  "about_support_what",  "about_support_how",  "about_support_why"),
        ],
    ),
]

# плоский индекс тем для поиска: (section_key, topic_tuple)
_FLAT_TOPICS = [(sec_key, topic) for sec_key, _, topics in _SECTIONS for topic in topics]


class HelpWindow:
    """Окно справки. Структура: Toplevel → EDGE-рамка → NIGHT-фон → Canvas-шапка →
    Canvas-вкладки → search-строка → прокручиваемый список аккордеонов."""

    def __init__(self, root, height=None):
        self.root = root
        self._drag = (0, 0)
        self.win = tk.Toplevel(root)
        self.win.configure(bg=T.EDGE)
        self.win.overrideredirect(True)
        h = int(height) if height else 600
        # позиционировать правее панели
        try:
            px, py = root.winfo_x(), root.winfo_y()
            pw = root.winfo_width()
        except Exception:
            px, py, pw = 40, 40, 425
        x = max(0, px + pw + 12)
        y = max(0, py)
        # держать на экране
        try:
            sw = root.winfo_screenwidth()
            if x + HELP_W > sw:
                x = max(0, px - HELP_W - 12)
        except Exception:
            pass
        self.win.geometry(f"{HELP_W}x{h}+{x}+{y}")
        self.attached = True
        self._rel = (x - px, y - py)

        self._locale = _cur_lang()
        self._cur_section = _SECTIONS[0][0]   # section_key текущей вкладки
        self._search_q = ""
        self._accordion_states = {}  # topic_key -> bool (open)
        self._accordion_widgets = {}  # topic_key -> (head_lbl, body_frame)
        self._search_result_widgets = []  # список виджетов результатов поиска

        self._init_scroll_style()
        self._build()
        self._add_resize_grip()

    # ── вспомогательные ──

    def _font(self, sz, bold=False):
        sz += 1
        fams = set(tkfont.families())
        fam = next((f for f in T.PIX_FONTS if f in fams), "Consolas")
        return (fam, sz, "bold" if bold else "normal")

    def _init_scroll_style(self):
        st = ttk.Style(self.win)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Night.Vertical.TScrollbar",
                     troughcolor=T.NIGHT, background=T.EDGE,
                     bordercolor=T.NIGHT, arrowcolor=T.SUB,
                     darkcolor=T.EDGE, lightcolor=T.EDGE, relief="flat")
        st.map("Night.Vertical.TScrollbar",
               background=[("active", T.EDGE_HI), ("pressed", T.EDGE_HI)])

    def _press(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _move(self, e):
        self.attached = False
        nx = e.x_root - self._drag[0]
        ny = e.y_root - self._drag[1]
        self.win.geometry(f"+{nx}+{ny}")

    def follow(self, px, py):
        if not getattr(self, "attached", False):
            return
        try:
            self.win.geometry(f"+{int(px + self._rel[0])}+{int(py + self._rel[1])}")
        except Exception:
            pass

    def _add_resize_grip(self):
        grip = tk.Frame(self.win, bg=T.EDGE_HI, height=7, cursor="sb_v_double_arrow")
        grip.place(relx=0.0, rely=1.0, anchor="sw", relwidth=1.0, height=7)
        grip.bind("<Button-1>", self._rz_press)
        grip.bind("<B1-Motion>", self._rz_drag)

    def _rz_press(self, e):
        self._rz = (e.y_root, self.win.winfo_height())

    def _rz_drag(self, e):
        nh = max(360, self._rz[1] + (e.y_root - self._rz[0]))
        self.win.geometry(f"{HELP_W}x{int(nh)}+{self.win.winfo_x()}+{self.win.winfo_y()}")

    def _close(self):
        try:
            self.win.destroy()
        except Exception:
            pass

    # ── построение ──

    def _build(self):
        outer = tk.Frame(self.win, bg=T.EDGE)
        outer.pack(fill="both", expand=True)
        self._root_frame = tk.Frame(outer, bg=T.NIGHT)
        self._root_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # ── шапка (Canvas) ──
        self.head_c = tk.Canvas(self._root_frame, height=32, bg=T.NIGHT,
                                highlightthickness=0, bd=0)
        self.head_c.pack(fill="x", padx=10, pady=(9, 4))
        self.head_c.bind("<Button-1>", self._press, add="+")
        self.head_c.bind("<B1-Motion>", self._move, add="+")
        self.head_c.bind("<Configure>", lambda e: self._redraw_header())
        self.head_c.tag_bind("close", "<Button-1>", lambda e: self._close())
        self._redraw_header()

        # ── вкладки (Canvas) ──
        self._tabkeys = [(s[0], s[1]) for s in _SECTIONS]  # (section_key, tab_i18n_key)
        self.tabs_c = tk.Canvas(self._root_frame, height=34, bg=T.EDGE,
                                highlightthickness=0, bd=0)
        self.tabs_c.pack(fill="x", padx=10, pady=(2, 0))
        self.tabs_c.bind("<Configure>", lambda e: self._redraw_tabs())
        self.tabs_c.bind("<Button-1>", self._tab_click)
        self._redraw_tabs()

        # ── строка поиска ──
        search_row = tk.Frame(self._root_frame, bg=T.NIGHT)
        search_row.pack(fill="x", padx=10, pady=(6, 2))
        entwrap = tk.Frame(search_row, bg=T.EDGE)
        entwrap.pack(fill="x")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        self._search_entry = tk.Entry(
            entwrap, textvariable=self._search_var,
            bg=T.PANEL, fg=T.INK, insertbackground=T.MOON,
            relief="flat", font=self._font(9), bd=0,
            width=40
        )
        self._search_entry.pack(padx=1, pady=1, ipady=3, ipadx=6, fill="x", expand=True)
        self._update_search_placeholder()

        # ── прокручиваемая область ──
        scroll_outer = tk.Frame(self._root_frame, bg=T.EDGE)
        scroll_outer.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        sb = ttk.Scrollbar(scroll_outer, orient="vertical",
                           style="Night.Vertical.TScrollbar")
        sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self._canvas = tk.Canvas(scroll_outer, bg=T.NIGHT, highlightthickness=0, bd=0,
                                 yscrollcommand=sb.set)
        self._canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        sb.config(command=self._canvas.yview)

        self._scroll_holder = tk.Frame(self._canvas, bg=T.NIGHT)
        self._cwin = self._canvas.create_window((0, 0), window=self._scroll_holder, anchor="nw")

        self._scroll_holder.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # колесо мыши активно пока курсор в окне
        self.win.bind("<Enter>", lambda e: self.win.bind_all("<MouseWheel>", self._wheel))
        self.win.bind("<Leave>", lambda e: self.win.unbind_all("<MouseWheel>"))
        self.win.bind("<Destroy>", lambda e: self._try_unbind_wheel())

        self._render_section(self._cur_section)

    def _try_unbind_wheel(self):
        try:
            self.win.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _wheel(self, e):
        self._canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_content_configure(self, _=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._cwin, width=e.width)

    # ── шапка и вкладки ──

    def _redraw_header(self):
        c = self.head_c
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        cy = H // 2 if H > 2 else 16
        c.create_text(4, cy, anchor="w", text=ht("hw_title", self._locale),
                      fill=T.MOON, font=self._font(13, True))
        c.create_text(W - 6, cy, anchor="e", text="✕", fill=T.STOPC,
                      font=self._font(12, True), tags="close")
        self.head_c.tag_bind("close", "<Button-1>", lambda e: self._close())

    def _redraw_tabs(self):
        c = self.tabs_c
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        n = len(self._tabkeys)
        if not n:
            return
        seg = W / n
        for i, (key, i18n_key) in enumerate(self._tabkeys):
            x0 = i * seg + 1
            x1 = (i + 1) * seg - 1
            on = (self._cur_section == key and not self._search_q)
            c.create_rectangle(x0, 2, x1, H - 2,
                                fill=(T.PANEL2 if on else T.PANEL), outline="")
            c.create_text((x0 + x1) / 2, H / 2,
                          text=ht(i18n_key, self._locale),
                          fill=(T.MOON if on else T.SUB),
                          font=self._font(9, True))

    def _tab_click(self, e):
        W = self.tabs_c.winfo_width()
        n = len(self._tabkeys)
        if not n or W <= 0:
            return
        i = int(e.x // (W / n))
        i = max(0, min(n - 1, i))
        sec_key = self._tabkeys[i][0]
        # clear search and switch
        self._search_var.set("")
        self._search_q = ""
        self._cur_section = sec_key
        self._redraw_tabs()
        self._render_section(sec_key)

    # ── поиск ──

    def _update_search_placeholder(self):
        """Цвет-подсказка в поле поиска (placeholder через текст)."""
        # просто оставляем поле с fg=T.INK; placeholder не встроен в tk.Entry,
        # используем fg=T.FAINT когда пусто, T.INK когда есть текст
        q = self._search_var.get()
        self._search_entry.config(fg=T.INK if q else T.FAINT)

    def _on_search_change(self, *_):
        q = self._search_var.get().strip().lower()
        self._search_q = q
        self._update_search_placeholder()
        if q:
            self._redraw_tabs()   # убрать активный таб-стиль при поиске
            self._render_search(q)
        else:
            self._redraw_tabs()
            self._render_section(self._cur_section)

    def _search_topics(self, q):
        """Поиск по всем темам в текущей локали. Возвращает [(section_key, topic_tuple, matched_keys)]."""
        results = []
        words = q.split()
        for sec_key, topic in _FLAT_TOPICS:
            tkey, title_k, what_k, how_k, why_k = topic
            # текст для поиска: заголовок + что + как + зачем
            combined = " ".join([
                ht(title_k, self._locale),
                ht(what_k, self._locale),
                ht(how_k, self._locale),
                ht(why_k, self._locale),
            ]).lower()
            if all(w in combined for w in words):
                results.append((sec_key, topic))
        return results

    def _highlight(self, text, q):
        """Вернуть список [(substr, is_match)] для подсветки совпадения."""
        if not q:
            return [(text, False)]
        ql = q.lower()
        out = []
        i = 0
        tl = text.lower()
        while i < len(text):
            pos = tl.find(ql, i)
            if pos == -1:
                out.append((text[i:], False))
                break
            if pos > i:
                out.append((text[i:pos], False))
            out.append((text[pos:pos + len(q)], True))
            i = pos + len(q)
        return out

    # ── рендеринг ──

    def _clear_scroll_holder(self):
        for w in self._scroll_holder.winfo_children():
            w.destroy()
        self._accordion_widgets.clear()
        self._search_result_widgets.clear()
        self._canvas.yview_moveto(0)

    def _render_section(self, sec_key):
        self._clear_scroll_holder()
        section = next((s for s in _SECTIONS if s[0] == sec_key), None)
        if section is None:
            return
        _, _, topics = section
        for topic in topics:
            tkey = topic[0]
            open_state = self._accordion_states.get(tkey, False)
            self._make_accordion(self._scroll_holder, topic, open_state)
        self._on_content_configure()

    def _render_search(self, q):
        self._clear_scroll_holder()
        results = self._search_topics(q)
        if not results:
            tk.Label(self._scroll_holder,
                     text=ht("hw_no_results", self._locale),
                     bg=T.NIGHT, fg=T.FAINT,
                     font=self._font(10)).pack(anchor="w", padx=12, pady=12)
        else:
            hdr = tk.Label(self._scroll_holder,
                           text=f"🔍 {ht('hw_results_in', self._locale)}: {len(results)}",
                           bg=T.NIGHT, fg=T.SUB, font=self._font(9))
            hdr.pack(anchor="w", padx=12, pady=(6, 2))
            for sec_key, topic in results:
                self._make_accordion(self._scroll_holder, topic,
                                     open_by_default=True, highlight_q=q)
        self._on_content_configure()

    def _make_accordion(self, parent, topic, open_by_default=False, highlight_q=""):
        tkey, title_k, what_k, how_k, why_k = topic
        loc = self._locale

        # внешний враппер (карточка)
        card = tk.Frame(parent, bg=T.PANEL)
        card.pack(fill="x", pady=2, padx=4)

        title_text = ht(title_k, loc)
        state = {"open": open_by_default}

        # строка-заголовок аккордеона
        head_lbl = tk.Label(
            card,
            text=("▾ " if open_by_default else "▸ ") + title_text,
            bg=T.PANEL, fg=T.MOON,
            font=self._font(10, True),
            cursor="hand2", anchor="w", justify="left",
            wraplength=HELP_W - 40, padx=8, pady=6,
        )
        head_lbl.pack(fill="x")

        # тело аккордеона
        body_frame = tk.Frame(card, bg=T.PANEL)

        def _add_section(label_en, text, fg_color):
            lbl = tk.Label(body_frame, text=label_en,
                           bg=T.PANEL, fg=T.FAINT, font=self._font(8, True),
                           anchor="w", padx=14)
            lbl.pack(anchor="w", pady=(4, 0))
            if highlight_q:
                # highlighted text via multiple labels on a frame
                wrap_row = tk.Frame(body_frame, bg=T.PANEL)
                wrap_row.pack(anchor="w", padx=14, fill="x")
                self._render_highlighted(wrap_row, text, highlight_q, fg_color, self._font(9))
            else:
                tk.Label(body_frame, text=text,
                         bg=T.PANEL, fg=fg_color,
                         font=self._font(9), wraplength=HELP_W - 60,
                         justify="left", anchor="w", padx=14).pack(anchor="w")

        _add_section("WHAT", ht(what_k, loc), T.INK)
        _add_section("HOW",  ht(how_k, loc),  T.SUB)
        _add_section("WHY",  ht(why_k, loc),  T.FAINT)

        # разделитель внизу тела
        sep = tk.Frame(body_frame, bg=T.EDGE, height=1)
        sep.pack(fill="x", padx=8, pady=(6, 2))

        def toggle(_=None):
            state["open"] = not state["open"]
            self._accordion_states[tkey] = state["open"]
            if state["open"]:
                head_lbl.config(text="▾ " + title_text)
                body_frame.pack(fill="x", pady=(0, 4))
            else:
                head_lbl.config(text="▸ " + title_text)
                body_frame.pack_forget()
            self.win.after(10, self._on_content_configure)

        head_lbl.bind("<Button-1>", toggle)
        card.bind("<Button-1>", toggle)

        if open_by_default:
            body_frame.pack(fill="x", pady=(0, 4))

        self._accordion_widgets[tkey] = (head_lbl, body_frame, state, title_text)

    def _render_highlighted(self, parent, text, q, base_fg, font):
        """Отрисовать текст с подсвеченными совпадениями в многострочном wraplength Label."""
        # Ввиду сложности построчной подсветки в tk.Text — используем одиночный Label
        # с жёлтым фоном на совпадение (tk.Text approach).
        txt_widget = tk.Text(
            parent, bg=T.PANEL, fg=base_fg,
            font=font, relief="flat", bd=0,
            wrap="word", height=1, state="normal",
            width=1,
        )
        txt_widget.pack(fill="x", expand=True)
        txt_widget.tag_config("hi", background=T.MOON, foreground=T.NIGHT)
        parts = self._highlight(text, q)
        for substr, is_match in parts:
            if is_match:
                txt_widget.insert("end", substr, "hi")
            else:
                txt_widget.insert("end", substr)
        # авто-высота
        txt_widget.config(state="disabled")
        txt_widget.bind("<Configure>", lambda e: self._auto_resize_text(txt_widget))
        self.win.after(20, lambda: self._auto_resize_text(txt_widget))

    def _auto_resize_text(self, w):
        try:
            w.config(height=1)
            w.update_idletasks()
            lines = int(w.index("end-1c").split(".")[0])
            w.config(height=max(1, lines))
        except Exception:
            pass

    # ── live-смена языка ──

    def set_language(self, locale):
        """Live-перерисовка всего окна помощи на новой локали."""
        self._locale = locale
        try:
            self._redraw_header()
            self._redraw_tabs()
            self._update_search_placeholder()
            if self._search_q:
                self._render_search(self._search_q)
            else:
                self._render_section(self._cur_section)
        except Exception:
            pass


# ─── публичная функция ────────────────────────────────────────────────────────

def open_help(root, height=None):
    """Открыть окно справки рядом с панелью. Возвращает экземпляр HelpWindow."""
    return HelpWindow(root, height=height)
