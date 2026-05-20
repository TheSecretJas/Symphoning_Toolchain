import os
import sys
import json
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from pypdf import PdfReader, PdfWriter

# Global configuration
USE_GUI = True
CONFIG_FILE = "Brahms_config.json"
OUTPUT_FOLDER = "output"

class Voice:
    """Represents an instrumental voice containing merged PDF pages."""
    def __init__(self, name):
        self.name = name
        self.pages = []

    def add_pages(self, file_path, start, end):
        """Extracts specific pages from a PDF and appends them to the voice."""
        reader = PdfReader(file_path)
        max_page = len(reader.pages)
        if start < 1 or end > max_page:
            raise ValueError(f"Invalid page range: {start}-{end} (max. {max_page})")
        for i in range(start-1, end):
            self.pages.append(reader.pages[i])

    def export_pdf(self, suite_title, composer):
        """Writes the accumulated pages to a new PDF file."""
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        filename = f"{suite_title}_{self.name}.pdf".replace(" ", "_")
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        writer = PdfWriter()
        for page in self.pages:
            writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)
        print(f"Export successful: {output_path}")

class ScoreGUI:
    """Main graphical interface for managing PDF assembly."""
    def __init__(self, master):
        self.master = master
        self.master.title("Score Assembler")
        
        # Enforce initial and minimum window dimensions to prevent widget clipping
        self.master.geometry("1000x700")
        self.master.minsize(850, 500)
        
        self.voices = {}
        self.symphony_frames = []
        self.voice_comboboxes = []

        self.setup_metadata_ui()
        self.setup_notebook_ui()

        self.notebook.bind("<Double-Button-1>", self.rename_tab)
        self.notebook.bind("<Button-3>", self.rightclick_tab)

    def setup_metadata_ui(self):
        """Initializes the upper control panel."""
        frame = tk.Frame(self.master, padx=10, pady=10, bg="#f9f9f9")
        frame.pack(padx=10, pady=10, fill="x")

        tk.Label(frame, text="Suite Title:", bg="#f9f9f9").grid(row=0, column=0, sticky="w")
        self.title_entry = tk.Entry(frame, width=40)
        self.title_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame, text="Composer:", bg="#f9f9f9").grid(row=1, column=0, sticky="w")
        self.composer_entry = tk.Entry(frame, width=40)
        self.composer_entry.grid(row=1, column=1, padx=5, pady=5)

        btn_frame = tk.Frame(frame, bg="#f9f9f9")
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="Load JSON", width=20, command=self.load_from_json).pack(side="left", padx=5)

    def setup_notebook_ui(self):
        """Initializes the tabbed interface for symphonies."""
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        self.add_symphony_tab()
        self.add_plus_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self.handle_tab_change)

    def bind_scroll(self, widget, canvas):
        """Attaches platform-specific scroll events to a specific widget."""
        def _scroll_mw(event):
            if canvas.winfo_ismapped():
                if os.name == 'nt':
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                else:
                    canvas.yview_scroll(int(-1*event.delta), "units")
        
        def _scroll_up(event):
            if canvas.winfo_ismapped(): canvas.yview_scroll(-1, "units")
            
        def _scroll_down(event):
            if canvas.winfo_ismapped(): canvas.yview_scroll(1, "units")

        widget.bind("<MouseWheel>", _scroll_mw)
        widget.bind("<Button-4>", _scroll_up)
        widget.bind("<Button-5>", _scroll_down)

    def bind_all_children(self, widget, canvas):
        """Recursively binds scroll events to a widget hierarchy."""
        self.bind_scroll(widget, canvas)
        for child in widget.winfo_children():
            self.bind_all_children(child, canvas)

    def add_symphony_tab(self, tab_name=None):
        """Creates a new tab for a symphony section."""
        if tab_name is None:
            tab_name = f"Symphony {len(self.symphony_frames)+1}"

        tab_frame = tk.Frame(self.notebook, bg="#eaeaea")
        
        plus_idx = next((i for i in range(self.notebook.index("end")) if self.notebook.tab(i, "text") == "+"), None)
        if plus_idx is not None:
            self.notebook.insert(plus_idx, tab_frame, text=tab_name)
        else:
            self.notebook.add(tab_frame, text=tab_name)

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

        self.bind_scroll(canvas, canvas)

        btn_frame = tk.Frame(tab_frame, bg="#eaeaea")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Add File Entry", width=20, command=lambda: self.add_file_row(files_frame, canvas)).pack()

        self.symphony_frames.append(files_frame)

    def add_plus_tab(self):
        """Adds the persistent tab used for creating new symphonies."""
        plus_frame = tk.Frame(self.notebook)
        self.notebook.add(plus_frame, text="+")

    def handle_tab_change(self, event):
        """Detects selection of the '+' tab to spawn a new symphony."""
        current = self.notebook.select()
        if self.notebook.tab(current, "text") == "+":
            self.add_symphony_tab()
            self.notebook.select(self.notebook.index("end")-2)

    def update_comboboxes(self):
        """Refreshes all dropdowns to include newly added voices."""
        voice_list = list(self.voices.keys())
        for cb in self.voice_comboboxes:
            cb['values'] = voice_list

    def add_file_row(self, parent_frame, canvas, data=None):
        """Appends an editable row for PDF assignment with inline addition and reliable layout."""
        row_frame = tk.Frame(parent_frame, relief=tk.RIDGE, borderwidth=2, bg="#f5f5f5")
        row_frame.pack(padx=5, pady=5, fill="x")

        f_var = tk.StringVar(value=data["file"] if data else "")
        v_var = tk.StringVar(value=data["voice_name"] if data else "")
        s_var = tk.StringVar(value=str(data["start_page"]) if data else "")
        e_var = tk.StringVar(value=str(data["end_page"]) if data else "")

        # File Input Row
        tk.Label(row_frame, text="File:", bg="#f5f5f5").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Entry(row_frame, textvariable=f_var, width=40).grid(row=0, column=1, sticky="w", padx=5)
        
        def browse():
            """Opens file dialog and launches the selected PDF in the default viewer."""
            path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
            if path:
                f_var.set(path)
                try:
                    if os.name == 'nt':
                        os.startfile(path)
                    elif sys.platform == 'darwin':
                        subprocess.Popen(['open', path])
                    else:
                        subprocess.Popen(['xdg-open', path])
                except Exception as e:
                    messagebox.showerror("Execution Error", f"Failed to open PDF:\n{e}")

        tk.Button(row_frame, text="Browse", command=browse).grid(row=0, column=2, sticky="w", padx=5)

        # Voice Selection Row
        tk.Label(row_frame, text="Voice:", bg="#f5f5f5").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        cb = ttk.Combobox(row_frame, textvariable=v_var, values=list(self.voices.keys()), state="readonly", width=37)
        cb.grid(row=1, column=1, sticky="w", padx=5)
        self.voice_comboboxes.append(cb)

        def open_inline_voice_dialog():
            v_win = tk.Toplevel(self.master)
            v_win.title("New Voice")
            v_win.geometry("+%d+%d" % (self.master.winfo_rootx() + 100, self.master.winfo_rooty() + 100))
            
            tk.Label(v_win, text="Voice Name:").grid(row=0, column=0, padx=5, pady=5)
            v_entry = tk.Entry(v_win, width=20)
            v_entry.grid(row=0, column=1, padx=5, pady=5)
            v_entry.focus_set()

            feedback_label = tk.Label(v_win, text="", fg="green")
            feedback_label.grid(row=1, column=0, columnspan=3)

            def confirm(event=None):
                val = v_entry.get().strip()
                if val:
                    if val not in self.voices:
                        self.voices[val] = True
                        self.update_comboboxes()
                    v_var.set(val) 
                    feedback_label.config(text=f"'{val}' added successfully!")
                    v_win.update()
                    v_win.after(800, v_win.destroy)

            tk.Button(v_win, text="Add", command=confirm).grid(row=0, column=2, padx=5)
            v_win.bind("<Return>", confirm)

        tk.Button(row_frame, text="Add", command=open_inline_voice_dialog).grid(row=1, column=2, sticky="w", padx=5)

        # Page Ranges Row
        tk.Label(row_frame, text="Pages:", bg="#f5f5f5").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        page_frame = tk.Frame(row_frame, bg="#f5f5f5")
        page_frame.grid(row=2, column=1, sticky="w", padx=5)
        tk.Entry(page_frame, textvariable=s_var, width=5).pack(side="left")
        tk.Label(page_frame, text=" to ", bg="#f5f5f5").pack(side="left")
        tk.Entry(page_frame, textvariable=e_var, width=5).pack(side="left")

        # Global Remove Button
        def remove_row():
            self.voice_comboboxes.remove(cb)
            row_frame.destroy()

        row_frame.columnconfigure(3, weight=1)
        tk.Button(row_frame, text="Remove", fg="red", command=remove_row).grid(row=0, column=3, rowspan=3, sticky="e", padx=15)

        row_frame.state_vars = {"file": f_var, "voice": v_var, "start": s_var, "end": e_var}
        
        self.bind_all_children(row_frame, canvas)

    def rename_tab(self, event):
        """Allows inline renaming of symphony tabs."""
        idx = self.notebook.index(f"@{event.x},{event.y}")
        old_name = self.notebook.tab(idx, "text")
        if old_name == "+": return
        
        entry = tk.Entry(self.notebook, width=20)
        entry.insert(0, old_name)
        entry.place(x=event.x, y=event.y)
        entry.focus_set()

        def save(e=None):
            if entry.get().strip():
                self.notebook.tab(idx, text=entry.get().strip())
            entry.destroy()
        
        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)

    def rightclick_tab(self, event):
        """Opens context menu to close a tab."""
        idx = self.notebook.index(f"@{event.x},{event.y}")
        if self.notebook.tab(idx, "text") == "+": return
        menu = tk.Menu(self.master, tearoff=0)
        menu.add_command(label="Close Tab", command=lambda: self.close_tab(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def close_tab(self, index):
        """Removes a tab and its associated data structures."""
        tab_widget_name = self.notebook.tabs()[index]
        tab_widget = self.master.nametowidget(tab_widget_name)
        
        for sf in self.symphony_frames:
            if str(sf).startswith(str(tab_widget)):
                self.symphony_frames.remove(sf)
                break
        self.notebook.forget(index)

    def load_from_json(self):
        """Populates the UI based on an external JSON configuration."""
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not path: return
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.title_entry.delete(0, tk.END)
        self.title_entry.insert(0, data.get("metadata", {}).get("suite_title", ""))
        self.composer_entry.delete(0, tk.END)
        self.composer_entry.insert(0, data.get("metadata", {}).get("composer", ""))

        while self.notebook.index("end") > 1:
            self.notebook.forget(0)
        self.symphony_frames.clear()
        self.voice_comboboxes.clear()
        self.voices.clear()

        symphonies = data.get("symphonies", [])
        for i, symph in enumerate(symphonies):
            self.add_symphony_tab(f"Symphony {i+1}")
            current_sf = self.symphony_frames[-1]
            canvas = current_sf.master
            
            for entry in symph:
                v_name = entry["voice_name"]
                if v_name not in self.voices:
                    self.voices[v_name] = True
                self.add_file_row(current_sf, canvas, data=entry)
        
        self.update_comboboxes()

    def export_all(self):
        """Parses the current UI state, creates JSON, and triggers PDF processing."""
        title = self.title_entry.get().strip()
        composer = self.composer_entry.get().strip()
        if not title or not composer:
            messagebox.showerror("Error", "Title and composer are required.")
            return

        export_data = {"metadata": {"suite_title": title, "composer": composer}, "symphonies": []}
        active_voices = {}

        for sf in self.symphony_frames:
            symphony_data = []
            for row in sf.winfo_children():
                if hasattr(row, "state_vars"):
                    f_val = row.state_vars["file"].get()
                    v_val = row.state_vars["voice"].get()
                    try:
                        s_val = int(row.state_vars["start"].get())
                        e_val = int(row.state_vars["end"].get())
                    except ValueError:
                        messagebox.showerror("Error", "Page numbers must be integers.")
                        return
                    
                    if not f_val or not os.path.exists(f_val):
                        messagebox.showerror("Error", f"Invalid file path: {f_val}")
                        return

                    symphony_data.append({
                        "file": f_val, "voice_name": v_val,
                        "start_page": s_val, "end_page": e_val
                    })
                    
                    if v_val not in active_voices:
                        active_voices[v_val] = Voice(v_val)
                    
                    try:
                        active_voices[v_val].add_pages(f_val, s_val, e_val)
                    except Exception as e:
                        messagebox.showerror("Processing Error", str(e))
                        return
            
            export_data["symphonies"].append(symphony_data)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=4)

        for voice_obj in active_voices.values():
            voice_obj.export_pdf(title, composer)
            
        messagebox.showinfo("Success", "Files successfully exported and JSON updated.")

if __name__ == "__main__":
    if USE_GUI:
        root = tk.Tk()
        gui = ScoreGUI(root)
        tk.Button(root, text="Export All", width=20, bg="#d0e0ff", command=gui.export_all).pack(pady=10)
        root.mainloop()