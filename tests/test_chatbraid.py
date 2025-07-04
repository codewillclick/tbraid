import pytest
from chatbraid import chatbraid, LLMManager

class DummyLLMManager:
    def __init__(self):
        self.called = False
        self.last_request = None
    def call(self, request):
        self.called = True
        self.last_request = request
        return "dummy-response"

def test_chatbraid_llm_handler(monkeypatch):
    llm = DummyLLMManager()
    cb = chatbraid(llm)
    cb.run({'q': {'$llm': 'Hello, %(name)s!', 'name': 'World'}})
    cb.wait('q')
    assert cb['q'] == "dummy-response"
    assert llm.called
    assert llm.last_request['$llm'] == 'Hello, %(name)s!'

def test_chatbraid_process_prompt():
    llm = DummyLLMManager()
    cb = chatbraid(llm)
    ts = {'foo': 'bar'}
    # string
    assert cb._process('hi %(foo)s', ts) == 'hi bar'
    # tuple of strings
    assert cb._process(('sys %(foo)s', 'user %(foo)s'), ts) == ('sys bar', 'user bar')
    # list of [role, content]
    prompt = [['system', 'sys %(foo)s'], ['user', 'user %(foo)s']]
    processed = cb._process(prompt, ts)
    assert processed == [['system', 'sys bar'], ['user', 'user bar']]

def test_chatbraid_default_llm_params():
    llm = DummyLLMManager()
    cb = chatbraid(llm, default_llm_params={'model': 'gpt-4.1-mini'})
    cb.run({'q': {'$llm': 'test'}})
    cb.wait('q')
    assert llm.last_request['model'] == 'gpt-4.1-mini'
