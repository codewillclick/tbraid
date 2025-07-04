#!/usr/bin/env python3

import logging
import subprocess
import json
import requests
from tbraid import tbraid

logger = logging.getLogger(__name__)

class LLMManager:
    def __init__(self, openai_api_key=None, ollama_path='ollama'):
        self.openai_api_key = openai_api_key
        self.ollama_path = ollama_path

    def call(self, request):
        """
        Dispatch LLM call based on request dict.
        Expected format:
        {
            "$llm": "<prompt string>",
            "provider": "openai" or "ollama" (optional, default "openai"),
            "model": "<model_name>" (optional),
            ... other provider-specific params ...
        }
        """
        provider = request.get('provider', 'openai')
        if provider == 'openai':
            return self._call_openai(request)
        elif provider == 'ollama':
            return self._call_ollama(request)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _call_openai(self, request):
        import openai
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not set")
        openai.api_key = self.openai_api_key

        model = request.get('model', 'gpt-4.1-mini')
        prompt = request.get('$llm')
        if prompt is None:
            raise ValueError("Prompt ('$llm') not provided")

        logger.debug(f"OpenAI call: model={model}, prompt={prompt}")

        # For chat models, wrap prompt in messages list
        messages = [
            {"role": "user", "content": prompt}
        ]

        # Use new OpenAI API client style per openai>=1.0.0
        from openai import OpenAI
        client = OpenAI(api_key=self.openai_api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content

    def _call_ollama(self, request):
        model = request.get('model')
        if not model:
            raise ValueError("Ollama model not specified")
        prompt = request.get('$llm')
        if prompt is None:
            raise ValueError("Ollama prompt ('$llm') not provided")

        logger.debug(f"Ollama call: model={model}, prompt={prompt}")

        try:
            proc = subprocess.run(
                [self.ollama_path, 'chat', model, '--json'],
                input=json.dumps({"prompt": prompt}),
                text=True,
                capture_output=True,
                check=True
            )
            output = proc.stdout.strip()
            data = json.loads(output)
            return data.get('response', '')
        except subprocess.CalledProcessError as e:
            logger.error(f"Ollama call failed: {e.stderr}")
            raise

class chatbraid(tbraid):
    def __init__(self, llm_manager, *args, **kwargs):
        """
        llm_manager: instance of LLMManager or compatible interface.
        """
        super().__init__(*args, **kwargs)
        self.llm_manager = llm_manager

        # Register the LLM handler with higher priority
        self.register(
            lambda a: isinstance(a, dict) and '$llm' in a,
            self._handle_llm_call
        )

    def _handle_llm_call(self, _, a, ts):
        logger.info(f'Sending LLM request: {a}')
        try:
            # Process the prompt(s) with current tstack (ts)
            processed_prompt = self._process(a.get('$llm'), ts)

            # Create a shallow copy of the request dict to avoid mutating original
            request_copy = dict(a)
            request_copy['$llm'] = processed_prompt

            response = self.llm_manager.call(request_copy)
            logger.info(f'LLM response received')
            return response
        except Exception as e:
            logger.error(f'LLM call failed: {e}', exc_info=True)
            raise

    def _process(self, prompt, tstack):
        """
        Process the prompt input by formatting all prompt strings with tstack.

        prompt: can be
          - string (user prompt)
          - tuple/list of two strings (system, user)
          - list of pairs [ [role, content], ... ] for full conversation

        tstack: tablestack instance used as dict for string formatting

        Returns the processed prompt in the same structure.
        """
        def format_str(s):
            if isinstance(s, str) and '%' in s:
                try:
                    return s % tstack
                except KeyError as e:
                    logger.warning(f"Missing key {e} in tstack for prompt formatting")
                    return s
            return s

        if isinstance(prompt, str):
            return format_str(prompt)
        elif isinstance(prompt, (list, tuple)):
            # If it's a pair of strings (system, user)
            if len(prompt) == 2 and all(isinstance(x, str) for x in prompt):
                return tuple(format_str(x) for x in prompt)
            else:
                # Assume list of [role, content] pairs
                processed = []
                for item in prompt:
                    if (isinstance(item, (list, tuple)) and len(item) == 2 and
                        isinstance(item[0], str) and isinstance(item[1], str)):
                        role, content = item
                        processed.append([role, format_str(content)])
                    else:
                        # Unexpected format, pass through as is
                        processed.append(item)
                return processed
        else:
            # Unknown type, return as is
            return prompt


# Example usage if run as main:
if __name__ == '__main__':
    import time
    import os

    logging.basicConfig(level=logging.INFO)

    openai_key = os.getenv('OPENAI_API_KEY')
    llm_manager = LLMManager(openai_api_key=openai_key)

    cb = chatbraid(llm_manager)

    cb.run({
        'query1': {
            '$llm': 'What is the capital of France?',
            'model': 'gpt-4.1-mini'
        },
        'query2': {
            '$llm': 'Tell me a joke.'
            # model and provider default to openai and gpt-4.1-mini
        },
        'q3': [
            {'$wait':['query1']},
            {'$llm': 'Supposedly, %(query1)s is a fact.  Tell me how it USED to be a fact... 5000 years ago, in the age when man still roamed the Earth.'}
        ]
    })

    cb.wait()
    for k in cb:
        print(f'{k}: {cb[k]}')
