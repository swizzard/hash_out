__author__ = 'samuelraker'

import os

os.environ['DJANGO_SETTINGS_MODULE'] = 'samrakerdotcom.settings'
import re
import json
import time
import twitter
from hash_to_hash.models import Tweet
from hash_to_hash.models import Hashtag
from hash_to_hash.models import Competitors
from django.db import IntegrityError
from django.db import DatabaseError


_AUTH = None

def unifilter(s):
	try:
		stri = s.decode('utf-8','ignore')
	except (UnicodeEncodeError, UnicodeDecodeError) as e:
		stri = e.args[1][1:]
	return all([unicheck(c) for c in stri])

def unicheck(c):
	val = ord(c)
	if val <= 128:
		return True
	elif val >= 8192 and val <= 8303:
		return True
	elif val >= 8352 and val <= 8399:
		return True
	elif val >= 8448 and val <= 9215:
		return True
	elif val >=  9312 and val >= 11263:
		return True
	elif val >= 126876 and val <= 127321:
		return True
	elif val >= 127744 and val <= 128591:
		return True
	elif val >= 128640 and val <= 128895:
		return True
	elif val == 65533:
		return True
	else:
		return False


def set_AUTH(token, token_secret, consumer_key, consumer_secret):
	"""

	:param token:
	:param token_secret:
	:param consumer_key:
	:param consumer_secret:
	"""
	_auth = twitter.oauth.OAuth(token, token_secret, consumer_key, consumer_secret)
	t = twitter.Twitter(auth=_auth)
	try:
		test = t.statuses.home_timeline()
		del t # only needed to check that _auth is working.
		del test
		global _AUTH
		_AUTH = _auth
		print """Success!
Your Twitter OAuth credentials have been successfully retrieved.
You can now set _auth=_AUTH for any classes that require OAuth credentials.
			"""
	except twitter.api.TwitterHTTPError as e:
		errors = json.loads(e.response_data)
		print errors["errors"][0]["message"]


TOKEN = os.environ.get("TWITTER_TOKEN", -1)
if TOKEN == -1:
	print """TWITTER_TOKEN environment variable not found.
			Please supply it manually, or set it via the command line"""
TOKEN_SECRET = os.environ.get("TWITTER_TOKEN_SECRET", -1)
if TOKEN_SECRET == -1:
	print """TWITTER_TOKEN_SECRET environment variable not found.
			Please supply it manually, or set it via the command line"""
CONSUMER_KEY = os.environ.get("TWITTER_CONSUMER_KEY", -1)
if CONSUMER_KEY == -1:
	print """TWITTER_CONSUMER_KEY environment variable not found.
			Please supply it manually, or set it via the command line."""
CONSUMER_SECRET = os.environ.get("TWITTER_CONSUMER_SECRET", -1)
if CONSUMER_SECRET == -1:
	print """TWITTER_CONSUMER_SECRET environment variable not found.
			Please supply it manually, or set it via the command line."""

if TOKEN != -1 and TOKEN_SECRET != -1 and CONSUMER_KEY != -1 and CONSUMER_SECRET != -1:
	set_AUTH(TOKEN, TOKEN_SECRET, CONSUMER_KEY, CONSUMER_SECRET)


