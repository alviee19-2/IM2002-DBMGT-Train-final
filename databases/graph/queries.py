"""
TransitFlow - Neo4j Graph Database Layer
========================================
This module handles route and network queries against Neo4j.

Graph schema used by skeleton/seed_neo4j.py:
  - Node label: Station
  - Station properties: station_id, name, lines, network
  - Relationship types: CONNECTS_TO, INTERCHANGES_WITH
  - Relationship properties: network, line, travel_time_min
"""

from __future__ import annotations

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing.

    Args:
        None

    Returns:
        Neo4j driver instance.
    """
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _normalise_network(network: str) -> str:
    """Convert public network names to values stored in Neo4j.

    Args:
        network: "metro", "rail", "national_rail", or "auto".

    Returns:
        Normalised network string.
    """
    return "national_rail" if network == "rail" else network


def _station_projection() -> str:
    """Return the reusable Cypher map projection for Station nodes.

    Args:
        None

    Returns:
        Cypher map expression for a station dictionary.
    """
    return """
    {
        station_id: station.station_id,
        name: station.name,
        network: station.network,
        lines: station.lines
    }
    """


def _legs_projection() -> str:
    """Return the reusable Cypher expression for route legs.

    Args:
        None

    Returns:
        Cypher CASE expression that builds a list of leg dictionaries.
    """
    return """
    CASE
        WHEN size(route_relationships) = 0 THEN []
        ELSE [
            index IN range(0, size(route_relationships) - 1) |
            {
                from_station_id: route_nodes[index].station_id,
                from_name: route_nodes[index].name,
                to_station_id: route_nodes[index + 1].station_id,
                to_name: route_nodes[index + 1].name,
                relationship_type: type(route_relationships[index]),
                network: route_relationships[index].network,
                line: route_relationships[index].line,
                travel_time_min: route_relationships[index].travel_time_min
            }
        ]
    END
    """


def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph.

    Args:
        None

    Returns:
        Number of nodes currently stored in Neo4j.
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]


def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.

    Args:
        origin_id: e.g. "MS01" or "NR01".
        destination_id: e.g. "MS09" or "NR05".
        network: "metro", "rail", "national_rail", or "auto".

    Returns:
        Dict with found, origin_id, destination_id, total_time_min, path, legs.
    """
    network_filter = _normalise_network(network)
    relationship_filter = (
        "CONNECTS_TO>|INTERCHANGES_WITH>"
        if network_filter == "auto"
        else "CONNECTS_TO>"
    )

    # APOC Dijkstra finds the weighted shortest path using travel_time_min.
    # Single-network queries avoid interchange edges by traversing CONNECTS_TO only.
    cypher = """
    MATCH (origin:Station {station_id: $origin_id})
    MATCH (destination:Station {station_id: $destination_id})
    WHERE $network = 'auto'
       OR (origin.network = $network AND destination.network = $network)
    CALL apoc.algo.dijkstra(
        origin,
        destination,
        $relationship_filter,
        'travel_time_min'
    )
    YIELD path, weight
    WITH nodes(path) AS route_nodes,
         relationships(path) AS route_relationships,
         weight AS total_time_min
    RETURN
        total_time_min,
        [station IN route_nodes | __STATION_PROJECTION__] AS path,
        __LEGS_PROJECTION__ AS legs
    """.replace("__STATION_PROJECTION__", _station_projection()).replace(
        "__LEGS_PROJECTION__",
        _legs_projection(),
    )

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                network=network_filter,
                relationship_filter=relationship_filter,
            )
            record = result.single()

    if record is None:
        return {
            "found": False,
            "origin_id": origin_id,
            "destination_id": destination_id,
            "total_time_min": None,
            "path": [],
            "legs": [],
        }

    return {
        "found": True,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "total_time_min": record["total_time_min"],
        "path": record["path"],
        "legs": record["legs"],
    }


