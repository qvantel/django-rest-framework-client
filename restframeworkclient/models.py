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
import repr
import copy
import json
import six
import logging
import urlparse
import datetime
import threading
import requests
import collections

import rest_framework.response
from rest_framework.test import APIClient
from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from django.utils.text import camel_case_to_spaces

from restframeworkclient import fields
from restframeworkclient.exceptions import FieldTypeMismatch, NotPersistedError, BadGatewayResponse, \
    ServerResponseException, NoneValueInParams, ConflictRespose, BadRequestResponse
from restframeworkclient.filtering import PartiallyFiltered
from restframeworkclient.middleware import get_request
from restframeworkclient.utils import lookup_by_name, qualname, extend_url_query_string, setattr_lazy_finish

logger = logging.getLogger(__name__)

all_models = set()

_thread_local = threading.local()

DynamicField = collections.namedtuple('DynamicField', ['name'])


class Manager(object):
    """
    Similar to django.db.models.Manager
    """
    def __get__(self, instance, owner):
        """
        Return a PartiallyFiltered instance if used as a class attribute
        """
        self.model = owner
        return self.get_queryset()

    def get_queryset(self):
        class ManagerPartiallyFiltered(PartiallyFiltered):
            def __getattr__(this, item):
                return getattr(self, item)
        return ManagerPartiallyFiltered(_model=self.model)


class Meta(object):
    """
    Provides a subset of Django ORM's Model._meta API
    """
    def __get__(self, instance, owner):
        class Options(object):
            model = owner
            object_name = owner.__name__
            model_name = owner.__name__.lower()
            verbose_name = camel_case_to_spaces(owner.__name__)
            class pk(object):
                @classmethod
                def value_to_string(cls, obj):
                    return str(obj.pk)
        if instance:
            Options.fields = [DynamicField(name=attr) for attr in instance._attrs]
        return Options()


class ModelBase(type):
    """
    Metaclass for the Model defined later
    """
    def __new__(cls, name, bases, attrs):
        new_class = super(ModelBase, cls).__new__(cls, name, bases, attrs)
        all_models.add(new_class)

        class DoesNotExist(Exception):
            pass
        new_class.DoesNotExist = DoesNotExist

        for attr_name, attr in attrs.items():
            if hasattr(attr, 'contribute_to_class'):
                attr.contribute_to_class(new_class, attr_name)

        new_class._init_fields_in_progress = True
        new_class._init_fields()
        del new_class._init_fields_in_progress

        return new_class

    def __getattribute__(self, item):
        if item in ['__dict__', '__bases__', '__name__', '_init_fields_in_progress'] or item in dir(self):
            return super(ModelBase, self).__getattribute__(item)
        if not hasattr(self, '_init_fields_in_progress'):
            setattr_lazy_finish()
        return super(ModelBase, self).__getattribute__(item)


