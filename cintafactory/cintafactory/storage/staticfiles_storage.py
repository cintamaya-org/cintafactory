from whitenoise.storage import CompressedManifestStaticFilesStorage


class WhiteNoiseStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Whitenoise storage with graceful fallback when collectstatic is lagging.

    Setting manifest_strict to False prevents missing-entry errors and lets the
    app serve files from their original locations until collectstatic runs.
    """

    manifest_strict = False
