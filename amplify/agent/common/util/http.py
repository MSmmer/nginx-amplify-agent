# -*- coding: utf-8 -*-
import logging
import time
import ujson
import zlib

import requests

from amplify.agent import Singleton
from amplify.agent.common.context import context

requests.packages.urllib3.disable_warnings()
"""

WHY DO YOU DISABLE THIS WARNING?

We don't want to show you redundant messages.


IS IT A REAL PROBLEM?

No. It is not a real problem.
It's just a notification that urllib3 uses standard Python SSL library.


GIVE ME MORE DETAILS!

By default, urllib3 uses the standard library’s ssl module.
Unfortunately, there are several limitations which are addressed by PyOpenSSL.

In order to work with Python OpenSSL bindings urllib3 needs
requests[security] to be installed, which contains cryptography,
pyopenssl and other modules.

The problem is we CAN'T ship Amplify with built-in OpenSSL & cryptography.
You can install those libs manually and enable warnings back.

More details: https://urllib3.readthedocs.org/en/latest/security.html#pyopenssl

"""


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__credits__ = ["Mike Belov", "Andrei Belov", "Ivan Poluyanov", "Oleg Mamontov", "Andrew Alexeev", "Grant Hulegaard"]
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class HTTPClient(Singleton):

    def __init__(self):
        config = context.app_config
        self.timeout = float(config['cloud']['api_timeout'])
        self.verify_ssl_cert = config['cloud']['verify_ssl_cert']
        self.gzip = config['cloud']['gzip']
        self.session = None
        self.url = None

        self.proxies = config.get('proxies')  # Support old configs which don't have 'proxies' section
        if self.proxies and self.proxies.get('https', '') == '':
            self.proxies = None  # Pass None to trigger requests default scraping of environment variables

        self.update_cloud_url()

        logging.getLogger("requests").setLevel(logging.WARNING)

    def update_cloud_url(self):
        config = context.app_config
        content_type = 'binary/octet-stream' if self.gzip else 'application/json'
        self.url = '%s/%s' % (config['cloud']['api_url'], config['credentials']['api_key'])
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': content_type,
            'User-Agent': 'nginx-amplify-agent/%s' % context.version
        })

    def make_request(self, location, method, data=None, timeout=None, json=True, log=True):
        url = location if location.startswith('http') else '%s/%s' % (self.url, location)
        timeout = timeout if timeout is not None else self.timeout
        payload = ujson.encode(data) if data else '{}'
        payload = zlib.compress(payload, self.gzip) if self.gzip else payload

        start_time = time.time()
        result, http_code = '', 500
        try:
            if method == 'get':
                r = self.session.get(
                    url,
                    timeout=timeout,
                    verify=self.verify_ssl_cert,
                    proxies=self.proxies
                )
            else:
                r = self.session.post(
                    url,
                    data=payload,
                    timeout=timeout,
                    verify=self.verify_ssl_cert,
                    proxies=self.proxies
                )
            http_code = r.status_code
            r.raise_for_status()
            result = r.json() if json else r.text
            return result
        except Exception as e:
            if log:
                context.log.error('failed %s "%s", exception: "%s"' % (method.upper(), url, e.message))
                context.log.debug('', exc_info=True)
            raise e
        finally:
            end_time = time.time()
            log_method = context.log.info if log else context.log.debug
            context.log.debug(result)
            log_method(
                "%s %s %s %s %s %.3f" % (method, url, http_code, len(payload), len(result), end_time - start_time)
            )

    def post(self, url, data=None, timeout=None, json=True):
        return self.make_request(url, 'post', data=data, timeout=timeout, json=json)

    def get(self, url, timeout=None, json=True, log=True):
        return self.make_request(url, 'get', timeout=timeout, json=json, log=log)


def resolve_uri(uri):
    """
    Resolves uri if it's not absolute

    :param uri: str uri
    :return: str url
    """
    if not(uri.startswith('http://') or uri.startswith('https://')):
        return '127.0.0.1%s' % uri
    else:
        return uri
