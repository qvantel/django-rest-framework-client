""""
Django REST Framework client
https://github.com/qvantel/django-rest-framework-client
Copyright (c) 2017, Qvantel
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the Qvantel nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL QVANTEL BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import threading

import django.test

_thread_local = threading.local()


class RESTFrameworkClientCacheMiddleware(object):
    """
    Enables per-request client-side cache for REST API calls.

    Cached key is URL address of the REST API call.
    Only GET requests are cached.
    New webapp requests invalidate the cache.
    Non-GET requests in the same webapp request invalidate the cache.
    The cache is per thread.
    """
    def process_request(self, request):
        if isinstance(request.META['wsgi.input'], django.test.client.FakePayload):
            # Ignore any nested requests caused by settings.REST_FRAMEWORK_CLIENT['USE_LOCAL_REST_FRAMEWORK'] == True
            pass
        else:
            _thread_local.request = request


def get_request():
    """
    Return the current django request from anywhere when RESTFrameworkClientCacheMiddleware is enabled.
    """
    if hasattr(_thread_local, 'request'):
        return _thread_local.request
    return None
