#!/usr/bin/env python3

import re
import sys
import json
import time
import logging
import threading
import traceback


logging.basicConfig(
	level=logging.WARN,
	#level=logging.INFO,
	#level=logging.DEBUG,
	format='%(levelname)s (<%(threadName)s>): %(message)s')
logger = logging.getLogger(__name__)

class UnfinishedThreadError(Exception): pass
class KeyOverrideAttemptError(Exception): pass
class NoMatchedFunctionError(Exception): pass
class WaitTimeoutError(Exception): pass

class tablestack:
	''' Stack of dict-likes, primarily for getter operations, that are all
	treated like a single dict object, moving down to find keys from the
	top of the stack to the bottom. '''

	def __init__(self,*r,**kw):
		self._stack = []
		for d in r:
			self.add(d)
		for k,v in kw.items():
			self._stack[-1][k] = v
	
	def add(self,d):
		''' Add a dict-like to the stack of dict-likes for index-getting. '''
		self._stack.append(d)
		return self
	
	def clone(self):
		''' Create a copy directly referencing its own stack items. '''
		return tablestack(*self._stack)
	
	def flat(self):
		''' Return a flat dict reflecting all visible key-val pairs in stack. '''
		a = {}
		for b in self._stack:
			for k in iter(b):
				logger.debug(f'b ({b}) of self._stack, k ({k})')
				try:
					a[k] = b[k]
				except UnfinishedThreadError:
					a[k] = None
		return a

	def __contains__(self,k):
		try:
			return not not self[k]
		except KeyError:
			return False
	
	def __getitem__(self,k):
		for i in range(len(self._stack)-1,0-1,-1):
			t = self._stack[i]
			if k in t:
				return t[k]
		raise KeyError(k)
	
	def __setitem__(self,k,v):
		self._stack[-1][k] = v
	
	def __iter__(self):
		for k,v in self.flat().items():
			yield k
	
	def keys(self):
		for k in self.flat().keys():
			yield k
	
	def items(self):
		for k,v in self.flat().items():
			yield (k,v)

