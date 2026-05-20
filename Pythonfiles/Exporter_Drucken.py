import os
import shutil
from pypdf import PdfReader, PdfWriter

# ----------------------------
# 1. Configuration / Settings
# ----------------------------
OUTPUT_FOLDER = "Drucken"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Copy counts for specific string sections (Pulte/Spieler)
COPIES_VIOLINE1 = 10
COPIES_VIOLINE2 = 9
COPIES_VIOLA    = 4
COPIES_CELLO    = 8
COPIES_BASS     = 2

# ----------------------------
# 2. Helper Functions
# ----------------------------
def get_copy_count(voice_name):
    """
    Determines how many copies are needed based on voice name.
    """
    v_lower = voice_name.lower()
    
    # Priority 1: Specific String Sections
    if "violine1" in v_lower: return COPIES_VIOLINE1
    if "violine2" in v_lower: return COPIES_VIOLINE2
    if "viola" in v_lower:    return COPIES_VIOLA
    if "cello" in v_lower or "violoncello" in v_lower: return COPIES_CELLO
    if "bass" in v_lower or "kontrabass" in v_lower:   return COPIES_BASS

    # Priority 2: Combined parts (e.g., Trompete12 -> 2 copies)
    if voice_name.endswith("12"):
        return 2

    # Default
    return 1

# ----------------------------
# 3. Voice Class
# ----------------------------
class Voice:
    """
    Represents a specific instrument voice (e.g., Violin 1).
    Collects pages from multiple pieces to merge them into one file.
    """
    def __init__(self, name):
        self.name = name
        self.pages = []

    def add_pages(self, file_path):
        """
        Extracts all pages from a source PDF and adds them to the voice's page list.
        """
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                self.pages.append(page)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    def export_pdf(self):
        """
        Writes the collected pages to a single PDF file in the output folder.
        """
        filename = f"{self.name}.pdf".replace(" ", "_")
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        
        writer = PdfWriter()
        for page in self.pages:
            writer.add_page(page)
            
        with open(output_path, "wb") as f:
            writer.write(f)
            
        return len(self.pages)

# ----------------------------
# 4. Main Processing Function
# ----------------------------
def merge_pdfs_by_voice(base_folder="."):
    """
    Scans folders, sorts PDFs by voice suffix, generates files, and calculates print stats.
    Saves the overview to a .txt file.
    """
    voices = {}
    page_counts_per_voice = {} 
    total_score_pages = 0
    
    # Init Logging List
    report_lines = []
    
    def log(msg):
        print(msg)
        report_lines.append(msg)

    # Get subfolders (pieces) sorted alphabetically
    # EXCLUDE the Output Folder from scanning to prevent recursive loops/SameFileError
    piece_folders = sorted(
        [f for f in os.listdir(base_folder) 
         if os.path.isdir(os.path.join(base_folder, f)) 
         and f != OUTPUT_FOLDER]
    )

    for piece in piece_folders:
        piece_path = os.path.join(base_folder, piece)

        # Walk through the directory tree
        for root, dirs, files in os.walk(piece_path):
            # Safety check: avoid entering output folder if nested
            if OUTPUT_FOLDER in dirs:
                dirs.remove(OUTPUT_FOLDER)

            for file in sorted(files):
                if file.lower().endswith(".pdf"):
                    full_path = os.path.join(root, file)
                    
                    # Extract voice name
                    try:
                        parts = file.rsplit(".", 1)[0].split("_")
                        if len(parts) < 2:
                            voice_name = file.rsplit(".", 1)[0]
                        else:
                            voice_name = parts[-1] 
                    except Exception as e:
                        print(f"Skipping file ({file}): {e}")
                        continue

                    # --- CASE A: Partitur (Score) ---
                    if voice_name == "Partitur":
                        try:
                            reader = PdfReader(full_path)
                            p_count = len(reader.pages)
                            total_score_pages += p_count
                        except:
                            p_count = 0
                        
                        out_path = os.path.join(OUTPUT_FOLDER, file)
                        
                        # Prevent SameFileError if source and dest are identical
                        if os.path.abspath(full_path) != os.path.abspath(out_path):
                            shutil.copy(full_path, out_path)
                            print(f"Score copied: {out_path}")
                        else:
                            print(f"Skipping copy (Source == Dest): {file}")
                        
                    # --- CASE B: Instrument Parts ---
                    else:
                        if voice_name not in voices:
                            voices[voice_name] = Voice(voice_name)
                        voices[voice_name].add_pages(full_path)

    # Export merged voices and collect raw page counts
    for voice_name, voice_obj in voices.items():
        count = voice_obj.export_pdf()
        page_counts_per_voice[voice_name] = count

    # ----------------------------
    # 5. Output Statistics & Log to File
    # ----------------------------
    log("\n" + "="*65)
    log(f"{'DRUCKÜBERSICHT':^65}")
    log("="*65)
    # Headers: Voice | Pages per File | Copies | Total Sum
    log(f"{'Stimme':<20} | {'Seiten':>8} | {'Anzahl':>8} | {'Gesamt':>10}")
    log("-" * 65)
    
    grand_total_print_pages = 0

    # Sort voices alphabetically
    for voice in sorted(page_counts_per_voice.keys()):
        pages_per_doc = page_counts_per_voice[voice]
        
        # Calculate needed copies
        copies = get_copy_count(voice)
        
        # Calculate total for this voice
        total_voice = pages_per_doc * copies
        grand_total_print_pages += total_voice
        
        log(f"{voice:<20} | {pages_per_doc:>8} | {copies:>8} | {total_voice:>10}")
    
    # Add Partitur summary
    if total_score_pages > 0:
        log("-" * 65)
        log(f"{'Partitur (Summe)':<20} | {total_score_pages:>8} | {1:>8} | {total_score_pages:>10}")
        grand_total_print_pages += total_score_pages
    
    log("="*65)
    log(f"{'GESAMTDRUCKVOLUMEN (Seiten)':<43} | {grand_total_print_pages:>10}")
    log("="*65)

    # Write report to .txt file
    report_path = os.path.join(OUTPUT_FOLDER, "Druckuebersicht.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\n[INFO] Übersicht gespeichert unter: {report_path}")

# ----------------------------
# Execution
# ----------------------------
if __name__ == "__main__":
    print("Starting PDF sort and merge process...")
    merge_pdfs_by_voice()
    print("Process completed.")