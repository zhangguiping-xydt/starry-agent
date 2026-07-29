from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any


def _version(lock: Mapping[str, Any]) -> int:
    value = lock.get("contract_version", lock.get("version", 2))
    return value if isinstance(value, int) and not isinstance(value, bool) else 2


def _items(lock: Mapping[str, Any], section: str) -> list[Mapping[str, Any]]:
    values = lock.get(section, [])
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, Mapping)]


def _ids(values: list[Mapping[str, Any]]) -> set[str]:
    return {
        item_id
        for value in values
        if isinstance((item_id := value.get("id")), str) and item_id
    }


def _edge_role_ids(plan: Mapping[str, Any], role: str) -> set[str]:
    edge_roles = plan.get("edge_roles", {})
    if not isinstance(edge_roles, Mapping):
        return set()
    values = edge_roles.get(role, [])
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str) and value}


def _topology(relations: list[Mapping[str, Any]]) -> tuple[Counter[str], Counter[str]]:
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    for relation in relations:
        source = relation.get("from")
        target = relation.get("to")
        if isinstance(source, str) and source:
            outgoing[source] += 1
        if isinstance(target, str) and target:
            incoming[target] += 1
    return incoming, outgoing


def _validate_flow(
    lock: Mapping[str, Any],
    plan: Mapping[str, Any],
    errors: list[str],
    metrics: dict[str, Any],
) -> None:
    nodes = _items(lock, "nodes")
    edges = _items(lock, "edges")
    incoming, outgoing = _topology(edges)
    roles = {
        str(node.get("id")): node.get("notation_role")
        for node in nodes
        if isinstance(node.get("id"), str)
    }
    role_counts = Counter(role for role in roles.values() if isinstance(role, str))
    metrics["role_counts"] = dict(sorted(role_counts.items()))

    for node_id, role in roles.items():
        if role == "decision" and outgoing[node_id] < 2:
            errors.append(
                f"FLOW_DECISION_BRANCH_COUNT: decision {node_id} must have at least two outgoing branches"
            )
        elif role == "merge" and incoming[node_id] < 2:
            errors.append(
                f"FLOW_MERGE_INPUT_COUNT: merge {node_id} must have at least two incoming branches"
            )
        elif role == "start" and incoming[node_id] != 0:
            errors.append(f"FLOW_START_HAS_INCOMING: start {node_id} must not have incoming edges")
        elif role == "end" and outgoing[node_id] != 0:
            errors.append(f"FLOW_END_HAS_OUTGOING: end {node_id} must not have outgoing edges")

    data_objects = {node_id for node_id, role in roles.items() if role == "data-object"}
    primary_items = plan.get("primary_items", [])
    if isinstance(primary_items, list):
        misplaced = sorted(data_objects & {str(value) for value in primary_items})
        if misplaced:
            errors.append(
                "FLOW_DATA_OBJECT_ON_PRIMARY_PATH: data objects must be sidecars, not process steps: "
                f"{misplaced}"
            )

    control_edges = _edge_role_ids(plan, "control")
    for edge in edges:
        edge_id = edge.get("id")
        source = edge.get("from")
        target = edge.get("to")
        if source not in data_objects and target not in data_objects:
            continue
        if edge.get("kind") != "data":
            errors.append(
                f"FLOW_DATA_OBJECT_EDGE_KIND: edge {edge_id} touching a data object must use kind 'data'"
            )
        if isinstance(edge_id, str) and edge_id not in control_edges:
            errors.append(
                f"FLOW_DATA_OBJECT_EDGE_ROLE: edge {edge_id} touching a data object must use the control edge rail"
            )


def _validate_state(
    lock: Mapping[str, Any],
    errors: list[str],
    metrics: dict[str, Any],
) -> None:
    states = _items(lock, "states")
    transitions = _items(lock, "transitions")
    incoming, outgoing = _topology(transitions)
    by_role: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for state in states:
        role = state.get("notation_role")
        if isinstance(role, str):
            by_role[role].append(state)

    initial_states = by_role["initial"]
    final_states = by_role["final"]
    metrics["initial_count"] = len(initial_states)
    metrics["final_count"] = len(final_states)
    if len(initial_states) != 1:
        errors.append(
            f"STATE_INITIAL_COUNT: state machine must define exactly one initial pseudo-state, got {len(initial_states)}"
        )
    if not final_states:
        errors.append("STATE_FINAL_MISSING: state machine must define at least one final pseudo-state")

    for state in states:
        state_id = state.get("id")
        role = state.get("notation_role")
        label = state.get("label")
        if not isinstance(state_id, str):
            continue
        if role in {"initial", "final"} and isinstance(label, str) and label.strip():
            errors.append(
                f"STATE_PSEUDOSTATE_LABEL: {role} pseudo-state {state_id} must be unlabeled; put the event or result on its transition"
            )
        if role == "state" and (not isinstance(label, str) or not label.strip()):
            errors.append(f"STATE_LABEL_MISSING: state {state_id} must have a label")
        if role == "initial":
            if incoming[state_id] != 0:
                errors.append(
                    f"STATE_INITIAL_HAS_INCOMING: initial pseudo-state {state_id} must not have incoming transitions"
                )
            if outgoing[state_id] != 1:
                errors.append(
                    f"STATE_INITIAL_OUTGOING_COUNT: initial pseudo-state {state_id} must have exactly one outgoing transition"
                )
        if role == "final":
            if outgoing[state_id] != 0:
                errors.append(
                    f"STATE_FINAL_HAS_OUTGOING: final pseudo-state {state_id} must not have outgoing transitions"
                )
            if incoming[state_id] < 1:
                errors.append(
                    f"STATE_FINAL_HAS_NO_INCOMING: final pseudo-state {state_id} must have an incoming transition"
                )


