# ==============================================================
# FILENAME: make_version_info.py
# PROJECT : Symphoning_Toolchain
# AUTHOR  : Jonas Thern
# NOTE    : Kommentare und Formatierung wurden mit Unterstuetzung
#           von kuenstlicher Intelligenz (Claude, Anthropic) erstellt.
# ==============================================================
#
# Erzeugt eine PyInstaller-Versionsdatei (--version-file), damit die
# .exe unter Eigenschaften > Details Autor, Produktname und Version
# anzeigt. Hinweis: Der "Herausgeber" im SmartScreen-Dialog kommt nur
# aus einer Code-Signatur, nicht aus diesen Angaben.
#
# Aufruf: python make_version_info.py <Ausgabedatei> <Tag> <Dateiname> <Beschreibung>

import re
import sys

COMPANY = "Jonas Thern"
PRODUCT = "Symphoning Toolchain"


def version_tuple(tag):
    """v1.2.3 -> (1, 2, 3, 0); fehlende oder ungueltige Teile werden 0."""
    numbers = [int(n) for n in re.findall(r"\d+", tag)][:4]
    return tuple(numbers + [0] * (4 - len(numbers)))


def main():
    out_path, tag, exe_name, description = sys.argv[1:5]
    version = version_tuple(tag)
    version_str = ".".join(str(n) for n in version)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version}, prodvers={version},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040704B0', [
        StringStruct('CompanyName', {COMPANY!r}),
        StringStruct('FileDescription', {description!r}),
        StringStruct('FileVersion', {version_str!r}),
        StringStruct('InternalName', {exe_name!r}),
        StringStruct('LegalCopyright', {('© ' + COMPANY)!r}),
        StringStruct('OriginalFilename', {(exe_name + '.exe')!r}),
        StringStruct('ProductName', {PRODUCT!r}),
        StringStruct('ProductVersion', {version_str!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()
