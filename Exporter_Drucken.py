# ----------------------------------------------------------------
# FILENAME: Exporter_Drucken_GUI.py
# PROJECT:  Notenverwaltung Orchester
# AUTHOR:   Jonas Thern
# NOTE:     Kommentare und Formatierung wurden mit Unterstuetzung von
#           kuenstlicher Intelligenz (Claude, Anthropic) erstellt.
# ----------------------------------------------------------------
# Ablauf: Ordner waehlen -> Scannen -> Kopienzahlen pruefen/anpassen
# -> Exportieren. Scan und Export laufen in einem Hintergrund-Thread
# mit Fortschrittsanzeige, damit die Oberflaeche nicht einfriert.
# Die Vorschau rechts zeigt die gewaehlte Stimme mit der eingestellten
# Skalierung (benoetigt pypdfium2 und Pillow, sonst nur ein Hinweis).
# Namenskonvention unveraendert: Stimme = Suffix nach dem letzten
# Unterstrich, "Partitur" wird unveraendert kopiert.
# ----------------------------------------------------------------

import gc
import os
import queue
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pypdf import PdfReader, PdfWriter, Transformation

try:
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter, ImageTk
except ImportError:  # Vorschau ist optional, Export funktioniert ohne
    pdfium = None

OUTPUT_FOLDER = "Drucken"

# Standard-Kopienzahlen fuer die Streichergruppen (Pulte/Spieler)
COPIES_VIOLINE1 = 10
COPIES_VIOLINE2 = 9
COPIES_VIOLA = 4
COPIES_CELLO = 8
COPIES_BASS = 2

# Skalierung in Prozent (100 = unveraendert)
SCALE_DEFAULT = 100
SCALE_MIN = 50
SCALE_MAX = 200

# Spaltenbreiten der Tabelle in Pixeln (Kopfzeile und Zeilen identisch,
# damit die Ueberschriften unabhaengig von der Schrift buendig sind)
COLUMNS = (("Stimme", 190, "w"), ("Seiten", 60, "e"), ("Kopien", 90, "e"),
           ("Gesamt", 70, "e"), ("Skalierung %", 120, "e"))

# Vorschau: Anzeigehoehe in Pixeln und Grauwert, unter dem ein Pixel als
# Inhalt (Notentinte) gilt. Ein schmaler Rand wird bei der Inhaltssuche
# ignoriert, damit dunkle Scankanten nicht als Inhalt zaehlen.
PREVIEW_HEIGHT = 400
PREVIEW_PANEL_WIDTH = 330
INK_THRESHOLD = 160
EDGE_IGNORE = 0.015


def get_copy_count(voice_name):
    """Ermittelt die Standard-Kopienzahl anhand des Stimmennamens."""
    v_lower = voice_name.lower()

    # Prioritaet 1: Streichergruppen
    if "violine1" in v_lower:
        return COPIES_VIOLINE1
    if "violine2" in v_lower:
        return COPIES_VIOLINE2
    if "viola" in v_lower:
        return COPIES_VIOLA
    if "cello" in v_lower or "violoncello" in v_lower:
        return COPIES_CELLO
    if "bass" in v_lower or "kontrabass" in v_lower:
        return COPIES_BASS

    # Prioritaet 2: kombinierte Stimmen (z. B. Trompete12 -> 2 Kopien)
    if voice_name.endswith("12"):
        return 2

    return 1


def extract_voice_name(filename):
    """Liest den Stimmennamen aus dem Dateinamen.

    Erkennt beide Namensvarianten:
    - Stueck_Violine1.pdf  -> Violine1
    - Stueck_Violine_1.pdf -> Violine1 (Zahl-Suffix wird angehaengt)
    Leerzeichen im Stimmennamen werden entfernt (Violine 1 -> Violine1).
    """
    stem = filename.rsplit(".", 1)[0]
    parts = stem.split("_")
    if len(parts) < 2:
        return stem

    voice = parts[-1]
    # Besteht das letzte Segment nur aus Ziffern (z. B. Violine_1),
    # gehoert es zum vorherigen Segment
    if voice.isdigit() and len(parts) >= 3:
        voice = parts[-2] + voice

    return voice.replace(" ", "")


