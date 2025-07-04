import pytest
from unittest.mock import patch, MagicMock
from chatbraid import LLMManager

import sys
import types

import os
from unittest.mock import patch, MagicMock

def test_llmmanager_call_openai(monkeypatch):
    # Assign openai_api_key from environment variable
    api_key = os.getenv('OPENAI_API_KEY', 'fake-key')
    manager = LLMManager(openai_api_key=api_key)
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="Paris"))]

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch('chatbraid.OpenAI', return_value=fake_client):
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
