"""External data source clients and provenance integration modules."""

from ingestion.sources.acled_client import (
    ACLEDClient,
    calculate_acled_severity,
    map_acled_record_to_protest,
    record_acled_provenance,
)
from ingestion.sources.datagovin_client import DataGovInClient, sync_datagovin_provenance
from ingestion.sources.eia_client import EIAClient, sync_eia_observations
from ingestion.sources.pib_client import PIBClient, classify_pib_action_type, sync_pib_government_actions
from ingestion.sources.portwatch_client import (
    PortWatchClient,
    derive_portwatch_status,
    sanitize_text,
    sync_portwatch_chokepoints,
)
from ingestion.sources.world_bank_client import (
    WorldBankPinkSheetClient,
    sync_world_bank_observations,
)

__all__ = [
    "ACLEDClient",
    "calculate_acled_severity",
    "map_acled_record_to_protest",
    "record_acled_provenance",
    "DataGovInClient",
    "sync_datagovin_provenance",
    "EIAClient",
    "sync_eia_observations",
    "PIBClient",
    "classify_pib_action_type",
    "sync_pib_government_actions",
    "PortWatchClient",
    "derive_portwatch_status",
    "sanitize_text",
    "sync_portwatch_chokepoints",
    "WorldBankPinkSheetClient",
    "sync_world_bank_observations",
]