class tbraid:
	def __init__(self,interval=.1,timeout=300,throttle=30):
		self._sleep = interval
		self._timeout = timeout
		self._throttle = throttle
		self._tstack = None
		self._ttable = None
		self._matches = []
		self.reset()
		# Register returning the leftovers as-is.
		self.register(
			lambda a:True,
			self._handle_base_ignore)
		# Register literal conversions.
		self.register(
			lambda a:True,
			self._handle_base_special_literals)
		# Register parallel thread object.
		self.register(
			lambda a:type(a) is dict,
			self._handle_base_object)
		# Register sequential chain object (list).
		self.register(
			lambda a:type(a) is list,
			self._handle_base_list)
		# Register wait object.
		self.register(
			lambda a:type(a) is dict and '$wait' in a,
			self._handle_base_wait)
		# Register arbitrary function run.
		self.register(
			lambda a:type(a) is dict and '$run' in a,
			self._handle_base_run)
	
	def reset(self):
		''' Clear out initialized properties, though no killing threads. '''
		self._tstack = tablestack(self)
		self._ttable = {}
		return self
	
	def register(self,check,func):
		''' Add another check and response for specific object types. '''
		self._matches.append((check,func))
		return self
	
	def __contains__(self,k):
		return k in self._ttable
	
	def __getitem__(self,k):
		ob = self._ttable[k]
		#if not (ob['state'] in ('done','error')):
		#	raise UnfinishedThreadError(k)
		return ob['value']
	
	def __iter__(self):
		for k,v in self._ttable.items():
			yield k
	
	def keys(self):
		for k in self._ttable.keys():
			yield k
	
	def items(self):
		for k,v in self._ttable.items():
			yield (k,v)
	
	def _handle_base_ignore(self,_,a,ts):
		logger.info(f'_handle_base_ignore {a}')
		return a
	
	def _handle_base_special_literals(self,_,a,ts):
		logger.info(f'_handle_base_special_literals {a}')
		# Alias for {$wait:...}, '@key1,key2,...'
		if type(a) is str and len(a) and a[0] == '@':
			r = a.strip()[1:].split(',')
			return self._handle_base_wait(_,{'$wait':r},ts)
		return self._handle_base_ignore(_,a,ts)
	
	def _handle_base_object(self,_,a,ts):
		logger.info(f'_handle_base_object {a} {ts}')
		b = dict(a) # <- allow for mutability without affecting source
		t2 = ts.clone().add({}) # <- same as ^
		# This thread defaults to waiting until all created sub-threads are done
		# running before returning, but this can be bypassed with an '$async' flag.
		asy = '$async' in b and (not not b['$async'])
		kr = [k for k in b.keys() if k[0] != '$']
		try:
			self.run(ob=b,ts=t2)
		finally:
			if not asy:
				self.wait(*kr)
		if '$result' in t2:
			return t2['$result']
		return None
	
	def _handle_base_list(self,_,a,ts):
		logger.info(f'_handle_base_list {a} {ts}')
		t2 = ts.clone().add({'$result':None})
		for ob in a:
			f = self._find_matchfunc(ob)
			val = f(self,ob,t2)
			t2['$result'] = val
		return t2['$result']
	
	def _handle_base_wait(self,_,a,ts):
		logger.info(f'_handle_base_wait {a} {ts}')
		assert '$wait' in a
		assert type(a['$wait']) is list
		self.wait(*a['$wait'])
		return ts['$result'] if '$result' in ts else None
	
	def _handle_base_run(self,_,a,ts):
		logger.info(f'_handle_base_run {a} {ts}')
		f = a['$run']
		return f(a,ts)
	
	def _find_matchfunc(self,a):
		# Check for match against register (in reverse order for now, so latest
		# entries take highest priority).
		for i in range(len(self._matches)-1,0-1,-1):
			check,f = self._matches[i]
			assert check
			assert f
			if check(a):
				return f
		raise NoMatchedFunctionError(f'ob: {a}')
	
	def run(self,ob=None,tt=None,ts=None,**kw):
		''' Run against a provided json/dict object, execution logic. '''
		ob = ob or {}
		ts = ts or self._tstack
		tt = tt or self._ttable
		if type(ob) in (list,tuple):
			obx = {}
			obx['$root'] = ob # should only apply to root run object
			ob = obx
		for k,v in kw.items():
			ob[k] = v
		special = set(['$throttle','$async'])
		throt = self._throttle
		if '$throttle' in ob:
			throt = ob['$throttle']
		# Worker function to handle various input types.
		sem = threading.Semaphore(throt)
		def tworker(a,tstack,key):
			f = self._find_matchfunc(a)
			with sem:
				try:
					val = f(self,a,tstack)
					tt[key]['value'] = val
					tt[key]['state'] = 'done'
				except Exception as e:
					trace = traceback.format_exc()
					logging.warn(f'tworker {key}:({a}), exception:\n{trace}')
					tt[key]['state'] = 'error'
		# Loop through keys for threads to run.
		added = set()
		for k,v in ob.items():
			if k in special:
				continue
			if k in tt:
				raise KeyOverrideAttemptError(k)
			t = threading.Thread(target=tworker,args=(v,ts,k),name=f't.{k}')
			ob = {
				'state':'not-started',
				'value':None,
				'thread':t
			}
			tt[k] = ob
			added.add(k)
		# Start all threads after tt's been assigned its objects.
		for k in added:
			logger.info(f'  start thread ({k})')
			tt[k]['thread'].start()
		return self
	
	def wait(self,*r):
		''' Wait for provided thread-names to finish before continuing. '''
		# NOTE: There is surely a more elegant to do this than a sleep loop, but
		#   for now it's reliable so I'll come back to it later.
		start = time.time()
		while time.time() < start + self._timeout:
			kr = list((r if len(r) else self._ttable.keys()))
			logger.debug(f'kr: {kr}\n{self._ttable}')
			if len([k for k in kr if \
					self._ttable[k]['state'] in ('done','error')]) == len(kr):
				return self
			time.sleep(self._sleep)
		raise WaitTimeoutError(f'timeout: {self._timeout}s')


if __name__ == '__main__':
	import pprint

	b = tbraid(interval=.1)
	b.run({
		'thingo1':{
			'a':1,
			'b':2
		},
		'thingo2':[
			{'c':3},
			{'d':4},
			{'$wait':['thingo3']},
			{'e':5}
		],
		'thingo3':{
			'$run':(lambda *r:time.sleep(.75))
		}
	})
	print('DANG BOI')
	b.wait()
	print('BOI DANGO!')
	pprint.pprint(b._ttable,indent=2)

	c = tbraid().run([
		{
			'set':1,
			'some':2,
			'vars':3,
			'here': [
				{'$run':(lambda *r:time.sleep(.5))},
				4
			]
		},
		{
			'$run':lambda a,b:print(a,dict(b))
		}
	]).wait()
	pprint.pprint(c._ttable,indent=2)