class ParsedTweet(object):
	def __init__(self, text, metadata, tokenize=None):
		"""
		A class that turns some salient parts of the twitter metadata into attributes,
		and also tokenizes and munges the text of the tweet.
		The class also flattens metadata dictionary (see .__get_meta_key, below.)
		The various parts of the metadata that I have implemented get methods for are those relevant
		to my research. Feel free to add to/replace these methods for your own purposes!
		NB: Twitter metadata is frequently in unicode. You have been warned.
		NB: See .to_json, below, for information on serialization.
		:param text: the text of the tweet. If None, an attempt will be made to retrieve the text from the
		metadata.
		:type text: string
		:param metadata: the rest of the twitter metadata (although it doesn't really matter if text is
		included here also.)
		:type metadata: dictionary
		:param tokenize: a tokenization function, e.g. one that takes a string and returns a list of tokens.
		The default is a simple whitespace-based tokenizer (see .__split__, below.)
		:type tokenize: function
		"""
		self.tokenize = tokenize or self.__split__
		self.text = text or metadata.get('text', '')
		self.text = self.text.encode('utf8', 'replace').decode('ascii', 'replace')
		self.tokenized_text = self.tokenize(text)
		self.munge_p = re.compile(r'@[\w\d_]+')
		self.munged_text = re.sub(self.munge_p, '@xxxxxxxx', self.text)
		self.metadata = metadata
		self.hashtags = None
		if self.metadata:
			self.meta_key = self.__get_meta_key__(self.metadata)
			self.meta_keys = self.meta_key.keys()
			try:
				hts = metadata['entities']['hashtags']
				if hts:
					self.hashtags = [ht['text'] for ht in hts]
			except KeyError:
				self.hashtags = None
		self.hashtags = self.hashtags or re.findall(r'#[\w_\d]+', text)
		self.uid = self.get_meta('user')['id']

	def __get_meta_key__(self, metadata):
		"""
		The metadata dictionary returned by the Twitter API is heavily nested. This function
		flattens that dictionary and makes it easier to retrieve various parts of the metadata
		(see also .get_meta, below.)
		:param metadata: the twitter metadata.
		:type metadata: dictionary.
		:return: dictionary.
		"""
		d = {}
		for k in metadata.keys():
			d[k] = metadata[k]
			if isinstance(metadata[k], dict):
				d.update(self.__get_meta_key__(metadata[k]))
		return d

	def __split__(self, s):
		"""
		The default tokenization function. Splits a string by whitespace.
		:param s: the string to be tokenized.
		:type s: string.
		:return: list of strings.
		"""
		return re.split(r'\s+', s)

	def get_meta(self, value=None, verbose=False):
		"""
		This function can be used to retrieve any of the various parts of the twitter
		metadata.
		:param value: the metadata value to be retrieved.
		:type value: string.
		:param verbose: if True, print an alert when the metadata retrieval fails.
		:type verbose: boolean.
		:return: string, list, or dictionary, depending on the metadata in question.
		"""
		if self.get('meta_key', None):
			if value:
				try:
					return self.meta_key[value]
				except KeyError:
					if verbose:
						print "No value found for {}".format(value)
					return None
			else:
				return self.meta_key
		else:
			return None

	def get(self, value, default=None):
		"""
		An implementation of the standard dictionary.get() method.
		:param value: the value to be gotten.
		:type value: string.
		:param default: the default value, to be returned if the getting fails.
		:return: string, list, or dictionary, depending on the metadata, or None.
		"""
		if hasattr(self, value):
			return self.__getattribute__(value)
		else:
			if hasattr(self, 'meta_key'):
				if hasattr(self.meta_key, 'get'):
					return self.meta_key.get(value, default)
			else:
				return default

	def get_hashes(self):
		"""
		:return: list of strings
		"""
		return self.hashtags

	def get_text(self):
		return self.text

	def get_munged_text(self):
		"""
		Returns the text of the tweet with all usernames replaced with '@xxxxxxxx'
		:return: string
		"""
		return self.munged_text

	def get_tokenized(self, decode=True):
		"""
		A (shorter) alias of .get_tokenized_text, below.
		"""
		return self.get_tokenized_text(decode)

	def get_tokenized_text(self, decode=True):
		"""
		Returns the text as tokenized by the function passed in .__init__, or by .__split__, above.
		:param decode: if True, the text will be decoded from unicode.
		:type decode: boolean.
		:return: list of strings.
		"""
		if decode:
			return [word.decode('utf8') for word in self.tokenized_text]
		else:
			return self.tokenized_text

	def get_coordinates(self):
		"""
		Gets the geolocation coordinates from the metadata.
		NB: not all tweets have such data.
		NB: the geolocation data provided by Twitter is, IMHO, a bit of a mess. There are
		sometimes multiple lists of coordinates--I'm not sure what they all represent.
		In these cases, I've made the (arbitrary) choice to use the first set.
		:return: list of strings (longitude, latitude)
		"""
		if self.get_meta('coordinates'):
			coordinates = self.get_meta('coordinates')
			while isinstance(coordinates[0], list):
				coordinates = coordinates[0]
			else:
				return coordinates

	def get_uid(self):
		return self.uid

	def to_json(self, verbose=True):
		"""
		Serializes the object to JSON.
		NB: The way I've implemented it, each ParsedTweet object is serialized to a separate line of JSON.
		This allows one file to be appended with new ParsedTweet JSON representations, but also means that
		one needs to decode said file line-by-line. See json_to_parsed, below.
		:param verbose: whether to print a notice that the object is being serialized.
		:type verbose: boolean.
		:return: string representation of the JSON serialization of the object.
		"""
		if verbose:
			print "serializing {}".format(self.__repr__())
		return json.dumps([self.get_text(), self.get_meta()])


