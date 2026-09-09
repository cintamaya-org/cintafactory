# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

MAX_REMOTE_SELECT_RESULTS = 30
MAX_REMOTE_SELECT_QUERY_LENGTH = 100


def normalize_remote_select_query(value) -> str:
    return str(value or "").strip()[:MAX_REMOTE_SELECT_QUERY_LENGTH]
