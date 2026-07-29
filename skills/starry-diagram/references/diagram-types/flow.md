# Flow

Generate when source material provides ordered steps, decisions, approvals, or status transitions. Prefer Mermaid flowchart and medium or strong visual enhancement.

Choose `linear-flow` for three to eight ordered steps, `branching-flow` for decisions and exception convergence, and `control-sidecar-flow` when state, policy, evidence, or guardrails form a separate control plane. Keep the happy path on one axis. Route exceptions and loopbacks on outer rails. Split overview, process detail, and control-plane detail when the selected pattern budget is exceeded.

Classify schema declarations, payloads, files, field capacities, and persistence contracts as `data-object`, not `process`. Put them in a side region and connect them with `kind: data` on the control rail. A `decision` must branch and a `merge` must converge; decorative diamonds are invalid.
