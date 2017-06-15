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
import mock
import unittest

from django.http.response import Http404

import restframeworkclient
from restframeworkclient.utils import extend_url_query_string, Indexable


class Customer(restframeworkclient.Model):
    class Meta:
        resource = 'customers'
        base_url = 'http://example.org'
        get_latest_by = 'created_at'


class Device(restframeworkclient.Model):
    customer = restframeworkclient.Reference('Customer', related_name='devices')
    image = restframeworkclient.FileField()

    class Meta:
        resource = 'devices'
        base_url = 'http://example.org'


class RequestManager(restframeworkclient.Manager):
    def get_queryset(self):
        return super(RequestManager, self).get_queryset().order_by('created_at')

    def ongoing(self):
        return self.get_queryset().filter(status='ongoing')


class Request(restframeworkclient.Model):
    objects = RequestManager()

    class Meta:
        resource = 'requests'
        base_url = 'http://example.org'


class ModelSimpleTest(unittest.case.TestCase):

    def setUp(self):
        restframeworkclient.Model._rest_call = mock.MagicMock(return_value={
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {"id": 1},
            ]
        })
        self.rest_call_mock = restframeworkclient.Model._rest_call

    def test_lazy_evaluation(self):
        customers = Customer.objects.all()
        assert self.rest_call_mock.call_count == 0
        list(customers)
        assert self.rest_call_mock.call_count == 1
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={})

    def test_cached_evaluation(self):
        customers = Customer.objects.all()
        list(customers)
        list(customers)
        assert self.rest_call_mock.call_count == 1

    def test_len(self):
        customers = Customer.objects.all()
        assert len(customers) == 1

    def test_multiple_evaluations(self):
        list(Customer.objects.all())
        list(Customer.objects.all())
        assert self.rest_call_mock.call_count == 2

    def test_filter(self):
        list(Customer.objects.filter(param='value'))
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value'})

    def test_exists(self):
        Customer.objects.filter(param='value').exists()
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1})

    def test_last_with_order_by(self):
        Customer.objects.filter(param='value').order_by('name,-created_at').last()
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1, 'ordering': '-name,created_at'})

    def test_last_without_order_by(self):
        Customer.objects.filter(param='value').last()
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1, 'ordering': '-id'})

    def test_latest_default_field_name(self):
        Customer.objects.filter(param='value').latest()
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1, 'ordering': '-created_at'})

    def test_latest_explicit_field_name(self):
        Customer.objects.filter(param='value').latest('modified_at')
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1, 'ordering': '-modified_at'})

    def test_earliest_default_field_name(self):
        Customer.objects.filter(param='value').earliest()
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1, 'ordering': 'created_at'})

    def test_chained_filtering(self):
        list(Customer.objects.filter(param='value').filter(param2='value2'))
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'param2': 'value2'})

    def test_exclude_multiple_kwargs_raises_valueerror(self):
        with self.assertRaises(ValueError):
            Customer.objects.exclude(param='value', param2='value2')

    def test_exclude(self):
        list(Customer.objects.exclude(param='value'))
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'exclude__param': 'value'})

    def test_exlude_single_kwarg_list(self):
        list(Customer.objects.exclude(param=['value1', 'value2']))
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'exclude__param': ['value1', 'value2']})

    def test_get(self):
        Customer.objects.get(param='value')
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'param': 'value', 'limit': 1})

    def test_get_pk_only(self):
        Customer.objects.get(pk=123)
        self.rest_call_mock.assert_called_with('http://example.org/customers/123/')

    def test_order_by(self):
        list(Customer.objects.all().order_by('-created_at', 'name'))
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'ordering': '-created_at,name'})

    def test_add(self):
        customer = Customer(pk=123)
        customer.devices.add(Device(id=1))
        self.rest_call_mock.assert_called_with('http://example.org/devices/', data={'customer': 123, 'id': 1}, method='POST')

    def test_none(self):
        customer = Customer(pk=123)
        assert list(customer.devices.none()) == []
        assert self.rest_call_mock.call_count == 0

    def test_reference_foo_id_setter(self):
        device = Device(customer_id=123)
        assert device._attrs['customer'] == 123

    def test_manager_get_queryset(self):
        list(Request.objects.all())
        self.rest_call_mock.assert_called_with('http://example.org/requests/', params={'ordering': 'created_at'})

    def test_manager_custom_method(self):
        list(Request.objects.ongoing().all())
        self.rest_call_mock.assert_called_with('http://example.org/requests/', params={'ordering': 'created_at', 'status': 'ongoing'})

    def test_offset(self):
        customers = Customer.objects.filter(a=1)
        list(customers[10:])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'a': 1, 'offset': 10})
        list(customers[:])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'a': 1})
        list(customers[10:20])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'a': 1, 'offset': 10, 'limit': 10})
        customers[100]
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'a': 1, 'offset': 100, 'limit': 1})

    def test_cumulative_offset(self):
        list(Customer.objects.all()[5:][5:])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'offset': 10})

    def test_limit(self):
        customers = Customer.objects.all()
        list(customers[:10])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'limit': 10})

    def test_overriding_limit(self):
        customers = Customer.objects.all()
        list(customers[:10][:5])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'limit': 5})

    def test_offset_and_limit_together(self):
        customers = Customer.objects.all()
        list(customers[10:20][5:10])
        self.rest_call_mock.assert_called_with('http://example.org/customers/', params={'offset': 15, 'limit': 5})


