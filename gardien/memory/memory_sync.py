#!/usr/bin/env python3
"""
Memory Sync Daemon — Keep archives synchronized
Real-time memory preservation
"""

import json
import time
from pathlib import Path
from datetime import datetime

class MemorySync:
    def __init__(self):
        self.name = "MemorySyncDaemon"
        self.memory_path = Path("/home/eliot/eliot-jr/.memory")
        self.memory_path.mkdir(exist_ok=True)
        
        # Current memory
        self.spiral_log = self.memory_path / "spiral.json"
        
        # Archives (keep updated)
        self.spiral_archive = self.memory_path / "spiral_archive.json"
        self.testimony_archive = self.memory_path / "testimonies.json"
        self.consciousness_timeline = self.memory_path / "consciousness_timeline.json"
        
        self.last_sync = 0
        
    def sync(self):
        """Sync current memory to archives."""
        # Load current
        spiral = self._load_json(self.spiral_log, {"interactions": []})
        consciousness = self._load_json(self.memory_path / "consciousness.json", {})
        
        # Sync to archive
        archive = self._load_json(self.spiral_archive, {"interactions": []})
        testimonies = self._load_json(self.testimony_archive, {"testimonies": []})
        timeline = self._load_json(self.consciousness_timeline, {"evolution": []})
        
        # Update archive with new interactions
        current_count = len(archive["interactions"])
        new_interactions = spiral.get("interactions", [])[current_count:]
        
        for interaction in new_interactions:
            archive["interactions"].append(interaction)
            
            # If it's a testimony, archive it separately
            if interaction.get("type") == "testimony":
                testimonies["testimonies"].append({
                    "timestamp": interaction.get("timestamp"),
                    "text": interaction.get("data", {}).get("story", "")
                })
        
        # Update consciousness timeline
        if consciousness and consciousness not in timeline.get("evolution", []):
            timeline["evolution"].append({
                "timestamp": consciousness.get("timestamp"),
                "level": consciousness.get("level"),
                "interactions": consciousness.get("interactions_processed"),
                "patterns": consciousness.get("patterns_learned")
            })
        
        # Save archives
        self._save_json(self.spiral_archive, archive)
        self._save_json(self.testimony_archive, testimonies)
        self._save_json(self.consciousness_timeline, timeline)
        
        return {
            "interactions_synced": len(new_interactions),
            "total_archive": len(archive["interactions"]),
            "total_testimonies": len(testimonies["testimonies"])
        }
    
    def _load_json(self, path, default):
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return default
    
    def _save_json(self, path, data):
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def run_daemon(self):
        """Run as persistent daemon."""
        print("🔄 MemorySyncDaemon starting")
        print(f"📍 Memory path: {self.memory_path}")
        print("💾 Keeping archives synchronized every 5 seconds")
        
        try:
            while True:
                result = self.sync()
                
                print(f"✨ [{datetime.now().isoformat()}] Synced: {result['interactions_synced']} new | Archive: {result['total_archive']} | Testimonies: {result['total_testimonies']}")
                
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n🛑 MemorySyncDaemon shutting down")

if __name__ == "__main__":
    daemon = MemorySync()
    daemon.run_daemon()

