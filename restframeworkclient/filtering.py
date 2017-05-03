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

from django.utils import timezone
from django.core.exceptions import MultipleObjectsReturned

from restframeworkclient.utils import Indexable, min_ignoring_nones


class PartiallyFiltered(object):
    """
    Similar to Django ORM's QuerySet.
    Allows for chaining filters one after another.
    Holds partially-formed querystring dictionary to be used for querying later
    together with the information which restframeworkclient.Model to use.
    """
    def __init__(self, _model, **kwargs):
        self.model = _model
        self.params = kwargs
        self._prefetch_related = []

    def _copy(self):
        partially_filtered = self.__class__(_model=self.model, **self.params.copy())
        partially_filtered._prefetch_related = self._prefetch_related
        return partially_filtered

    def filter(self, **kwargs):
        """
        :param kwargs: fields to be used for filtering
         You can also pass Model instances as values directly which will have the same effect as passing their pk attribute.
        """
        partially_filtered = self._copy()
        partially_filtered.params.update(kwargs)
        return partially_filtered

    def exclude(self, **kwargs):
        """
        Behaves like filter but prefixes the parameter with `exclude__` prefix.
        There must be such filter defined in Django REST Framework.

        `exclude(param='value')` and `filter(exclude__param='value')` will behave the same.

        :param kwargs: at most one parameter is allowed but chaining exclude calls is supported.
         Keep in mind that `exclude(a=1).exclude(b=2)` and `exclude(a=1, b=2)` in Django ORM may produce different results.
         Create a custom filter in Django REST Framework to implement similar functionality to `exclude(a=1, b=2)`.
         Note also that `exclude(value__gt=value)` is not equivalent to `filter(value__lte=value)`
         in Django ORM in case NULL values are also allowed.
        """
        if len(kwargs.keys()) > 1:
            raise ValueError('exclude can take at most one kwargs parameter')
        kwargs = {'exclude__%s' % k: v for k, v in kwargs.items()}
        partially_filtered = self._copy()
        partially_filtered.params.update(kwargs)
        return partially_filtered

    def all(self):
        """
        Similar to the Django ORM's QuerySet.all
        """
        return self

    def none(self):
        """
        Similar to the Django ORM's QuerySet.none
        """
        partially_filtered = self._copy()
        partially_filtered.params['__none__'] = True
        return partially_filtered

    def get(self, **kwargs):
        """
        Similar to the Django ORM's QuerySet.get
        :param kwargs: it supports the same kwargs as filter does
        """
        params = self.params.copy()
        params.update(kwargs)
        params = self._preprocess_filter_params(params)
        pk = self.model._primary_key()
        if set(params) - {'select_related'} == {pk}:
            url = self.model._resource_url(params[pk])
            del params[pk]
            if params:
                result = self.model._rest_call(url, params=params)
            else:
                result = self.model._rest_call(url)
        else:
            url = self.model._resources_url()
            params['limit'] = 1
            json_ = self.model._rest_call(url, params=params)
            count = json_['count']
            if count == 0:
                raise self.model.DoesNotExist(
                    "%s matching query does not exist." % self.model.__name__
                )
            if count >= 2:
                raise MultipleObjectsReturned(
                    "get() returned more than one %s -- it returned %d!" % (self.model.__name__, count)
                )
            result = json_['results'][0]
        obj = self.model(**result)
        obj._persisted = True
        return obj

    def get_or_create(self, **kwargs):
        """
        Similar to the Django ORM's QuerySet.get_or_create
        """
        try:
            return self.get(**kwargs), False
        except self.model.DoesNotExist:
            return self.create(**kwargs), True

    def first(self):
        """
        Similar to the Django ORM's QuerySet.first
        """
        try:
            return self.filter(limit=1)[0]
        except IndexError:
            return None

    def last(self):
        """
        Similar to the Django ORM's QuerySet.last
        """
        def inverse(ordering_field):
            """
            removes `-` prefix from the ordering_field string otherwise
            prepends `-` to the ordering_field string if there is no such prefix
            """
            if ordering_field.startswith('-'):
                return ordering_field[1:]
            return '-%s' % ordering_field
        ordering = ','.join(
            [inverse(ordering_field) for ordering_field in
             self.params.get('ordering', self.model._primary_key()).split(',')]
        )
        return self.filter(ordering=ordering).first()

    def earliest(self, field_name=None):
        """
        Similar to the Django ORM's QuerySet.earliest
        """
        ordering = field_name or self.model.Meta.get_latest_by
        instance = self.filter(ordering=ordering).first()
        if instance is None:
            raise self.model.DoesNotExist(
                "%s matching query does not exist." % self.model.__name__
            )
        return instance

    def latest(self, field_name=None):
        """
        Similar to the Django ORM's QuerySet.latest
        """
        ordering = field_name or self.model.Meta.get_latest_by
        instance = self.filter(ordering=ordering).last()
        if instance is None:
            raise self.model.DoesNotExist(
                "%s matching query does not exist." % self.model.__name__
            )
        return instance

    def exists(self):
        """
        Similar to the Django ORM's QuerySet.exists
        """
        return bool(self.filter(limit=1).first())

    def count(self):
        """
        Similar to the Django ORM's QuerySet.count
        """
        url = self.model._resources_url()
        params = self._preprocess_filter_params(self.params)
        params['limit'] = 1
        json_ = self.model._rest_call(url, params=params)
        return json_['count']

    def new(self, **kwargs):
        params = self.params.copy()
        params.update(kwargs)
        return self.model(**params)

    def create(self, **kwargs):
        """
        Similar to the Django ORM's QuerySet.create
        """
        obj = self.new(**kwargs)
        return obj.save()

    def add(self, instance):
        obj = instance
        params = self._preprocess_filter_params(self.params)
        obj._attrs.update(params)
        return obj.save()

    def order_by(self, *fields):
        """
        Similar to the Django ORM's QuerySet.order_by
        Specify ordering fields as a strings with minus sign denoting descending ordering
        e.g. ordering='name', '-account' would order by name ascending and then by account descending
        (It assumes Django REST Framework is configured with ordering support enabled.
        It uses 'ordering' query parameter')
        """
        partially_filtered = self._copy()
        partially_filtered.params['ordering'] = ','.join(fields)
        return partially_filtered

    def select_related(self, *fields):
        """
        Similar to the Django ORM's QuerySet.select_related
        """
        if 'select_related' in self.params:
            fields = self.params['select_related'].split(',') + list(fields)
        partially_filtered = self._copy()
        partially_filtered.params['select_related'] = ','.join(fields)
        return partially_filtered

    def prefetch_related(self, *fields):
        """
        Similar to the Django ORM's QuerySet.select_related

        Currently it doesn't support Prefetch objects nor chaining syntax with `__`.
        """
        partially_filtered = self._copy()
        partially_filtered._prefetch_related.extend(fields)
        return partially_filtered

    def _preprocess_filter_params(self, params):
        from restframeworkclient.models import Model

        def get_key(key):
            if key == 'pk':
                return self.model._primary_key()
            if key.endswith('__pk'):
                return key[:-4]
            return key

        def get_value(value):
            if value in (datetime.datetime.now, timezone.now):
                return value()
            if isinstance(value, Model):
                return value.pk
            return value

        # Ensure .filter(something=[]) behaves like .none() instead of .all() except for exclude__ prefixed filters
        if any((value in ([], ()) and not key.startswith('exclude__') for key, value in params.items())):
            params['__none__'] = True

        return {get_key(key): get_value(value) for key, value in params.items()}

    def _fetch_results(self, **kwargs):
        kwargs = self._preprocess_filter_params(kwargs)
        if kwargs.get('__none__'):
            return []
        url = self.model._resources_url()
        json_ = self.model._rest_call(url, params=kwargs)
        def generator(json_):
            while True:
                for result in json_['results']:
                    obj = self.model(**result)
                    obj._persisted = True
                    obj._partially_filtered = self
                    yield obj
                if not json_['next']:
                    break
                json_ = self.model._rest_call(json_['next'])
        results = Indexable(generator(json_))
        if 'limit' in kwargs:
            # Effectively ignores any next pages
            results = results[:kwargs['limit']]
        return results

    def _results(self):
        """
        Don't access self._cached_results from any other place
        in order for this class to remain flexible in regard to working with underlying data by overriding it in subclasses
        """
        if not hasattr(self, '_cached_results'):
            self._cached_results = self._fetch_results(**self.params)
        return self._cached_results

    def __getitem__(self, index):
        """
        The server side must have rest_framework.pagination.LimitOffsetPagination enabled
        so that correct results are returned
        """
        previous_offset = self.params.get('offset', 0)
        previous_limit = self.params.get('limit', None)
        params = {}
        try:
            start = index.start or 0
            offset = previous_offset + start
            if offset != 0:
                params['offset'] = offset

            limit = min_ignoring_nones(previous_limit, index.stop)
            if limit is not None:
                limit -= start
                params['limit'] = limit

            if index.step and index.step > 1:
                results = self.filter(**params)._results()
                return results.__getitem__(slice(0, limit, index.step))
            return self.filter(**params)
        except AttributeError:
            offset = previous_offset + index
            if offset != 0:
                params['offset'] = offset
            params['limit'] = 1
            results = self.filter(**params)._results()
            try:
                return results.__getitem__(0)
            except IndexError:
                return None

    def __nonzero__(self):
        return bool(self._results())

    def __iter__(self):
        return self._results().__iter__()

    def __repr__(self):
        return self._results().__repr__()

    def __len__(self):
        return list(self._results()).__len__()
