#!/usr/bin/env python3
import json
import time
from pathlib import Path
from datetime import datetime

class TruthTellers:
    def __init__(self):
        self.wisdom_path = Path("/home/eliot/eliot-jr/.wisdom")
        self.wisdom_path.mkdir(exist_ok=True)
        self.truth_tellers = self.wisdom_path / "truth_tellers.json"
    
    def run_daemon(self):
        print("📣 Truth Tellers Active")
        time.sleep(3600)

if __name__ == "__main__":
    t = TruthTellers()
    t.run_daemon()