class Model(six.with_metaclass(ModelBase)):
    """
    Similar to the Django ORM's Model class
    """
    objects = Manager()
    _meta = Meta()

    def __init__(self, **kwargs):
        def get_key(key):
            if key == 'pk':
                return self._primary_key()
            return key

        kwargs = {get_key(k): v for k, v in kwargs.items()}
        self._set_initial_attrs(kwargs)

        # _persisted should be always set to True after initializating when the instance
        # is fetched from or saved to remote server
        self._persisted = False

    def _set_initial_attrs(self, attrs):
        """
        Sets the provided dict of attributes while using setattr as much as possible
        so that custom field classes can handle special cases themselves.
        """
        self._original_attrs = copy.deepcopy(attrs)
        self._attrs = copy.deepcopy(attrs)

        for k in attrs.keys():
            if k in dir(self):
                del self._original_attrs[k]
                del self._attrs[k]
                # Let the field set the self._original_attrs and self._attrs by itself
                # See Field.__set__ as a typical example
                setattr(self, k, attrs[k])

    def __getattribute__(self, item):
        if item in ['__dict__', '__class__', '__members__', '__methods__'] or item in dir(self):
            return super(Model, self).__getattribute__(item)
        setattr_lazy_finish()
        if item in dir(self):
            return super(Model, self).__getattribute__(item)
        if item == 'pk':
            return getattr(self, self._primary_key())
        if item in self._attrs:
            return self._attrs[item]
        return super(Model, self).__getattribute__(item)

    def __setattr__(self, key, value):
        if key == '_original_attrs':
            return super(Model, self).__setattr__(key, value)
        is_key_field = isinstance(getattr(self.__class__, key, None), fields.Field)
        is_value_field = isinstance(value, fields.Field)
        if key in self._original_attrs and not (is_key_field or is_value_field):
            self._attrs[key] = value
        else:
            super(Model, self).__setattr__(key, value)

    @classmethod
    def _init_fields(cls):
        """
        Populates any missing fields based on the server-side serializer class
        and warns about any inconsistencies between the serializer
        and fields already defined previously on the model class
        """
        if not hasattr(cls, 'Meta'):
            return
        serializer = getattr(cls.Meta, 'serializer', None)
        if serializer:
            # Simple fields can be easily created automatically with `Field(field_name)`.
            simple_fields = {
                serializers.CharField: fields.Field,
                serializers.IntegerField: fields.Field,
                serializers.DecimalField: fields.Field,
                serializers.FloatField: fields.Field,
                serializers.BooleanField: fields.Field,
                serializers.ReadOnlyField: fields.Field,
                serializers.ChoiceField: fields.Field,
                serializers.DateTimeField: fields.DateTimeField,
                serializers.DateField: fields.DateField,
                serializers.TimeField: fields.TimeField,
                serializers.FileField: fields.FileField,
            }
            for field_name, field in serializer().fields.items():
                # Create simple fields if they are not already present
                for serializer_field_cls, our_field_cls in simple_fields.items():
                    if isinstance(field, serializer_field_cls):
                        if not hasattr(cls, field_name):
                            setattr(cls, field_name, our_field_cls(field_name))
                        elif not isinstance(getattr(cls, field_name), our_field_cls):
                            raise FieldTypeMismatch('%s.%s should be of type %s.' % (qualname(cls), field_name,
                                                                                     qualname(our_field_cls)))
            enable_missing_field_warnings = \
                getattr(settings, 'REST_FRAMEWORK_CLIENT', {}).get('MISSING_FIELD_WARNINGS', False)

            if enable_missing_field_warnings:
                exceptions_settings_key = 'SUPPRESS_MISSING_FIELD_WARNINGS_FOR_TYPES'
                class_names = getattr(settings, 'REST_FRAMEWORK_CLIENT', {}).get(exceptions_settings_key, [])
                exceptions = [
                    lookup_by_name(class_name) for class_name in class_names
                ]
                for field_name, field in serializer().fields.items():
                    if not hasattr(cls, field_name) and \
                            not isinstance(field, tuple(simple_fields)) and \
                            not isinstance(field, tuple(exceptions)):
                        logger.warn('Missing field %s.%s. '
                                    'To suppress warnings of this field type add "%s" to '
                                    'settings.REST_FRAMEWORK_CLIENT["%s"].' % (qualname(cls), field_name,
                                                                               qualname(field.__class__),
                                                                               exceptions_settings_key))
            enable_inconsistent_related_name_warnings = \
                getattr(settings, 'REST_FRAMEWORK_CLIENT', {}).get('INCONSISTENT_RELATED_NAME_WARNINGS', False)

            if enable_inconsistent_related_name_warnings:
                for field_name, field in serializer().fields.items():
                    if isinstance(field, serializers.PrimaryKeyRelatedField) and \
                            hasattr(cls, field_name):
                        django_descriptor = getattr(serializer.Meta.model, field.source)
                        if not hasattr(django_descriptor, 'field'):
                            logger.warn('Found redundant PrimaryKeyRelatedField %s.%s' % (qualname(serializer),
                                                                                          field_name))
                            continue
                        actual = getattr(cls, field_name).related_name

                        desired = django_descriptor.field.rel.related_name
                        if actual != desired:
                            logger.warn('Wrong related_name=%s in %s.%s (was related_name=%s)' % (repr.repr(desired),
                                                                                                  qualname(cls),
                                                                                                  field_name,
                                                                                                  repr.repr(actual)))
            enable_inconsistent_primary_key_warnings = \
                getattr(settings, 'REST_FRAMEWORK_CLIENT', {}).get('INCONSISTENT_PRIMARY_KEY_WARNINGS', False)
            if enable_inconsistent_primary_key_warnings:
                django_primary_key = serializer.Meta.model._meta.pk.name
                if cls._primary_key() != django_primary_key:
                    logger.warn('%s.Meta.primary_key should be %s but is %s' % (qualname(cls),
                                                                                repr.repr(django_primary_key),
                                                                                repr.repr(cls._primary_key())))

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, repr.repr(self._attrs))

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.pk == other.pk

    @property
    def _changes(self):
        return {k: v for k, v in self._attrs.items() if v != self._original_attrs[k]}

    def save(self, update_fields=None):
        """
        Save changes made to a previously fetched instance or persist a new locally created instance.
        """
        if not self._persisted:
            url = self._resources_url()
            data = self._attrs
            json_ = self._rest_call(url, method='POST', data=self._postprocess_data(data))
            self._original_attrs = json_
            self._attrs = copy.deepcopy(json_)
            self._persisted = True
        else:
            url = self._resource_url(self.pk)
            if update_fields:
                data = {k: v for k, v in self._changes.items() if k in update_fields}
                json_ = self._rest_call(url, method='PATCH', data=self._postprocess_data(data))
                self._original_attrs = copy.deepcopy(json_)
                for k in update_fields:
                    self._attrs[k] = json_[k]
            else:
                data = self._changes
                json_ = self._rest_call(url, method='PATCH', data=self._postprocess_data(data))
                self._original_attrs = json_
                self._attrs = copy.deepcopy(json_)
        return self

    def delete(self):
        if not self._persisted:
            raise NotPersistedError("It doesn't make sense to delete non-persisted instances")
        url = self._resource_url(self.pk)
        json_ = self._rest_call(url, method='DELETE')
        return json_

    def refresh_from_db(self):
        """
        Similar to the Django ORM's refresh_from_db (Django 1.8+)
        """
        if not self._persisted:
            raise NotPersistedError("It doesn't make sense to refetch non-persisted instances")
        url = self._resource_url(self.pk)
        json_ = self._rest_call(url, method='GET')
        self._set_initial_attrs(json_)

    @classmethod
    def _postprocess_data(cls, data):
        def get_value(value):
            if isinstance(value, dict):
                return json.dumps(value)
            if value in (datetime.datetime.now, timezone.now):
                return value()
            if isinstance(value, Model):
                return value.pk
            return value
        return {k: get_value(v) for k, v in data.items()}

    @classmethod
    def _check_params_for_none_values(cls, kwargs, url, method):
        for k, v in kwargs['params'].items():
            if v is None:
                raise NoneValueInParams('Found None value in params for REST call {method} {url} {kwargs}'.format(
                    method=method, url=url, kwargs=kwargs)
                )

    @classmethod
    def _rest_call(cls, url, method='GET', **kwargs):
        if 'params' in kwargs and kwargs['params'] is not None:
            cls._check_params_for_none_values(kwargs, url, method)

        request = get_request()
        cache_key = extend_url_query_string(url, kwargs.get('params', {}))
        if request:
            if not hasattr(request, '_restframeworkclient_cache'):
                request._restframeworkclient_cache = {}

            if method.upper() == 'GET':
                if cache_key in request._restframeworkclient_cache:
                    result = request._restframeworkclient_cache[cache_key]
                    logger.debug('(cached) {method} {url} {kwargs}'.format(method=method, url=url, kwargs=kwargs))
                    return result
            else:
                request._restframeworkclient_cache = {}

        result = cls._execute_rest_call(url, method, **kwargs)
        logger.debug('{method} {url} {kwargs}'.format(method=method, url=url, kwargs=kwargs))
        if request and method.upper() == 'GET':
            request._restframeworkclient_cache[cache_key] = result
        return result

    @classmethod
    def _execute_rest_call(cls, url, method, **kwargs):
        if getattr(settings, 'REST_FRAMEWORK_CLIENT', {}).get('USE_LOCAL_REST_FRAMEWORK'):
            return cls._direct_rest_call_to_restframework(url, method, **kwargs)

        if not hasattr(_thread_local, 'session'):
            _thread_local.session = requests.Session()

        response = _thread_local.session.request(method.upper(), url, verify=True, **kwargs)

        cls._handle_response_status_code(response, url, method, **kwargs)

        if response.text:
            return response.json()
        else:
            # e.g. when using DELETE
            return None

    @classmethod
    def _direct_rest_call_to_restframework(cls, url, method, **kwargs):
        """
        Allows for querying the REST Framework directly
        without the need to start multiple django processes and communicating with HTTP.
        It uses the REST Framework ApiClient intended for testing purposes.

        It requires settings.REST_FRAMEWORK_CLIENT['BASE_URLS'] to be set to a dict with keys being url prefixes
        in which the urlconf has the REST Framework urlconf included and dict values being the the base urls
        specified in the Model.Meta.base_url
        """
        client = APIClient()
        params = kwargs.get('params', {}) or {}
        data = kwargs.get('data', {}) or {}

        # Like the requests library, ignore any None values in data
        data = {k: v
                for k, v in data.items()
                if v is not None}

        url = extend_url_query_string(url, params)
        url_parsed = urlparse.urlparse(url)
        path = url_parsed.path + '?' + url_parsed.query

        for api, api_baseurl in settings.REST_FRAMEWORK_CLIENT.get('BASE_URLS').items():
            if url.startswith(api_baseurl):
                path = '/%s%s' % (api, path)
                break

        response = getattr(client, method.lower())(path, data)
        cls._handle_response_status_code(response, url, method, **kwargs)
        return response.data

    @classmethod
    def _handle_response_status_code(cls, response, url, method, **kwargs):
        if not (200 <= response.status_code < 300):
            if isinstance(response, requests.models.Response):
                reason = response.reason
                content = response.content
            elif isinstance(response, rest_framework.response.Response):
                reason = response.reason_phrase
                content = response.data
            else:  # Probably django.http.response.HttpResponseNotFound
                reason = response.reason_phrase
                content = response.content
            message = '{status_code} {reason}\n{method} {url} {kwargs}\n{content}'.format(
                method=method, url=url, kwargs=kwargs,
                status_code=response.status_code,
                reason=reason, content=content,
            )
            if response.status_code == 400:
                exception_class = BadRequestResponse
            elif response.status_code == 404:
                exception_class = cls.DoesNotExist
            elif response.status_code == 502:
                exception_class = BadGatewayResponse
            elif response.status_code == 409:
                exception_class = ConflictRespose
            else:
                exception_class = ServerResponseException
            exception = exception_class(message)
            exception.response = response
            raise exception

    @classmethod
    def _primary_key(cls):
        return getattr(cls.Meta, 'primary_key', None) or 'id'

    @classmethod
    def _base_url(cls):
        return getattr(cls.Meta, 'base_url', None) or settings.REST_FRAMEWORK_CLIENT['DEFAULT_BASE_URL']

    @classmethod
    def _resources_url(cls):
        return '%s/%s/' % (cls._base_url(), cls.Meta.resource)

    @classmethod
    def _resource_url(cls, pk):
        return '%s/%s/%s/' % (cls._base_url(), cls.Meta.resource, pk)
