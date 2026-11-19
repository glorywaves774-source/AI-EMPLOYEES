"""Pure dependency-graph helpers shared by orchestration services and tests."""


def would_create_cycle(edges, task_id, depends_on_task_id):
    """Return True when adding task_id -> depends_on_task_id creates a cycle.

    Edges are (task_id, prerequisite_task_id) pairs. A task may depend on a
    prerequisite only when that prerequisite does not already depend on it.
    """
    task_id = int(task_id)
    depends_on_task_id = int(depends_on_task_id)
    if task_id == depends_on_task_id:
        return True

    prerequisites = {}
    for child, parent in edges:
        prerequisites.setdefault(int(child), set()).add(int(parent))
    prerequisites.setdefault(task_id, set()).add(depends_on_task_id)

    pending = [depends_on_task_id]
    visited = set()
    while pending:
        current = pending.pop()
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(prerequisites.get(current, ()))
    return False


def ready_task_ids(candidate_ids, edges, completed_ids):
    """Return candidate IDs whose prerequisites are all completed."""
    completed = {int(value) for value in completed_ids}
    prerequisites = {}
    for child, parent in edges:
        prerequisites.setdefault(int(child), set()).add(int(parent))
    return [
        int(task_id)
        for task_id in candidate_ids
        if prerequisites.get(int(task_id), set()).issubset(completed)
    ]
