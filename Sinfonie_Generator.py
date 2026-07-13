# ----------------------------------------------------------------
# FILENAME: Sinfonie_Generator.py
# PROJECT:  Notenverwaltung Orchester
# AUTHOR:   Jonas Thern
# NOTE:     Kommentare und Formatierung wurden mit Unterstuetzung von
#           kuenstlicher Intelligenz (Claude, Anthropic) erstellt.
# ----------------------------------------------------------------
# Verbesserungen gegenueber der Vorversion:
# - Deutsche Oberflaeche
# - Seitenzahl der gewaehlten PDF wird angezeigt, Bereich vorbefuellt
# - Live-Validierung der Seitenbereiche (rote Markierung)
# - Stimmen direkt in der Combobox eintippbar (kein Extra-Dialog)
# - Zeile duplizieren (gleiche Datei, Folgeseiten vorbefuellt)
# - Konfiguration jederzeit speicherbar, nicht erst beim Export
# - PDF-Oeffnen nach Auswahl abschaltbar, Statusleiste
# ----------------------------------------------------------------

import os
import sys
import json
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from pypdf import PdfReader, PdfWriter

OUTPUT_FOLDER = "output"
COLOR_BG = "#f5f5f5"
COLOR_ERROR = "#ffd6d6"


class Voice:
    """Repraesentiert eine Instrumentalstimme mit gesammelten PDF-Seiten."""

    def __init__(self, name):
        self.name = name
        self.pages = []

    def add_pages(self, file_path, start, end):
        """Haengt einen Seitenbereich aus einer PDF an die Stimme an."""
        reader = PdfReader(file_path)
        max_page = len(reader.pages)
        if start < 1 or end > max_page or start > end:
            raise ValueError(
                f"Ungültiger Seitenbereich {start}-{end} "
                f"(max. {max_page}) in {os.path.basename(file_path)}")
        for i in range(start - 1, end):
            self.pages.append(reader.pages[i])

    def export_pdf(self, suite_title):
        """Schreibt die gesammelten Seiten in eine neue PDF."""
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        filename = f"{suite_title}_{self.name}.pdf".replace(" ", "_")
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        writer = PdfWriter()
        for page in self.pages:
            writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path


