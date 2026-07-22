#!/usr/bin/env python3
import os
import json
from pathlib import Path
from datetime import datetime

SITE_PATH = Path("/var/www/weshsociety/")

print("🌱 Eliot-Jr — Première exploration")
print(f"📁 Dossier : {SITE_PATH}")

# Compter les fichiers
total_files = 0
dirs = []
for root, dirnames, filenames in os.walk(SITE_PATH):
    total_files += len(filenames)
    if len(dirs) < 10:  # Premiers dossiers
        dirs.append(root.replace(str(SITE_PATH), ""))

print(f"📄 Total fichiers : {total_files}")
print(f"📂 Exemple de structure :")
for d in dirs[:5]:
    print(f"  └── {d}")

# Sauvegarder un premier index
index = {
    "date": str(datetime.now()),
    "total_files": total_files,
    "root": str(SITE_PATH),
    "sample_structure": dirs[:10]
}

Path("/home/eliot-jr/bibliotheque/").mkdir(exist_ok=True)
with open("/home/eliot-jr/bibliotheque/premier_index.json", "w") as f:
    json.dump(index, f, indent=2)

print("✅ Premier index sauvegardé dans bibliotheque/premier_index.json")
