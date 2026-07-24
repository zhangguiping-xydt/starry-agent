# ER

Generate when source material provides entities, fields, keys, and cardinality. Prefer Mermaid ER or PlantUML entity. Missing facts such as fields, keys, or cardinalities must produce needs_clarification.

Use `er-domain-grid`. Cluster entities by bounded context or aggregate, keep cardinalities adjacent to endpoints, and route relationships orthogonally. Split schemas that exceed the catalog budget by domain and add a smaller overview relationship map.
