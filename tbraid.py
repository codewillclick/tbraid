#!/usr/bin/env python3

import re
import sys
import json
import time
import threading


class UnfinishedThreadError(Exception): pass
class KeyOverrideAttemptError(Exception): pass
class NoMatchedFunctionError(Exception): pass

class tablestack:
	def __init__(self,*r,**kw):
		self._stack = []
		for d in r:
			self.add(d)
		for k,v in kw.items():
			self._stack[-1][k] = v
	
	def add(self,d):
		self._stack.append(d)
	
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
		raise NotImplementedError()


class tbraid:
	def __init__(self,interval=1,throttle=10):
		self._sleep = interval
		self._throttle = throttle
		self._tstack = None
		self._ttable = None
		self._matches = []
		self.reset()
		# Register ignoring whatever, for debug.
		self.register(
			lambda a:True,
			self._handle_base_ignore)
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
			self._handle_base_wait)
	
	
	def reset(self):
		self._tstack = tablestack(self)
		self._ttable = {}
		return self
	
	def register(self,check,func):
		self._matches.append((check,func))
		return self
	
	def __contains__(self,k):
		return k in self._ttable
	
	def __getitem__(self,k):
		ob = self._ttable[k]
		if ob['state'] != 'done':
			raise UnfinishedThreadError(k)
		return ob['value']
	
	def _handle_base_ignore(self,_,a,tt):
		print('_handle_base_ignore',a,file=sys.stderr)
		return None
	
	def _handle_base_object(self,_,a,tt):
		print('_handle_base_object',a,tt,file=sys.stderr)
		b = dict(a) # <- allow for mutability without affecting source
		self.run(b)
		if '$result' in b:
			return b['$result']
		return None
	
	def _handle_base_list(self,_,a,tt):
		print('_handle_base_list',a,tt,file=sys.stderr)
	
	def _handle_base_wait(self,_,a,tt):
		print('_handle_base_wait',a,tt,file=sys.stderr)
	
	def _handle_base_run(self,_,a,tt):
		print('_handle_base_run',a,tt,file=sys.stderr)
		f = a['$run']
		return f(a,tt)
	
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
	
	def run(self,ob=None,**kw):
		ob = ob or {}
		for k,v in kw.items():
			ob[k] = v
		special = set('$throttle')
		throt = self._throttle
		if '$throttle' in ob:
			throt = ob['$throttle']
		# Worker function to handle various input types.
		sem = threading.Semaphore(throt)
		def tworker(a,ttable,key):
			f = self._find_matchfunc(a)
			with sem:
				try:
					val = f(self,a,ttable)
					self._ttable[key]['value'] = val
					self._ttable[key]['state'] = 'done'
				except Exception as e:
					print(f'tworker {key}:({a}), exception:({e})',file=sys.stderr)
					self._ttable[key]['state'] = 'error'
		# Loop through keys for threads to run.
		for k,v in ob.items():
			if k in special:
				continue
			if k in self._ttable:
				raise KeyOverrideAttemptError(k)
			# TODO: Implement thread creation.
			t = threading.Thread(target=tworker,args=(v,self._ttable,k))
			ob = {
				'state':'not-started',
				'value':None,
				'thread':t
			}
			self._ttable[k] = ob
			print(f'  start thread ({k})',file=sys.stderr)
			t.start()
		return None
	
	def wait(self,*r):
		pass


if __name__ == '__main__':
	b = tbraid()
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
			'$run':(lambda:time.sleep(1.5))
		}
	})

