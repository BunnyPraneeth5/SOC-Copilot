import sys
from pathlib import Path
import traceback

sys.path.insert(0, str(Path("src").absolute()))

from soc_copilot.phase4.controller.app_controller import AppController

def main():
    ctrl = AppController(models_dir="data/models")
    ctrl.initialize()
    
    with open("test_logs.txt", "r") as f:
        records = [{"raw_line": line.strip()} for line in f if line.strip()]
        
    try:
        res = ctrl.process_batch(records)
        print(f"Batch processed. Result present: {res is not None}")
        if res:
            print(f"Num logs: {len(res.logs)}")
            for log in res.logs:
                print(log)
        else:
            print(f"Dropped count: {ctrl._dropped_count}")
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    main()