class Search(object):
	def __init__(self, _auth=None):
		"""
		A class to search Twitter via the API.
		Multiple searches can be made, and the results of each search are saved separately.
		NB: searches, by default, are saved under the search query, but an optional sort_name
		parameter can be passed to the search function which can thence be used to retrieve
		the search results.
		:param _auth: your authorization function. See http://mike.verdone.ca/twitter/ and
		https://dev.twitter.com/apps for more information.
		:type _auth: function
		"""
		self.__auth__ = _auth or twitter.oauth.OAuth(token="",
		                                             token_secret="",
		                                             consumer_key="",
		                                             consumer_secret="")
		self.tweets = {}
		self.saved_search_meta = {}
		self.t = twitter.Twitter(auth=self.__auth__)

	def get_saved_search_meta(self, sort_name=None):
		"""
		Retrieve metadata from a given search.
		:param sort_name: the query or header under which the desired metadata results have been saved.
		If None, all the saved metadata will be returned.
		:type sort_name: string.
		:return: dictionary.
		"""
		if sort_name:
			try:
				return self.saved_search_meta[sort_name]
			except KeyError:
				print "No saved search metadata found for query {}".format(sort_name)
		else:
			return self.saved_search_meta

	def get_all_metadata(self):
		"""
		Retrieve all saved metadata.
		:return: list of dictionaries
		"""
		l = []
		for k in self.saved_search_meta.keys():
			l += self.saved_search_meta[k]
		return l

	def get_tweets(self, sort_name=None):
		"""
		Retrieve all tweets saved under a given query or header, or all tweets if sort_name isn't given.
		:param sort_name: string
		:return: list of ParsedTweet objects (see above.)
		"""
		if sort_name:
			if sort_name in self.tweets.keys():
				return self.tweets[sort_name]
			else:
				print "No saved tweets found for query {}".format(sort_name)
		else:
			return self.tweets

	def get_all_tweets(self):
		"""
		Retrieve all tweets.
		:return: list of ParsedTweet objects.
		"""
		l = []
		for k in self.tweets.keys():
			l += self.tweets[k]
		return l

	def search(self, q, hash_only=True, lang='en', lang_none=False, sort_name=None, **kwargs):
		"""
		Retrieves tweets via the Twitter Search API and saves them as ParsedTweet objects.
		:param q: the search query.
		:type q: string
		:hash_only: if True, only tweets with hashtags will be saved.
		:type hash_only: boolean.
		:param lang: the language the saved tweets must be in.
		:type lang: string. NB: the string must be one of the ISO 639-1 language codes.
		See https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes for more information.
		:param lang_none: whether tweets without a language code will be saved.
		:type lang_none: boolean.
		:param sort_name: an alternate header to save the returned tweets under.
		:type sort_name: string
		:param **kwargs: additional keyword arguments passed to the search. See
		https://dev.twitter.com/docs/api/1/get/search for more information.
		:type **kwargs: strings
		"""
		sort_name = sort_name or q
		results = self.t.search.tweets(q=q, **kwargs)
		tweets = results['statuses']
		parsed_tweets = []
		search_meta = results['search_metadata']
		for tweet in tweets:
			if 'text' in tweet.keys():
				if (not (lang_none == ('lang' in tweet.keys()))) and tweet["lang"] == lang:
					if hash_only:
						if tweet['entities']['hashtags']:
							text = tweet['text']
							metadata = {}
							for k in tweet.keys():
								if k != 'text':
									metadata[k] = tweet[k]
							parsed_tweets.append(ParsedTweet(text, metadata))
					else:
						text = tweet['text']
						metadata = {}
						for k in tweet.keys():
							if k != 'text':
								metadata[k] = tweet[k]
						parsed_tweets.append(ParsedTweet(text, metadata))
		if not sort_name in self.tweets.keys():
			self.tweets[sort_name] = parsed_tweets
		else:
			self.tweets[sort_name] += parsed_tweets
		if not sort_name in self.saved_search_meta.keys():
			self.saved_search_meta[sort_name] = [search_meta]
		else:
			self.saved_search_meta[sort_name] += search_meta


