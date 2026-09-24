# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from .seaweedfs_storage import SeaweedFSStorage
from .staticfiles_storage import WhiteNoiseStaticFilesStorage

__all__ = ["SeaweedFSStorage", "WhiteNoiseStaticFilesStorage"]
