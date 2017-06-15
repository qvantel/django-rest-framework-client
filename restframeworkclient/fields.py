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
import copy
import datetime
import urlparse

import dateutil.parser
from django.utils.functional import curry

from restframeworkclient.filtering import PartiallyFiltered
from restframeworkclient.utils import ObjRef, lookup_by_objref, setattr_lazy


class ModelPropertyMixin(object):
    """
    Allows for specifying model in __init__ as string to avoid circular imports
    """
    def __init__(self, model):
        if isinstance(model, basestring):
            # The attribute _objref may be set in the ModelBase metaclass later
            # to provide module information as well
            self._objref = ObjRef(name=model, module=None)
            self._model = None
        else:
            self._model = model
            self._objref = None

    def contribute_to_class(self, cls, name):
        field = super(ModelPropertyMixin, self)
        if hasattr(field, 'contribute_to_class'):
            field.contribute_to_class(cls, name)

        # Allow specifying models as strings with path to a model class relative to the model's module
        if self._objref is not None:
            self._objref = ObjRef(name=self._objref.name,
                                  module=cls.__module__)

    @property
    def model(self):
        if self._model is None and self._objref is not None:
            self._model = lookup_by_objref(self._objref)
        return self._model


class Field(object):
    """
    Base class for all fields that are backed by exactly one field received from server
    """
    def __init__(self, field_name):
        self.field_name = field_name

    def contribute_to_class(self, cls, name):
        # Infer field_name from its attribute name if not provided explicitly
        if self.field_name is None:
            self.field_name = name

    def _cache_key(self):
        return '_cached_instance_%s' % self.field_name

    def __set__(self, instance, value):
        if self.field_name not in instance._original_attrs.keys():
            instance._original_attrs[self.field_name] = value
        if isinstance(value, (dict, list, tuple)):
            instance._attrs[self.field_name] = copy.deepcopy(value)
        else:
            instance._attrs[self.field_name] = value

        # Invalidate cache
        if hasattr(instance, self._cache_key()):
            delattr(instance, self._cache_key())

    def __get__(self, instance, owner):
        if not instance:
            return self
        return instance._attrs[self.field_name]


class Reference(ModelPropertyMixin, Field):
    """
    To be used as a class attribute for automatic dereferencing of individual instances.
    """
    def __init__(self, model, field_name=None, related_name=None, one_to_one=False):
        """
        :param field_name: mandatory if used outside of a class definition.
        """
        ModelPropertyMixin.__init__(self, model)
        Field.__init__(self, field_name)
        self.related_name = related_name
        self.one_to_one = one_to_one

    def __get__(self, instance, owner):
        if not instance:
            return self
        if not hasattr(instance, self._cache_key()):
            value = instance._attrs[self.field_name]
            from restframeworkclient.models import Model
            if isinstance(value, Model):
                return value
            if isinstance(value, dict):
                obj = self.model(**value)
                obj._persisted = True
                return obj
            pk = value
            if pk is None:
                return None
            setattr(instance, self._cache_key(), self.model.objects.get(pk=pk))
        return getattr(instance, self._cache_key())

    def contribute_to_class(self, cls, name):
        super(Reference, self).contribute_to_class(cls, name)

        # Create ReverseReference in the opposite direction unless related_name ends with '+'
        if not self.related_name or not self.related_name.endswith('+'):
            related_name = self.related_name or '%s_set' % cls.__name__.lower()
            reverse_reference = ReverseReference(cls, field_name=self.field_name, one_to_one=self.one_to_one)
            setattr_lazy(lambda objref=self._objref: lookup_by_objref(objref),
                         related_name, reverse_reference)

        # Allow direct access to the reference without fetching the instance from the server first
        getter = property(curry(self.foo_id_getter, field=self))
        setter = getter.setter(curry(self.foo_id_setter, field=self))
        setattr(cls, '%s_id' % self.field_name, setter)

    def foo_id_getter(self, instance, field):
        # Currently assumes references consists of primary keys and not URLs
        value = instance._attrs[field.field_name]
        from restframeworkclient.models import Model
        if isinstance(value, Model):
            return value.pk
        return value

    def foo_id_setter(self, instance, value, field):
        # Currently assumes references consists of primary keys and not URLs
        if field.field_name not in instance._original_attrs.keys():
            instance._original_attrs[field.field_name] = value
        instance._attrs[field.field_name] = value

    @property
    def field(self):
        """
        Getting model class from the reference the Django ORM way
        to enable code reuse that works both with Django ORM and restframeworkclient
        """
        class RelatedForeignKeyField(object):
            class related(object):
                parent_model = self.model
            class rel(object):
                to = self.model
        return RelatedForeignKeyField()


