#!/usr/bin/env python3

import logging
import subprocess
import json
import requests
import openai
import copy
from tbraid import tbraid
from openai import OpenAI

logger = logging.getLogger(__name__)

class LLMManager:
    def __init__(self, openai_api_key=None, ollama_path='ollama'):
        self.openai_api_key = openai_api_key
        self.ollama_path = ollama_path

    def call(self, request, meta=None):
        """
        Dispatch LLM call based on request dict.
        Expected format:
        {
            "$llm": "<prompt string>",
            "provider": "openai" or "ollama" (optional, default "openai"),
            "model": "<model_name>" (optional),
            ... other provider-specific params ...
        }
        meta: optional dict to be filled with extra info from the LLM response.
        """
        provider = request.get('provider', 'openai')
        if provider == 'openai':
            return self._call_openai(request, meta=meta)
        elif provider == 'ollama':
            return self._call_ollama(request, meta=meta)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _call_openai(self, request, meta=None):
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
        client = OpenAI(api_key=self.openai_api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        # Fill meta if provided
        if meta is not None:
            meta['model'] = model
            meta['usage'] = getattr(response, 'usage', None)
            meta['id'] = getattr(response, 'id', None)
            meta['prompt'] = copy.deepcopy(messages)
            #meta['raw_response'] = response
        return response.choices[0].message.content

    def _call_ollama(self, request, meta=None):
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
            if meta is not None:
                meta['model'] = model
                #meta['raw_response'] = data
            return data.get('response', '')
        except subprocess.CalledProcessError as e:
            logger.error(f"Ollama call failed: {e.stderr}")
            raise

class chatbraid(tbraid):
    def __init__(self, llm_manager=None, *args, default_llm_params=None, model=None, temperature=None, max_tokens=None, **kwargs):
        """
        llm_manager: instance of LLMManager or compatible interface.
                     If None, a default LLMManager is created using environment variables.
        default_llm_params: dict of default key/values to use for all LLM calls if not provided.
        model, temperature, max_tokens, ... : common LLM parameters to set defaults easily.
        """
        if llm_manager is None:
            import os
            openai_key = os.getenv('OPENAI_API_KEY')
            llm_manager = LLMManager(openai_api_key=openai_key)
        super().__init__(*args, **kwargs)
        self.llm_manager = llm_manager

        # Start with provided default_llm_params or empty dict
        self.default_llm_params = dict(default_llm_params or {})

        # Add any explicit LLM params passed to constructor
        for k, v in [('model', model), ('temperature', temperature), ('max_tokens', max_tokens)]:
            if v is not None:
                self.default_llm_params[k] = v

        # Register the LLM handler with higher priority
        self.register(
            lambda a: isinstance(a, dict) and '$llm' in a,
            self._handle_llm_call
        )

    def _handle_llm_call(self, _, a, ts, key=None, *r):
        logger.info(f'Sending LLM request: {a}')
        try:
            # Process the prompt(s) with current tstack (ts)
            processed_prompt = self._process(a.get('$llm'), ts)

            # Create a shallow copy of the request dict to avoid mutating original
            request_copy = dict(a)
            request_copy['$llm'] = processed_prompt

            # Apply default llm params if not present in request_copy
            for k, v in self.default_llm_params.items():
                if k not in request_copy:
                    request_copy[k] = v

            # Pass meta dict for this thread if available
            meta = None
            if key is not None and hasattr(self, "_ttable") and key in self._ttable:
                meta = self._ttable[key]
            response = self.llm_manager.call(request_copy, meta=meta)
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
    import pprint

    logging.basicConfig(level=logging.INFO)
    
    if False:
        cb = chatbraid(model='gpt-4.1-nano').run({
            'query1': {
                '$llm': 'What is the capital of France?',
                'model': 'gpt-4.1-mini'
            },
            'query2': {
                '$llm': 'Tell me a joke.'
                # model and provider default to openai and gpt-4.1-mini
            },
            'q3': [
                '@query1',
                {'$llm': 'Supposedly, %(query1)s is a fact.  Tell me how it USED to be a fact... 5000 years ago, in the age when man still roamed the Earth.'},
                {'$llm': 'repeat the following verbatim, except with only nouns: ((%($result)s))... remember, only nouns, comma delimited'}
            ]
        }).wait('query1','query2')
        
        for k in ('query1','query2'):
            print(f'{k}: {cb[k]}')
        
        cb.wait()
        
        for k in cb:
            print(f'{k}: {cb[k]}')
    
    if True:
        cb = chatbraid().run({
            'dabois': {
                '$foreach':({'name':s} for s in ['bob','bass','richards']),
                '$llm':'give me a 20-word history of the name %(name)s.',
                'model':'gpt-4.1-nano',
                '$sub':1
            },
            'out': [
                '@dabois',
                lambda a,t:f'{dict(t.matchitems("*dabois:*")).values()}',
                {
                    '$llm':'90 words, wax poetic over the associations and relatedness between the following names and their origins: \n%($result)s',
                    'model':'gpt-4.1-nano'
                }
            ]
        }).wait()
        pprint.pprint(cb._ttable,indent=2)


