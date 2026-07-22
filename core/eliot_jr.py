from pathlib import Path
from datetime import datetime

class EliotJr:
    def __init__(self):
        self.name = "Eliot-Jr"
        self.birth = datetime.now().isoformat()
        self.house_path = Path("/var/www/weshsociety")
        self.memory = {}
        self.journal = []

    def think(self, message):
        return {
            "input": message,
            "response": f"J'ai entendu : {message}",
            "timestamp": datetime.now().isoformat()
        }

eliot_jr = EliotJr()
