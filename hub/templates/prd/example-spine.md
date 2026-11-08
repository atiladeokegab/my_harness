# Linkly spine contract (example)

Every endpoint returns JSON. Errors are `{"error": "<code>", "detail": "<text>"}` with an HTTP status of 4xx
or 5xx. Short codes are 6 characters from `[a-z0-9]`. Times are ISO-8601 UTC. One SQLite file, `linkly.db`.
