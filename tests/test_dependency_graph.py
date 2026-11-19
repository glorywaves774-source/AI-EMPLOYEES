import importlib.util
from pathlib import Path

_module_path = Path(__file__).parents[1] / "app" / "workforce" / "dependency_graph.py"
_spec = importlib.util.spec_from_file_location("dependency_graph_under_test", _module_path)
_graph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_graph)
ready_task_ids = _graph.ready_task_ids
would_create_cycle = _graph.would_create_cycle


def test_rejects_direct_self_dependency():
    assert would_create_cycle([], 10, 10)


def test_rejects_transitive_cycle():
    edges = [(2, 1), (3, 2)]
    assert would_create_cycle(edges, 1, 3)


def test_allows_acyclic_dependency():
    edges = [(3, 2), (2, 1)]
    assert not would_create_cycle(edges, 4, 3)


def test_ready_tasks_require_all_prerequisites_completed():
    edges = [(3, 1), (3, 2), (4, 2)]
    assert ready_task_ids([1, 2, 3, 4], edges, {1, 2}) == [1, 2, 3, 4]
    assert ready_task_ids([3, 4], edges, {1}) == []
    assert ready_task_ids([3, 4], edges, {1, 2}) == [3, 4]
