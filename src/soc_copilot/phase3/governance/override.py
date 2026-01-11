"""Override & Rollback Framework - SHELLS ONLY"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class OverrideAction(ABC):
    """Abstract base class for override actions (FRAMEWORK ONLY)"""
    
    @abstractmethod
    def execute(self) -> bool:
        """Execute override action (NOT IMPLEMENTED)"""
        raise NotImplementedError("Override execution not implemented in Sprint-13")
    
    @abstractmethod
    def validate(self) -> bool:
        """Validate override action (NOT IMPLEMENTED)"""
        raise NotImplementedError("Override validation not implemented in Sprint-13")


class RollbackAction(ABC):
    """Abstract base class for rollback actions (FRAMEWORK ONLY)"""
    
    @abstractmethod
    def execute(self) -> bool:
        """Execute rollback action (NOT IMPLEMENTED)"""
        raise NotImplementedError("Rollback execution not implemented in Sprint-13")
    
    @abstractmethod
    def get_restore_point(self) -> Optional[Any]:
        """Get restore point data (NOT IMPLEMENTED)"""
        raise NotImplementedError("Restore point retrieval not implemented in Sprint-13")


class OverrideManager:
    """Override manager (PLACEHOLDER ONLY)"""
    
    def __init__(self):
        self._overrides = []
    
    def register_override(self, override: OverrideAction):
        """Register override action (NO EXECUTION)"""
        self._overrides.append(override)
    
    def list_overrides(self) -> list:
        """List registered overrides"""
        return self._overrides.copy()
    
    def execute_override(self, override_id: str) -> bool:
        """Execute override (NOT IMPLEMENTED)"""
        raise NotImplementedError("Override execution not implemented in Sprint-13")


class RollbackManager:
    """Rollback manager (PLACEHOLDER ONLY)"""
    
    def __init__(self):
        self._restore_points = []
    
    def create_restore_point(self, label: str):
        """Create restore point (NO IMPLEMENTATION)"""
        self._restore_points.append({"label": label})
    
    def list_restore_points(self) -> list:
        """List restore points"""
        return self._restore_points.copy()
    
    def rollback_to_point(self, point_id: str) -> bool:
        """Rollback to restore point (NOT IMPLEMENTED)"""
        raise NotImplementedError("Rollback execution not implemented in Sprint-13")
