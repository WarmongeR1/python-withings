# -*- coding: utf-8 -*-
#
"""
Python library for the Withings API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Withings Body metrics Services API
<http://www.withings.com/en/api/wbsapiv2>

Uses Oauth 1.0 to authentify. You need to obtain a consumer key
and consumer secret from Withings by creating an application
here: <https://oauth.withings.com/partner/add>

Usage:

auth = WithingsAuth(CONSUMER_KEY, CONSUMER_SECRET)
authorize_url = auth.get_authorize_url()
print "Go to %s allow the app and copy your oauth_verifier" % authorize_url
oauth_verifier = raw_input('Please enter your oauth_verifier: ')
creds = auth.get_credentials(oauth_verifier)

client = WithingsApi(creds)
measures = client.get_measures(limit=1)
print "Your last measured weight: %skg" % measures[0].weight

"""

from __future__ import unicode_literals

__title__ = 'withings'
__version__ = '0.4.0'
__author__ = 'Maxime Bouroumeau-Fuseau'
__license__ = 'MIT'
__copyright__ = 'Copyright 2012 Maxime Bouroumeau-Fuseau'

__all__ = [str('WithingsCredentials'), str('WithingsAuth'), str('WithingsApi'),
           str('WithingsMeasures'), str('WithingsMeasureGroup')]

import arrow
import json
import requests

from arrow.parser import ParserError
from requests_oauthlib import OAuth1, OAuth1Session
from dateutil import tz


class WithingsCredentials(object):
    def __init__(self, access_token=None, access_token_secret=None,
                 consumer_key=None, consumer_secret=None, user_id=None):
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.user_id = user_id


class WithingsAuth(object):
    URL = 'https://oauth.withings.com/account'

    def __init__(self, consumer_key, consumer_secret):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.oauth_token = None
        self.oauth_secret = None

    def get_authorize_url(self, callback_uri=None):
        oauth = OAuth1Session(self.consumer_key,
                              client_secret=self.consumer_secret,
                              callback_uri=callback_uri)

        tokens = oauth.fetch_request_token('%s/request_token' % self.URL)
        self.oauth_token = tokens['oauth_token']
        self.oauth_secret = tokens['oauth_token_secret']

        return oauth.authorization_url('%s/authorize' % self.URL)

    def get_credentials(self, oauth_verifier):
        oauth = OAuth1Session(self.consumer_key,
                              client_secret=self.consumer_secret,
                              resource_owner_key=self.oauth_token,
                              resource_owner_secret=self.oauth_secret,
                              verifier=oauth_verifier)
        tokens = oauth.fetch_access_token('%s/access_token' % self.URL)
        return WithingsCredentials(access_token=tokens['oauth_token'],
                                   access_token_secret=tokens[
                                       'oauth_token_secret'],
                                   consumer_key=self.consumer_key,
                                   consumer_secret=self.consumer_secret,
                                   user_id=tokens['userid'])


class WithingsApi(object):
    URL = 'http://wbsapi.withings.net'

    def __init__(self, credentials):
        self.credentials = credentials
        self.oauth = OAuth1(credentials.consumer_key,
                            credentials.consumer_secret,
                            credentials.access_token,
                            credentials.access_token_secret,
                            signature_type='query')
        self.client = requests.Session()
        self.client.auth = self.oauth
        self.client.params.update({'userid': credentials.user_id})

    def request(self, service, action, params=None, method='GET',
                version=None):
        if params is None:
            params = {}
        params['action'] = action
        url_parts = filter(None, [self.URL, version, service])
        r = self.client.request(method, '/'.join(url_parts), params=params)
        response = json.loads(r.content.decode())
        if response['status'] != 0:
            raise Exception("Error code %s" % response['status'])
        return response.get('body', None)

    def get_user(self):
        return self.request('user', 'getbyuserid')

    def get_activities(self, **kwargs):
        r = self.request('measure', 'getactivity', params=kwargs, version='v2')
        activities = r['activities'] if 'activities' in r else [r]
        return [WithingsActivity(act) for act in activities]

    def get_intradayactivity(self, **kwargs):
        r = self.request('measure', 'getintradayactivity', params=kwargs,
                         version='v2')
        activities = r['activities'] if 'activities' in r else [r]
        return [WithingsIntradayActivity(act) for act in activities]

    def get_sleep_summary(self, **kwargs):
        r = self.request('sleep', 'getsummary', params=kwargs, version='v2')
        return WithingsSleepSummary(r)

    def get_measures(self, **kwargs):
        r = self.request('measure', 'getmeas', kwargs)
        return WithingsMeasures(r)

    def get_sleep(self, **kwargs):
        r = self.request('sleep', 'get', params=kwargs, version='v2')
        return WithingsSleep(r)

    def get_workout(self, **kwargs):
        r = self.request('measure', 'getworkouts', params=kwargs, version='v2')
        return WithingsWorkout(r)

    def subscribe(self, callback_url, comment, **kwargs):
        params = {'callbackurl': callback_url, 'comment': comment}
        params.update(kwargs)
        self.request('notify', 'subscribe', params)

    def unsubscribe(self, callback_url, **kwargs):
        params = {'callbackurl': callback_url}
        params.update(kwargs)
        self.request('notify', 'revoke', params)

    def is_subscribed(self, callback_url, appli=1):
        params = {'callbackurl': callback_url, 'appli': appli}
        try:
            self.request('notify', 'get', params)
            return True
        except:
            return False

    def list_subscriptions(self, appli=1):
        r = self.request('notify', 'list', {'appli': appli})
        return r['profiles']


