"""Strict validation for coordinator-generated team plans."""

MAX_STEPS = 8
MAX_STEP_INSTRUCTIONS = 5000


def validate_team_plan(raw_plan, active_specialists):
    """Validate a JSON plan against active tenant employee IDs and DAG rules.

    Returns normalized steps with stable keys. Never accepts free-form employee
    names as authority to select an employee.
    """
    if not isinstance(raw_plan, dict) or not isinstance(raw_plan.get("steps"), list):
        raise ValueError("Coordinator plan must contain a steps list.")
    if not 1 <= len(raw_plan["steps"]) <= MAX_STEPS:
        raise ValueError(f"A team plan must contain between 1 and {MAX_STEPS} steps.")
    allowed = {int(employee.id): employee for employee in active_specialists}
    steps = []
    seen = set()
    for index, item in enumerate(raw_plan["steps"]):
        if not isinstance(item, dict):
            raise ValueError("Every team step must be an object.")
        try:
            employee_id = int(item.get("employee_id"))
        except (TypeError, ValueError):
            raise ValueError("Each step must identify an active specialist employee ID.")
        employee = allowed.get(employee_id)
        if employee is None:
            raise ValueError("The coordinator selected an employee who is not active in this workspace.")
        title = str(item.get("title", "")).strip()[:180]
        instructions = str(item.get("instructions", "")).strip()
        if not title or not instructions or len(instructions) > MAX_STEP_INSTRUCTIONS:
            raise ValueError("Each step needs a title and instructions of at most 5,000 characters.")
        key = f"step_{index + 1}"
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list) or any(not isinstance(x, int) for x in dependencies):
            raise ValueError("Step dependencies must be a list of step numbers.")
        if any(x < 1 or x > len(raw_plan["steps"]) or x == index + 1 for x in dependencies):
            raise ValueError("A step contains an invalid dependency reference.")
        steps.append({"step_key": key, "employee_id": employee_id,
                      "employee_name": employee.name, "title": title,
                      "instructions": instructions,
                      "depends_on": [f"step_{x}" for x in dependencies]})
        seen.add(key)
    # A small DFS catches cycles before any queue work is dispatched.
    by_key = {step["step_key"]: step for step in steps}
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError("The coordinator plan contains a dependency cycle.")
        if key in visited:
            return
        visiting.add(key)
        for dependency in by_key[key]["depends_on"]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for key in by_key:
        visit(key)
    return steps


def ready_steps(steps):
    """Return queued step keys whose dependencies have all completed."""
    completed = {step.step_key for step in steps if step.status == "completed"}
    return [step.step_key for step in steps if step.status == "queued"
            and set(step.depends_on_json or []).issubset(completed)]