# TASK 6 EXTENSION:
def query_fewest_transfers_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find a route that minimises the number of traversed station links.

    Args:
        origin_id: e.g. "MS01" or "NR01".
        destination_id: e.g. "MS09" or "NR05".
        network: "metro", "rail", "national_rail", or "auto".

    Returns:
        Dict with found, origin_id, destination_id, total_time_min, path, legs.
    """
    network_filter = _normalise_network(network)
    relationship_pattern = (
        "CONNECTS_TO|INTERCHANGES_WITH"
        if network_filter == "auto"
        else "CONNECTS_TO"
    )

    # TASK 6 EXTENSION:
    # This query intentionally uses Neo4j's built-in shortestPath() instead of
    # APOC Dijkstra. Dijkstra is the right tool when the product goal is the
    # lowest weighted travel_time_min, but this extension is optimising a
    # different passenger promise: fewer station-to-station hops and fewer route
    # decisions. That matters commercially because travellers with luggage,
    # families, tourists, and accessibility-sensitive passengers often prefer a
    # route that is simpler to follow even when it is a few minutes slower.
    # shortestPath() matches that business value directly because it minimises
    # the number of relationships in the path before we add up the travel time
    # only for display compatibility with the existing route UI.
    cypher = f"""
    MATCH (origin:Station {{station_id: $origin_id}})
    MATCH (destination:Station {{station_id: $destination_id}})
    WHERE $network = 'auto'
       OR (origin.network = $network AND destination.network = $network)
    MATCH path = shortestPath(
        (origin)-[:{relationship_pattern}*..30]-(destination)
    )
    WHERE $network = 'auto'
       OR all(rel IN relationships(path) WHERE rel.network = $network)
    WITH nodes(path) AS route_nodes,
         relationships(path) AS route_relationships,
         reduce(
             total = 0,
             rel IN relationships(path) |
             total + coalesce(rel.travel_time_min, 0)
         ) AS total_time_min
    RETURN
        total_time_min,
        [station IN route_nodes | __STATION_PROJECTION__] AS path,
        __LEGS_PROJECTION__ AS legs
    """.replace("__STATION_PROJECTION__", _station_projection()).replace(
        "__LEGS_PROJECTION__",
        _legs_projection(),
    )

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                network=network_filter,
            )
            record = result.single()

    if record is None:
        return {
            "found": False,
            "origin_id": origin_id,
            "destination_id": destination_id,
            "total_time_min": None,
            "path": [],
            "legs": [],
        }

    return {
        "found": True,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "total_time_min": record["total_time_min"],
        "path": record["path"],
        "legs": record["legs"],
    }


def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find an approximate cheapest path between two stations.

    Args:
        origin_id: e.g. "NR01".
        destination_id: e.g. "NR05".
        network: "metro", "rail", "national_rail", or "auto".
        fare_class: "standard" or "first".

    Returns:
        Dict with found, total_fare_usd, stations, and legs.
    """
    # The current graph seed has travel time but no fare weights. We return a
    # stable approximation so the agent can respond without raising an error.
    route = query_shortest_route(origin_id, destination_id, network)
    if not route["found"]:
        return {
            "found": False,
            "origin_id": origin_id,
            "destination_id": destination_id,
            "total_fare_usd": None,
            "stations": [],
            "legs": [],
            "note": "No route found.",
        }

    per_leg_estimate = 1.0 if fare_class == "standard" else 1.5
    total_fare_usd = round(len(route["legs"]) * per_leg_estimate, 2)

    return {
        "found": True,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "fare_class": fare_class,
        "total_fare_usd": total_fare_usd,
        "stations": route["path"],
        "legs": route["legs"],
        "note": "Estimated graph fare because graph edges do not store fare properties.",
    }


