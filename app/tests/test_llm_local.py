"""Tests for llm_local.py: turning the AI off must stick, even while the model file is being checked, and a slow load is
left to finish for as long as it keeps getting further.
No model is started and no large file is read: the size, the digest, the measuring and the spawn are all replaced here."""
import hashlib
import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import llm_local

TINY = b'0123456789'
FIT = {'ev': 'fit', 'status': 'fits', 'ram_total': 0, 'device_bytes': 1, 'host_bytes': 1, 'memory': []}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.model = self.dir / llm_local.FILE
        self.model.write_bytes(TINY)
        for patch in (mock.patch.object(llm_local, 'STATE_FILE', self.dir / 'llm' / 'state.json'),
                      mock.patch.object(llm_local, 'SIZE', len(TINY)),
                      mock.patch.object(llm_local, 'SHA256', hashlib.sha256(TINY).hexdigest()),
                      mock.patch.object(llm_local, 'places', lambda: [self.dir])):
            patch.start()
            self.addCleanup(patch.stop)
        self.local = llm_local.Local()
        self.local.runner = Path('fake-runner')
        self.spawned = []
        self.local._spawn = lambda: self.spawned.append(1)

    def fake_run(self, during=None):
        """A stand-in for subprocess.run when measuring; `during` runs while the measuring is going on."""
        def run(argv, **kw):
            self.measured = True
            if during:
                during()
            return mock.Mock(stdout=json.dumps(FIT, separators=(',', ':')).encode(), stderr=b'')
        return mock.patch.object(llm_local.subprocess, 'run', run)


class TurnedOff(Base):
    def test_off_during_measuring_stays_off(self):
        with self.fake_run(during=lambda: self.local.set_enabled(False)):
            self.local.discover()
        self.assertEqual(self.local.state, 'off')
        self.assertFalse(self.local.available())

    def test_off_during_checking_stays_off(self):
        real = hashlib.sha256
        with self.fake_run(), mock.patch.object(llm_local.hashlib, 'sha256', lambda: (self.local.set_enabled(False), real())[1]):
            self.local.discover()
        self.assertEqual(self.local.state, 'off')

    def test_check_and_measure_do_nothing_when_off(self):
        self.local.set_enabled(False)
        with self.fake_run():
            self.assertFalse(self.local._check(self.model))
            self.local._measure()
        self.assertEqual(self.local.state, 'off')
        self.assertFalse(getattr(self, 'measured', False))

    def test_turned_off_model_is_not_started_or_offered(self):
        self.local.state, self.local.path, self.local.fit = 'stopped', self.model, {'fits': True}
        self.local.saved['enabled'] = False
        self.assertFalse(self.local.available())
        self.assertTrue(self.local.ensure_running())      # a sentence saying why not
        self.assertEqual(self.spawned, [])


class Clock:
    """Stands in for the time module inside llm_local, so ten minutes pass at once. `tick` runs once for each sleep."""
    def __init__(self):
        self.now, self.tick = 1000.0, lambda: None

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s
        self.tick()


class SlowLoad(Base):
    """ensure_running gives up START_WAIT seconds after the load last got further, not START_WAIT seconds after it began."""

    def setUp(self):
        super().setUp()
        self.clock = Clock()
        patch = mock.patch.object(llm_local, 'time', self.clock)
        patch.start()
        self.addCleanup(patch.stop)
        self.lines = queue.Queue()                  # what the model program writes: one JSON line each, None when it ends
        self.proc = mock.Mock(stdout=iter(self.lines.get, None))
        self.proc.poll.return_value = None
        self.proc.wait.return_value = 0
        self.addCleanup(self.lines.put, None)
        self.local.state, self.local.path, self.local.fit = 'stopped', self.model, {'fits': True}
        self.local._spawn = self.spawn

    def spawn(self):
        """What _spawn does, without the program: the real reader takes the lines from self.lines."""
        self.spawned.append(1)
        self.local.state, self.local.pct, self.local.message = 'loading', 0, ''
        self.local.proc = self.proc
        self.local.t_spawn = self.local.t_progress = self.clock.time()
        self.local.furthest = 0
        llm_local.threading.Thread(target=self.local._read, args=(self.proc, queue.Queue()), daemon=True).start()

    def say(self, ev, seen):
        """The program writes one line; returns once the reader has taken it in."""
        self.lines.put(json.dumps(ev).encode())
        end = time.monotonic() + 5
        while not seen() and time.monotonic() < end:
            time.sleep(0.001)
        self.assertTrue(seen(), ev)

    def every(self, seconds, events):
        """Has the program write the next of `events` each time `seconds` have passed."""
        events, due = iter(events), [self.clock.now + seconds]

        def tick():
            if self.clock.now >= due[0]:
                due[0] += seconds
                ev = next(events, None)
                if ev:
                    self.say(ev, self.lines.empty)
                    self.say({'ev': 'fit'}, self.lines.empty)      # once this one is taken, the one before is fully handled
        self.clock.tick = tick

    def test_load_that_keeps_getting_further_is_left_to_finish(self):
        step = llm_local.START_WAIT / 2
        self.every(step, [{'ev': 'progress', 'p': p} for p in range(5, 101, 5)] + [{'ev': 'ready'}])
        t0 = self.clock.now
        self.assertIsNone(self.local.ensure_running())
        self.assertGreater(self.clock.now - t0, 10 * llm_local.START_WAIT)      # far past the old limit
        self.assertEqual(self.local.state, 'ready')
        self.proc.stdin.write.assert_not_called()                                # never told to quit
        self.assertEqual(self.spawned, [1])

    def test_load_that_stops_getting_further_is_stopped(self):
        step = llm_local.START_WAIT / 2
        self.every(step, [{'ev': 'progress', 'p': p} for p in (5, 10, 15)])
        t0 = self.clock.now
        self.assertEqual(self.local.ensure_running(), 'The local AI took too long to start.')
        self.assertAlmostEqual(self.clock.now - t0, 3 * step + llm_local.START_WAIT, delta=1)   # START_WAIT after the last step
        self.assertEqual(self.local.state, 'stopped')                            # the next question may try again
        self.proc.stdin.write.assert_called_once_with(b'{"op":"quit"}\n')

    def test_the_same_percentage_again_does_not_keep_it_waiting(self):
        step = llm_local.START_WAIT / 2
        self.every(step, [{'ev': 'progress', 'p': 40}] * 50)
        t0 = self.clock.now
        self.assertEqual(self.local.ensure_running(), 'The local AI took too long to start.')
        self.assertAlmostEqual(self.clock.now - t0, step + llm_local.START_WAIT, delta=1)

    def test_going_back_and_forth_does_not_keep_it_waiting(self):
        step = llm_local.START_WAIT / 2
        self.every(step, [{'ev': 'progress', 'p': 20}] + [{'ev': 'progress', 'p': p} for p in (19, 20)] * 25)
        t0 = self.clock.now
        self.assertEqual(self.local.ensure_running(), 'The local AI took too long to start.')
        self.assertAlmostEqual(self.clock.now - t0, step + llm_local.START_WAIT, delta=1)   # counted from the first 20
        self.assertEqual(self.local.furthest, 20)

    def test_load_that_never_reports_is_stopped_after_the_wait(self):
        t0 = self.clock.now
        self.assertEqual(self.local.ensure_running(), 'The local AI took too long to start.')
        self.assertAlmostEqual(self.clock.now - t0, llm_local.START_WAIT, delta=1)


if __name__ == '__main__':
    unittest.main()
