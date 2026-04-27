"""Distribution helpers — locate source assets that ship with the CLI
and expose them to commands that need to copy files to the user system
(extension installer, desktop-icon installer, …).
"""

from streamseeker.distribution.extension_sync import (
    SyncResult,
    installed_extension_version,
    link_extension,
    sync_extension,
)
from streamseeker.distribution.sources import (
    source_extension_dir,
    source_master_icon,
)

__all__ = [
    "SyncResult",
    "installed_extension_version",
    "link_extension",
    "source_extension_dir",
    "source_master_icon",
    "sync_extension",
]
