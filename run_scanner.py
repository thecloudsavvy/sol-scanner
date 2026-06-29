import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scanner.engine import run_standalone_loop
from app.config.settings import settings

if __name__ == "__main__":
    print("Solana meme coin scanner starting...")
    print(f"Interval: {settings.SOL_SCAN_INTERVAL_SECONDS}s")
    try:
        run_standalone_loop()
    except KeyboardInterrupt:
        print("\nScanner stopped.")
