[![Build status](https://api.travis-ci.org/qvantel/django-rest-framework-client.svg?branch=master)](https://travis-ci.org/qvantel/django-rest-framework-client)

Django REST Framework client
============================

*Django REST Framework client* is a Python client for REST APIs serving relational data. At the moment it supports JSON responses produced by *Django REST Framework*'s `ModelSerializer`. It provides a subset of *Django* ORM API.

Quickstart
----------

Define a client model:

    class Customer(restframeworkclient.Model):
        class Meta:
            resource = 'customers'
            base_url = 'http://example.org/v1'

(NOTE: You can also define `REST_FRAMEWORK_CLIENT = {'DEFAULT_BASE_URL': 'http://example.org/v1'}` in your Django settings to provide a default value for all models so you don't need to specify `Meta.base_url` for each model separately.)

Then use it just as you would use `django.db.models.Model`:

    customer = Customer.objects.get(pk=29481739)

This will make a `GET` request to `http://example.org/v1/customers/29481739/`
The server might reply with the following response:

    {
        "id": 133562,
        "name": "John Smith",
        "created_at": "2016-08-24T00:34:26Z"
    }

Object fields
-------------

### Native JSON values

The returned object field values are available as `customer.id`, `customer.name` and `customer.created_at`.

Additionally `customer.pk` is an alias for `customer.id` by default. To change the default:

    class Customer(restframeworkclient.Model):
        class Meta:
            resource = 'customers'
            primary_key = 'pk'  # 'id' is the default value

### Date and time values

JSON doesn't support *datetime* objects natively so in order to get native python `datetime.datetime` objects you need to declare the fields explicitly using `restframeworkclient.fields.DateTimeField`:

    class Customer(restframeworkclient.Model):
        created_at = restframeworkclient.fields.DateTimeField()
        class Meta:
            resource = 'customers'

There are also `restframeworkclient.fields.DateField` and `restframeworkclient.fields.TimeField` for `datetime.date` and `datetime.time` respectively.

### Custom fields

You can subclass restframeworkclient.fields.Field for implementing custom field types. For an example, see `restframeworkclient.fields.FileField` which is designed to simlulate *Django*'s `FileField`, see https://docs.djangoproject.com/en/dev/ref/models/fields/#django.db.models.FileField.

Handling paginated results
--------------------------

When iterating over `Customer.objects.all()` the server might reply with the following response:

    {
        "count": 10,
        "next": "http://example.org/v1/customers/?limit=2&offset=2",
        "previous": null,
        "results": [
            {
                "id": 133562,
                "name": "John Smith",
                "created_at": "2016-08-24T00:34:26Z"
            },
            {
                "id": 133563,
                "name": "John Carpenter",
                "created_at": "2016-08-25T00:34:26Z"
            },
        ]
    }

The keys `count` (the total amount of records), `next` (next page URL), `previous` (previous page URL) and `results` must be present in the response. *Django REST Framework* does this natively when using its `ModelSerializer`.

After iterating over the first page results the `next` page URL will be used to get the next results as needed. If the iterator is to be consumed fully then iteration stops when the server responds with `null` as the next page URL.

### Support for `offset` and `limit` on the server-side

It is assumed that the server supports `offset` and `limit` GET parameters -- for example *Django REST Framework* is used with `LimitOffsetPagination` enabled (see http://www.django-rest-framework.org/api-guide/pagination/#limitoffsetpagination) as restframeworkclient will use `offset` and `limit` GET parameters where appropriate, for example:

    Customer.objects.first()

will make a `GET` request to `http://example.org/v1/customers/?limit=1` and

    list(Customer.objects.all()[10:30])

will make a `GET` request to `http://example.org/v1/customers/?offset=10&limit=20`.

Automatic dereferencing
-----------------------

You can use `restframeworkclient.Reference` to refer to another client model similarly as you would when using Django's `ForeignKey`.

    class UserAccount(restframeworkclient.Model):
        customer = Reference(Customer, related_name='user', one_to_one=True)
        class Meta:
            resource = 'ssusers'

The first parameter can be either a direct reference to a class (e.g. `Customer`) or a string containing the importable class reference (e.g. `'Customer'`). The use of strings here can help avoid circular dependencies.

Getting another referenced model instance is easy

    user = UserAccount.objects.get(pk=1)

The server might reply with the following response:

    {
        "id": 1,
        "customer": 133562
    }

When accessing `user.customer` a `GET` request to `http://example.org/v1/customers/133562/` will be made and a `Customer` instance will be returned:

    >>> customer = user.customer
    >>> customer
    Customer(id=133562, ...)

Use the `_id` sufffix after the field name (e.g. `user.customer_id`) to get the raw reference value (`133562`)

Use `related_name` as a field name to get the other instance in the other direction just as you would do in *Django*'s `OneToOneField` or `ForeignKey`:

    >>> customer.user
    UserAccount(id=1, ...)

This will make a `GET` request to `http://example.org/v1/ssusers/?customer=133562&limit=1`.

Cross-API references
--------------------

You can specify for each client model its own `Meta.base_url` so there can be several REST APIs referencing each other seamlessly on the client-side.

One to many relationships
-------------------------

Consider these two client models:

    class Contract(restframeworkclient.Model):
        class Meta:
            resource = 'contracts'

    class Device(restframeworkclient.Model):
        contract = Reference(Contract, related_name='devices')
        class Meta:
            resource = 'devices'

    contract = Contract.objects.get(pk=1)

Getting the devices of a given contract:

    contract.devices.all()

which will make a `GET` request to `http://example.org/v1/devices/?contract=28537`.

You can use more filters at the same time:

    contract.devices.filter(is_active=True)

which will make a `GET` request to `http://example.org/v1/devices/?contract=28537&is_active=True`.


Generic relations with ModelSerializer
--------------------------------------

Like with Django contenttypes framework (see https://docs.djangoproject.com/en/dev/ref/contrib/contenttypes/) restframeworkclient also supports generic relations with which different objects can refer to other objects regardless of the model.

When using *Django REST Framework*'s `HyperlinkedModelSerializer` the related objects are referred by hyperlinks so support for generic relations comes natively as the URL contains all the necessary information where to fetch the related objects.

When using *Django REST Framework*'s `ModelSerializer` on the other hand there is only the primary key so for a generic relation an additional field must be dedicated for storing the information of the resource where the target object can be found.

Let's consider the following two client models:

    class Memo(restframeworkclient.Model):
        content_object = GenericRelationField('content_type', 'object_id')
        class Meta:
            resource = 'memos'

    class Customer(restframeworkclient.Model):
        class Meta:
            resource = 'customers'
            content_type = 'customer'

When doing:

    memo = Memo.objects.get(pk=1)

the server might respond with:

    {
        "id": 1,
        "target_id": 10,
        "content_type": "customer"
    }

Accessing the name of the `GenericRelationField` will then fetch the related object from the client model that has `Meta.content_type` identical with the value of the first field passed to `GenericRelationField` (in this case `content_type`):

    >>> memo.content_object
    Customer(id=10)

which will make a GET request to `http://example.org/v1/customers/15643/`

### Generic relations and ReverseReference

To be able to get all the objects related to a object via a generic relation use `ReverseReference`, for example:

    class Customer(restframeworkclient.Model):
        memos = ReverseReference('Memo', field_name='object_id', filters={'model': 'Customer'})
        class Meta:
            resource = 'customers'

You can then get all memos related to a given customer via:

    customer.memos.all()

which will make a `GET` request to `http://example.org/v1/memos/?object_id=133562&model=Customer&limit=1`

Filtering
---------

### filter()

Calling

    Customer.objects.filter(first_name='John')

will make a `GET` request to `http://example.org/v1/customers/?first_name=John`.

Chaining multiple filters is also possible:

    Customer.objects.filter(first_name='John').filter(last_name='Smith')

which is equivalent to

    Customer.objects.filter(first_name='John', last_name='Smith')

both would make a `GET` request to `http://example.org/v1/customers/?first_name=John&last_name=Smith`.

### get()

`get()` works similarly to *Django*'s `get()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.get

When specifying just the `pk` parameter, e.g. `Customer.objects.get(pk=1)`) the `GET` query sent to the server will be `https://example.org/v1/customers/1/` instead of the universal form `https://example.org/v1/customers/?id=1`. Parameter `pk` is being rewritten as `Meta.primary_key` (`id` by default). When specifying more than one parameter, the universal form is used.

### get_or_create()

`get_or_create()` works similarly to *Django*'s `get_or_create()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.get_or_create

### create()

`create()` works similarly to *Django*'s `create()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.create

### exclude()

Calling

    Customer.objects.exclude(something=1)

is equivalent to calling

    Customer.objects.filter(exclude__something=1)

Unlike Django, `exclude` doesn't accept more than one parameter at the same time.

### exists()

`exists()` works similarly to *Django*'s `exists()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.exists

Calling

    contract.devices.exists()

makes a `GET` request to `http://example.org/v1/devices/?contract=28537&limit=1`

### first()

`first()` works similarly to *Django*'s `first()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.first

    contract.devices.first()

makes a `GET` request to `http://example.org/v1/devices/?contract=28537&limit=1` and returns the client model instance or `None` if server returned empty results.

### all()

`all()` works similarly to *Django*'s `all()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.all

### none()

`none()` works similarly to *Django*'s `none()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.none

Calling `none()` will return empty results and won't make any requests to the server.

    Customer.objects.none()

### count()

`count()` returns the total number of objects as reported by the server in the reply. Calling:

    Customer.objects.filter(first_name='John').count()

makes a `GET` query to `http://example.org/v1/customers/?first_name=John&limit=1` and returns the number `10` extracted from the `count` key from the JSON response:

    {
        "count": 10,
        "next": "...",
        "previous": null,
        "results": [
            {
                ...
            }
        ]
    }

Note that *Django REST Framework* returns the total number of results regardless of paging parameters so doing calls like `Customer.objects.all()[10:30].count()` will return the same value as `Customer.objects.all().count()`.

Ordering
--------

### last()

`last()` works similarly to *Django*'s `last()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.last

    contract.devices.last()

makes a `GET` request to `http://example.org/v1/devices/?contract=28537&ordering=-id&limit=1`

### order_by()

`order_by()` works similarly to *Django*'s `order_by()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.order_by

    contract.devices.order_by('-created_at', 'termination_time').last()

makes a `GET` request to `http://example.org/v1/devices/?ordering=created_at%2C-termination_time&limit=1&contract=28537`

### earliest()

`earliest()` works similarly to *Django*'s `earliest()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.earliest

### latest()

`latest()` works similarly to *Django*'s `latest()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#django.db.models.query.QuerySet.latest

    contract.devices.latest('created_at')

makes a `GET` request to `https://example.org/v1/devices/?ordering=-created_at&limit=1&contract=28537`

Performance optimization
------------------------

### select_related()

Calling

    Customer.objects.all().select_related('field1', 'field2')

is identical to calling

    Customer.objects.all().filter(select_related='field1,field2')

as both produce the same `GET` request. The `restframeworkclient.Reference` will automatically turn nested objects into object instances without making additional requests regardless of calling `select_related()` or not. If the server is setup to return nested objects based on the value of the `select_related` `GET` parameter then it will behave similarly to the *Django*'s `select_related()`, see https://docs.djangoproject.com/en/dev/ref/models/querysets/#select-related.

### prefetch_related()

Call `prefetch_related()` when filtering objects that have `ReverseReference` fields which will be accessed multiple times for multiple objects returned. Accessing `ReverseReference` with its name passed into `prefetch_related()` will fetch all related objects at once. For example:

    for customer in Customer.objects.all().prefetch_related('devices'):
        customer.devices.filter(is_active=True)

First call to `customer.devices` will make a cumulative `GET` query with all of the customer ids that the query `Customer.objects.all()` returns (let's say 1,2,3): `http://example.org/v1/devices/?customer__in=1&customer__in=2&customer__in=3&is_active=True` instead of doing these 3 queries separately:

    http://example.org/v1/devices/?customer1&is_active=True
    http://example.org/v1/devices/?customer2&is_active=True
    http://example.org/v1/devices/?customer3&is_active=True

### Per-request response caching with automatic cache invalidation

To enable the built-in per-request response caching of the `restframeworkclient` put `'restframeworkclient.middleware.RESTFrameworkClientCacheMiddleware'` into your *Django*'s `MIDDLEWARE_CLASSES`. Only `GET` requests will be cached. New web application requests will invalidate the cache. Non-`GET` requests in the same web application request will invalidate the cache. There is one cache per thread.

Object instance methods
-----------------------
### save()

To change a field value do:

    customer = Customer.objects.get(pk=1)
    customer.first_name = 'Joe'
    customer.save()

which will make a `PATCH` request to http://example.org/v1/customers/1/ with the body `{"first_name": "Joe"}`. As opposed to *Django* not all fields are saved, only the changed ones.

### delete()

Call `delete()` on an client model instance to request deletion on the server, e.g.

    Customer.objects.get(pk=1).delete()

will make a `DELETE` request to http://example.org/v1/customers/1/

### refresh_from_db()

Call `refresh_from_db()` to re-fetch an object from the server.

    customer = Customer.objects.get(pk=1)
    customer.first_name = 'Joe'
    customer.refresh_from_db()

will make a `GET` request to http://example.org/v1/customers/1/ and local changes to `customer.first_name` will be lost.

Working with arbitrary non-relational data
------------------------------------------

### Calling instance-related server functions

Although the main point of restframeworkclient is working with relational data there is also support for invoking custom server-side logic returning arbitrary data given a specific model instance. Example:

    class Customer(restframeworkclient.Model):
        fetch_invoices = Method('fetch_invoices', method='POST')
        invoice_payers = Method('invoice_payers', method='GET', as_property=True)

        class Meta:
            resource = 'customers'

Calling

    customer.fetch_invoices(param='value')

makes a `POST` request to `http://example.org/v1/customers/133562/fetch_invoices/?param=value` returning what the server returns (must be JSON).

    customer.invoice_payers

on the other hand makes a `GET` request to `http://example.org/v1/customers/133562/invoice_payers/`. The parameter `as_property=True` makes `invoice_payers` an object property instead of a callable method.

You can pass `unwrapping_key='result'` to `Method()` to extract a single value from the response (e.g. returning `True` from JSON response `{'result': true}`).

### Calling server functions unrelated to a specific instance

You can pass `static=True` to `Method()` to enable such functionality so you can do:

    class Customer(restframeworkclient.Model):
        fetch_invoices = Method('fetch_invoices', method='POST', static=True)
        # ...

Then calling:

    Customer.fetch_invoices(param='value')

which will make a `POST` requst to `http://example.org/v1/customers/fetch_invoices/?param=value`.

### Returning model instances from custom server functions

If the server returns a list of objects you can use `MethodReturningCollection` to have them wrapped into instances of some `restframeworkclient.Model` instead of working with them as a plain python `dict`s. Example:

    class Customer(restframeworkclient.Model):
        active_devices = MethodReturningCollection('active_devices', model='Device')
        class Meta:
            resource = 'customers'

    class Device(restframeworkclient.Model):
        pass

Calling `customer.active_contracts()` will make a `GET` request to `http://example.org/v1/customers/133562/active_devices` and if the server responds with:

    [
        {"id": 1, "color": "black"},
        {"id": 2, "color": "white"}
    ]

the call will turn this response into a list of `Contract` instances. No paging is supported here.

When using *Django REST Framework* the usage of `ReverseReference` should be preferred to `MethodReturningCollection` as `ReverseReference` can be used together with paging and other *Django REST Framework* filters simultaneously:

    class Customer(restframeworkclient.Model):
        active_devices = ReverseReference('Device', field_name='active_devices_of_customer')
        class Meta:
            resource = 'customers'

    class Device(restframeworkclient.Model):
        class Meta:
            resource = 'devices'

Calling `customer.active_contracts.filter(param='value')` will make a `GET` request to `http://example.org/v1/devices/?active_devices_of_customer=133562&param=value`. The server response must be in the paginated form (see *Handling paginated results* in this document).


Advanced configuration
----------------------

The default configuration of restframeworkclient should be good for most use cases but some settings can be customized.

When `REST_FRAMEWORK_CLIENT['USE_LOCAL_REST_FRAMEWORK']` is enabled *restframeworkclient* won't attempt to connect to the REST APIs using the `Model.Meta.base_url` or `REST_FRAMEWORK_CLIENT['DEFAULT_BASE_URL']`. Instead, it will use the REST APIs running inside the same Django application that the restframeworkclient is running in. It will use `rest_framework.test.APIClient` of the *Django REST Framework* to avoid HTTP overhead. In order for this to work `REST_FRAMEWORK_CLIENT['BASE_URLS']` must be set to a dict where keys should be equal to the URL prefixes under which are included urlconfs of each of the REST APIs respectively and values should contain the original base URLs of the REST APIs.

Example of a *Django* settings:

    REST_FRAMEWORK_CLIENT = {
        'USE_LOCAL_REST_FRAMEWORK': True,  # default False
        'BASE_URLS': {'example-org-v1': 'http://example.org/v1'},
    }

Example of `urls.py` additional patterns:

    urlpatterns +=  patterns('', url('^example-org-v1/', include('path.to.example-org-v1.urls')))

Beware that this way both the server and the client share the same Django settings.

Credits
=======

- Work was sponsored by Qvantel (http://qvantel.com).
- Author and package maintainer: Martin Riesz (https://github.com/matmas/).


License
=======

Copyright (c) 2017, Qvantel

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

 - Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
 - Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.
 - Neither the name of the Qvantel nor the
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
