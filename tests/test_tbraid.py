import pytest
import threading
from tbraid import tbraid, tablestack, UnfinishedThreadError, KeyOverrideAttemptError, NoMatchedFunctionError, WaitTimeoutError

def test_tablestack_basic():
    d1 = {'a': 1}
    d2 = {'b': 2}
    ts = tablestack(d1)
    ts.add(d2)
    assert ts['a'] == 1
    assert ts['b'] == 2
    ts['c'] = 3
    assert ts['c'] == 3
    assert 'a' in ts
    assert 'b' in ts
    assert 'c' in ts

def test_tablestack_clone():
    d1 = {'a': 1}
    ts = tablestack(d1)
    ts2 = ts.clone()
    assert ts2['a'] == 1
    ts2['b'] = 2
    assert ts2['b'] == 2
    assert 'b' in ts2

def test_tbraid_run_and_wait():
    tb = tbraid(interval=0.01)
    tb.run({
        'x': 1,
        'y': 2
    })
    tb.wait('x', 'y')
    assert tb['x'] == 1
    assert tb['y'] == 2

def test_tbraid_handle_base_list():
    tb = tbraid(interval=0.01)
    tb.run({
        'seq': [
            1,
            2,
            3
        ]
    })
    tb.wait('seq')
    assert tb['seq'] == 3

def test_tbraid_wait_timeout():
    tb = tbraid(interval=0.01, timeout=0.05)
    def slow_fn(a, ts):
        import time
        time.sleep(0.1)
        return 42
    tb.register(lambda a: isinstance(a, dict) and '$run' in a, lambda _, a, ts: a['$run'](a, ts))
    tb.run({
        'slow': {'$run': slow_fn}
    })
    with pytest.raises(WaitTimeoutError):
        tb.wait('slow')

def test_tbraid_key_override():
    tb = tbraid()
    tb.run({'a': 1})
    with pytest.raises(KeyOverrideAttemptError):
        tb.run({'a': 2})

def test_tbraid_no_matched_function():
    tb = tbraid()
    # Remove all handlers to force error
    tb._matches = []
    with pytest.raises(NoMatchedFunctionError):
        tb._find_matchfunc(123)
