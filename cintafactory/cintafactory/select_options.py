MAX_REMOTE_SELECT_RESULTS = 30
MAX_REMOTE_SELECT_QUERY_LENGTH = 100


def normalize_remote_select_query(value) -> str:
    return str(value or "").strip()[:MAX_REMOTE_SELECT_QUERY_LENGTH]
