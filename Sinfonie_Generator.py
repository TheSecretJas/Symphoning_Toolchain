import os
import sys
import json
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from pypdf import PdfReader, PdfWriter

# ----------------------------
# Globale Einstellungen
# ----------------------------
USE_GUI = False
CONFIG_FILE = "Brahms_config.json"
OUTPUT_FOLDER = "output"

# ----------------------------
# Stimme Klasse
# ----------------------------
class Voice:
    def __init__(self, name):
        self.name = name
        self.pages = []

    def add_pages(self, file_path, start, end):
        reader = PdfReader(file_path)
        max_page = len(reader.pages)
        if start < 1 or end > max_page:
            raise ValueError(f"Seitenbereich ungültig: {start}-{end} (max. {max_page})")
        for i in range(start-1, end):
            page = reader.pages[i]
            self.pages.append(page)

    def export_pdf(self, suite_title, composer):
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        filename = f"{suite_title}_{self.name}.pdf".replace(" ", "_")
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        writer = PdfWriter()
        for page in self.pages:
            writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)
        print(f"✅ {self.name}-PDF erstellt: {output_path}")

# ----------------------------
# GUI Klasse
# ----------------------------
class ScoreGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Score Assembler")
        self.voices = {}
        self.suite_title = ""
        self.composer = ""
        self.symphonies = []
        self.tabs = {}

        self.create_metadata_frame()
        self.create_notebook()

        # Tab Features
        self.notebook.bind("<Double-Button-1>", self.rename_tab)  # Doppelklick → Name ändern
        self.notebook.bind("<Button-3>", self.rightclick_tab)     # Rechtsklick → Tab schließen

    # ----------------------------
    # Metadaten
    # ----------------------------
    def create_metadata_frame(self):
        frame = tk.Frame(self.master, padx=10, pady=10, bg="#f9f9f9")
        frame.pack(padx=10, pady=10, fill="x")

        tk.Label(frame, text="Titel der Suite:", bg="#f9f9f9").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.title_entry = tk.Entry(frame, width=40)
        self.title_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame, text="Komponist:", bg="#f9f9f9").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.composer_entry = tk.Entry(frame, width=40)
        self.composer_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Button(frame, text="Stimmgruppe hinzufügen", width=30, command=self.create_voices).grid(row=2, column=0, columnspan=2, pady=10)

    # ----------------------------
    # Notebook / Tabs
    # ----------------------------
    def create_notebook(self):
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        self.add_symphony_tab()  # erste Sinfonie Tab
        self.add_plus_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self.check_plus_tab)

    def add_symphony_tab(self, tab_name=None):
        if tab_name is None:
            tab_name = f"Sinfonie {len(self.symphonies)+1}"

        tab_frame = tk.Frame(self.notebook, bg="#eaeaea")

        # Prüfen, ob + Tab existiert
        plus_tab_index = None
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == "+":
                plus_tab_index = i
                break

        if plus_tab_index is not None:
            self.notebook.insert(plus_tab_index, tab_frame, text=tab_name)
        else:
            self.notebook.add(tab_frame, text=tab_name)

        style = ttk.Style()
        style.configure("TNotebook.Tab", padding=[12, 4])
        style.map("TNotebook.Tab",
                  background=[("selected", "#d0e0ff")],
                  foreground=[("selected", "black")])

        container = tk.Frame(tab_frame)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg="#eaeaea")
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        files_frame = tk.Frame(canvas, bg="#eaeaea")

        files_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=files_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            if os.name == 'nt':
                canvas.yview_scroll(-1 * int(event.delta / 120), "units")
            else:
                canvas.yview_scroll(-1 * int(event.delta), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        btn_frame = tk.Frame(tab_frame, bg="#eaeaea")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Datei hinzufügen", width=20, command=lambda: self.add_file_frame(files_frame)).pack(side="left", padx=5)

        self.symphonies.append([])
        self.tabs[len(self.symphonies)-1] = files_frame

    def add_plus_tab(self):
        plus_frame = tk.Frame(self.notebook)
        self.notebook.add(plus_frame, text="+")
        style = ttk.Style()
        style.configure("TNotebook.Tab", padding=[12, 4])
        style.map("TNotebook.Tab",
                  background=[("selected", "#c0ffc0")],
                  foreground=[("selected", "black")])

    def check_plus_tab(self, event):
        current = self.notebook.select()
        text = self.notebook.tab(current, "text")
        if text == "+":
            self.add_symphony_tab()
            self.notebook.select(self.notebook.index("end")-2)

    # ----------------------------
    # Stimmen erstellen
    # ----------------------------
    def create_voices(self):
        self.suite_title = self.title_entry.get()
        self.composer = self.composer_entry.get()
        if not self.suite_title or not self.composer:
            messagebox.showerror("Fehler", "Bitte Titel und Komponist eingeben")
            return

        self.voice_window = tk.Toplevel(self.master)
        self.voice_window.title("Stimmgruppe hinzufügen")
        self.voice_window.geometry("600x300")
        self.voice_window.configure(bg="#f0f0f0")

        tk.Label(self.voice_window, text="Name der Stimmgruppe:", bg="#f0f0f0").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.voice_name_entry = tk.Entry(self.voice_window, width=30)
        self.voice_name_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        self.voice_name_entry.focus_set()

        tk.Button(self.voice_window, text="Hinzufügen", width=12, command=self.add_voice).grid(row=0, column=2, padx=10, pady=10)
        tk.Button(self.voice_window, text="Fertig", width=12, command=self.voice_window.destroy).grid(row=1, column=0, columnspan=3, pady=10)

        self.added_voices_frame = tk.Frame(self.voice_window, bg="#f0f0f0")
        self.added_voices_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=10, sticky="w")

        self.voice_window.bind("<Return>", self.handle_voice_enter)

    def handle_voice_enter(self, event):
        if not self.voice_name_entry.get().strip():
            self.voice_window.destroy()
        else:
            self.add_voice()

    def add_voice(self):
        name = self.voice_name_entry.get().strip()
        if name and name not in self.voices:
            self.voices[name] = Voice(name)
            tk.Label(self.added_voices_frame, text=f"Stimme hinzugefügt: {name}", fg="blue", bg="#f0f0f0").pack(anchor="w")
            self.voice_name_entry.delete(0, tk.END)

    # ----------------------------
    # Datei Frame hinzufügen
    # ----------------------------
    def add_file_frame(self, parent_frame):
        frame = tk.Frame(parent_frame, relief=tk.RIDGE, borderwidth=2, bg="#f5f5f5")
        frame.pack(padx=5, pady=5, fill="x")

        tk.Label(frame, text="Datei:", bg="#f5f5f5").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        file_path_var = tk.StringVar()
        file_entry = tk.Entry(frame, textvariable=file_path_var, width=50)
        file_entry.grid(row=0, column=1, padx=5, pady=5)

        def browse_file():
            path = filedialog.askopenfilename(parent=self.master, filetypes=[("PDF-Dateien", "*.pdf")])
            if path:
                file_path_var.set(path)
                try:
                    if os.name == 'nt':
                        os.startfile(path)
                    elif os.name == 'posix':
                        import subprocess
                        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])
                except Exception as e:
                    messagebox.showerror("Fehler", f"PDF konnte nicht geöffnet werden:\n{e}")

        tk.Button(frame, text="Durchsuchen", command=browse_file, width=12).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(frame, text="Stimme:", bg="#f5f5f5").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        voice_var = tk.StringVar(value=list(self.voices.keys())[0] if self.voices else "")
        voice_dropdown = ttk.Combobox(frame, textvariable=voice_var, values=list(self.voices.keys()), state="readonly", width=30)
        voice_dropdown.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(frame, text="Startseite:", bg="#f5f5f5").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        start_entry = tk.Entry(frame, width=10)
        start_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        tk.Label(frame, text="Endseite:", bg="#f5f5f5").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        end_entry = tk.Entry(frame, width=10)
        end_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        def confirm():
            file_path = file_path_var.get().strip()
            voice_name = voice_var.get().strip()
            if not file_path or not os.path.exists(file_path):
                messagebox.showerror("Fehler", "Bitte gültige PDF-Datei auswählen!")
                return
            if voice_name not in self.voices.keys():
                messagebox.showerror("Fehler", f"Stimme '{voice_name}' ungültig!")
                return
            try:
                start = int(start_entry.get())
                end = int(end_entry.get())
            except ValueError:
                messagebox.showerror("Fehler", "Start- und Endseite müssen Zahlen sein!")
                return
            try:
                self.voices[voice_name].add_pages(file_path, start, end)
            except ValueError as e:
                messagebox.showerror("Fehler", str(e))
                return

            tab_index = self.notebook.index(self.notebook.select())
            self.symphonies[tab_index].append({
                "file": file_path,
                "voice_name": voice_name,
                "start_page": start,
                "end_page": end
            })

            for widget in frame.winfo_children():
                widget.grid_remove()
            added_label = tk.Label(frame, text=f"{voice_name}: Hinzugefügt!", fg="green", bg="#f5f5f5")
            added_label.grid(row=0, column=0, columnspan=3)

        end_entry.bind("<Return>", lambda event: confirm())
        tk.Button(frame, text="Hinzufügen", command=confirm, width=12).grid(row=4, column=1, pady=5)

    # ----------------------------
    # Tab Features
    # ----------------------------
    def rename_tab(self, event):
        index = self.notebook.index("@%d,%d" % (event.x, event.y))
        if index >= len(self.symphonies):
            return
        old_name = self.notebook.tab(index, "text")
        entry = tk.Entry(self.notebook, width=20)
        entry.insert(0, old_name)
        entry.place(x=event.x_root - self.master.winfo_rootx(),
                    y=event.y_root - self.master.winfo_rooty())
        entry.focus_set()

        def save_name(event=None):
            new_name = entry.get().strip()
            if new_name:
                self.notebook.tab(index, text=new_name)
            entry.destroy()

        entry.bind("<Return>", save_name)
        entry.bind("<FocusOut>", save_name)

    def rightclick_tab(self, event):
        index = self.notebook.index("@%d,%d" % (event.x, event.y))
        if index >= len(self.symphonies):
            return
        menu = tk.Menu(self.master, tearoff=0)
        menu.add_command(label="Tab schließen", command=lambda idx=index: self.close_tab(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def close_tab(self, index):
        self.notebook.forget(index)
        del self.symphonies[index]
        del self.tabs[index]
        # Indizes aktualisieren
        self.tabs = {i: self.tabs.get(i if i<index else i+1) for i in range(len(self.symphonies))}

    # ----------------------------
    # Export
    # ----------------------------
    def export_all(self):
        data = {
            "metadata": {"suite_title": self.suite_title, "composer": self.composer},
            "symphonies": self.symphonies
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        for voice in self.voices.values():
            voice.export_pdf(self.suite_title, self.composer)
        messagebox.showinfo("Fertig", "Alle Stimmen exportiert!")

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    if USE_GUI:
        root = tk.Tk()
        gui = ScoreGUI(root)
        tk.Button(root, text="Alle exportieren", width=20, command=gui.export_all).pack(pady=5)
        root.mainloop()
    else:
        if not os.path.exists(CONFIG_FILE):
            raise FileNotFoundError(f"{CONFIG_FILE} nicht gefunden!")
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = data["metadata"]
        symphonies = data["symphonies"]

        voices = {}
        for symphony in symphonies:
            for entry in symphony:
                name = entry["voice_name"]
                if name not in voices:
                    voices[name] = Voice(name)
                voices[name].add_pages(entry["file"], entry["start_page"], entry["end_page"])

        for voice in voices.values():
            voice.export_pdf(metadata["suite_title"], metadata["composer"])
