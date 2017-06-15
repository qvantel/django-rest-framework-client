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
import pydoc
import logging
import collections
import threading
import itertools
import urllib
import urlparse

ObjRef = collections.namedtuple('ObjRef', ['name', 'module'])


def qualname(cls):
    """
    Similar to the Python 3.3+ __qualname__ attribute.
    >>> qualname(C)
    'C'
    >>> qualname(C.f)
    'C.f'
    >>> qualname(C.D)
    'C.D'
    >>> qualname(C.D.g)
    'C.D.g'
    """
    return '%s.%s' % (cls.__module__, cls.__name__)


def lookup_by_name(class_name):
    """
    Imports an object by name or dotted path.
    """
    obj = pydoc.locate(class_name)
    if obj is None:
        raise ImportError('Unable to import "%s"' % (class_name))
    return obj


def lookup_by_objref(objref):
    """
    Imports an object by an ObjRef object.

    If ObjRef object also contains module attribute, it will also attempt to relative import from it
    when absolute import was not successful.
    """
    obj = pydoc.locate(objref.name)
    if obj is None:
        if objref.module is None:
            raise ImportError('Unable to import "%s"' % (objref.name))
        path = '.'.join([objref.module, objref.name])
        obj = pydoc.locate(path)
        if obj is None:
            raise ImportError('Unable to import "%s" nor "%s"' % (objref.name, path))
    return obj


class Indexable(object):
    """
    Indexable generator wrapper.

    Allows accessing individual items from a generator via indexes and slices.
    Computed items are cached so they can be accessed multiple times.

    Negative indexes are not supported.

    Example:
    >>> def generator():
    ...     i = 0
    ...     while True:
    ...         yield i
    ...         i += 1
    ...
    >>> generator()[0]
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    TypeError: 'generator' object has no attribute '__getitem__'
    >>> Indexable(generator())[0]
    0
    >>> Indexable(generator())[10:20:2]
    [10, 12, 14, 16, 18]
    >>> Indexable(generator())
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, '...(remaining elements truncated)...']

    See http://stackoverflow.com/a/2322711/682025
    """
    def __init__(self, it):
        self.it = iter(it)
        self.already_computed = []

    def __iter__(self):
        already_computed_it = iter(self.already_computed)
        try:
            while True:
                if already_computed_it.__length_hint__() == 0:
                    item = next(self.it)
                    self.already_computed.append(item)
                yield next(already_computed_it)
        except StopIteration:
            pass

    def __getitem__(self, index):
        try:
            max_idx = index.stop - 1
        except AttributeError:
            max_idx = index
        n = max_idx - len(self.already_computed) + 1
        if n > 0:
            self.already_computed.extend(itertools.islice(self.it, n))
        return self.already_computed[index]

    def __nonzero__(self):
        try:
            return self[0] is not None
        except IndexError:
            return False

    def __repr__(self):
        num_to_show = 10
        beginning = list(self[:num_to_show + 1])
        if len(beginning) == num_to_show + 1:
            beginning[num_to_show] = '...(remaining elements truncated)...'
        return beginning.__repr__()


_pending_setattrs = []
_pending_setattrs_lock = threading.Lock()


def setattr_lazy(get_obj, name, value):
    """
    Like setattr(obj, name, value) but for cases when obj is not yet known or importable.

    The actual setattr calls will be executed when calling setattr_lazy_finish() later.
    """
    with _pending_setattrs_lock:
        _pending_setattrs.append((get_obj, name, value))


def setattr_lazy_finish():
    """
    Sets the attributes marked to be set in calls to setattr_lazy
    """
    if not _pending_setattrs:
        return

    with _pending_setattrs_lock:
        while _pending_setattrs:
            get_obj, name, value = _pending_setattrs.pop()
            try:
                obj = get_obj()
            except ImportError as e:
                logging.error(e)
                raise
            setattr(obj, name, value)
            if hasattr(value, 'contribute_to_class'):
                value.contribute_to_class(obj, name)


def extend_url_query_string(url, params):
    """
    Extend the querystring of the url by the params dict and return the new URL
    """
    url_parsed = urlparse.urlparse(url)

    def no_nones(value):
        """
        Removes None values from a list or a tuple.
        Ignore any other value types.
        """
        if isinstance(value, (list, tuple)):
            return [x for x in value if x is not None]
        return value

    # Like the requests library, ignore any None values in params
    params = {k: no_nones(v)
              for k, v in params.iteritems()
              if v is not None}

    url_params = urlparse.parse_qs(url_parsed.query)
    url_params.update(params)
    query_string = urllib.urlencode(url_params, doseq=True)

    url_parts = list(url_parsed)
    url_parts[4] = query_string
    url = urlparse.urlunparse(url_parts)
    return url


def min_ignoring_nones(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)
