# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

import multiprocessing, os
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = max(2, multiprocessing.cpu_count() * 2 + 1)
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"
