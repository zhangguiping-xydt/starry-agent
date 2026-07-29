# Sequence

Generate when source material provides ordered calls, messages, async events, or agent orchestration. Prefer PlantUML sequence for complex interactions and Mermaid for simple interactions. Use light visual enhancement after the semantic gate passes.

Use `sequence-lifelines`. Keep participant order stable and messages strictly top-to-bottom. Classify requests as `kind: call`, replies as `kind: return`, and async sends as `kind: async`. Use `alt|opt|loop|ref` fragments only when those control semantics are explicit in the source. When the participant/message soft budget is exceeded, partition every message into contiguous `phase` fragments; split the scenario when a phase still exceeds its message budget.
