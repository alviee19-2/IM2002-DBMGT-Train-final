# Task 6 Extension

## Feature

Fewest-transfers route option for TransitFlow graph routing.

## Modified Files

- `databases/graph/queries.py`
  - `query_fewest_transfers_route(origin_id, destination_id, network="auto")`
  - Uses Neo4j `shortestPath()` to minimise station-link count, then reports the same route shape as the weighted route functions.
- `skeleton/agent.py`
  - Imports `query_fewest_transfers_route`.
  - Extends `find_route` so `optimise_by="transfers"` calls the extension.

## Demo Query

Ask the Gradio UI:

```text
Find the route from MS01 to MS09 with the fewest transfers.
```

The agent should call `find_route(..., optimise_by="transfers")` and return a station-by-station route.