class WithingsObject(object):
    def __init__(self, data, timezone='UTC'):
        self.set_attributes(data, timezone)

    def set_attributes(self, data, timezone='UTC'):
        self.data = data
        for key, val in data.items():
            try:
                if 'date' in key:
                    attr_value = arrow.get(val)
                    attr_value = attr_value.to(timezone)
                    setattr(self, key, attr_value)
                else:
                    setattr(self, key, val)
            except ParserError:
                setattr(self, key, val)


class WithingsActivity(WithingsObject):
    pass


class WithingsMeasures(list, WithingsObject):
    def __init__(self, data):
        timezone = data.get('timezone', 'UTC')
        super(WithingsMeasures, self).__init__(
            [WithingsMeasureGroup(g, timezone) for g in data['measuregrps']])
        self.set_attributes(data)


class WithingsMeasureGroup(WithingsObject):
    MEASURE_TYPES = (('weight', 1), ('height', 4), ('fat_free_mass', 5),
                     ('fat_ratio', 6), ('fat_mass_weight', 8),
                     ('diastolic_blood_pressure', 9),
                     ('systolic_blood_pressure', 10),
                     ('heart_pulse', 11), ('spo2', 54))

    def __init__(self, data, timezone='UTC'):
        super(WithingsMeasureGroup, self).__init__(data, timezone)
        for n, t in self.MEASURE_TYPES:
            self.__setattr__(n, self.get_measure(t))

    def is_ambiguous(self):
        return self.attrib == 1 or self.attrib == 4

    def is_measure(self):
        return self.category == 1

    def is_target(self):
        return self.category == 2

    def get_measure(self, measure_type):
        for m in self.measures:
            if m['type'] == measure_type:
                return m['value'] * pow(10, m['unit'])
        return None


class WithingsSleepSummary(WithingsObject):
    def __init__(self, data):
        super(WithingsSleepSummary, self).__init__(data)
        self.raw_data = data
        self.series = [WithingsSleepSummarySeries(series) for series in
                       self.series]


class WithingsSleepSummarySeries(WithingsObject):
    def __init__(self, data):
        super(WithingsSleepSummarySeries, self).__init__(data)
        for n in self.data:
            self.__setattr__(n, data['data'][n])
            self.startdate = data['startdate']
            self.enddate = data['enddate']


class WithingsIntradayActivitySeries(WithingsObject):
    def __init__(self, time, data, ):
        self.date = arrow.get(time)
        super(WithingsIntradayActivitySeries, self).__init__(data[time])


class WithingsIntradayActivity(WithingsObject):
    def __init__(self, data):
        super(WithingsIntradayActivity, self).__init__(data)
        self.series = [WithingsIntradayActivitySeries(series, data['series'])
                       for series in self.series]


class WithingsSleepSeries(WithingsObject):
    def __init__(self, data):
        super(WithingsSleepSeries, self).__init__(data)
        self.timedelta = self.enddate - self.startdate


class WithingsSleep(WithingsObject):
    def __init__(self, data):
        super(WithingsSleep, self).__init__(data)
        self.series = [WithingsSleepSeries(series) for series in self.series]


class WithingsWorkout(WithingsObject):
    def __init__(self, data):
        super(WithingsWorkout, self).__init__(data)
        self.series = [WithingsWorkoutSeries(series) for series in self.series]


class WithingsWorkoutSeries(WithingsObject):
    def __init__(self, data):
        super(WithingsWorkoutSeries, self).__init__(data)
        for n in self.data:
            self.__setattr__(n, data['data'][n])
