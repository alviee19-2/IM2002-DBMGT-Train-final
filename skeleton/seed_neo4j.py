"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from databases.graph.queries import _driver

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def _create_constraints(session):
    """Create Neo4j constraints used by the graph seed.

    Args:
        session: Active Neo4j session.

    Returns:
        None
    """
    session.run(
        """
        CREATE CONSTRAINT station_id_unique IF NOT EXISTS
        FOR (s:Station) REQUIRE s.station_id IS UNIQUE
        """
    )


def _create_station_nodes(session, stations, network):
    """Create transit station nodes for one network.

    Args:
        session: Active Neo4j session.
        stations: Station dictionaries loaded from JSON.
        network: Network identifier stored on each node.

    Returns:
        None
    """
    for station in stations:
        session.run(
            """
            MERGE (s:Station {station_id: $station_id})
            SET s.name = $name,
                s.lines = $lines,
                s.network = $network
            """,
            station_id=station["station_id"],
            name=station["name"],
            lines=station.get("lines", []),
            network=network,
        )


def _create_network_links(session, stations, network):
    """Create directed links between adjacent stations."""
    for station in stations:
        for adjacent in station.get("adjacent_stations", []):
            target_id = adjacent.get("to_station_id") or adjacent.get("station_id")
            
            if not target_id:
                continue

            session.run(
                """
                MATCH (from:Station {station_id: $from_id})
                MATCH (to:Station {station_id: $to_id})
                MERGE (from)-[r:CONNECTS_TO {
                    network: $network,
                    line: $line
                }]->(to)
                SET r.travel_time_min = $travel_time_min
                """,
                from_id=station["station_id"],
                to_id=target_id,
                network=network,
                line=adjacent["line"],
                travel_time_min=adjacent["travel_time_min"],
            )


def _create_interchange_links(session, metro_stations):
    """Create directed interchange links between metro and rail stations.

    Args:
        session: Active Neo4j session.
        metro_stations: Metro station dictionaries loaded from JSON.

    Returns:
        None
    """
    for station in metro_stations:
        rail_station_id = station.get("interchange_national_rail_station_id")
        if not rail_station_id:
            continue

        session.run(
            """
            MATCH (metro:Station {station_id: $metro_station_id, network: 'metro'})
            MATCH (rail:Station {
                station_id: $rail_station_id,
                network: 'national_rail'
            })
            MERGE (metro)-[to_rail:INTERCHANGES_WITH]->(rail)
            SET to_rail.network = 'interchange',
                to_rail.line = 'interchange',
                to_rail.travel_time_min = $travel_time_min
            MERGE (rail)-[to_metro:INTERCHANGES_WITH]->(metro)
            SET to_metro.network = 'interchange',
                to_metro.line = 'interchange',
                to_metro.travel_time_min = $travel_time_min
            """,
            metro_station_id=station["station_id"],
            rail_station_id=rail_station_id,
            travel_time_min=5,
        )


def seed():
    """Seed Neo4j with metro and national rail graph data.

    Args:
        None

    Returns:
        None
    """
    metro_stations = _load("metro_stations.json")
    rail_stations = _load("national_rail_stations.json")

    with _driver() as driver:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("  Cleared existing graph data")

            _create_constraints(session)
            _create_station_nodes(session, metro_stations, "metro")
            _create_station_nodes(
                session,
                rail_stations,
                "national_rail",
            )
            print(
                f"  Created {len(metro_stations)} metro stations and "
                f"{len(rail_stations)} national rail stations"
            )

            _create_network_links(session, metro_stations, "metro")
            _create_network_links(session, rail_stations, "national_rail")
            _create_interchange_links(session, metro_stations)
            print("  Created network and interchange relationships")

    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
