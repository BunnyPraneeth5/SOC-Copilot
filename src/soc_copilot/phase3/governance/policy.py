"""Governance Policy Module - Authority States and Permissions"""

from enum import Enum
from typing import Dict, Set
import yaml
from pathlib import Path


class AuthorityState(Enum):
    """Authority states for governance control"""
    DISABLED = "disabled"
    OBSERVE_ONLY = "observe_only"
    ADVISORY_ONLY = "advisory_only"


class GovernancePolicy:
    """Manages governance policies and authority states"""
    
    DEFAULT_STATE = AuthorityState.DISABLED
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path
        self._state = self.DEFAULT_STATE
        self._permitted_components: Dict[AuthorityState, Set[str]] = {
            AuthorityState.DISABLED: set(),
            AuthorityState.OBSERVE_ONLY: {"logging", "monitoring"},
            AuthorityState.ADVISORY_ONLY: {"logging", "monitoring", "recommendations"}
        }
        
        if config_path:
            self._load_policy(config_path)
    
    def _load_policy(self, config_path: str):
        """Load policy from YAML configuration"""
        path = Path(config_path)
        if not path.exists():
            return
        
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        
        if not config:
            return
        
        # Load state (but keep DISABLED as default)
        state_str = config.get('default_state', 'disabled')
        try:
            self._state = AuthorityState(state_str)
        except ValueError:
            self._state = self.DEFAULT_STATE
        
        # Load permitted components
        if 'permitted_components' in config:
            for state_str, components in config['permitted_components'].items():
                try:
                    state = AuthorityState(state_str)
                    self._permitted_components[state] = set(components)
                except ValueError:
                    continue
    
    @property
    def current_state(self) -> AuthorityState:
        """Get current authority state"""
        return self._state
    
    def is_component_permitted(self, component: str) -> bool:
        """Check if component is permitted in current state"""
        return component in self._permitted_components.get(self._state, set())
    
    def get_permitted_components(self) -> Set[str]:
        """Get all permitted components for current state"""
        return self._permitted_components.get(self._state, set()).copy()
    
    def to_dict(self) -> dict:
        """Export policy state as dictionary"""
        return {
            "current_state": self._state.value,
            "permitted_components": list(self.get_permitted_components())
        }