class ReverseReference(ModelPropertyMixin, Field):
    """
    Useful when specifying generic relations or
    when there is a need to return a collection of instances using a custom server-side filter or filters
    based on a instance of a different type.

    This is also created automatically for each Reference unless Reference.related_name contains '+'.
    """
    def __init__(self, model, field_name, filters=None, one_to_one=False):
        ModelPropertyMixin.__init__(self, model)
        Field.__init__(self, field_name)
        self.filters = filters
        self.one_to_one = one_to_one

    def contribute_to_class(self, cls, name):
        super(ReverseReference, self).contribute_to_class(cls, name)
        self._attr_name = name

    def __get__(self, instance, owner):
        if not instance:
            return self
        params = {}
        if self.filters:
            params.update(self.filters)
        if self.one_to_one:
            params[self.field_name] = instance.pk
            cache_key = '_cached_instance_%s' % self.field_name
            if not hasattr(instance, cache_key):
                setattr(instance, cache_key, self.model.objects.get(**params))
            return getattr(instance, cache_key)
        else:
            partially_filtered = getattr(instance, '_partially_filtered', None)
            if partially_filtered and \
                    self._attr_name in partially_filtered._prefetch_related:
                cache_key = '_prefetch_related_results_%s' % self._attr_name
                if not hasattr(partially_filtered, cache_key):
                    prefetch_related_ids = [obj.pk for obj in partially_filtered]
                    params['%s__in' % self.field_name] = prefetch_related_ids
                    multiplexed_results = PartiallyFiltered(_model=self.model, **params)
                    setattr(partially_filtered, cache_key, multiplexed_results)
                multiplexed_results = getattr(partially_filtered, cache_key)

                class DemultiplexingPartiallyFiltered(PartiallyFiltered):
                    def _results(that):
                        results = [obj for obj in multiplexed_results
                                   if getattr(obj, '%s_id' % self.field_name) == instance.pk]
                        return results

                return DemultiplexingPartiallyFiltered(_model=self.model, **params)
            else:
                params[self.field_name] = instance.pk
                return PartiallyFiltered(_model=self.model, **params)

    @property
    def related(self):
        """
        Getting model class from the reference the Django ORM way
        to enable code reuse that works both with Django ORM and restframeworkclient
        """
        class RelatedObject(object):
            related_model = self.model
        return RelatedObject()


class DateTimeField(Field):
    """
    Parses string attributes as datetime.datetime objects
    """
    def __init__(self, field_name=None):
        Field.__init__(self, field_name)

    def __get__(self, instance, owner):
        if not instance:
            return self
        value = instance._attrs[self.field_name]
        if isinstance(value, datetime.datetime):
            return value
        return dateutil.parser.parse(value) if value else value


class DateField(Field):
    """
    Parses string attributes as datetime.date objects
    """
    def __init__(self, field_name=None):
        Field.__init__(self, field_name)

    def __get__(self, instance, owner):
        if not instance:
            return self
        value = instance._attrs[self.field_name]
        if isinstance(value, datetime.date):
            return value
        return dateutil.parser.parse(value).date() if value else None


class TimeField(Field):
    """
    Parses string attributes as datetime.time objects
    """
    def __init__(self, field_name=None):
        Field.__init__(self, field_name)

    def __get__(self, instance, owner):
        if not instance:
            return self
        value = instance._attrs[self.field_name]
        if isinstance(value, datetime.time):
            return value
        return dateutil.parser.parse(value).time() if value else None


class FileField(Field):
    """
    This field tries to mimick Django ORM's FileField
    """
    def __init__(self, field_name=None):
        Field.__init__(self, field_name)

    @property
    def url(self):
        url = self.instance._attrs[self.field_name]
        if not urlparse.urlparse(url).path.startswith('/'):
            # It looks like server is sending just the name, probably due to UPLOADED_FILES_USE_URL set to False
            # or individually as serializers.FileField(use_url=False)
            return '/%s' % url
        return url

    def __get__(self, instance, owner):
        self.instance = instance
        return self


def _get_model_by_content_type(content_type, default=None):
    from restframeworkclient import models
    for model in models.all_models:
        if hasattr(model, 'Meta') and getattr(model.Meta, 'content_type', None) == content_type:
            return model
    return default


class GenericRelationField(object):
    """
    Represents instance of generic relation. Requires two additional
    fields, one for content_type storage and one for object_id storage.
    """

    def __init__(self, content_type_field, object_id_field):
        self.content_type_field = content_type_field
        self.object_id_field = object_id_field

    def __get__(self, instance, owner):
        if not instance:
            return self
        model = _get_model_by_content_type(getattr(instance, self.content_type_field).value)
        if model:
            return model.objects.get(pk=getattr(instance, self.object_id_field))
        else:
            raise ValueError('Content type "%s" not found in meta of any client model.',
                             self.content_type_field)

    def __set__(self, instance, value):
        instance._original_attrs[self.content_type_field] = value.Meta.content_type
        instance._original_attrs[self.object_id_field] = value.pk
        instance._attrs[self.content_type_field] = value.Meta.content_type
        instance._attrs[self.object_id_field] = value.pk


class ContentTypeField(Field):
    """
    This field tries to mimick Django ORM's ContentType instances
    without the need to fetch them from server as the model and app_label was already provided
    in the descriptive string instead of the ContentType primary key.
    """
    def __init__(self, field_name=None):
        Field.__init__(self, field_name)

    @property
    def value(self):
        return self.instance._attrs[self.field_name]

    @property
    def model(self):
        return self.value.split('_')[1]

    @property
    def app_label(self):
        return self.value.split('_')[0]

    def __get__(self, instance, owner):
        self.instance = instance
        return self