def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """
    Find alternative paths that avoid a specific intermediate station.

    Args:
        origin_id: e.g. "NR01".
        destination_id: e.g. "NR05".
        avoid_station_id: Station ID to avoid.
        network: "metro", "rail", "national_rail", or "auto".
        max_routes: Maximum number of route alternatives.

    Returns:
        List of routes. Each route is a list of leg dictionaries.
    """
    network_filter = _normalise_network(network)

    # The mock graph is small, so bounded simple-path enumeration is acceptable
    # for alternative routes. apoc.coll.toSet removes repeated-node loops.
    cypher = """
    MATCH (origin:Station {station_id: $origin_id})
    MATCH (destination:Station {station_id: $destination_id})
    MATCH path = (origin)-[:CONNECTS_TO|INTERCHANGES_WITH*1..12]->(destination)
    WHERE none(station IN nodes(path)[1..-1] WHERE station.station_id = $avoid_station_id)
      AND ($network = 'auto'
           OR all(rel IN relationships(path) WHERE rel.network = $network))
      AND size(nodes(path)) = size(apoc.coll.toSet(nodes(path)))
    WITH
        path,
        reduce(
            total = 0,
            rel IN relationships(path) |
            total + coalesce(rel.travel_time_min, 0)
        ) AS total_time_min
    ORDER BY total_time_min ASC, length(path) ASC
    LIMIT $max_routes
    WITH nodes(path) AS route_nodes,
         relationships(path) AS route_relationships
    RETURN __LEGS_PROJECTION__ AS legs
    """.replace("__LEGS_PROJECTION__", _legs_projection())

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
                network=network_filter,
                max_routes=max_routes,
            )
            return [record["legs"] for record in result]


def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a cross-network path using metro-national rail interchange links.

    Args:
        origin_id: e.g. "MS03" or "NR05".
        destination_id: e.g. "NR05" or "MS09".

    Returns:
        Dict with found, stations, interchange_points, total_time_min, and legs.
    """
    route = query_shortest_route(origin_id, destination_id, network="auto")
    if not route["found"]:
        return {
            "found": False,
            "origin_id": origin_id,
            "destination_id": destination_id,
            "stations": [],
            "interchange_points": [],
            "total_time_min": None,
            "legs": [],
        }

    interchange_points = [
        {
            "from_station_id": leg["from_station_id"],
            "from_name": leg["from_name"],
            "to_station_id": leg["to_station_id"],
            "to_name": leg["to_name"],
            "travel_time_min": leg["travel_time_min"],
        }
        for leg in route["legs"]
        if leg["relationship_type"] == "INTERCHANGES_WITH"
    ]

    return {
        "found": True,
        "origin_id": origin_id,
        "destination_id": destination_id,
        "stations": route["path"],
        "interchange_points": interchange_points,
        "total_time_min": route["total_time_min"],
        "legs": route["legs"],
    }


def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Find all stations within N hops of a delayed or disrupted station.

    Args:
        delayed_station_id: e.g. "NR03" or "MS01".
        hops: How many connections out to search.

    Returns:
        List of dicts: station_id, name, network, hops_away, lines_affected.
    """
    if hops <= 0:
        return []

    # Cypher variable-length relationship bounds cannot be parameterised, so
    # we clamp the integer in Python before inserting it into the query string.
    safe_hops = int(hops)
    cypher = f"""
    MATCH (delayed:Station {{station_id: $delayed_station_id}})
    MATCH path = shortestPath(
        (delayed)-[:CONNECTS_TO|INTERCHANGES_WITH*1..{safe_hops}]-(affected:Station)
    )
    WHERE delayed <> affected
    WITH affected,
         length(path) AS hops_away,
         relationships(path) AS path_relationships
    RETURN
        affected.station_id AS station_id,
        affected.name AS name,
        affected.network AS network,
        hops_away,
        apoc.coll.toSet([rel IN path_relationships | rel.line]) AS lines_affected
    ORDER BY hops_away ASC, station_id ASC
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, delayed_station_id=delayed_station_id)
            return [dict(record) for record in result]


def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct outgoing connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01".

    Returns:
        List of direct connection dictionaries.
    """
    cypher = """
    MATCH (station:Station {station_id: $station_id})-[rel]->(connected:Station)
    RETURN
        connected.station_id AS station_id,
        connected.name AS name,
        connected.network AS network,
        connected.lines AS lines,
        type(rel) AS relationship_type,
        rel.network AS relationship_network,
        rel.line AS line,
        rel.travel_time_min AS travel_time_min
    ORDER BY relationship_type ASC, station_id ASC
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, station_id=station_id)
            return [dict(record) for record in result]
