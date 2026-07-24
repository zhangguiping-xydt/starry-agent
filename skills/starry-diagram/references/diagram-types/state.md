# State

Generate when source material provides lifecycle states and transitions. Prefer Mermaid stateDiagram and light visual enhancement.

Choose `state-transition` for lifecycle topology and `branching-flow` only when the reading task is procedural rather than state-centric. Put the primary lifecycle on one axis, keep exceptions outside it, and route self-transitions or loopbacks locally. Split orthogonal state regions when the transition graph exceeds the catalog budget.
