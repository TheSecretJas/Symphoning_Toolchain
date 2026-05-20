# Symphoning_Toolchain
 Automatisierte Notenverwaltung und PDF-Synthese

Diese Dokumentation beschreibt die Funktionsweise und Bedienung der beiden Python-Skripte `Exporter_Drucken.py` und `Sinfonie_Generator.py`. Die Tools bilden eine Pipeline zur Verarbeitung, Zusammenführung und Druckvorbereitung von unserem Notenmaterial.

---

## 1. `Exporter_Drucken.py`: Druckvorbereitung

Dieses Skript automatisiert das Zusammenführen von Einzelstimmen aus verschiedenen Werken und berechnet das benötigte Druckvolumen für das Orchester.

### Funktionsweise
- **Ordner-Traversierung:** Das Skript scannt alle Unterordner (die jeweils ein Werk repräsentieren) im Ausführungsverzeichnis. Der Zielordner `Drucken` wird dabei ignoriert, um rekursive Schleifen zu vermeiden.
- **Stimmen-Klassifizierung:** Es analysiert die Dateinamen der PDFs (Suffix nach dem letzten Unterstrich, z.B. `StückA_Violine1.pdf`) und gruppiert alle Seiten mit demselben Suffix.
- **Partitur-Handling:** Dateien mit dem Suffix `Partitur` werden nicht zusammengeführt, sondern direkt als Kopie in den Ausgabeordner übertragen.
- **Druckkontingent-Berechnung:** Basierend auf einer vordefinierten Matrix (10x Violine 1, 9x Violine 2, 4x Viola, 8x Cello, 2x Bass) wird die Anzahl der benötigten physischen Seiten berechnet. Geteilte Bläserstimmen (z.B. mit der Endung `12` wie `Trompete12`) generieren automatisch 2 Kopien. Standardstimmen erhalten 1 Kopie.

### Bedienung
1. **Dateistruktur vorbereiten:** Platziere das Skript in einem Hauptordner. Erstelle für jedes Musikstück einen eigenen Unterordner und lege die jeweiligen PDF-Einzelstimmen dort ab.
   - *Wichtig:* Die Dateinamen müssen mit dem Namen der Stimme enden (z.B. `Auszug_Viola.pdf`).
2. **Ausführung:** Führe das Skript im Terminal aus:
   ```bash
   python Exporter_Drucken.py
   ```
3. **Output:** - Im Ordner `Drucken/` befinden sich die gebündelten PDFs (z.B. `Viola.pdf`, die alle Viola-Seiten aller Stücke enthält).
   - Die Datei `Druckuebersicht.txt` enthält eine tabellarische Aufstellung der zu druckenden Seiten pro Stimmgruppe sowie das finale Gesamtdruckvolumen.

---

## 2. `Sinfonie_Generator.py`: Bastelskript für so Sachen wie "Wir spielen aus 4 Sinfonien je einen Satz"

Dieses Tool dient der Extraktion spezifischer Seitenbereiche aus umfassenden PDFs, um daraus neue, Stimmenhefte (z.B. für mehrsätzige Sinfonien oder Suiten) zu generieren.

### Funktionsweise
- **Dualer Betriebsmodus:** Das Skript kann entweder über eine grafische Benutzeroberfläche (GUI) oder im Headless-Modus (via JSON-Konfigurationsdatei) ausgeführt werden.
- **Stimmgruppen-Mapping:** Einem definierten Instrument (z.B. "Horn 1") können gezielt Seitenabschnitte (z.B. Seite 5–8) aus verschiedenen Quelldateien zugewiesen werden.
- **JSON-Persistenz:** Bei Nutzung der GUI werden alle Eingaben beim Export in die Datei `Brahms_config.json` geschrieben. Dies ermöglicht eine reproduzierbare Generierung, falls Quelldateien später ausgetauscht werden müssen.

### Bedienung

#### Interaktiver Modus
1. Starte das Skript oder die .exe: 
   ```bash
   python Sinfonie_Generator.py
   ```
2. **Metadaten:** Trage Titel der Suite und Komponist ein.
3. **Bekannte Konfiguration bearbeiten (Optional):** Öffne eine .json einer vorherigen Konfiguration, um diese zu bearbeiten.
4. **Dateien zuweisen:** - Füge über "Datei hinzufügen" eine Quell-PDF hinzu.
   - Wähle die Stimme aus dem Dropdown-Menü oder füge ggf. eine hinzu.
   - Trage die exakten Start- und Endseiten ein.
5. **Sätze trennen:** Nutze das "+"-Tab, um weitere Sätze oder Stücke strukturiert hinzuzufügen.
   - Zu viel hinzugefügte Sätze können über einen Rechtsklick auf den Satz und "close tab" wieder geschlossen werden. 
6. Klicke auf "Alle exportieren", um die PDFs im Ordner `output/` zu erstellen und die Konfiguration zu speichern.

