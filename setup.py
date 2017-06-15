from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='django-rest-framework-client',
    version='0.8.0',
    description='Client for Django REST Framework APIs serving relational data providing a subset of Django ORM API',
    long_description=long_description,
    url='https://github.com/qvantel/django-rest-framework-client',
    author="Martin Riesz",
    author_email="ext-martin.riesz@qvantel.com",
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Framework :: Django',
    ],
    keywords='django rest framework client',
    packages=find_packages(exclude=['tests']),
    install_requires=[
        'setuptools',
        'Django',
        'djangorestframework',
        'python-dateutil',
        'requests',
    ],
    extras_require={
        'test': ['mock', 'pytest'],
    },

    license='BSD-3',
    zip_safe=True,
)
