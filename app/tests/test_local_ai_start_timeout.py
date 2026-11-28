"""Deterministic local-AI startup timeout tests; no model file needed."""
import threading
import unittest
from unittest.mock import patch

import llm_local


class FakeProcess:
    def poll(self):
        return 0


class StartupTimeoutTests(unittest.TestCase):
    def make_local(self):
        local = llm_local.Local.__new__(llm_local.Local)
        local.lock = threading.RLock()
        local.state = "loading"
        local.pct = 0
        local.message = ""
        local.path = "fake-model"
        local.fit = {"fits": True}
        local.proc = FakeProcess()
        local.t_progress = 0.0
        local.last_used = 0
        local.enabled = lambda: True
        def stop(why=""):
            local.state = "stopped"
        local.stop = stop
        return local

    def test_stalled_load_times_out(self):
        local = self.make_local()
        clock = [0.0]
        with patch.object(llm_local.time, "time", side_effect=lambda: clock[0]), \
             patch.object(llm_local.time, "sleep", side_effect=lambda _: clock.__setitem__(0, clock[0] + 100)):
            self.assertIn("too long", local.ensure_running())
        self.assertEqual(local.state, "stopped")

    def test_progress_extends_wait_past_ten_minutes(self):
        local = self.make_local()
        clock = [0.0]
        steps = [0]
        def sleep(_):
            clock[0] += 200
            steps[0] += 1
            if steps[0] <= 4:
                local.t_progress = clock[0]
                local.pct += 10
            if steps[0] == 5:
                local.state = "ready"
        with patch.object(llm_local.time, "time", side_effect=lambda: clock[0]), \
             patch.object(llm_local.time, "sleep", side_effect=sleep):
            self.assertIsNone(local.ensure_running())
        self.assertGreater(clock[0], 600)

    def test_progress_at_timeout_boundary_prevents_stale_stop(self):
        local = self.make_local()
        clock = [0.0]
        steps = [0]
        def sleep(_):
            steps[0] += 1
            if steps[0] == 1:
                clock[0] = 600.0
                # Simulates the reader's new progress before the waiter locks.
                with local.lock:
                    local.pct = 10
                    local.t_progress = clock[0]
            elif steps[0] == 2:
                local.state = "ready"
            else:
                raise AssertionError("unexpected extra wait")
        with patch.object(llm_local.time, "time", side_effect=lambda: clock[0]), \
             patch.object(llm_local.time, "sleep", side_effect=sleep):
            self.assertIsNone(local.ensure_running())
        self.assertEqual(local.state, "ready")

    def test_status_lock_is_available_during_slow_shutdown(self):
        local = self.make_local()
        clock = [0.0]
        shutdown_checked = []
        def finish_stop(proc, why):
            # This callback represents a child that has not finished shutting
            # down yet. The status lock must not be owned by the waiter.
            acquired = []
            def read_status():
                with local.lock:
                    acquired.append((local.state, local.proc))
            thread = threading.Thread(target=read_status)
            thread.start()
            thread.join(timeout=1)
            shutdown_checked.append((not thread.is_alive(), acquired))
            if thread.is_alive():
                thread.join(timeout=1)
        local._finish_stop = finish_stop
        with patch.object(llm_local.time, "time", side_effect=lambda: clock[0]), \
             patch.object(llm_local.time, "sleep", side_effect=lambda _: clock.__setitem__(0, 600.0)):
            self.assertIn("too long", local.ensure_running())
        self.assertEqual(shutdown_checked, [(True, [("stopped", None)])])

    def test_cancel_does_not_kill_shared_loader(self):
        local = self.make_local()
        self.assertEqual(local.ensure_running(cancelled=lambda: True), "stopped")
        self.assertEqual(local.state, "loading")


if __name__ == "__main__":
    unittest.main()
