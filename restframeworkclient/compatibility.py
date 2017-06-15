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
import django
from django.http.response import Http404
from django.forms import model_to_dict as django_model_to_dict
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404 as django_get_object_or_404

from restframeworkclient.filtering import PartiallyFiltered
from restframeworkclient.models import ModelBase, Model


def model_to_dict(instance, fields=None, exclude=None):
    """
    Similar to the model_to_dict of the Django ORM but it supports also instance to be of type restframeworkclient.Model
    """
    if isinstance(instance, Model):
        return {k: v for k, v in instance._attrs.items()
                if (not fields or k in fields) and
                (not exclude or k not in exclude)}
    else:
        result = django_model_to_dict(instance, fields=fields, exclude=exclude)
    return result


def get_content_type_for_model(instance):
    """
    If instance is Django model instance then it returns its ContentType instance.

    If instance is restframeworkclient.Model instance then it returns string stored in its Meta.content_type
    """
    if isinstance(instance, Model):
        return instance.Meta.content_type
    else:
        return ContentType.objects.get_for_model(instance)


def get_object_or_404(klass, *args, **kwargs):
    """
    Similar to django.shortcuts.get_object_or_404 but it also supports klass argument to be of type
    restframework.Model or PartiallyFiltered
    """
    if isinstance(klass, (ModelBase, PartiallyFiltered)):
        partially_filtered = klass if isinstance(klass, PartiallyFiltered) else klass.objects.all()
        model = partially_filtered.model
        try:
            return partially_filtered.get(*args, **kwargs)
        except model.DoesNotExist:
            raise Http404('No %s matches the given query.' % model._meta.object_name)
    else:
        return django_get_object_or_404(klass, *args, **kwargs)


def is_model(obj):
    return isinstance(obj, (django.db.models.Model, Model))