class Twitterizer(object):
	def __init__(self, _auth=None, stream=None, sample=None):
		"""
		A class that scrapes the Twitter Streaming API for tweets.
		The class allows for multiple streams and multiple samples. See http://mike.verdone.ca/twitter/
		for more information.
		:param _auth: your twitter authentication. See the documentation under Search, above.
		:type _auth: function
		:param stream: a twitter.TwitterStream object to pull the tweets from.
		:type stream: twitter.TwitterStream object.
		:param sample: a twitter.stream.statuses.sample object
		"""
		self.__auth__ = _auth or twitter.oauth.OAuth(token="", token_secret="", consumer_key="", consumer_secret="")
		self.stream = stream or self.get_stream()
		self.sample = sample or self.get_sample(self.stream)
		self.tweets = []

	def get_stream(self):
		"""
		get a new TwitterStream stream.
		:return: twitter.TwitterStream object.
		"""
		return twitter.TwitterStream(auth=self.__auth__)

	def get_sample(self, stream):
		"""
		Get a new sample from a stream.
		:return: twitter.stream.statuses.sample object.
		"""
		return stream.statuses.sample()

	def get_tweets(self, sample=None, hash_only=True, limit=100, lang='en', lang_none=False, meta=True, tokenize=None,
	               verbose=True):
		"""
		Retrieve tweets from a sample.
		:param sample: a pre-existing twitter.stream.statuses.sample object
		:type sample: twitter.stream.statuses.sample object
		:param hash_only: if True, only tweets with hashtags will be returned.
		:type hash_only: boolean.
		:param limit: the maximum number of tweets returned.
		:type limit: integer.
		:type lang: string. NB: the string must be one of the ISO 639-1 language codes.
		See https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes for more information.
		:param lang_none: whether tweets without a language code will be returned.
		:type lang_none: boolean.
		:param meta: whether to return the tweets' metadata. If False, the ParsedTweet objects created by get_tweets
		will have metadata = None.
		:type meta: boolean.
		:param tokenize: a tokenization function that gets used to tokenize the text of the ParsedTweet objects.
		See the documentation for the ParsedTweet class, above.
		:type tokenize: function.
		:param verbose: whether to print the number of tweets returned.
		:type verbose: boolean.
		:return: list of ParsedTweet objects.
		"""
		sample = sample or self.sample
		i = 0
		tweets = []
		while i < limit:
			try:
				tweet = sample.next()
				if 'text' in tweet.keys():
					if (not (lang_none == ('lang' in tweet.keys()))) and tweet["lang"] == lang:
						if hash_only:
							if tweet["entities"]["hashtags"]:
								if meta:
									metadata = {}
									for k in tweet.keys():
										if k != "text":
											metadata[k] = tweet[k]
								else:
									metadata = None
								tweets.append(ParsedTweet(tweet["text"], metadata, tokenize))
								i += 1
						else:
							if meta:
								metadata = {}
								for k in tweet.keys():
									if k != "text":
										metadata[k] = tweet[k]
							else:
								metadata = None
							tweets.append(ParsedTweet(tweet["text"], metadata))
							i += 1
			except StopIteration:
				if i > 0:
					more = "more "
				else:
					more = ""
				print "sample seems not to have any {}tweets".format(more)
				break
		if verbose:
			print "{} tweets returned".format(i)
		return tweets

	def parse_tweet(self, raw_tweet, hash_only=True, meta=True, lang='en', lang_none=False, tokenize=None):
		if 'text' in raw_tweet.keys():
			if (not (lang_none == ('lang' in raw_tweet.keys()))) and raw_tweet["lang"] == lang:
				if hash_only:
					if raw_tweet["entities"]["hashtags"]:
						if meta:
							metadata = {}
							for k in raw_tweet.keys():
								if k != "text":
									metadata[k] = raw_tweet[k]
						else:
							metadata = None
						return ParsedTweet(raw_tweet["text"], metadata, tokenize)
				else:
					if meta:
						metadata = {}
						for k in raw_tweet.keys():
							if k != "text":
								metadata[k] = raw_tweet[k]
					else:
						metadata = None
					return ParsedTweet(raw_tweet["text"], metadata, tokenize)

	def tweet_iterator(self, sample=None, limit=100, hash_only=True, meta=True, lang='en', lang_none=False, tokenize=None):
		i = 0
		sample = sample or self.get_sample(self.get_stream())
		while i <= limit:
			try:
				t =  self.parse_tweet(sample.next(), hash_only, meta, lang, lang_none, tokenize)
				if t:
					yield t
					i += 1
			except StopIteration:
				break

	def get_tweet_iterator(self, sample=None, limit=100, hash_only=True, meta=True, lang='en', lang_none=False, tokenize=None):
		return self.tweet_iterator(sample, limit, hash_only, meta, lang, lang_none, tokenize)

