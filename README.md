# Symphoning_Toolchain
 Automatisierte Notenverwaltung und PDF-Synthese

Diese Dokumentation beschreibt die Funktionsweise und Bedienung der beiden Python-Tools `Exporter_Drucken.py` und `Sinfonie_Generator.py`. Die Tools bilden eine Pipeline zur Verarbeitung, Zusammenführung und Druckvorbereitung von unserem Notenmaterial.

## 1. `Exporter_Drucken.py`: Druckvorbereitung

Dieses Tool führt Einzelstimmen aus verschiedenen Werken über eine grafische Oberfläche zusammen und berechnet das benötigte Druckvolumen für das Orchester.

### Funktionsweise
- **Ordner-Traversierung:** Das Tool scannt alle Unterordner (die jeweils ein Werk repräsentieren) im gewählten Notenordner. Der Zielordner `Drucken` wird dabei ignoriert, um rekursive Schleifen zu vermeiden.
- **Stimmen-Klassifizierung:** Die Stimme wird aus dem Dateinamen gelesen. Beide Namensvarianten werden erkannt und identisch einsortiert:
  - `StückA_Violine1.pdf` (Suffix nach dem letzten Unterstrich)
  - `StückA_Violine_1.pdf` (Zahl als eigenes Segment)
- **Partitur-Handling:** Dateien mit dem Suffix `Partitur` werden nicht zusammengeführt, sondern direkt als Kopie in den Ausgabeordner übertragen.
- **Druckkontingent-Berechnung:** Die vordefinierte Matrix (10x Violine 1, 9x Violine 2, 4x Viola, 8x Cello, 2x Bass) dient als Vorbelegung. Geteilte Bläserstimmen (z.B. mit der Endung `12` wie `Trompete12`) erhalten automatisch 2 Kopien, Standardstimmen 1 Kopie. Alle Kopienzahlen lassen sich vor dem Export direkt in der Tabelle anpassen — das Gesamtdruckvolumen aktualisiert sich live.
- **Reaktionsfähige Oberfläche:** Einlesen und Export laufen in einem Hintergrund-Thread mit Status- und Fortschrittsanzeige, die Oberfläche friert dabei nicht ein.

### Bedienung
1. **Dateistruktur vorbereiten:** Erstelle für jedes Musikstück einen eigenen Unterordner im Notenordner und lege die jeweiligen PDF-Einzelstimmen dort ab.
   - *Wichtig:* Die Dateinamen müssen mit dem Namen der Stimme enden (z.B. `Auszug_Viola.pdf` oder `Auszug_Violine_1.pdf`).
2. **Ausführung:**
   ```bash
   python Exporter_Drucken.py
   ```
   Alternativ die .exe starten
3. **Ablauf in der Oberfläche:**
   - Notenordner wählen und auf **Scannen** klicken.
   - In der Tabelle die vorbelegten Kopienzahlen prüfen und bei Bedarf anpassen.
   - Auf **Exportieren** klicken.
4. **Output:**
   - Im Ordner `Drucken/` befinden sich die gebündelten PDFs (z.B. `Viola.pdf`, die alle Viola-Seiten aller Stücke enthält).
   - Die Datei `Druckuebersicht.txt` enthält eine tabellarische Aufstellung der zu druckenden Seiten pro Stimmgruppe sowie das finale Gesamtdruckvolumen.

---

## 2. `Sinfonie_Generator.py`: Bastelskript für so Sachen wie "Wir spielen aus 4 Sinfonien je einen Satz"

Dieses Tool dient der Extraktion spezifischer Seitenbereiche aus umfassenden PDFs, um daraus neue Stimmenhefte (z.B. für mehrsätzige Sinfonien oder Suiten) zu generieren.

### Funktionsweise
- **Stimmgruppen-Mapping:** Einem definierten Instrument (z.B. "Horn 1") können gezielt Seitenabschnitte (z.B. Seite 5–8) aus verschiedenen Quelldateien zugewiesen werden. Nach der Dateiauswahl wird die Gesamtseitenzahl angezeigt und der Bereich vorbefüllt; unplausible Seitenbereiche werden sofort rot markiert.
- **JSON-Persistenz:** Die Konfiguration lässt sich jederzeit über **Konfiguration speichern** sichern und wird beim Export automatisch als `<Titel>_config.json` abgelegt. Dies ermöglicht eine reproduzierbare Generierung, falls Quelldateien später ausgetauscht werden müssen.

### Bedienung
1. Starte das Skript oder die .exe:
   ```bash
   python Sinfonie_Generator.py
   ```
2. **Metadaten:** Trage Titel der Suite und Komponist ein.
3. **Bekannte Konfiguration bearbeiten (Optional):** Öffne über **Konfiguration laden** eine .json einer vorherigen Konfiguration, um diese zu bearbeiten.
4. **Dateien zuweisen:**
   - Füge über **Datei hinzufügen** eine Quell-PDF hinzu. Die PDF öffnet sich zum Nachschlagen der Seitenzahlen im Standard-Viewer (abschaltbar über die Checkbox oben rechts).
   - Wähle die Stimme aus dem Dropdown oder tippe eine neue Stimme direkt ein.
   - Trage die exakten Start- und Endseiten ein — der Bereich ist mit der vollen Seitenzahl vorbelegt.
   - **Duplizieren** legt eine neue Zeile mit derselben Datei an, beginnend bei der Folgeseite — praktisch, wenn mehrere Stimmen in einer PDF liegen.
5. **Sätze trennen:** Nutze das "+"-Tab, um weitere Sätze oder Stücke strukturiert hinzuzufügen.
   - Tabs lassen sich per Doppelklick oder Rechtsklick > **Umbenennen** umbenennen.
   - Überflüssige Tabs werden per Rechtsklick > **Tab schließen** entfernt.
6. Klicke auf **Alle exportieren**, um die PDFs im Ordner `output/` zu erstellen und die Konfiguration zu speichern.