def scale_page_centered(page, factor):
    """Skaliert den Seiteninhalt um die Seitenmitte, Seitengroesse bleibt.

    Anders als z. B. der Browser-Druckdialog, der von der linken unteren
    Ecke aus skaliert, bleibt der Inhalt hier zentriert. Bei factor > 1
    werden die Raender gleichmaessig beschnitten, bei factor < 1 entsteht
    gleichmaessig mehr Rand.
    """
    if factor == 1:
        return
    box = page.cropbox  # sichtbarer Bereich (Standard: MediaBox)
    cx = (float(box.left) + float(box.right)) / 2
    cy = (float(box.bottom) + float(box.top)) / 2
    # Punkt p -> factor * p + (1 - factor) * Mitte: die Mitte bleibt fix
    page.add_transformation(
        Transformation().scale(factor, factor)
        .translate(cx * (1 - factor), cy * (1 - factor)))


def max_scale_without_crop(image):
    """Groesster Skalierungsfaktor, bei dem kein Inhalt ueber den Rand ragt.

    Sucht die Bounding-Box der dunklen Pixel und berechnet, wie weit
    sie um die Seitenmitte wachsen kann, bis sie den Rand beruehrt.
    """
    w, h = image.size
    mx, my = round(w * EDGE_IGNORE), round(h * EDGE_IGNORE)
    ink = (image.convert("L")
           .point(lambda v: 255 if v < INK_THRESHOLD else 0)
           .filter(ImageFilter.MedianFilter(3)))  # einzelne Staubpunkte weg
    bbox = ink.crop((mx, my, w - mx, h - my)).getbbox()
    limit = SCALE_MAX / 100
    if bbox is None:
        return limit
    x0, y0, x1, y1 = bbox[0] + mx, bbox[1] + my, bbox[2] + mx, bbox[3] + my
    cx, cy = w / 2, h / 2
    if x0 < cx:
        limit = min(limit, cx / (cx - x0))
    if x1 > cx:
        limit = min(limit, cx / (x1 - cx))
    if y0 < cy:
        limit = min(limit, cy / (cy - y0))
    if y1 > cy:
        limit = min(limit, cy / (y1 - cy))
    return limit


