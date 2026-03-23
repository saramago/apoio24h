import time
import unittest

from core.session_memory import SessionMemoryStore


class SessionMemoryTests(unittest.TestCase):
    def test_short_follow_up_is_merged_with_previous_query(self) -> None:
        store = SessionMemoryStore(ttl_seconds=1800)
        session_id = store.ensure_session_id("sess-1")
        store.remember(session_id, "preciso de um medicamento", "practical_health")

        resolved_query, context = store.resolve_query(session_id, "em lisboa")

        self.assertTrue(context["continued"])
        self.assertEqual(resolved_query, "preciso de um medicamento em lisboa")

    def test_expired_session_is_not_reused(self) -> None:
        store = SessionMemoryStore(ttl_seconds=0)
        session_id = store.ensure_session_id("sess-2")
        store.remember(session_id, "hospital mais proximo", "practical_health")
        time.sleep(0.01)

        resolved_query, context = store.resolve_query(session_id, "em coimbra")

        self.assertFalse(context["continued"])
        self.assertEqual(resolved_query, "em coimbra")


if __name__ == "__main__":
    unittest.main()
