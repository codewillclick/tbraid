
# Purpose.

_tbraid_, for thread braid.

Simplify the use of medium-complexity interwoven concurrent thread behaviors by providing a json interface for rough serialization.  Meant originally to host LLM calls, it turns out even without that it's a useful idea for threading in general.


# Dev methodology.

Practice LLM assisted coding around hand-woven abstract classes.


# Core classes.

tbraid:
- the root class meant to be extended to add special object interpretation
- interprets json object recursively to run internal methods
- all execution methods except for wait() kick off a thread
- dict objects imply parallel threads kicking off their own chains
- arrays imply a chain of things to execute in sequence
	- with the prior item's result passed in under '$result' in the table object
- all methods are passed in a table object that is a stack of dicts

tablestack:
- behaves like a dict, but is more like a stack of dicts
	- or objects with '[x]' indexable bracket syntax anyway
	- where the top one is checked for a key first, then the next, then the next...
	- this is used for adding onto the root tbraid result dict
		- when a local dict for the current executing step, or a whole chain,
		- is passed in its own object
	- when the llms come into play, this becomes useful
		- for string '%' mod table key insertions '%(key)', like that

