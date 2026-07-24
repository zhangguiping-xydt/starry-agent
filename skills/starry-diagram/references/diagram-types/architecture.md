# Architecture

Generate when source material names modules, services, stores, runtime boundaries, or external systems. Prefer Graphviz and strong visual enhancement.

Choose `layered-system` when dependency direction or runtime tiers are primary, `bounded-context-map` when ownership boundaries are primary, and `dependency-map` for directed component dependencies. Allocate boundaries before nodes. Keep one dominant dependency direction and route cross-boundary links through ports or boundary gaps. Split runtime, deployment, and event concerns when one view exceeds the selected pattern budget.
