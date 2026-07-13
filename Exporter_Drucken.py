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
from pypdf import PdfReader, PdfWriter

OUTPUT_FOLDER = "Drucken"

# Standard-Kopienzahlen fuer die Streichergruppen (Pulte/Spieler)
COPIES_VIOLINE1 = 10
COPIES_VIOLINE2 = 9
COPIES_VIOLA = 4
COPIES_CELLO = 8
COPIES_BASS = 2


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
        self.master.geometry("720x640")
        self.master.minsize(600, 480)

        self.voices = {}
        self.scores = []
        self.rows = []  # (Stimmenname, Seitenzahl, Kopien-Variable, Summen-Label)
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
        header = ttk.Frame(self.master, padding=(10, 4))
        header.pack(fill="x")
        for text, width in (("Stimme", 24), ("Seiten", 8), ("Kopien", 8), ("Gesamt", 10)):
            ttk.Label(header, text=text, width=width,
                      font=("TkDefaultFont", 9, "bold")).pack(side="left", padx=4)

        container = ttk.Frame(self.master, padding=(10, 0))
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
        gc.collect()  # alte Zeilen-Variablen im Hauptthread finalisieren

        for voice_name in sorted(self.voices.keys()):
            pages = sum(p for _, p in self.voices[voice_name])
            self.add_row(voice_name, pages, get_copy_count(voice_name))

        if self.scores:
            score_pages = sum(p for _, _, p in self.scores)
            self.add_row("Partitur (Summe)", score_pages, 1)

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

    def add_row(self, name, pages, default_copies):
        """Fuegt eine Tabellenzeile mit editierbarer Kopienzahl hinzu."""
        row = ttk.Frame(self.table_frame)
        row.pack(fill="x", pady=1)

        ttk.Label(row, text=name, width=24).pack(side="left", padx=4)
        ttk.Label(row, text=str(pages), width=8, anchor="e").pack(side="left", padx=4)

        copies_var = tk.StringVar(value=str(default_copies))
        ttk.Spinbox(row, from_=0, to=99, textvariable=copies_var,
                    width=6).pack(side="left", padx=4)

        total_label = ttk.Label(row, text=str(pages * default_copies), width=10, anchor="e")
        total_label.pack(side="left", padx=4)

        self.rows.append((name, pages, copies_var, total_label))
        copies_var.trace_add("write", lambda *args: self.update_total())

    def get_copies(self, copies_var):
        try:
            return max(0, int(copies_var.get()))
        except ValueError:
            return 0

    def update_total(self):
        grand_total = 0
        for name, pages, copies_var, total_label in self.rows:
            total = pages * self.get_copies(copies_var)
            total_label.configure(text=str(total))
            grand_total += total
        self.total_var.set(f"Gesamtdruckvolumen: {grand_total} Seiten")

    # ------------------------------------------------------------
    # Exportieren
    # ------------------------------------------------------------
    def start_export(self):
        base = self.folder_var.get()
        copies_by_row = [(name, pages, self.get_copies(var)) for name, pages, var, _ in self.rows]
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
                writer = PdfWriter()
                for path, _ in voices[voice_name]:
                    try:
                        for page in PdfReader(path).pages:
                            writer.add_page(page)
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
            report("=" * 65)
            report(f"{'DRUCKÜBERSICHT':^65}")
            report("=" * 65)
            report(f"{'Stimme':<24} | {'Seiten':>8} | {'Anzahl':>8} | {'Gesamt':>10}")
            report("-" * 65)

            grand_total = 0
            for name, pages, copies in copies_by_row:
                total = pages * copies
                grand_total += total
                report(f"{name:<24} | {pages:>8} | {copies:>8} | {total:>10}")

            report("=" * 65)
            report(f"{'GESAMTDRUCKVOLUMEN (Seiten)':<47} | {grand_total:>10}")
            report("=" * 65)

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