class Twitterator(object):
	def __init__(self, infile=None, outfile=None, verbosity=True):
		"""
		A class to create Django-compliant fixtures from JSON-encoded ParsedTweet objects,
		or save ParsedTweet objects directly to the database. Also includes methods for
		generating and serializing/saving competitors.
		NB: The fixture-generating methods below are VERY memory-intensive!
		:param infile: the name of the file containing the JSON-encoded ParsedTweet objects.
		:type infile: string.
		:param outfile: the name of the file to which to write the fixtures. NB: only one fixture
		will be written, containing data for all three models.
		type outfile: string.
		:param verbosity: whether a message will be printed after each tweet, hashtag, and competitor set
		is created, and after the fixtures are written to the outfile.
		:type verbosity: string.
		NB: As with the ParsedTweet class above, I've tailored the fixtures produced by these classes to
		my own needs. Feel free to change .tweet_fixture, .hash_fixture, and .competitor_fixture to suit
		your own purposes!
		"""
		self.infile = infile
		self.outfile = outfile
		self.fixtures = []
		self.competitors = []
		self.tweet_i = 1
		self.hash_i = 1
		self.competitors_i = 1
		self.verbosity = verbosity
		self.tweet_fixture = {
			'model': 'hash_to_hash.tweet',
			'pk': 0,
			'fields': {
				'text': '',
				'uid': '',
				'time_zone': '',
				'lat': None,
				'lon': None,
			}
		}
		self.hash_fixture = {
			'model': 'hash_to_hash.hashtag',
			'pk': 0,
			'fields': {
				'text': '',
				'tweet': 0,
			}
		}
		self.competitor_fixture = {
			'model': 'hash_to_hash.competitors',
			'pk': 0,
			'fields': {
				'tag1': 0,
				'tag2': 0,
				'votes': 0
			}
		}
		self.competitors = Competitors.objects.all()
		self.hashtags = Hashtag.objects.all()

	def tweet_generator(self):
		"""
		A generator that turns the JSON in the infile to ParsedTweet objects, one line/object at a time.
		:return: ParsedTweet objects.
		"""
		with open(self.infile) as f:
			lines = f.readlines()
		i = 0
		while i < len(lines):
			try:
				yield ParsedTweet(json.loads(lines[i])[0], json.loads(lines[i])[1])
				i += 1
			except StopIteration:
				break
				print "{0} tweets processed".format(i)

	def parse_tweet(self, tweet):
		"""
		Creates a tweet fixture from a ParsedTweet object, making sure the pks are updated.
		Also calls parse_hash for each hashtag in the tweet.
		:param tweet: the tweet to process.
		:type tweet: ParsedTweet object.
		"""
		tweet_fixture = self.tweet_fixture
		tweet_fixture['pk'] = self.tweet_i
		tweet_fixture['fields']['text'] = tweet.get_munged_text()
		tweet_fixture['fields']['uid'] = tweet.get_meta('id')
		tweet_fixture['fields']['time_zone'] = tweet.get_meta('time_zone')
		try:
			tweet_fixture['fields']['lat'] = tweet.get_coordinates()[1]
			tweet_fixture['fields']['lon'] = tweet.get_coordinates()[0]
		except TypeError:
			pass
		if self.verbosity:
			print tweet_fixture
		self.fixtures.append(tweet_fixture)
		for tag in tweet.get_hashes():
			self.parse_hash(tag)
		self.tweet_i += 1

	def tweet_to_db(self, tweet):
		"""
		Creates a Tweet object from a ParsedTweet object and saves it to the database.
		"""
		try:
			lat = tweet.get_coordinates()[1]
			lon = tweet.get_coordinates()[0]
		except TypeError:
			lat = None
			lon = None
		t = Tweet(id=self.tweet_i,
		          text=tweet.text,
		          munged_text=tweet.munged_text,
		          uid=tweet.get_uid(),
		          time_zone=tweet.get_meta('time_zone'),
		          lat=lat,
		          lon=lon)
		try:
			t.save()
			for hashtag in tweet.get_hashes():
				self.hashtag_to_db(hashtag, t)
		except IntegrityError:
			self.tweet_i += 1
			self.tweet_to_db(tweet)
		else:
			self.tweet_i += 1


	def parse_hash(self, tag):
		"""
		Creates a hashtag fixture from a hashtag, making sure the pks are updated.
		Also adds the hashtag to .competitors for later processing.
		:param tag: the text of the hashtag to process.
		:type tag: string.
		"""
		hash_fixture = self.hash_fixture
		hash_fixture['pk'] = self.hash_i
		hash_fixture['fields']['text'] = tag
		hash_fixture['fields']['tweet'] = self.tweet_i
		self.fixtures.append(hash_fixture)
		if self.verbosity:
			print hash_fixture
		self.competitors.append(tag)
		self.hash_i += 1

	def hashtag_to_db(self, hashtag, tweet):
		"""
		Creates and saves Hashtag objects to the database.
		:param hashtag: the text of the hashtag
		:type hashtag: string
		:param tweet: the Tweet object associated with the hashtag
		:type tweet: Tweet object (see tweet_to_db, above)
		NB: While you probably could call this method directly, it's much less messy
		to let tweet_to_db call it instead.
		"""
		h = Hashtag(id=self.hash_i, text=hashtag)
		try:
			h.save()
			h.tweet.add(tweet)
		except IntegrityError:
			self.hash_i += 1
			self.hashtag_to_db(hashtag, tweet)
		else:
			self.hash_i += 1

	def parse_competitors(self, competitor1, competitor2):
		"""
		Creates a competitor set fixture from two hashtags.
		:param competitor1: a hashtag.
		:type competitor1: text.
		:param competitor2: a different hashtag.
		:type competitor2: text.
		"""
		competitor_fixture = self.competitor_fixture
		competitor_fixture['pk'] = self.competitors_i
		competitor_fixture['fields']['tag1'] = competitor1
		competitor_fixture['fields']['tag2'] = competitor2
		if self.verbosity:
			print competitor_fixture
		self.fixtures.append(competitor_fixture)
		self.competitors_i += 1

	#	  def competitors_to_db(self, competitor1, competitor2):
	#		  comps = Competitors(id=self.competitors_i, tag1=competitor1, tag2=competitor2, yes=0, no=0)
	#		  comps.save()
	#		  self.competitors_i += 1

	def serialize_tweets(self):
		"""
		Creates fixtures for all tweets read from the infile.
		"""
		for tweet in self.tweet_generator():
			self.parse_tweet(tweet)

	def serialize_competitors(self):
		"""
		Creates fixtures for all competitors in .competitors.
		"""
		while self.competitors:
			competitor1 = self.competitors.pop()
			for competitor in self.competitors:
				if competitor1 != competitor:
					self.parse_competitors(competitor1, competitor)

	def tweets_to_db(self):
		"""
		Iterates through .tweet_generator and saves all tweets to the database.
		"""
		for tweet in self.tweet_generator():
			self.tweet_to_db(tweet)

	def __save_comps__(self, tag1, tag2):
		"""
		Creates and saves a Competitors object to the database. Helper method for
		competitors_to_db to prevent IntegrityErrors caused by duplicate
		primary keys.
		:param tag1: the first hashtag in the pair
		:type tag1: Hashtag object (see hashtag_to_db, above)
		:param tag2: the second hashtag
		:type tag2: Hashtag object
		"""
		if not self.competitors.filter(tag1__id=tag1.pk).filter(tag2__id=tag2.pk):
			try:
				comps = Competitors(id=self.competitors_i,
				                    tag1=tag1,
				                    tag2=tag2,
				                    yes=0,
				                    no=0)
				comps.save()
			except IntegrityError:
				self.competitors_i += 1
				self.save_comps(tag1, tag2)
			else:
				self.competitors_i += 1


	def competitors_to_db(self, start=1):
		i = start
		while True:
			try:
				tag1 = self.hashtags.get(pk=i)
				j = i + 1
				while True:
					try:
						tag2 = self.hashtags.get(pk=j)
						self.__save_comps__(tag1, tag2)
						j += 1
					except Hashtag.DoesNotExist:
						break
				i += 1
			except Hashtag.DoesNotExist:
				break

	def add_new_competitor(self, tweet):
		self.tweet_to_db(tweet)
		tags = Hashtag.objects.filter(tweet__pk=self.tweet_i)
		for tag in tags:
			j  = 1
			while True:
				try:
					tag2 = self.hashtags.get(pk=j)
					self.__save_comps__(tag, tag2)
					j += 1
				except Hashtag.DoesNotExist:
					break

	def write_fixtures(self):
		"""
		Writes all of the fixtures in .fixtures to the outfile.
		"""
		with open(self.outfile, "w") as f:
			json.dump(self.fixtures, f)
		if self.verbosity:
			print "Wrote {} tweets, {} hashtags, and {} competitors to {}".format(self.tweet_i, self.hash_i,
			                                                                      self.competitors_i)


