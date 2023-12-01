import requests
import datetime
import json
import time
from urllib import parse
from requests.models import HTTPError
__author__ = "Forrest Beck"


class Lightspeed(object):

	def __init__(self, config, testing=False):
		"""
		Creates new Lightspeed object.
		:param config: Specify dictionary with config
		"""
		self.config = config

		self.token_url = "https://cloud.lightspeedapp.com/oauth/access_token.php"
		if "account_id" in config:
			self.api_url = "https://api.lightspeedapp.com/API/V3/Account/" + \
				config["account_id"] + "/"
		else:
			self.api_url = ""
		# Initialize token as expired.
		self.token_expire_time = datetime.datetime.now() - datetime.timedelta(days=1)
		self.bearer_token = None
		self.rate_limit_bucket_level = None
		self.rate_limit_bucket_rate = 1
		self.rate_limit_last_request = datetime.datetime.now()
		self.rate_limit_availability = 60

		# Create a new session for API calls. This will hold bearer token.
		self.session = requests.Session()
		self.session.headers.update({'Accept': 'application/json'})
		self.testing = testing

	def __repr__(self):
		return "Lightspeed API"

	def get_authorization_token(self, code):
		"""
		Ensures the Lightspeed HQ Bearer token is current
		:return:
		"""
		s = requests.Session()

		try:
			payload = {
				'refresh_token': self.config["refresh_token"],
				'client_secret': self.config["client_secret"],
				'client_id': self.config["client_id"],
				'grant_type': 'authorization_code',
				'code': code
			}
			r = s.post(self.token_url, data=payload)
			json = r.json()

			self.bearer_token = json["access_token"]
			self.session.headers.update(
				{'Authorization': 'Bearer ' + self.bearer_token})

			return json["refresh_token"]
		except:
			return None

	def get_token(self):
		"""
		Ensures the Lightspeed HQ Bearer token is current
		:return:
		"""
		if datetime.datetime.now() > self.token_expire_time:

			s = requests.Session()

			try:
				payload = {
					'refresh_token': self.config["refresh_token"],
					'client_secret': self.config["client_secret"],
					'client_id': self.config["client_id"],
					'grant_type': 'refresh_token',
				}
				r = s.post(self.token_url, data=payload)
				json = r.json()
				self.token_expire_time = datetime.datetime.now() + \
					datetime.timedelta(seconds=int(json["expires_in"]))
				self.bearer_token = json["access_token"]
				self.session.headers.update(
					{'Authorization': 'Bearer ' + self.bearer_token})

				return self.bearer_token
			except:
				return None
		else:
			return self.bearer_token

	def request_bucket(self, method, url, data=None):
		"""
		Sends request to session.  Ensures the request doesn't exceed the rate limits of the leaky bucket.
		:param method: post, get, put, delete
		:param url: complete api url
		:param data: post/put data
		:return: results in json
		"""
		if self.testing:
			print(method, url, data)

		if method in ("post", "put", "delete"):
			units_needed = 10
		else:
			units_needed = 1

		if self.rate_limit_availability < units_needed:
			left_over = units_needed - self.rate_limit_availability
			seconds_wait = left_over / self.rate_limit_bucket_rate
			last_request = datetime.timedelta.total_seconds(
				datetime.datetime.now() - self.rate_limit_last_request)
			if last_request < seconds_wait:
				time.sleep(seconds_wait - last_request)

		try:
			tries = 0
			while tries <= 3:
				# Check the bearer token is up to date.
				self.get_token()
				s = self.session.request(method.upper(), url, data=data)
				# Watch for too many requests status
				if s.status_code == 429:
					time.sleep(3)
					tries += 1
				else:
					break

			# if s.status_code == 200:
			try:
				s.raise_for_status()
				# Update time with latest request.
				self.rate_limit_last_request = datetime.datetime.now()
				# Update Bucket Levels
				self.rate_limit_bucket_level = s.headers['X-LS-API-Bucket-Level']
				requested, total = self.rate_limit_bucket_level.split('/')
				self.rate_limit_availability = float(total) - float(requested)
				# Update Drip Rates
				self.rate_limit_bucket_rate = float(
					s.headers['X-LS-API-Drip-Rate'])
				# return s.json()
			except HTTPError as e:
				print(e)
				print(s.headers)
			finally:
				return s.json()

		except requests.exceptions.HTTPError as e:
			return "Error: " + str(e)

	def build_url(self, source, id_=None, parameters=None, encode=False):
		if parameters:
			if encode:
				url = self.api_url + source + ".json?" + \
					parse.urlencode(parameters, safe=':-')
			else:
				url = self.api_url + source + ".json?" + parameters
		elif id_:
			url = self.api_url + source + f"/{id_}.json"
		else:
			url = self.api_url + source + ".json"
		return url

	def has_next(self, resp):
		return True if resp.get('@attributes', {}).get('next', {}) else False

	def next_page(self, resp):
		if self.has_next(resp):
			next_page = resp['@attributes']['next']
			return self.request_bucket("get", next_page)
		return None

	def has_previous(self, resp):
		return True if resp.get('@attributes', {}).get('previous', {}) else False

	def previous_page(self, resp):
		if self.has_previous(resp):
			previous_page = resp['@attributes']['previous']
			return self.request_bucket("get", previous_page)
		return None

	def get(self, source, id_=None, parameters=None, keep_attributes=False):
		"""
		Get data from API.
		:param source: API Source desired
		:param parameters: Optional URL Parameters.
		:return: JSON Results

		"""

		# Check the bearer token is up to date.
		data = []
		for p in self.get_paginated(source,id_,parameters,keep_attributes):
			if isinstance(p,list):
				data.extend(p)
			elif isinstance(p,dict):
				data.append(p)
		return data
		# url = self.build_url(source=source, id_=id_,
		# 					 parameters=parameters, encode=True)

		# r = self.request_bucket("get", url)

		# if isinstance(r, dict):
		# 	if r:
		# 		next_resp = self.next_page(r)
		# 		while next_resp:
		# 			# if r.get('@attributes',{}).get('next',{}):
		# 			# next_page = r['@attributes']['next']
		# 			# while next_page:
		# 			# p = self.request_bucket("get", next_page)
		# 			# next_page = p.get('@attributes',{}).get('next',{})
		# 			# Append new data to original request
		# 			for i in next_resp:
		# 				if isinstance(next_resp[i], list):
		# 					r[i].extend(next_resp[i])
		# 			next_resp = self.next_page(next_resp)
		# 			# if not next_page:
		# 			# 	break
		# return r

	def get_paginated(self, source, id_=None, parameters=None, keep_attributes=True):
		"""
		Get data from API. Implement pagination.
		:param source: API Source desired
		:param parameters: Optional URL Parameters.
		:return: JSON Results
		:paginate: yield results or return a list
		:keep_attributes: if not then return source from response
		"""

		# Check the bearer token is up to date.

		url = self.build_url(source=source, id_=id_,
							 parameters=parameters, encode=True)

		r = self.request_bucket("get", url)
		if not keep_attributes:
			# attrs = r.pop('@attributes')
			yield r[source]
		else:
			yield r
		next_resp = self.next_page(r)
		while next_resp:
			if not keep_attributes:
				try:
					yield next_resp[source]
				except:
					break
			else:
				yield next_resp
			next_resp = self.next_page(next_resp)

	def put(self, source, data, id_=None, parameters=None):
		"""
		Update object in API using PUT
		:param source: API Source
		:param data: PUT Data
		:param parameters: Optional URL Parameters.
		:return: JSON Results

		"""

		d = json.dumps(data)

		url = self.build_url(source=source, id_=id_, parameters=parameters)

		r = self.request_bucket("put", url, d)
		return r

	def post(self, source, data, parameters=None):
		"""
		Post new object in API with POST.
		:param source: API Source
		:param data: POST Data
		:param parameters: Optional URL Parameters.
		:return: JSON Results
		"""

		d = json.dumps(data)

		url = self.build_url(source=source, parameters=parameters)

		r = self.request_bucket("post", url, d)
		return r

	def delete(self, source, id_=None, parameters=None):
		"""
		Delete object from API
		:param source: API Source
		:param parameters: Optional URL Parameters.
		:return: JSON Results
		"""

		url = self.build_url(source=source, id_=id_, parameters=parameters)

		r = self.request_bucket("delete", url)
		return r

	def create(self, source, data, parameters=None):
		"""
		Preserved for compatability
		Create new object in API with POST.
		:param source: API Source
		:param data: POST Data
		:param parameters: Optional URL Parameters.
		:return: JSON Results
		"""

		# Check the bearer token is up to date.
		return self.post(source=source, data=data, parameters=parameters)

	def update(self, source, data, id_=None, parameters=None):
		"""
		Preserved for compatability
		Update object in API using PUT
		:param source: API Source
		:param data: PUT Data
		:param parameters: Optional URL Parameters.
		:return: JSON Results
		"""

		# Check the bearer token is up to date.
		return self.put(source=source, data=data, id_=id_, parameters=parameters)
