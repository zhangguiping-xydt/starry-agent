# Event Flow

Generate when source material names producers, topics, subscribers, projections, or async events. Prefer Mermaid or Graphviz. Use strong visual enhancement after the semantic gate passes and distinguish commands from events. Event-flow is not data-flow: events describe facts that happened and subscribers reacting to them, not payload transformation pipelines. Projection/read-model updates must be explicitly labeled with `kind: projection` edges so they are not confused with commands, events, or data movement.
