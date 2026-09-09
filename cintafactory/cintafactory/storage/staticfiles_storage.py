# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from whitenoise.storage import CompressedManifestStaticFilesStorage


class WhiteNoiseStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Whitenoise storage with graceful fallback when collectstatic is lagging.

    Setting manifest_strict to False prevents missing-entry errors and lets the
    app serve files from their original locations until collectstatic runs.
    """

    manifest_strict = False