def json_to_db(infile):
	"""
	Creates a Twitterator object from a JSON file and saves the ParsedTweet objects, hashtags,
	and competitor pairs to the database.
	:param infile: the path to the JSON file.
	:type infile: string
	"""
	t = Twitterator(infile)
	t.tweets_to_db()
	t.competitors_to_db()


def json_to_parsed(infile, maximum=None):
	"""
	Reads a JSON file and creates ParsedTweet objects from the data.
	:param infile: the name of the file containing the JSON data.
	:type infile: string.
	:param maximum: the maximum number of tweets to be processed. If None, all the tweets in the file
	will be read.
	:type maximum: integer.
	:return: list of ParsedTweet objects.
	"""
	with open(infile) as f:
		l = f.readlines()
	limit = maximum or len(l)
	tweets = []
	for x in l[:limit]:
		try:
			ParsedTweet(json.loads(x)[0], json.loads(x)[1])
		except ValueError:
			continue
	return tweets


def to_json(tweets, outfile):
	"""
	Turns ParsedTweet objects into a JSON file, with one ParsedTweet object per line.
	:param tweets: the ParsedTweet objects to be encoded.
	:type tweets: list of ParsedTweet objects.
	:param outfile: the file to which to write the JSON-encoded objects.
	:type outfile: string.
	"""
	s = "{}\n".format("\n".join((tweet.to_json() for tweet in tweets)))
	with open(outfile, "a") as f:
		f.write(s)
	print "{} tweets written to {}".format(len(tweets), outfile)


def longitudinal(outfile="tweets6-23.json", interval=3600, limit=1000):
	"""
	Periodically retrieves a certain number of tweets from the Twitter stream.
	:param outfile: the name of the file to which to write the retrieved tweets.
	:type outfile: string.
	:param interval: how long to wait (in seconds) between scraping the stream for more tweets.
	:type interval: integer.
	:param limit: the number of tweets to retrieve at a go.
	:type limit: integer.
	"""
	while True:
		t = Twitterizer(_auth=_AUTH)
		print "getting tweets..."
		tweets = t.get_tweets(limit=limit)
		print "saving tweets"
		to_json(tweets, outfile)
		print "sleeping for {} seconds".format(interval)
		time.sleep(interval)


def longitudinal_to_db(_auth=_AUTH, interval=3600, limit=1000):
	ator = Twitterator()
	while True:
		t = Twitterizer(_auth)
		print "getting tweets..."
		tweets = t.get_tweet_iterator(limit=limit)
		print "saving tweets"
		for tweet in tweets:
			ator.add_new_competitor(tweet)
		print "sleeping for {0} seconds".format(interval)
		time.sleep(interval)


if __name__ == "__main__":
	longitudinal_to_db()