def _validate_sequence(
    lock: Mapping[str, Any],
    layout: Mapping[str, Any],
    errors: list[str],
    metrics: dict[str, Any],
) -> None:
    participants = _items(lock, "participants")
    messages = _items(lock, "messages")
    fragments = _items(lock, "fragments")
    orders = [message.get("order") for message in messages]
    integer_orders = [order for order in orders if isinstance(order, int) and not isinstance(order, bool)]
    if len(integer_orders) == len(messages) and sorted(integer_orders) != list(
        range(1, len(messages) + 1)
    ):
        errors.append(
            "SEQUENCE_ORDER_GAP: message order values must be contiguous from 1 through the message count"
        )

    readability = layout.get("readability_limits", {})
    if not isinstance(readability, Mapping):
        readability = {}
    participant_limit = readability.get("max_participants_without_fragments", 7)
    message_limit = readability.get("max_messages_without_fragments", 18)
    phase_limit = readability.get("max_messages_per_phase", 12)
    metrics.update(
        {
            "participants": len(participants),
            "messages": len(messages),
            "fragments": len(fragments),
            "participant_soft_limit": participant_limit,
            "message_soft_limit": message_limit,
        }
    )
    high_density = (
        isinstance(participant_limit, int)
        and len(participants) > participant_limit
        or isinstance(message_limit, int)
        and len(messages) > message_limit
    )
    if not high_density:
        return

    phase_fragments = [
        fragment for fragment in fragments if fragment.get("notation_role") == "phase"
    ]
    if not phase_fragments:
        errors.append(
            "SEQUENCE_DENSITY_UNMITIGATED: a high-density sequence must declare phase fragments or be split into companion views"
        )
        return

    message_ids = _ids(messages)
    order_by_id = {
        str(message.get("id")): message.get("order")
        for message in messages
        if isinstance(message.get("id"), str)
    }
    memberships: list[str] = []
    for fragment in phase_fragments:
        fragment_id = fragment.get("id")
        members = fragment.get("members", [])
        if not isinstance(members, list):
            continue
        valid_members = [member for member in members if isinstance(member, str) and member in message_ids]
        memberships.extend(valid_members)
        member_orders = sorted(
            order_by_id[member]
            for member in valid_members
            if isinstance(order_by_id.get(member), int)
        )
        if member_orders and member_orders != list(range(member_orders[0], member_orders[-1] + 1)):
            errors.append(
                f"SEQUENCE_PHASE_NOT_CONTIGUOUS: phase {fragment_id} must contain a contiguous message range"
            )
        if isinstance(phase_limit, int) and len(valid_members) > phase_limit:
            errors.append(
                f"SEQUENCE_PHASE_TOO_DENSE: phase {fragment_id} contains {len(valid_members)} messages, limit is {phase_limit}"
            )

    counts = Counter(memberships)
    duplicates = sorted(item_id for item_id, count in counts.items() if count > 1)
    missing = sorted(message_ids - set(counts))
    if duplicates:
        errors.append(
            f"SEQUENCE_PHASE_OVERLAP: phase fragments must not duplicate messages: {duplicates}"
        )
    if missing:
        errors.append(
            f"SEQUENCE_PHASE_COVERAGE: high-density sequence phases must cover every message: {missing}"
        )


def _validate_loop(
    lock: Mapping[str, Any],
    plan: Mapping[str, Any],
    errors: list[str],
    metrics: dict[str, Any],
) -> None:
    if plan.get("pattern") != "loop-mechanism":
        return
    primary_items = plan.get("primary_items", [])
    if not isinstance(primary_items, list):
        return
    order = {item_id: index for index, item_id in enumerate(primary_items) if isinstance(item_id, str)}
    secondary_ids = _edge_role_ids(plan, "secondary")
    edges = _items(lock, "edges")
    backward_feedback = []
    for edge in edges:
        edge_id = edge.get("id")
        source = edge.get("from")
        target = edge.get("to")
        if edge_id not in secondary_ids or source not in order or target not in order:
            continue
        if order[str(source)] > order[str(target)]:
            backward_feedback.append(str(edge_id))
    metrics["backward_feedback_edges"] = backward_feedback
    if not backward_feedback:
        errors.append(
            "LOOP_FEEDBACK_MISSING: loop-mechanism must include an explicit backward feedback relation"
        )


def validate_semantic_quality(
    lock: Mapping[str, Any],
    *,
    layout: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    version = _version(lock)
    if version < 4:
        return {"checked": False, "contract_version": version}, errors, warnings

    plan = lock.get("layout_plan", {})
    if not isinstance(plan, Mapping):
        plan = {}
    layout = layout if isinstance(layout, Mapping) else {}
    diagram_type = lock.get("type")
    metrics: dict[str, Any] = {}
    if diagram_type == "flow":
        _validate_flow(lock, plan, errors, metrics)
    elif diagram_type == "state":
        _validate_state(lock, errors, metrics)
    elif diagram_type == "sequence":
        _validate_sequence(lock, layout, errors, metrics)
    elif diagram_type == "concept":
        _validate_loop(lock, plan, errors, metrics)

    return {
        "checked": True,
        "contract_version": version,
        "diagram_type": diagram_type,
        "metrics": metrics,
        "rule_errors": len(errors),
    }, errors, warnings
