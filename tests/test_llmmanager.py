import pytest
from unittest.mock import patch, MagicMock
from chatbraid import LLMManager

import sys
import types

def test_llmmanager_call_openai(monkeypatch):
    manager = LLMManager(openai_api_key="fake-key")
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="Paris"))]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(model, messages):
                    return fake_response

    fake_openai = types.SimpleNamespace()
    fake_openai.api_key = None
    fake_openai.OpenAI = lambda api_key=None: FakeClient

    # Inject fake openai module
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    req = {'$llm': 'What is the capital of France?', 'provider': 'openai', 'model': 'gpt-4.1-mini'}
    result = manager._call_openai(req)
    assert result == "Paris"

def test_llmmanager_call_ollama(monkeypatch):
    manager = LLMManager()
    req = {'$llm': 'Say hi', 'provider': 'ollama', 'model': 'llama2'}
    fake_output = '{"response": "Hello"}'
    fake_proc = MagicMock()
    fake_proc.stdout = fake_output
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)
    result = manager._call_ollama(req)
    assert result == "Hello"

def test_llmmanager_call_invalid_provider():
    manager = LLMManager()
    req = {'$llm': 'test', 'provider': 'unknown'}
    with pytest.raises(ValueError):
        manager.call(req)
