import unittest

from wiring.graph import (
    SelfDependencyError,
    MissingDependencyError,
    DependencyCycleError,
    UnknownScopeError,
    Graph,
)
from wiring.dependency import (
    injected,
    inject,
)
from wiring.scopes import ProcessScope

from . import ModuleTest


class GraphModuleTest(ModuleTest):
    module = 'wiring.graph'


class GraphTest(unittest.TestCase):

    def test_valid(self):
        db_hostname = 'example.com'

        def get_database_connection(db_hostname=injected('db.hostname')):
            if db_hostname == 'example.com':
                return {
                    'connected': True,
                }
            else:
                raise Exception("Injection went wrong.")

        class TestClass(object):
            @inject('db_connection')
            def __init__(self, db):
                self.is_ok = db['connected']

        graph = Graph()
        graph.register_instance('db.hostname', db_hostname)
        graph.register_factory('db_connection', get_database_connection)
        graph.register_factory(TestClass, TestClass)
        graph.validate()

        self.assertEqual(graph.get('db.hostname'), 'example.com')
        test_instance = graph.get(TestClass)
        self.assertIsInstance(test_instance, TestClass)
        self.assertTrue(test_instance.is_ok)

    def test_self_dependency(self):
        @inject('foobar')
        def function(foo):
            pass
        graph = Graph()
        graph.register_factory('foobar', function)
        with self.assertRaises(SelfDependencyError) as cm:
            graph.validate()
        self.assertEqual(cm.exception.specification, 'foobar')
        self.assertEqual(
            str(cm.exception),
            "Provider for 'foobar' is dependent on itself."
        )

    def test_missing_dependency(self):
        @inject('foobar')
        def function(foo):
            return foo + 1

        graph = Graph()
        graph.register_factory('function', function)
        with self.assertRaises(MissingDependencyError) as cm:
            graph.validate()
        self.assertEqual(cm.exception.dependency, 'foobar')
        self.assertEqual(cm.exception.dependant, 'function')
        self.assertEqual(
            str(cm.exception),
            "Cannot find dependency 'foobar' for 'function' provider."
        )

        graph.register_instance('foobar', 42)
        graph.validate()
        self.assertEqual(graph.get('function'), 43)

    def test_dependency_cycle(self):
        @inject('c')
        def a(c):
            pass

        @inject('a')
        def b(a):
            pass

        @inject('b')
        def c(b):
            pass

        graph = Graph()
        graph.register_factory('a', a)
        graph.register_factory('b', b)
        graph.register_factory('c', c)
        with self.assertRaises(DependencyCycleError) as cm:
            graph.validate()
        self.assertSetEqual(
            frozenset(cm.exception.cycle),
            frozenset(('a', 'b', 'c'))
        )
        message = str(cm.exception)
        self.assertIn("Dependency cycle: ", message)
        self.assertIn("'a'", message)
        self.assertIn("'b'", message)
        self.assertIn("'c'", message)

    def test_acquire_arguments(self):
        @inject(1, None, 3, foo=4)
        def function(a, b, c, foo=None, bar=None):
            return (a, b, c, foo, bar)

        graph = Graph()
        graph.register_instance(1, 11)
        graph.register_instance(3, 33)
        graph.register_instance(4, 44)
        graph.register_factory('function', function)
        graph.validate()

        self.assertTupleEqual(
            graph.acquire('function', arguments={1: 22, 'bar': 55}),
            (11, 22, 33, 44, 55)
        )
        self.assertTupleEqual(
            graph.acquire(
                'function',
                arguments={
                    1: 22,
                    'bar': 55,
                    'foo': 100,
                }
            ),
            (11, 22, 33, 100, 55)
        )
        with self.assertRaises(TypeError):
            graph.acquire(
                'function',
                arguments={
                    1: 22,
                    ('invalid', 'argument', 'key'): 55,
                }
            )

    def test_get_arguments(self):
        def function(a, b=None, c=injected(1)):
            return (a, b, c)

        graph = Graph()
        graph.register_instance(1, 11)
        graph.register_factory('function', function)
        graph.validate()

        self.assertTupleEqual(
            graph.get('function', 33, b=22),
            (33, 22, 11)
        )
        self.assertTupleEqual(
            graph.get('function', 33, b=22, c=44),
            (33, 22, 44)
        )

    def test_scope(self):
        notlocal = [0]

        def factory():
            notlocal[0] += 1
            return notlocal[0]

        graph = Graph()
        graph.register_factory('scoped', factory, scope=ProcessScope)
        graph.register_factory('unscoped', factory)

        self.assertEqual(graph.get('scoped'), 1)
        self.assertEqual(graph.get('scoped'), 1)
        self.assertEqual(graph.get('scoped'), 1)
        self.assertEqual(graph.get('scoped'), 1)
        self.assertEqual(graph.get('scoped'), 1)

        self.assertEqual(graph.get('unscoped'), 2)
        self.assertEqual(graph.get('unscoped'), 3)

        self.assertEqual(graph.get('scoped'), 1)
        self.assertEqual(graph.get('scoped'), 1)

        self.assertEqual(graph.get('unscoped'), 4)

    def test_unknown_scope(self):
        class FooBarScope(object):
            pass

        graph = Graph()

        with self.assertRaises(UnknownScopeError) as cm:
            graph.register_factory('foo', lambda: None, scope=FooBarScope)

        self.assertEqual(cm.exception.scope_type, FooBarScope)
        self.assertIn('FooBarScope', str(cm.exception))