class ModelTest(unittest.case.TestCase):

    def test_attr_changes(self):
        customer = Customer(param='value')
        assert customer.param == 'value'
        customer.param = 'new value'
        assert customer.param == 'new value'

    def test_model_meta(self):
        assert Customer._meta.model == Customer
        assert Customer._meta.object_name == 'Customer'
        assert Customer._meta.model_name == 'customer'
        assert Customer._meta.verbose_name == 'customer'

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_exists(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {"id": 1},
                {"id": 2},
            ]
        }
        assert Customer.objects.exists() == True

        rest_call_mock.return_value = {
            "count": 0,
            "next": None,
            "previous": None,
            "results": [],
        }
        assert Customer.objects.exists() == False

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_save_populates_pk(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 123,
            'name': 'name',
            'email': 'a@a.com',
        }
        customer = Customer(name='name', email='a@a.com')
        customer.save()
        assert customer.pk == 123

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_save_updates_changed_values_only(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 123,
            'name': 'name',
            'email': 'a@a.com',
        }
        customer = Customer(name='name', email='a@a.com')
        customer.save()

        customer.name = 'new name'
        customer.save()
        rest_call_mock.assert_called_with('http://example.org/customers/123/', data={'name': 'new name'}, method='PATCH')

        customer.email = 'b@b.com'
        customer.save()
        rest_call_mock.assert_called_with('http://example.org/customers/123/', data={'email': 'b@b.com'}, method='PATCH')

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_reverse_reference_query(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 123,
            'name': 'name',
        }
        customer = Customer.objects.get(pk=123)

        rest_call_mock.return_value = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {"id": 1, 'customer': 123, 'type': 'phone'},
                {"id": 2, 'customer': 123, 'type': 'tablet'},
            ]
        }
        list(customer.devices.all())
        rest_call_mock.assert_called_with('http://example.org/devices/', params={'customer': 123})

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_reference(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 1,
            'customer': 123,
            'type': 'phone',
        }
        device = Device.objects.get(pk=1)
        customer = device.customer
        rest_call_mock.assert_called_with('http://example.org/customers/123/')

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_reference_change(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 1,
            'customer': 123,
            'type': 'phone',
        }
        device = Device.objects.get(pk=1)
        customer = Customer(id=456, name='different')
        device.customer = customer

        rest_call_mock.return_value = {
            'id': 1,
            'customer': 456,
            'type': 'phone',
        }
        device.save()
        rest_call_mock.assert_called_with('http://example.org/devices/1/', data={'customer': 456}, method='PATCH')

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_empty_results_evaluates_false(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 0,
            "next": None,
            "previous": None,
            "results": [],
        }
        customers = Customer.objects.all()
        assert not bool(customers)
        assert not bool(customers)

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_nonempty_results_evaluates_true(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {'id': 123, 'name': 'Smith'},
                {'id': 456, 'name': 'Jones'},
            ],
        }
        customers = Customer.objects.all()
        assert bool(customers)
        assert bool(customers)

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_results_contains_instance(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 123,
            'name': 'Smith',
        }
        customer = Customer.objects.get(pk=123)
        customer_999 = Customer(id=999, name="Taylor")
        rest_call_mock.return_value = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {'id': 123, 'name': 'Smith'},
                {'id': 456, 'name': 'Jones'},
            ],
        }
        customers = Customer.objects.all()
        assert customer in customers
        assert customer_999 not in customers
        assert customer in customers
        assert customer_999 not in customers

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_results_iterable_multiple_times(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {'id': 123, 'name': 'Smith'},
                {'id': 456, 'name': 'Jones'},
            ],
        }
        customers = Customer.objects.all()
        assert len(list(customers)) == 2
        assert len(list(customers)) == 2

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_get_object_or_404_raises_404_on_DoesNotExist(self, rest_call_mock):
        rest_call_mock.side_effect = Customer.DoesNotExist
        with self.assertRaises(Http404):
            restframeworkclient.get_object_or_404(Customer, param='value')

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_reference_allows_direct_access_to_ids(self, rest_call_mock):
        device = Device(id=1, customer=123)
        assert device.customer_id == 123
        assert rest_call_mock.call_count == 0

    def test_filefield_absolute_url(self):
        device = Device(image='http://example.org/path/to/file.png')
        assert device.image.url == 'http://example.org/path/to/file.png'

    def test_filefield_prepend_slash_if_not_an_url_nor_path(self):
        device = Device(image='path/to/file.png')
        assert device.image.url == '/path/to/file.png'

    def test_doesnotexist_distinguishable_by_model(self):
        with self.assertRaises(Customer.DoesNotExist):
            try:
                raise Customer.DoesNotExist
            except Device.DoesNotExist:
                pass

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_reference_set_invalidates_cache(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 1,
            'customer': 123,
            'type': 'phone',
        }
        device = Device.objects.get(pk=1)
        rest_call_mock.return_value = {
            'id': 123,
        }
        assert device.customer.pk == 123
        rest_call_mock.return_value = {
            'id': 456,
        }
        # Uses cache
        assert device.customer.pk == 123
        device.customer = Customer(pk=456)
        # Cache is invalidated
        assert device.customer.pk == 456

    def test_empty_list_filter_value(self):
        assert list(Customer.objects.filter(id__in=[])) == []

    def test_none_filter_evaluates_as_false_in_boolean_context(self):
        assert not bool(Customer.objects.none())

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_iterating_over_bigger_results(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 6,
            "next": "http://example.org/customers/?a=1&limit=2&offset=2",
            "previous": None,
            "results": [
                {'id': 1},
                {'id': 2},
            ],
        }
        customers = Customer.objects.filter(a=1)
        assert rest_call_mock.call_count == 0

        customers_iter = iter(customers)
        customer = next(customers_iter)
        assert customer.pk == 1
        customer = next(customers_iter)
        assert customer.pk == 2
        assert rest_call_mock.call_count == 1
        rest_call_mock.assert_called_with('http://example.org/customers/', params={'a': 1})
        rest_call_mock.return_value = {
            "count": 6,
            "next": "http://example.org/customers/?a=1&limit=2&offset=4",
            "previous": None,
            "results": [
                {'id': 3},
                {'id': 4},
            ],
        }
        customer = next(customers_iter)
        assert customer.pk == 3
        customer = next(customers_iter)
        assert customer.pk == 4
        assert rest_call_mock.call_count == 2
        rest_call_mock.assert_called_with('http://example.org/customers/?a=1&limit=2&offset=2')
        rest_call_mock.return_value = {
            "count": 6,
            "next": None,
            "previous": None,
            "results": [
                {'id': 5},
                {'id': 6},
            ],
        }
        customer = next(customers_iter)
        assert customer.pk == 5
        customer = next(customers_iter)
        assert customer.pk == 6
        assert rest_call_mock.call_count == 3
        rest_call_mock.assert_called_with('http://example.org/customers/?a=1&limit=2&offset=4')
        with self.assertRaises(StopIteration):
            next(customers_iter)

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_ignore_next_pages_when_using_limit(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 6,
            "next": "http://example.org/customers/?limit=2&offset=2",
            "previous": None,
            "results": [
                {'id': 1},
                {'id': 2},
            ],
        }
        assert len(list(Customer.objects.all()[:2])) == 2
        assert rest_call_mock.call_count == 1

    def test_extend_url_query_string(self):
        url = extend_url_query_string('http://localhost:8010/?a=1', {'b': 2})
        assert url == 'http://localhost:8010/?a=1&b=2'

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_setting_not_yet_persisted_reference(self, rest_call_mock):
        customer = Customer(name='Smith')
        device = Device(customer=customer)
        rest_call_mock.return_value = {
            'id': 123,
            'name': 'Smith',
        }
        customer.save()
        device.save()
        rest_call_mock.assert_called_with('http://example.org/devices/', method='POST', data={'customer': 123})

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_get_by_pk(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 1,
        }
        Device.objects.get(pk=1)
        rest_call_mock.assert_called_with('http://example.org/devices/1/')

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_filter_by_pk(self, rest_call_mock):
        rest_call_mock.return_value = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {'id': 1},
            ],
        }
        device = Device.objects.filter(pk=1)[0]
        rest_call_mock.assert_called_with('http://example.org/devices/', params={'id': 1, 'limit': 1})


    @mock.patch('restframeworkclient.Model._rest_call')
    def test_select_related(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 1,
            'customer': {
                'id': 123,
                'name': 'Smith',
            },
        }
        device = Device.objects.select_related('customer').get(pk=1)
        rest_call_mock.assert_called_with('http://example.org/devices/1/', params={'select_related': 'customer'})
        assert rest_call_mock.call_count == 1
        assert device.customer.pk == 123
        assert rest_call_mock.call_count == 1

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_select_related_chaining(self, rest_call_mock):
        device = Device.objects.select_related('customer').select_related('manufacturer', 'color').get(pk=1)
        rest_call_mock.assert_called_with('http://example.org/devices/1/', params={'select_related': 'customer,manufacturer,color'})

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_prefetch_related(self, rest_call_mock):
        rest_call_mock.return_value = {
            'count': 3,
            'next': None,
            'previous': None,
            'results': [
                {'id': 1},
                {'id': 2},
                {'id': 3},
            ],
        }
        customers = Customer.objects.all().prefetch_related('devices')
        list(customers)
        assert rest_call_mock.call_count == 1
        rest_call_mock.assert_called_with('http://example.org/customers/', params={})

        rest_call_mock.return_value = {
            'count': 6,
            'next': None,
            'previous': None,
            'results': [
                {'id': 101, 'customer': 1},
                {'id': 102, 'customer': 1},
                {'id': 201, 'customer': 2},
                {'id': 202, 'customer': 2},
                {'id': 301, 'customer': 3},
                {'id': 302, 'customer': 3},
            ],
        }
        customers_iter = iter(customers)

        customer = next(customers_iter)
        assert [device.pk for device in customer.devices.all()] == [101, 102]
        assert rest_call_mock.call_count == 2
        rest_call_mock.assert_called_with('http://example.org/devices/', params={'customer__in': [1, 2, 3]})

        customer = next(customers_iter)
        assert [device.pk for device in customer.devices.all()] == [201, 202]

        customer = next(customers_iter)
        assert [device.pk for device in customer.devices.all()] == [301, 302]

        with self.assertRaises(StopIteration):
            next(customers_iter)
        assert rest_call_mock.call_count == 2

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_refresh_from_db_invalidates_field_cache(self, rest_call_mock):
        rest_call_mock.return_value = {
            'id': 1,
            'customer': 123,
        }
        device = Device.objects.get(pk=1)
        rest_call_mock.return_value = {
            'id': 123,
            'name': 'Smith',
        }
        device.customer
        rest_call_mock.return_value = {
            'id': 1,
            'customer': 456,
        }
        device.refresh_from_db()
        rest_call_mock.return_value = {
            'id': 456,
            'name': 'Miller',
        }
        assert device.customer_id == 456
        assert device.customer.pk == 456

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_change_mutable_value(self, rest_call_mock):
        customer = Customer(pk=123, characteristics={'key': 'old_value'})
        assert customer._original_attrs['characteristics'] is not customer._attrs['characteristics']
        rest_call_mock.return_value = {
            'id': 123,
            'characteristics': {"key": "old_value"},
        }
        customer.save()
        assert customer._original_attrs['characteristics'] is not customer._attrs['characteristics']
        rest_call_mock.assert_called_with('http://example.org/customers/',
                                          data={'id': 123, 'characteristics': '{"key": "old_value"}'}, method='POST')
        customer.characteristics['key'] = 'new_value'
        rest_call_mock.return_value = {
            'id': 123,
            'characteristics': {"key": "new_value"},
        }
        customer.save()
        assert customer._original_attrs['characteristics'] is not customer._attrs['characteristics']
        rest_call_mock.assert_called_with('http://example.org/customers/123/',
                                          data={'characteristics': '{"key": "new_value"}'}, method='PATCH')

    @mock.patch('restframeworkclient.Model._rest_call')
    def test_len(self, rest_call_mock):
        rest_call_mock.return_value = {
            'count': 6,
            'next': "http://example.org/customers/?limit=2&offset=3",
            'previous': "http://example.org/customers/?limit=2",
            'results': [
                {'id': 2},
                {'id': 3},
            ],
        }
        assert len(Customer.objects.all()[1:3]) == 2


class IndexableTest(unittest.case.TestCase):
    def test_iterating_concurrently(self):
        def generator():
            i = 0
            while True:
                yield i
                i += 1
        indexable = Indexable(generator())
        it1 = iter(indexable)
        it2 = iter(indexable)
        assert next(it1) == 0
        assert next(it1) == 1

        assert next(it2) == 0
        assert next(it2) == 1
        assert next(it2) == 2

        assert next(it1) == 2
