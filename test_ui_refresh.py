import sys
from pathlib import Path
sys.path.insert(0, str(Path("src").absolute()))

from soc_copilot.phase4.controller.app_controller import AppController
from PyQt6.QtWidgets import QApplication
from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
from soc_copilot.phase4.ui.all_logs_view import AllLogsView

app = QApplication(sys.argv)
ctrl = AppController(models_dir="data/models")
ctrl.initialize()
bridge = ControllerBridge(ctrl)
view = AllLogsView(bridge)

# Read the test logs
bridge.add_file_source("test_logs.txt")

results = bridge.get_latest_alerts()
print(f"Results returned: {len(results)}")
for r in results:
    print(f"Has logs: {hasattr(r, 'logs')}")
    if hasattr(r, 'logs'):
        print(f"Logs length: {len(r.logs)}")
