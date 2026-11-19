import unittest
from types import SimpleNamespace
from app.ai_engine import select_specialists

class RoutingTests(unittest.TestCase):
    def test_finance_task_selects_accountant(self):
        staff = [
            SimpleNamespace(id=1, job_title="Accountant", name="AI Accountant", description="Financial reporting", skills_json=[], responsibilities_json=[]),
            SimpleNamespace(id=2, job_title="Marketing Officer", name="AI Marketing Officer", description="Campaigns", skills_json=[], responsibilities_json=[]),
            SimpleNamespace(id=3, job_title="Team Coordinator", name="AI Team Coordinator", description="Delegation", skills_json=[], responsibilities_json=[]),
        ]
        selected = select_specialists("Prepare a financial budget and revenue forecast", staff)
        self.assertTrue(any(e.job_title == "Accountant" for e in selected))
        self.assertFalse(any("Team Coordinator" in e.job_title for e in selected))

if __name__ == "__main__":
    unittest.main()
