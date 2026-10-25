"""Route policies of the exam template routes (PHASE_7B_DESIGN 9.1). S1 creates the dict; S2 fills it in its own
delimited block (policy names: `ids.POLICY_*`, listed in `route_inventory.POLICY_NAMES`)."""
EXAM_TEMPLATE_POLICIES: dict[tuple[str, str], str] = {}