class PreviewPanel:
    """Seitenvorschau mit der eingestellten Skalierung.

    Seiten werden einmal gerendert und zwischengespeichert, die
    Skalierung wird danach nur noch im Bild nachgebildet (gleiche
    Rechnung wie scale_page_centered), damit Aenderungen sofort sichtbar
    sind.
    """

    def __init__(self, parent, on_apply):
        self.on_apply = on_apply
        self.frame = ttk.LabelFrame(parent, text="Vorschau", padding=6)
        self.docs = {}    # Pfad -> PdfDocument
        self.cache = {}   # (Pfad, Seite) -> (Bild, max. Faktor)
        self.pages = []   # [(Pfad, Seite)] der gewaehlten Stimme
        self.index = 0
        self.factor = 1.0
        self.scalable = False
        self.voice_max = None
        self.job = 0      # Kennung, um veraltete Hintergrundberechnungen abzubrechen
        self.photo = None

        self.title_var = tk.StringVar(value="Stimme in der Tabelle anklicken.")
        ttk.Label(self.frame, textvariable=self.title_var,
                  font=("TkDefaultFont", 9, "bold")).pack(anchor="w")

        nav = ttk.Frame(self.frame)
        nav.pack(fill="x", pady=(4, 4))
        self.prev_btn = ttk.Button(nav, text="‹", width=3, command=lambda: self.turn(-1))
        self.prev_btn.pack(side="left")
        self.page_var = tk.StringVar(value="")
        ttk.Label(nav, textvariable=self.page_var, anchor="center").pack(
            side="left", fill="x", expand=True)
        self.next_btn = ttk.Button(nav, text="›", width=3, command=lambda: self.turn(1))
        self.next_btn.pack(side="right")

        self.canvas = tk.Canvas(self.frame, width=round(PREVIEW_HEIGHT / 1.414) + 8,
                                height=PREVIEW_HEIGHT + 8, bg="#b8b8b8",
                                highlightthickness=0)
        self.canvas.pack()

        self.warn_var = tk.StringVar(value="")
        self.warn_label = tk.Label(self.frame, textvariable=self.warn_var, anchor="w",
                                   justify="left", wraplength=PREVIEW_PANEL_WIDTH - 20)
        self.warn_label.pack(fill="x", pady=(4, 0))

        max_row = ttk.Frame(self.frame)
        max_row.pack(fill="x", pady=(2, 0))
        self.max_var = tk.StringVar(value="")
        ttk.Label(max_row, textvariable=self.max_var).pack(side="left")
        self.apply_btn = ttk.Button(max_row, text="Übernehmen", state="disabled",
                                    command=self.apply_max)
        self.apply_btn.pack(side="right")

        if pdfium is None:
            self.title_var.set("Vorschau nicht verfügbar.")
            self.warn_var.set("Dafür einmalig installieren:\n"
                              "pip install pypdfium2 pillow")
        self._update_nav()

    # -- Daten ---------------------------------------------------
    def reset(self):
        """Nach einem neuen Scan: Dokumente schliessen, Cache leeren."""
        self.job += 1
        for doc in self.docs.values():
            doc.close()
        self.docs.clear()
        self.cache.clear()
        self.pages = []
        self.canvas.delete("all")
        self.title_var.set("Stimme in der Tabelle anklicken." if pdfium
                           else "Vorschau nicht verfügbar.")
        self.page_var.set("")
        self.max_var.set("")
        if pdfium:
            self.warn_var.set("")
        self.apply_btn.configure(state="disabled")
        self._update_nav()

    def show_voice(self, name, pages, factor, scalable):
        if pdfium is None:
            return
        self.job += 1
        self.title_var.set(name)
        self.pages = pages
        self.index = 0
        self.factor = factor
        self.scalable = scalable
        self.voice_max = None
        self.apply_btn.configure(state="disabled")
        self.max_var.set("Max. ohne Beschnitt: wird berechnet…")
        self.redraw()
        # Maximale Skalierung ueber alle Seiten schrittweise berechnen,
        # damit die Oberflaeche dabei bedienbar bleibt
        self.frame.after(1, self._compute_max, self.job, 0, SCALE_MAX / 100)

    def set_factor(self, factor):
        self.factor = factor
        self.redraw()

    def _render(self, key):
        if key not in self.cache:
            path, idx = key
            if path not in self.docs:
                self.docs[path] = pdfium.PdfDocument(path)
            page = self.docs[path][idx]
            # Doppelte Aufloesung, damit auch vergroesserte Ansichten scharf sind
            scale = 2 * PREVIEW_HEIGHT / page.get_height()
            image = page.render(scale=scale).to_pil().convert("RGB")
            page.close()
            self.cache[key] = (image, max_scale_without_crop(image))
        return self.cache[key]

    def _compute_max(self, job, i, current):
        if job != self.job:
            return  # inzwischen andere Stimme gewaehlt
        if i >= len(self.pages):
            self.voice_max = current
            percent = int(current * 100)
            self.max_var.set(f"Max. ohne Beschnitt: {percent} %")
            if self.scalable:
                self.apply_btn.configure(state="normal")
            self._update_warning()
            return
        try:
            _, page_max = self._render(self.pages[i])
            current = min(current, page_max)
        except Exception:
            pass  # Fehler zeigt redraw() fuer die betroffene Seite an
        self.max_var.set(f"Max. ohne Beschnitt: berechne… ({i + 1}/{len(self.pages)})")
        self.frame.after(1, self._compute_max, job, i + 1, current)

    # -- Anzeige -------------------------------------------------
    def turn(self, step):
        if self.pages:
            self.index = (self.index + step) % len(self.pages)
            self.redraw()

    def _update_nav(self):
        state = "normal" if len(self.pages) > 1 else "disabled"
        self.prev_btn.configure(state=state)
        self.next_btn.configure(state=state)

    def redraw(self):
        self._update_nav()
        self.canvas.delete("all")
        if not self.pages:
            return
        self.page_var.set(f"Seite {self.index + 1} / {len(self.pages)}")
        try:
            image, _ = self._render(self.pages[self.index])
        except Exception as e:
            self.warn_label.configure(fg="#b00000")
            self.warn_var.set(f"Seite kann nicht angezeigt werden:\n{e}")
            return

        # Seite auf Anzeigegroesse bringen und wie beim Export um die
        # Mitte skalieren; was ueber den Rand ragt, faellt weg
        dh = PREVIEW_HEIGHT
        dw = round(image.width * dh / image.height)
        cw, ch = max(1, round(dw * self.factor)), max(1, round(dh * self.factor))
        shown = Image.new("RGB", (dw, dh), "white")
        shown.paste(image.resize((cw, ch), Image.BILINEAR),
                    ((dw - cw) // 2, (dh - ch) // 2))

        self.canvas.configure(width=dw + 8, height=dh + 8)
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.create_image(4, 4, image=self.photo, anchor="nw")
        self._update_warning()

    def _update_warning(self):
        if not self.pages:
            return
        key = self.pages[self.index]
        if key not in self.cache:
            return
        page_max = self.cache[key][1]
        dw, dh = int(self.canvas["width"]) - 8, int(self.canvas["height"]) - 8
        cut = self.factor > page_max + 0.005
        color = "#d00000" if cut else "#2a8a2a"
        self.canvas.delete("frame")
        self.canvas.create_rectangle(3, 3, dw + 4, dh + 4, outline=color,
                                     width=2, tags="frame")
        if cut:
            self.warn_label.configure(fg="#b00000")
            self.warn_var.set(f"Auf dieser Seite wird Inhalt abgeschnitten "
                              f"(Seite verträgt max. {int(page_max * 100)} %).")
        else:
            self.warn_label.configure(fg="#2a6a2a")
            self.warn_var.set("Seite passt vollständig aufs Blatt.")

    def apply_max(self):
        if self.voice_max is not None:
            self.on_apply(int(self.voice_max * 100))


def collect_pdf_paths(base_folder):
    """Sammelt alle PDF-Pfade aus den Unterordnern (ohne Ausgabeordner)."""
    pdf_paths = []
    piece_folders = sorted(
        f for f in os.listdir(base_folder)
        if os.path.isdir(os.path.join(base_folder, f)) and f != OUTPUT_FOLDER
    )
    for piece in piece_folders:
        piece_path = os.path.join(base_folder, piece)
        for root, dirs, files in os.walk(piece_path):
            if OUTPUT_FOLDER in dirs:
                dirs.remove(OUTPUT_FOLDER)
            for file in sorted(files):
                if file.lower().endswith(".pdf"):
                    pdf_paths.append(os.path.join(root, file))
    return pdf_paths


def scan_pdfs(pdf_paths, progress):
    """Liest die Seitenzahlen aller PDFs und sortiert sie nach Stimme.

    progress(index, total, dateiname) meldet den Fortschritt.
    Rueckgabe:
        voices: dict Stimme -> Liste (Pfad, Seitenzahl)
        scores: Liste (Pfad, Dateiname, Seitenzahl) fuer Partituren
        errors: Liste von Fehlermeldungen
    """
    voices = {}
    scores = []
    errors = []
    total = len(pdf_paths)

    for i, full_path in enumerate(pdf_paths, start=1):
        file = os.path.basename(full_path)
        progress(i, total, file)
        try:
            page_count = len(PdfReader(full_path).pages)
        except Exception as e:
            errors.append(f"Fehler beim Lesen von {file}: {e}")
            continue

        voice_name = extract_voice_name(file)
        if voice_name == "Partitur":
            scores.append((full_path, file, page_count))
        else:
            voices.setdefault(voice_name, []).append((full_path, page_count))

    return voices, scores, errors


class ExporterGUI:
    """Grafische Oberflaeche fuer den Druckexport."""

    def __init__(self, master):
        self.master = master
        self.master.title("Druckexporter")
        self.master.geometry("1100x830")
        self.master.minsize(900, 760)

        self.voices = {}
        self.scores = []
        # (Stimmenname, Seitenzahl, Kopien-Variable, Summen-Label,
        #  Skalierungs-Variable oder None)
        self.rows = []
        self.name_labels = {}  # Stimmenname -> Label (Markierung der Auswahl)
        self.selected = None
        self.msg_queue = queue.Queue()
        self.worker = None

        self.setup_folder_ui()
        self.setup_table_ui()
        self.setup_bottom_ui()

        # Nachrichten aus dem Hintergrund-Thread regelmaessig abholen
        self.master.after(100, self.poll_queue)

    # ------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------
    def setup_folder_ui(self):
        frame = ttk.Frame(self.master, padding=10)
        frame.pack(fill="x")

        ttk.Label(frame, text="Notenordner:").pack(side="left")
        self.folder_var = tk.StringVar(value=os.getcwd())
        ttk.Entry(frame, textvariable=self.folder_var).pack(
            side="left", fill="x", expand=True, padx=5)
        self.browse_btn = ttk.Button(frame, text="Durchsuchen", command=self.browse_folder)
        self.browse_btn.pack(side="left", padx=2)
        self.scan_btn = ttk.Button(frame, text="Scannen", command=self.start_scan)
        self.scan_btn.pack(side="left", padx=2)

        # Statuszeile mit Fortschrittsbalken
        status_frame = ttk.Frame(self.master, padding=(10, 0))
        status_frame.pack(fill="x")
        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(status_frame, mode="determinate", length=200)
        self.progress.pack(side="right", padx=2, pady=4)

    def setup_table_ui(self):
        middle = ttk.Frame(self.master, padding=(10, 0))
        middle.pack(fill="both", expand=True)

        # Rechts: Vorschau, links: Tabelle mit Kopfzeile
        self.preview = PreviewPanel(middle, on_apply=self.apply_scale)
        # Feste Breite, damit das Panel bei wechselnden Texten nicht springt
        self.preview.frame.configure(width=PREVIEW_PANEL_WIDTH)
        self.preview.frame.pack_propagate(False)
        self.preview.frame.pack(side="right", fill="y", padx=(10, 0))

        left = ttk.Frame(middle)
        left.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(left, padding=(0, 4))
        header.pack(fill="x")
        self._configure_columns(header)
        for col, (text, _, anchor) in enumerate(COLUMNS):
            ttk.Label(header, text=text, font=("TkDefaultFont", 9, "bold")).grid(
                row=0, column=col, sticky=anchor, padx=4)

        container = ttk.Frame(left)
        container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.table_frame = ttk.Frame(self.canvas)

        self.table_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def setup_bottom_ui(self):
        frame = ttk.Frame(self.master, padding=10)
        frame.pack(fill="x")

        self.total_var = tk.StringVar(value="Gesamtdruckvolumen: 0 Seiten")
        ttk.Label(frame, textvariable=self.total_var,
                  font=("TkDefaultFont", 10, "bold")).pack(side="left")

        ttk.Button(frame, text="Ausgabeordner öffnen",
                   command=self.open_output).pack(side="right", padx=2)
        self.export_btn = ttk.Button(frame, text="Exportieren",
                                     command=self.start_export, state="disabled")
        self.export_btn.pack(side="right", padx=2)

        self.log_text = tk.Text(self.master, height=6, state="disabled")
        self.log_text.pack(fill="x", padx=10, pady=(0, 10))

    @staticmethod
    def _configure_columns(frame):
        for col, (_, width, _) in enumerate(COLUMNS):
            frame.columnconfigure(col, minsize=width)

    def _on_mousewheel(self, event):
        if self.canvas.winfo_ismapped():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------
    # Thread-Kommunikation
    # ------------------------------------------------------------
    def poll_queue(self):
        """Verarbeitet Nachrichten aus dem Hintergrund-Thread."""
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "progress":
                    value, maximum = payload
                    self.progress.configure(maximum=maximum, value=value)
                elif kind == "log":
                    self.log(payload)
                elif kind == "scan_done":
                    self.finish_scan(*payload)
                elif kind == "export_done":
                    self.finish_export(payload)
        except queue.Empty:
            pass
        self.master.after(100, self.poll_queue)

    def set_busy(self, busy):
        """Sperrt die Bedienelemente waehrend laufender Hintergrundarbeit."""
        state = "disabled" if busy else "normal"
        self.scan_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        if busy:
            self.export_btn.configure(state="disabled")

    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------
    # Scannen
    # ------------------------------------------------------------
    def browse_folder(self):
        path = filedialog.askdirectory(initialdir=self.folder_var.get())
        if path:
            self.folder_var.set(path)

    def start_scan(self):
        base = self.folder_var.get()
        if not os.path.isdir(base):
            messagebox.showerror("Fehler", "Der gewählte Ordner existiert nicht.")
            return

        pdf_paths = collect_pdf_paths(base)
        if not pdf_paths:
            self.log("Keine PDFs gefunden. Erwartet werden Unterordner mit "
                     "Dateien nach dem Muster Stück_Stimme.pdf.")
            return

        self.set_busy(True)
        self.log(f"Scanne {len(pdf_paths)} PDFs...")

        # Verwaiste tk-Variablen jetzt im Hauptthread einsammeln, damit
        # der Garbage-Collector sie nicht spaeter im Worker-Thread
        # finalisiert (fuehrt sonst zu Tcl_AsyncDelete-Abstuerzen)
        gc.collect()

        def worker():
            def progress(i, total, filename):
                self.msg_queue.put(("status", f"Lese {filename} ({i}/{total})"))
                self.msg_queue.put(("progress", (i, total)))

            try:
                voices, scores, errors = scan_pdfs(pdf_paths, progress)
            except Exception as e:
                self.msg_queue.put(("log", f"Fehler beim Scannen: {e}"))
                self.msg_queue.put(("scan_done", ({}, [])))
                return
            for err in errors:
                self.msg_queue.put(("log", err))
            self.msg_queue.put(("scan_done", (voices, scores)))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def finish_scan(self, voices, scores):
        """Baut nach dem Scan die Tabelle im Hauptthread auf."""
        self.voices = voices
        self.scores = scores

        for widget in self.table_frame.winfo_children():
            widget.destroy()
        self.rows.clear()
        self.name_labels.clear()
        self.selected = None
        self.preview.reset()
        gc.collect()  # alte Zeilen-Variablen im Hauptthread finalisieren

        for voice_name in sorted(self.voices.keys()):
            pages = sum(p for _, p in self.voices[voice_name])
            self.add_row(voice_name, pages, get_copy_count(voice_name))

        if self.scores:
            score_pages = sum(p for _, _, p in self.scores)
            # Partituren werden unveraendert kopiert -> keine Skalierung
            self.add_row("Partitur (Summe)", score_pages, 1, scalable=False)

        self.update_total()
        self.set_busy(False)
        self.progress.configure(value=0)

        if self.voices or self.scores:
            self.export_btn.configure(state="normal")
            self.status_var.set(f"{len(self.voices)} Stimmen und {len(self.scores)} "
                                f"Partituren gefunden.")
            self.log("Kopienzahlen prüfen, dann exportieren.")
        else:
            self.status_var.set("Keine Stimmen gefunden.")

    def add_row(self, name, pages, default_copies, scalable=True):
        """Fuegt eine Tabellenzeile mit editierbarer Kopienzahl hinzu."""
        row = ttk.Frame(self.table_frame)
        row.pack(fill="x", pady=1)
        self._configure_columns(row)

        name_label = ttk.Label(row, text=name, cursor="hand2")
        name_label.grid(row=0, column=0, sticky="w", padx=4)
        self.name_labels[name] = name_label
        ttk.Label(row, text=str(pages)).grid(row=0, column=1, sticky="e", padx=4)

        copies_var = tk.StringVar(value=str(default_copies))
        copies_box = ttk.Spinbox(row, from_=0, to=99, textvariable=copies_var, width=5)
        copies_box.grid(row=0, column=2, sticky="e", padx=4)

        total_label = ttk.Label(row, text=str(pages * default_copies))
        total_label.grid(row=0, column=3, sticky="e", padx=4)

        scale_var = None
        if scalable:
            scale_var = tk.StringVar(value=str(SCALE_DEFAULT))
            scale_box = ttk.Spinbox(row, from_=SCALE_MIN, to=SCALE_MAX, increment=1,
                                    textvariable=scale_var, width=5)
            scale_box.grid(row=0, column=4, sticky="e", padx=4)
            scale_box.bind("<FocusIn>", lambda e: self.select_voice(name), add="+")
            scale_var.trace_add("write", lambda *args: self.on_scale_change(name))
        else:
            ttk.Label(row, text="–").grid(row=0, column=4, sticky="e", padx=4)

        # Klick auf die Zeile oder Fokus in einem Feld waehlt die Stimme
        # fuer die Vorschau aus
        for widget in (row, name_label):
            widget.bind("<Button-1>", lambda e: self.select_voice(name))
        copies_box.bind("<FocusIn>", lambda e: self.select_voice(name), add="+")

        self.rows.append((name, pages, copies_var, total_label, scale_var))
        copies_var.trace_add("write", lambda *args: self.update_total())

    # ------------------------------------------------------------
    # Vorschau
    # ------------------------------------------------------------
    def _row(self, name):
        return next(r for r in self.rows if r[0] == name)

    def _pages_of(self, name):
        if name in self.voices:
            return [(path, i) for path, count in self.voices[name] for i in range(count)]
        return [(path, i) for path, _, count in self.scores for i in range(count)]

    def select_voice(self, name):
        if name == self.selected:
            return
        if self.selected in self.name_labels:
            self.name_labels[self.selected].configure(font="TkDefaultFont")
        self.selected = name
        self.name_labels[name].configure(font=("TkDefaultFont", 9, "bold"))
        scale_var = self._row(name)[4]
        self.preview.show_voice(name, self._pages_of(name),
                                self.get_scale(scale_var) / 100, scale_var is not None)

    def on_scale_change(self, name):
        if name != self.selected:
            self.select_voice(name)  # z. B. Pfeiltaste ohne vorherigen Klick
        else:
            self.preview.set_factor(self.get_scale(self._row(name)[4]) / 100)

    def apply_scale(self, percent):
        """Uebernimmt die maximale Skalierung ohne Beschnitt."""
        scale_var = self._row(self.selected)[4] if self.selected else None
        if scale_var is not None:
            scale_var.set(str(max(SCALE_MIN, min(SCALE_MAX, percent))))

    def get_copies(self, copies_var):
        try:
            return max(0, int(copies_var.get()))
        except ValueError:
            return 0

    def get_scale(self, scale_var):
        """Liest die Skalierung in Prozent, ungueltige Werte -> 100."""
        if scale_var is None:
            return SCALE_DEFAULT
        try:
            value = int(float(scale_var.get().replace(",", ".")))
        except ValueError:
            return SCALE_DEFAULT
        return min(SCALE_MAX, max(SCALE_MIN, value))

    def update_total(self):
        grand_total = 0
        for name, pages, copies_var, total_label, _ in self.rows:
            total = pages * self.get_copies(copies_var)
            total_label.configure(text=str(total))
            grand_total += total
        self.total_var.set(f"Gesamtdruckvolumen: {grand_total} Seiten")

    # ------------------------------------------------------------
    # Exportieren
    # ------------------------------------------------------------
    def start_export(self):
        base = self.folder_var.get()
        copies_by_row = [(name, pages, self.get_copies(var), self.get_scale(scale_var))
                         for name, pages, var, _, scale_var in self.rows]
        scale_by_voice = {name: scale for name, _, _, scale in copies_by_row}
        voices = self.voices
        scores = self.scores

        self.set_busy(True)
        gc.collect()  # siehe start_scan: verhindert GC von tk-Variablen im Worker

        def worker():
            out_dir = os.path.join(base, OUTPUT_FOLDER)
            os.makedirs(out_dir, exist_ok=True)
            report_lines = []

            def report(msg):
                report_lines.append(msg)
                self.msg_queue.put(("log", msg))

            # Stimmen zusammenfuehren
            total_voices = len(voices)
            for i, voice_name in enumerate(sorted(voices.keys()), start=1):
                self.msg_queue.put(("status", f"Exportiere {voice_name} ({i}/{total_voices})"))
                self.msg_queue.put(("progress", (i, total_voices)))
                factor = scale_by_voice.get(voice_name, SCALE_DEFAULT) / 100
                writer = PdfWriter()
                for path, _ in voices[voice_name]:
                    try:
                        for page in PdfReader(path).pages:
                            added = writer.add_page(page)
                            scale_page_centered(added, factor)
                    except Exception as e:
                        self.msg_queue.put(
                            ("log", f"Fehler beim Lesen von {os.path.basename(path)}: {e}"))
                filename = f"{voice_name}.pdf".replace(" ", "_")
                with open(os.path.join(out_dir, filename), "wb") as f:
                    writer.write(f)

            # Partituren kopieren
            for full_path, file, _ in scores:
                out_path = os.path.join(out_dir, file)
                if os.path.abspath(full_path) != os.path.abspath(out_path):
                    shutil.copy(full_path, out_path)

            # Druckuebersicht erstellen
            report("=" * 78)
            report(f"{'DRUCKÜBERSICHT':^78}")
            report("=" * 78)
            report(f"{'Stimme':<24} | {'Seiten':>8} | {'Anzahl':>8} | {'Gesamt':>10}"
                   f" | {'Skalierung':>10}")
            report("-" * 78)

            grand_total = 0
            for name, pages, copies, scale in copies_by_row:
                total = pages * copies
                grand_total += total
                report(f"{name:<24} | {pages:>8} | {copies:>8} | {total:>10}"
                       f" | {str(scale) + ' %':>10}")

            report("=" * 78)
            report(f"{'GESAMTDRUCKVOLUMEN (Seiten)':<47} | {grand_total:>10}")
            report("=" * 78)

            report_path = os.path.join(out_dir, "Druckuebersicht.txt")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines))

            self.msg_queue.put(("export_done", out_dir))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def finish_export(self, out_dir):
        self.set_busy(False)
        self.export_btn.configure(state="normal")
        self.progress.configure(value=0)
        self.status_var.set("Export abgeschlossen.")
        self.log(f"Fertig. Übersicht gespeichert unter: "
                 f"{os.path.join(out_dir, 'Druckuebersicht.txt')}")
        messagebox.showinfo("Fertig", f"Export abgeschlossen.\nAusgabe: {out_dir}")

    def open_output(self):
        out_dir = os.path.join(self.folder_var.get(), OUTPUT_FOLDER)
        if os.path.isdir(out_dir):
            if os.name == "nt":
                os.startfile(out_dir)
        else:
            messagebox.showinfo("Hinweis", "Der Ausgabeordner existiert noch nicht.")


if __name__ == "__main__":
    root = tk.Tk()
    gui = ExporterGUI(root)
    root.mainloop()