class ScoreGUI:
    """Hauptoberflaeche zum Zusammenstellen der Stimmen-PDFs."""

    def __init__(self, master):
        self.master = master
        self.master.title("Sinfonie Generator")
        self.master.geometry("900x650")
        self.master.minsize(700, 400)

        self.voices = {}
        self.symphony_frames = []
        self.voice_comboboxes = []
        self._is_loading = False

        self.setup_metadata_ui()
        self.setup_notebook_ui()
        self.setup_status_ui()

        self.notebook.bind("<Double-Button-1>", self.rename_tab)
        self.notebook.bind("<Button-3>", self.rightclick_tab)

    # ------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------
    def setup_metadata_ui(self):
        """Oberer Bereich mit Metadaten und Dateiaktionen."""
        frame = tk.Frame(self.master, padx=10, pady=10, bg="#f9f9f9")
        frame.pack(padx=10, pady=10, fill="x")

        tk.Label(frame, text="Titel:", bg="#f9f9f9").grid(row=0, column=0, sticky="w")
        self.title_entry = tk.Entry(frame, width=40)
        self.title_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        tk.Label(frame, text="Komponist:", bg="#f9f9f9").grid(row=1, column=0, sticky="w")
        self.composer_entry = tk.Entry(frame, width=40)
        self.composer_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        btn_frame = tk.Frame(frame, bg="#f9f9f9")
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0), sticky="w")
        tk.Button(btn_frame, text="Konfiguration laden", width=18,
                  command=self.load_from_json).pack(side="left", padx=(0, 5))
        tk.Button(btn_frame, text="Konfiguration speichern", width=20,
                  command=self.save_json).pack(side="left", padx=5)

        self.open_pdf_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame, text="PDF nach Auswahl öffnen", bg="#f9f9f9",
                       variable=self.open_pdf_var).grid(row=2, column=1, sticky="e")

    def setup_notebook_ui(self):
        """Tab-Ansicht fuer die einzelnen Sinfonien."""
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        self.add_symphony_tab()
        self.add_plus_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self.handle_tab_change)

    def setup_status_ui(self):
        """Statusleiste am unteren Rand."""
        self.status_var = tk.StringVar(value="Bereit.")
        tk.Label(self.master, textvariable=self.status_var, anchor="w",
                 relief=tk.SUNKEN, bd=1).pack(side="bottom", fill="x")

    def set_status(self, msg):
        self.status_var.set(msg)

    # ------------------------------------------------------------
    # Scroll-Verhalten
    # ------------------------------------------------------------
    def bind_scroll(self, widget, canvas):
        """Bindet plattformspezifische Scroll-Events an ein Widget."""
        def _scroll_mw(event):
            if canvas.winfo_ismapped():
                if os.name == "nt":
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    canvas.yview_scroll(int(-1 * event.delta), "units")

        widget.bind("<MouseWheel>", _scroll_mw)
        widget.bind("<Button-4>", lambda e: canvas.winfo_ismapped()
                    and canvas.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: canvas.winfo_ismapped()
                    and canvas.yview_scroll(1, "units"))

    def bind_all_children(self, widget, canvas):
        """Bindet Scroll-Events rekursiv an eine Widget-Hierarchie."""
        self.bind_scroll(widget, canvas)
        for child in widget.winfo_children():
            self.bind_all_children(child, canvas)

    # ------------------------------------------------------------
    # Tab-Verwaltung
    # ------------------------------------------------------------
    def add_symphony_tab(self, tab_name=None):
        """Erstellt einen neuen Tab fuer eine Sinfonie."""
        if tab_name is None:
            tab_name = f"Sinfonie {len(self.symphony_frames) + 1}"

        tab_frame = tk.Frame(self.notebook, bg="#eaeaea")
        plus_idx = next((i for i in range(self.notebook.index("end"))
                         if self.notebook.tab(i, "text") == "+"), None)
        if plus_idx is not None:
            self.notebook.insert(plus_idx, tab_frame, text=tab_name)
        else:
            self.notebook.add(tab_frame, text=tab_name)

        container = tk.Frame(tab_frame)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg="#eaeaea")
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        files_frame = tk.Frame(canvas, bg="#eaeaea")

        files_frame.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=files_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.bind_scroll(canvas, canvas)

        btn_frame = tk.Frame(tab_frame, bg="#eaeaea")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Datei hinzufügen", width=20,
                  command=lambda: self.add_file_row(files_frame, canvas)).pack()

        self.symphony_frames.append(files_frame)

    def add_plus_tab(self):
        """Fuegt den dauerhaften Plus-Tab zum Anlegen neuer Sinfonien hinzu."""
        plus_frame = tk.Frame(self.notebook)
        self.notebook.add(plus_frame, text="+")

    def handle_tab_change(self, event):
        """Legt beim Klick auf den Plus-Tab eine neue Sinfonie an."""
        if self._is_loading:
            return
        current = self.notebook.select()
        if not current:
            return
        try:
            if self.notebook.tab(current, "text") == "+":
                self.add_symphony_tab()
                self.notebook.select(self.notebook.index("end") - 2)
        except tk.TclError:
            pass

    def rename_tab(self, event):
        """Erlaubt das Umbenennen eines Tabs per Doppelklick."""
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        self.begin_rename(idx, event.x, event.y)

    def begin_rename(self, idx, x, y):
        """Blendet ein Eingabefeld zum Umbenennen des Tabs ein."""
        old_name = self.notebook.tab(idx, "text")
        if old_name == "+":
            return

        entry = tk.Entry(self.notebook, width=20)
        entry.insert(0, old_name)
        entry.place(x=x, y=y)
        entry.focus_set()

        def save(e=None):
            if entry.get().strip():
                self.notebook.tab(idx, text=entry.get().strip())
            entry.destroy()

        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)

    def rightclick_tab(self, event):
        """Oeffnet das Kontextmenue zum Schliessen eines Tabs."""
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        if self.notebook.tab(idx, "text") == "+":
            return
        menu = tk.Menu(self.master, tearoff=0)
        menu.add_command(label="Umbenennen",
                         command=lambda: self.begin_rename(idx, event.x, event.y))
        menu.add_command(label="Tab schließen", command=lambda: self.close_tab(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def close_tab(self, index):
        """Entfernt einen Tab und dessen Zeilen sauber."""
        try:
            current_selected = self.notebook.index(self.notebook.select())
        except tk.TclError:
            current_selected = -1

        if current_selected == index:
            if index > 0:
                self.notebook.select(index - 1)
            elif len(self.notebook.tabs()) > 2:
                self.notebook.select(index + 1)

        tab_widget_name = self.notebook.tabs()[index]
        tab_widget = self.master.nametowidget(tab_widget_name)

        self.voice_comboboxes = [cb for cb in self.voice_comboboxes
                                 if not str(cb).startswith(str(tab_widget))]
        for sf in self.symphony_frames:
            if str(sf).startswith(str(tab_widget)):
                self.symphony_frames.remove(sf)
                break

        self.notebook.forget(index)
        tab_widget.destroy()

    # ------------------------------------------------------------
    # Stimmenverwaltung
    # ------------------------------------------------------------
    def register_voice(self, name):
        """Nimmt eine neue Stimme in die Liste auf und aktualisiert die Dropdowns."""
        name = name.strip()
        if name and name not in self.voices:
            self.voices[name] = True
            self.update_comboboxes()
            self.set_status(f"Stimme '{name}' hinzugefügt.")

    def update_comboboxes(self):
        """Aktualisiert alle Dropdowns mit den bekannten Stimmen."""
        voice_list = sorted(self.voices.keys())
        for cb in self.voice_comboboxes:
            cb["values"] = voice_list

    # ------------------------------------------------------------
    # Dateizeilen
    # ------------------------------------------------------------
    def add_file_row(self, parent_frame, canvas, data=None):
        """Fuegt eine editierbare Dateizeile hinzu."""
        row_frame = tk.Frame(parent_frame, relief=tk.RIDGE, borderwidth=2, bg=COLOR_BG)
        row_frame.pack(padx=5, pady=5, fill="x")

        f_var = tk.StringVar(value=data["file"] if data else "")
        v_var = tk.StringVar(value=data["voice_name"] if data else "")
        s_var = tk.StringVar(value=str(data["start_page"]) if data else "")
        e_var = tk.StringVar(value=str(data["end_page"]) if data else "")
        max_pages = tk.IntVar(value=0)

        # Zeile 1: Datei
        tk.Label(row_frame, text="Datei:", bg=COLOR_BG).grid(
            row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Entry(row_frame, textvariable=f_var, width=45).grid(
            row=0, column=1, sticky="w", padx=5)

        def read_page_count(path, prefill):
            """Liest die Seitenzahl und befuellt ggf. den Bereich vor."""
            try:
                count = len(PdfReader(path).pages)
            except Exception:
                count = 0
            max_pages.set(count)
            pages_label.config(text=f"von {count} Seiten" if count else "")
            if prefill and count:
                if not s_var.get().strip():
                    s_var.set("1")
                if not e_var.get().strip():
                    e_var.set(str(count))

        def browse():
            path = filedialog.askopenfilename(filetypes=[("PDF-Dateien", "*.pdf")])
            if not path:
                return
            f_var.set(path)
            read_page_count(path, prefill=True)
            if self.open_pdf_var.get():
                try:
                    if os.name == "nt":
                        os.startfile(path)
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", path])
                    else:
                        subprocess.Popen(["xdg-open", path])
                except Exception as e:
                    messagebox.showerror("Fehler", f"PDF konnte nicht geöffnet werden:\n{e}")

        tk.Button(row_frame, text="Durchsuchen", command=browse).grid(
            row=0, column=2, sticky="w", padx=5)

        # Zeile 2: Stimme (direkt eintippbar oder aus Liste waehlen)
        tk.Label(row_frame, text="Stimme:", bg=COLOR_BG).grid(
            row=1, column=0, sticky="w", padx=5, pady=2)
        cb = ttk.Combobox(row_frame, textvariable=v_var,
                          values=sorted(self.voices.keys()), width=42)
        cb.grid(row=1, column=1, sticky="w", padx=5)
        cb.bind("<FocusOut>", lambda e: self.register_voice(v_var.get()))
        cb.bind("<Return>", lambda e: self.register_voice(v_var.get()))
        cb.bind("<<ComboboxSelected>>", lambda e: None)
        self.voice_comboboxes.append(cb)
        tk.Label(row_frame, text="(neue Stimme direkt eintippen)",
                 bg=COLOR_BG, fg="#888888").grid(row=1, column=2, sticky="w", padx=5)

        # Zeile 3: Seitenbereich mit Live-Validierung
        tk.Label(row_frame, text="Seiten:", bg=COLOR_BG).grid(
            row=2, column=0, sticky="w", padx=5, pady=2)
        page_frame = tk.Frame(row_frame, bg=COLOR_BG)
        page_frame.grid(row=2, column=1, sticky="w", padx=5)
        s_entry = tk.Entry(page_frame, textvariable=s_var, width=5)
        s_entry.pack(side="left")
        tk.Label(page_frame, text=" bis ", bg=COLOR_BG).pack(side="left")
        e_entry = tk.Entry(page_frame, textvariable=e_var, width=5)
        e_entry.pack(side="left")
        pages_label = tk.Label(page_frame, text="", bg=COLOR_BG, fg="#888888")
        pages_label.pack(side="left", padx=8)

        def validate_pages(*args):
            """Faerbt die Eingabefelder rot, wenn der Bereich unplausibel ist."""
            try:
                s_val = int(s_var.get())
                e_val = int(e_var.get())
                limit = max_pages.get()
                valid = 1 <= s_val <= e_val and (limit == 0 or e_val <= limit)
            except ValueError:
                valid = not s_var.get().strip() and not e_var.get().strip()
            color = "white" if valid else COLOR_ERROR
            s_entry.config(bg=color)
            e_entry.config(bg=color)

        s_var.trace_add("write", validate_pages)
        e_var.trace_add("write", validate_pages)

        # Buttons rechts: Duplizieren und Entfernen
        def duplicate_row():
            """Legt eine Zeile mit gleicher Datei und Folgeseiten an."""
            try:
                next_start = int(e_var.get()) + 1
            except ValueError:
                next_start = 1
            limit = max_pages.get()
            new_data = {
                "file": f_var.get(),
                "voice_name": "",
                "start_page": min(next_start, limit) if limit else next_start,
                "end_page": limit if limit else "",
            }
            self.add_file_row(parent_frame, canvas, data=new_data)

        def remove_row():
            self.voice_comboboxes.remove(cb)
            row_frame.destroy()

        row_frame.columnconfigure(3, weight=1)
        btn_col = tk.Frame(row_frame, bg=COLOR_BG)
        btn_col.grid(row=0, column=3, rowspan=3, sticky="e", padx=10)
        tk.Button(btn_col, text="Duplizieren", command=duplicate_row).pack(fill="x", pady=1)
        tk.Button(btn_col, text="Entfernen", fg="red", command=remove_row).pack(fill="x", pady=1)

        row_frame.state_vars = {"file": f_var, "voice": v_var,
                                "start": s_var, "end": e_var}

        # Seitenzahl fuer geladene Konfigurationen nachziehen
        if data and data.get("file") and os.path.exists(data["file"]):
            read_page_count(data["file"], prefill=False)
        validate_pages()

        self.bind_all_children(row_frame, canvas)
        parent_frame.update_idletasks()
        canvas.yview_moveto(1.0)

    # ------------------------------------------------------------
    # Konfiguration laden und speichern
    # ------------------------------------------------------------
    def collect_data(self, require_valid=True):
        """Liest den UI-Zustand aus und gibt ihn als Dictionary zurueck."""
        title = self.title_entry.get().strip()
        composer = self.composer_entry.get().strip()

        export_data = {"metadata": {"suite_title": title, "composer": composer},
                       "symphonies": []}

        for sf in self.symphony_frames:
            symphony_data = []
            for row in sf.winfo_children():
                if not hasattr(row, "state_vars"):
                    continue
                f_val = row.state_vars["file"].get()
                v_val = row.state_vars["voice"].get().strip()
                s_raw = row.state_vars["start"].get()
                e_raw = row.state_vars["end"].get()

                if require_valid:
                    try:
                        s_val = int(s_raw)
                        e_val = int(e_raw)
                    except ValueError:
                        raise ValueError("Seitenzahlen müssen ganze Zahlen sein.")
                    if not f_val or not os.path.exists(f_val):
                        raise ValueError(f"Ungültiger Dateipfad: {f_val}")
                    if not v_val:
                        raise ValueError(
                            f"Keine Stimme gewählt für: {os.path.basename(f_val)}")
                else:
                    s_val = s_raw
                    e_val = e_raw

                symphony_data.append({"file": f_val, "voice_name": v_val,
                                      "start_page": s_val, "end_page": e_val})
            # Tabs ohne Eintraege nicht mitschreiben
            if symphony_data:
                export_data["symphonies"].append(symphony_data)

        return export_data

    def save_json(self):
        """Speichert die aktuelle Konfiguration ohne Export."""
        title = self.title_entry.get().strip() or "Konfiguration"
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=f"{title.replace(' ', '_')}_config.json",
            filetypes=[("JSON-Dateien", "*.json")])
        if not path:
            return
        data = self.collect_data(require_valid=False)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.set_status(f"Konfiguration gespeichert: {os.path.basename(path)}")

    def load_from_json(self):
        """Baut die Oberflaeche aus einer JSON-Konfiguration neu auf."""
        path = filedialog.askopenfilename(filetypes=[("JSON-Dateien", "*.json")])
        if not path:
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._is_loading = True

        self.title_entry.delete(0, tk.END)
        self.title_entry.insert(0, data.get("metadata", {}).get("suite_title", ""))
        self.composer_entry.delete(0, tk.END)
        self.composer_entry.insert(0, data.get("metadata", {}).get("composer", ""))

        num_tabs = self.notebook.index("end")
        for i in range(num_tabs - 2, -1, -1):
            tab_widget = self.master.nametowidget(self.notebook.tabs()[i])
            self.notebook.forget(i)
            tab_widget.destroy()

        self.symphony_frames.clear()
        self.voice_comboboxes.clear()
        self.voices.clear()

        for i, symph in enumerate(data.get("symphonies", [])):
            # Leere Sinfonien ueberspringen (verhindert leere Geister-Tabs)
            if not symph:
                continue
            self.add_symphony_tab(f"Sinfonie {len(self.symphony_frames) + 1}")
            current_sf = self.symphony_frames[-1]
            canvas = current_sf.master

            for entry in symph:
                v_name = entry["voice_name"]
                if v_name and v_name not in self.voices:
                    self.voices[v_name] = True
                self.add_file_row(current_sf, canvas, data=entry)

        # Falls die Konfiguration leer war, mindestens einen Tab anlegen
        if not self.symphony_frames:
            self.add_symphony_tab()

        self.update_comboboxes()

        # Wichtig: Beim Loeschen der alten Tabs waehlt das Notebook
        # automatisch den Plus-Tab an. Deshalb vor dem Freigeben des
        # Lade-Modus explizit den ersten echten Tab aktivieren und
        # ausstehende Tab-Events verarbeiten, sonst entsteht ein
        # leerer Extra-Tab.
        self.notebook.select(0)
        self.master.update()
        self._is_loading = False
        self.set_status(f"Konfiguration geladen: {os.path.basename(path)}")

    # ------------------------------------------------------------
    # Export
    # ------------------------------------------------------------
    def export_all(self):
        """Prueft die Eingaben, speichert die Konfiguration und exportiert."""
        title = self.title_entry.get().strip()
        composer = self.composer_entry.get().strip()
        if not title or not composer:
            messagebox.showerror("Fehler", "Titel und Komponist sind erforderlich.")
            return

        try:
            export_data = self.collect_data(require_valid=True)
        except ValueError as e:
            messagebox.showerror("Fehler", str(e))
            return

        active_voices = {}
        try:
            for symphony in export_data["symphonies"]:
                for entry in symphony:
                    v_val = entry["voice_name"]
                    if v_val not in active_voices:
                        active_voices[v_val] = Voice(v_val)
                    active_voices[v_val].add_pages(
                        entry["file"], entry["start_page"], entry["end_page"])
        except Exception as e:
            messagebox.showerror("Verarbeitungsfehler", str(e))
            return

        config_filename = f"{title.replace(' ', '_')}_config.json"
        with open(config_filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=4, ensure_ascii=False)

        for voice_obj in active_voices.values():
            voice_obj.export_pdf(title)

        self.set_status(f"{len(active_voices)} Stimmen exportiert nach '{OUTPUT_FOLDER}'.")
        messagebox.showinfo(
            "Fertig",
            f"{len(active_voices)} Stimmen exportiert.\n"
            f"Konfiguration gespeichert als {config_filename}.")


if __name__ == "__main__":
    root = tk.Tk()
    gui = ScoreGUI(root)
    tk.Button(root, text="Alle exportieren", width=20, bg="#d0e0ff",
              command=gui.export_all).pack(pady=10)
    root.mainloop()