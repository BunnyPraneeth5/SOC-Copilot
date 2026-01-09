"""Network feature extractor.

Computes features based on network connection patterns, port usage,
and graph-derived metrics.
"""

from typing import Any
from collections import defaultdict

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.data.feature_engineering.base import (
    BaseFeatureExtractor,
    FeatureDefinition,
    FeatureType,
    entropy,
    safe_divide,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


# Well-known port ranges
SYSTEM_PORTS = range(0, 1024)
REGISTERED_PORTS = range(1024, 49152)
DYNAMIC_PORTS = range(49152, 65536)

# Common security-relevant ports
SECURITY_PORTS = {
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    80: "http",
    110: "pop3",
    143: "imap",
    443: "https",
    445: "smb",
    993: "imaps",
    995: "pop3s",
    1433: "mssql",
    1521: "oracle",
    3306: "mysql",
    3389: "rdp",
    5432: "postgresql",
    5900: "vnc",
    8080: "http-alt",
    8443: "https-alt",
}


class NetworkFeatureConfig(BaseModel):
    """Configuration for network feature extraction."""
    
    # Source and destination fields
    src_ip_field: str = "src_ip"
    dst_ip_field: str = "dst_ip"
    src_port_field: str = "src_port"
    dst_port_field: str = "dst_port"
    protocol_field: str = "protocol"
    bytes_field: str = "bytes_total"
    
    # Entity field for aggregation
    entity_field: str = "src_ip"
    
    # Prefix for generated feature names
    feature_prefix: str = "net"


class NetworkFeatureExtractor(BaseFeatureExtractor):
    """Extracts network-based features from log data.
    
    Features computed:
    - Port pattern features (system/registered/dynamic ratios)
    - Connection diversity (unique destinations, ports)
    - Protocol distribution
    - Bytes per connection patterns
    - Simple graph metrics (degree, fan-out)
    
    All features are numeric and deterministic.
    """
    
    def __init__(self, config: NetworkFeatureConfig | None = None):
        """Initialize extractor.
        
        Args:
            config: Network feature configuration
        """
        super().__init__(config)
        self.config = config or NetworkFeatureConfig()
        
        # Learning state
        self._entity_conn_graph: dict[str, set[str]] = defaultdict(set)
        self._global_port_dist: dict[int, int] = defaultdict(int)
    
    @property
    def feature_definitions(self) -> list[FeatureDefinition]:
        """Get feature definitions."""
        definitions = []
        prefix = self.config.feature_prefix
        
        # Port pattern features
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_dst_port_is_system",
                description="Destination port is in system range (0-1023)",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_dst_port_is_common",
                description="Destination port is a common security-relevant port",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_dst_port_is_dynamic",
                description="Destination port is in dynamic/ephemeral range",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
        ])
        
        # Connection diversity features (per entity)
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_unique_dst_ips",
                description="Number of unique destination IPs for entity",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
            ),
            FeatureDefinition(
                name=f"{prefix}_unique_dst_ports",
                description="Number of unique destination ports for entity",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
            ),
            FeatureDefinition(
                name=f"{prefix}_dst_port_entropy",
                description="Entropy of destination port distribution",
                feature_type=FeatureType.NETWORK,
                min_value=0,
            ),
        ])
        
        # Graph-derived metrics
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_fanout_ratio",
                description="Ratio of unique destinations to total connections",
                feature_type=FeatureType.NETWORK,
                min_value=0,
                max_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_is_scanner_like",
                description="Pattern suggests scanning behavior (high fanout)",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
        ])
        
        # Bytes features
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_bytes_per_conn",
                description="Average bytes per connection for entity",
                feature_type=FeatureType.NETWORK,
                min_value=0,
            ),
            FeatureDefinition(
                name=f"{prefix}_conn_count",
                description="Total connection count for entity",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
            ),
        ])
        
        # Protocol features
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_is_tcp",
                description="Protocol is TCP",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_is_udp",
                description="Protocol is UDP",
                feature_type=FeatureType.NETWORK,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
        ])
        
        return definitions
    
    def fit(self, df: pd.DataFrame) -> None:
        """Learn baseline network patterns from training data.
        
        Args:
            df: Training DataFrame
        """
        entity_field = self.config.entity_field
        dst_ip_field = self.config.dst_ip_field
        dst_port_field = self.config.dst_port_field
        
        if entity_field in df.columns and dst_ip_field in df.columns:
            # Build connection graph
            for _, row in df.iterrows():
                entity = str(row.get(entity_field, ""))
                dst = str(row.get(dst_ip_field, ""))
                if entity and dst:
                    self._entity_conn_graph[entity].add(dst)
        
        # Port distribution
        if dst_port_field in df.columns:
            for port in df[dst_port_field].dropna():
                try:
                    self._global_port_dist[int(port)] += 1
                except (ValueError, TypeError):
                    pass
        
        self._fitted = True
        
        logger.info(
            "network_features_fit",
            entities=len(self._entity_conn_graph),
            unique_ports=len(self._global_port_dist),
        )
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract network features.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with network features added
        """
        result = df.copy()
        prefix = self.config.feature_prefix
        
        # Initialize features with defaults
        for feat_def in self.feature_definitions:
            result[feat_def.name] = feat_def.default_value
        
        # Per-record port features
        dst_port_field = self.config.dst_port_field
        if dst_port_field in result.columns:
            ports = pd.to_numeric(result[dst_port_field], errors="coerce")
            
            # System ports
            result[f"{prefix}_dst_port_is_system"] = ports.apply(
                lambda p: 1 if pd.notna(p) and 0 <= p < 1024 else 0
            )
            
            # Common ports
            result[f"{prefix}_dst_port_is_common"] = ports.apply(
                lambda p: 1 if pd.notna(p) and int(p) in SECURITY_PORTS else 0
            )
            
            # Dynamic ports
            result[f"{prefix}_dst_port_is_dynamic"] = ports.apply(
                lambda p: 1 if pd.notna(p) and p >= 49152 else 0
            )
        
        # Protocol features
        protocol_field = self.config.protocol_field
        if protocol_field in result.columns:
            protocols = result[protocol_field].astype(str).str.lower()
            result[f"{prefix}_is_tcp"] = (protocols == "tcp").astype(int)
            result[f"{prefix}_is_udp"] = (protocols == "udp").astype(int)
        
        # Per-entity features
        entity_field = self.config.entity_field
        dst_ip_field = self.config.dst_ip_field
        bytes_field = self.config.bytes_field
        
        if entity_field in result.columns:
            grouped = result.groupby(entity_field)
            
            for entity, indices in grouped.groups.items():
                entity_data = result.loc[indices]
                
                # Connection count
                conn_count = len(entity_data)
                result.loc[indices, f"{prefix}_conn_count"] = conn_count
                
                # Unique destination IPs
                if dst_ip_field in entity_data.columns:
                    unique_dsts = entity_data[dst_ip_field].nunique()
                    result.loc[indices, f"{prefix}_unique_dst_ips"] = unique_dsts
                    
                    # Fanout ratio
                    fanout = unique_dsts / conn_count if conn_count > 0 else 0
                    result.loc[indices, f"{prefix}_fanout_ratio"] = fanout
                    
                    # Scanner-like behavior (high unique destinations relative to connections)
                    is_scanner = 1 if fanout > 0.8 and unique_dsts > 10 else 0
                    result.loc[indices, f"{prefix}_is_scanner_like"] = is_scanner
                
                # Unique destination ports and entropy
                if dst_port_field in entity_data.columns:
                    ports = entity_data[dst_port_field].dropna()
                    unique_ports = ports.nunique()
                    result.loc[indices, f"{prefix}_unique_dst_ports"] = unique_ports
                    
                    if len(ports) > 0:
                        port_counts = ports.value_counts()
                        probs = (port_counts / port_counts.sum()).values
                        port_entropy = entropy(probs)
                        result.loc[indices, f"{prefix}_dst_port_entropy"] = port_entropy
                
                # Bytes per connection
                if bytes_field in entity_data.columns:
                    total_bytes = entity_data[bytes_field].sum()
                    bytes_per_conn = total_bytes / conn_count if conn_count > 0 else 0
                    result.loc[indices, f"{prefix}_bytes_per_conn"] = bytes_per_conn
        
        self._validate_output(result[self.feature_names])
        
        logger.info(
            "network_features_extracted",
            records=len(result),
            features=len(self.feature_names),
        )
        
        return result
    
    def get_connection_graph(self) -> dict[str, set[str]]:
        """Get learned connection graph.
        
        Returns:
            Dict of source -> set of destinations
        """
        return dict(self._entity_conn_graph)
