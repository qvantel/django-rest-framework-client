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
import datetime
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from restframeworkclient.fields import ModelPropertyMixin


class Method(ModelPropertyMixin, object):
    """
    Represents a REST subresource in the form /resource/123/subresource/
    Designed to be used for routes decorated with the @detail_route Django REST Framework decorator
    """
    def __init__(self, subresource, method, static=False, as_property=False, unwrapping_key=None, model=None):
        ModelPropertyMixin.__init__(self, model)
        self.subresource = subresource
        self.method = method
        self.static = static
        self.as_property = as_property
        self.unwrapping_key = unwrapping_key

    def __get__(self, instance, owner):
        from restframeworkclient.models import Model

        def callable(**kwargs):
            def get_value(value):
                if isinstance(value, dict):
                    return json.dumps(value, cls=DjangoJSONEncoder)
                if value in (datetime.datetime.now, timezone.now):
                    return value()
                if isinstance(value, Model):
                    return value.pk
                return value

            kwargs = {k: get_value(v) for k, v in kwargs.items()}
            arg_name = 'data' if self.method == 'POST' else 'params'
            if self.static:
                url = owner._resources_url() + self.subresource + '/'
                data = owner._rest_call(url, method=self.method, **{arg_name: kwargs})
            else:
                url = instance._resource_url(instance.pk) + self.subresource + '/'
                data = instance._rest_call(url, method=self.method, **{arg_name: kwargs})
            if self.unwrapping_key:
                data = data[self.unwrapping_key]
            if self.model:
                obj = self.model(**data)
                obj._persisted = True
                return obj
            return data
        return callable() if self.as_property else callable


class StaticMethod(Method):
    """
    Represents a nested REST resource in the form /resource/nested_resource/
    Designed to be used for routes decorated with the @list_route Django REST Framework decorator
    """
    def __init__(self, *args, **kwargs):
        super(StaticMethod, self).__init__(*args, static=True, **kwargs)


class MethodReturningCollection(ModelPropertyMixin, object):
    """
    Similar to Method but it also iterates over the json response and each item
    wraps into model instance.

    The results are cached until you toss the model instance away.

    Use this sparingly.
    ReverseReference with custom filter on the server side is often a better solution.
    """
    def __init__(self, subresource, model, as_property=False):
        ModelPropertyMixin.__init__(self, model)
        self.subresource = subresource
        self.as_property = as_property

    def __get__(self, instance, owner):
        if not instance:
            return self
        def callable():
            cache_key = '_cached_instances_%s' % self.subresource
            if not hasattr(instance, cache_key):
                setattr(instance, cache_key, [])
                url = instance._resource_url(instance.pk) + self.subresource + '/'
                for data in instance._rest_call(url):
                    obj = self.model(**data)
                    obj._persisted = True
                    getattr(instance, cache_key).append(obj)
            return getattr(instance, cache_key)
        return callable() if self.as_property else callable
