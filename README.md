
# tbraid

Thread braiding, like chaining, but with threads!  Meant for convenient mid-complexity interdependent LLM calls.


## Purpose

Practice working with both hand-made and LLM-assisted (via aider) classes.  Been meaning to implement something like this for a while now; I've finally got a mite of thread complexity and dependencies working with syntax I can understand even when I wake up feeling like I've got a bucket full of holes for a brain!


## Examples

It looks something like this right now...

```python
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
		'@query1',
		{'$llm': 'Supposedly, %(query1)s is a fact.  Tell me how it USED to be a fact... 5000 years ago, in the age when man still roamed the Earth.'},
		{'$llm': 'repeat the following verbatim, except with only nouns: ((%($result)s))... remember, only nouns, comma delimited'}
	]
}).wait()
```

See how nice that looks?  Fires all three LLM requests at the same time, with q3 waiting for query1 to finish before kicking off its own prompts that have the final values of the other threads available for insertion, and each in the chain with its prior result stored and available as well!

Really that's all there is to this little module, simplifying the appearance and utility of asynchronous thread behavior, plus LLMs.


## Misc.

Tests that auto-write themselves are the real magic of AI-assisted coding.  Even if they start off a little incorrect and self-defeating.  Are these things bypassing the entire llm call itself?

