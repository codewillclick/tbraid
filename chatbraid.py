#!/usr/bin/env python3

import logging
from tbraid import tbraid

logger = logging.getLogger(__name__)

class chatbraid(tbraid):
    def __init__(self, llm_api_call_func, *args, **kwargs):
        """
        llm_api_call_func: a callable that takes the LLM request dict and returns the response string.
        """
        super().__init__(*args, **kwargs)
        self.llm_api_call_func = llm_api_call_func

        # Register the LLM handler with higher priority (append at end so it is checked first)
        self.register(
            lambda a: isinstance(a, dict) and '$llm' in a,
            self._handle_llm_call
        )

    def _handle_llm_call(self, _, a, ts):
        """
        Handle dicts with '$llm' key by sending the request to the LLM API and returning the response.
        """
        request = a['$llm']
        logger.info(f'Sending LLM request: {request}')
        try:
            response = self.llm_api_call_func(request)
            logger.info(f'LLM response received')
            return response
        except Exception as e:
            logger.error(f'LLM call failed: {e}', exc_info=True)
            raise

# Example usage if run as main:
if __name__ == '__main__':
    import time

    # Dummy LLM API call function for testing
    def dummy_llm_api_call(request):
        time.sleep(1)  # simulate latency
        return f"Echo: {request}"

    cb = chatbraid(dummy_llm_api_call)

    # Example input with an LLM call
    cb.run({
        'query1': {
            '$llm': 'What is the capital of France?'
        },
        'query2': {
            '$llm': 'Tell me a joke.'
        }
    })

    cb.wait()
    for k in cb._ttable:
        print(f'{k}: {cb._ttable[k]["value"]}')
