# Data Flow

Generate when source material describes collection, transformation, storage, sync, or consumption. Prefer Graphviz or Mermaid. Use strong visual enhancement after the semantic gate passes. Data-flow is not event-flow: data edges describe movement, transformation, persistence, or consumption of data, not facts emitted after state changes. If the source includes commands, events, or projection/read-model updates, either mark those edges explicitly as `kind: command`, `kind: event`, or `kind: projection` in the lock, or move that content to a sequence/event-flow diagram where the semantics are primary.

Choose `data-pipeline` for ordered processing, `data-hub` for producer/consumer exchange, and `control-sidecar-flow` only when policy or audit state is a first-class concern. Keep data, command, event, and projection edges in separate visual channels. Split batch and streaming paths when they cannot share a clean primary axis.
