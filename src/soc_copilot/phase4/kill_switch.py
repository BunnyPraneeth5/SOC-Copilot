"""Kill switch for emergency shutdown"""

from pathlib import Path
from typing import Optional


class KillSwitch:
    """Emergency kill switch for SOC Copilot"""
    
    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent.parent
        self.kill_file = project_root / ".kill"
    
    def is_active(self) -> bool:
        """Check if kill switch is active"""
        return self.kill_file.exists()
    
    def activate(self) -> None:
        """Activate kill switch"""
        self.kill_file.touch()
    
    def deactivate(self) -> None:
        """Deactivate kill switch"""
        if self.kill_file.exists():
            self.kill_file.unlink()
