# pylint: disable=no-member
# pylint: disable=unbalanced-tuple-unpacking

import unittest
import six

import pyrtl
from pyrtl.rtllib import fifos


class TestSimpleModules(unittest.TestCase):

    def setUp(self):
        pyrtl.reset_working_block()

    def test_fifo_wire_sorts(self):
        f = fifos.Fifo(8, 4)
        self.assertTrue(isinstance(f.reset.sort, pyrtl.ToSync))
        self.assertTrue(isinstance(f.valid_in.sort, pyrtl.ToSync))
        self.assertTrue(isinstance(f.data_in.sort, pyrtl.ToSync))
        self.assertTrue(isinstance(f.ready_in.sort, pyrtl.ToSync))

        self.assertTrue(isinstance(f.ready_out.sort, pyrtl.FromSync))
        self.assertTrue(isinstance(f.valid_out.sort, pyrtl.FromSync))
        self.assertTrue(isinstance(f.data_out.sort, pyrtl.FromSync))

    def test_wire_sort_in_module(self):
        class T(pyrtl.Module):
            def __init__(self):
                super(T, self).__init__()

            def definition(self):
                r = pyrtl.Register(1, 'r')
                w1 = self.Input(1, 'w1')
                w2 = self.Input(1, 'w2')
                w3 = self.Input(1, 'w3')
                w4 = self.Input(1, 'w4')
                w8 = self.Output(1, 'w8')
                w9 = self.Output(1, 'w9')
                w5 = w1 & w2
                w10 = pyrtl.Const(0)
                r.next <<= w5 | w3
                w8 <<= r ^ w10
                w6 = ~w4
                w7 = r ^ w6
                w9 <<= w7 | w1

        t = T()
        self.assertTrue(isinstance(t.w1.sort, pyrtl.ToPort))
        self.assertEqual(t.w1.sort.output_port_set, {t.w9})
        self.assertTrue(isinstance(t.w2.sort, pyrtl.ToSync))
        self.assertTrue(isinstance(t.w3.sort, pyrtl.ToSync))
        self.assertTrue(isinstance(t.w4.sort, pyrtl.ToPort))
        self.assertEqual(t.w4.sort.output_port_set, {t.w9})
        self.assertTrue(isinstance(t.w8.sort, pyrtl.FromSync))
        self.assertTrue(isinstance(t.w9.sort, pyrtl.FromPort))
        self.assertEqual(t.w9.sort.input_port_set, {t.w1, t.w4})


class TestMultipleIntraModules(unittest.TestCase):
    class M(pyrtl.Module):
        def __init__(self, name=""):
            super(TestMultipleIntraModules.M, self).__init__(name=name)

        def definition(self):
            a = self.Input(4, 'a')
            b = self.Output(6, 'b')
            b <<= a * 4

    class N(pyrtl.Module):
        def __init__(self, name=""):
            super(TestMultipleIntraModules.N, self).__init__(name=name)

        def definition(self):
            a = self.Input(10, 'a')
            b = self.Output(10, 'b')
            r = pyrtl.Register(10, 'r')
            r.next <<= a + 1
            b <<= r * 4

    def setUp(self):
        pyrtl.reset_working_block()

    def test_single_connected(self):
        m = TestMultipleIntraModules.M()
        a_in = pyrtl.Input(4, 'a_in')
        b_out = pyrtl.Output(6, 'b_out')
        m.a <<= a_in + 1
        b_out <<= m.b - 1

        sim = pyrtl.Simulation()
        sim.step_multiple({'a_in': [1, 2, 3]}, {'b_out': [7, 11, 15]})

        output = six.StringIO()
        sim.tracer.print_trace(output, compact=True)
        self.assertEqual(output.getvalue(), " a_in 123\nb_out 71115\n")

        self.assertTrue(isinstance(m.a.sort, pyrtl.ToPort))
        self.assertTrue(isinstance(m.b.sort, pyrtl.FromPort))
        self.assertEqual(m.a.sort.output_port_set, {m.b})
        self.assertEqual(m.b.sort.input_port_set, {m.a})

    def test_simple_connected_to_self_no_loop(self):
        n = TestMultipleIntraModules.N()
        n.a <<= n.b
        out = pyrtl.Output(10, 'out')
        out <<= n.b

        sim = pyrtl.Simulation()
        sim.step_multiple({}, nsteps=5)
        output = six.StringIO()
        sim.tracer.print_trace(output, compact=True)
        self.assertEqual(output.getvalue(), "out 042084340\n  r 0152185\n")

    def test_three_connected_simple_no_cycle_because_state(self):
        n1 = TestMultipleIntraModules.N(name="n1")
        n2 = TestMultipleIntraModules.N(name="n2")
        n3 = TestMultipleIntraModules.N(name="n3")
        n2.a <<= n1.b
        n3.a <<= n2.b
        n1.a <<= n3.b

        self.assertTrue(isinstance(n1.a.sort, pyrtl.ToSync))
        self.assertEqual(n1.a.sort.output_port_set, set())
        self.assertTrue(isinstance(n1.b.sort, pyrtl.FromSync))
        self.assertFalse(n1.b.sort.input_port_set, set())

    def test_three_connected_simple_cycle_with_no_state_immediate_check(self):
        pyrtl.working_block().immediate_intermodular_checks = True
        # This test assumes checks done after each net insertion.
        m1 = TestMultipleIntraModules.M()
        m2 = TestMultipleIntraModules.M()
        m3 = TestMultipleIntraModules.M()
        m2.a <<= m1.b
        m3.a <<= m2.b
        with self.assertRaises(pyrtl.PyrtlError) as ex:
            m1.a <<= m3.b
        self.assertTrue(str(ex.exception).startswith("Connection error"))

    def test_ill_connected_to_self_loop_immediate_check(self):
        # This test assumes checks done after each net insertion.
        pyrtl.working_block().immediate_intermodular_checks = True
        m = TestMultipleIntraModules.M()

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            m.a <<= m.b
        self.assertTrue(str(ex.exception).startswith("Connection error"))

    def test_ill_connected_transitive_with_normal_intermediate_wire_immediate_check(self):
        # This test assumes checks done after each net insertion.
        pyrtl.working_block().immediate_intermodular_checks = True
        m = TestMultipleIntraModules.M()
        x = m.b * 2

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            m.a <<= x
        self.assertTrue(str(ex.exception).startswith("Connection error"))

    def test_loop_after_many_steps_immediate_check(self):
        """ Tests the scenario where you connect module input to
            something (say X), then connect module output to something
            else (say Y), and then later connect X to Y.
        """
        pyrtl.working_block().immediate_intermodular_checks = True
        m = TestMultipleIntraModules.M()
        w1 = pyrtl.WireVector(4)
        m.a <<= w1
        w2 = m.b * 2
        with self.assertRaises(pyrtl.PyrtlError) as ex:
            w1 <<= w2
        self.assertTrue(str(ex.exception).startswith("Connection error"))

    def test_outputs_to_multiple_connections_immediate_check(self):
        pyrtl.working_block().immediate_intermodular_checks = True

        class M(pyrtl.Module):
            def __init__(self, name):
                super(M, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a')
                b = self.Input(6, 'b')
                c = self.Output(6, 'c')
                c <<= a * 4 - b

        m = M("M")
        w1 = m.c * 4
        w2 = m.c + 2
        r = pyrtl.Register(8)
        r.next <<= w1
        m.a <<= r
        with self.assertRaises(pyrtl.PyrtlError) as ex:
            m.b <<= w2
        self.assertTrue(str(ex.exception).startswith("Connection error"))

    def test_three_connected_simple_cycle_with_no_state_check_after(self):
        m1 = TestMultipleIntraModules.M("M1")
        m2 = TestMultipleIntraModules.M("M2")
        m3 = TestMultipleIntraModules.M("M3")
        m2.a <<= m1.b
        m3.a <<= m2.b
        m1.a <<= m3.b
        with self.assertRaises(pyrtl.PyrtlError) as ex:
            pyrtl.Simulation()
        self.assertTrue(
            str(ex.exception).startswith(
                'Invalid intermodular connections detected in "Top":\n'
            ))

    def test_ill_connected_to_self_loop_check_after(self):
        m = TestMultipleIntraModules.M("M")
        m.a <<= m.b

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            pyrtl.Simulation()
        self.assertEqual(
            str(ex.exception),
            'Invalid intermodular connections detected in "Top":\n'
            '(b/6O[M] -> a/4I[M])'
        )

    def test_ill_connected_transitive_with_normal_intermediate_wire_check_after(self):
        m = TestMultipleIntraModules.M("M")
        x = m.b * 2
        m.a <<= x

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            pyrtl.Simulation()
        self.assertEqual(
            str(ex.exception),
            'Invalid intermodular connections detected in "Top":\n'
            '(b/6O[M] -> a/4I[M])'
        )

    def test_loop_after_many_steps_immediate_check_after(self):
        """ Tests the scenario where you connect module input to
            something (say X), then connect module output to something
            else (say Y), and then later connect X to Y.
        """

        m = TestMultipleIntraModules.M("M")
        w1 = pyrtl.WireVector(4)
        m.a <<= w1
        w2 = m.b * 2
        w1 <<= w2
        with self.assertRaises(pyrtl.PyrtlError) as ex:
            pyrtl.working_block().sanity_check()
        self.assertEqual(
            str(ex.exception),
            'Invalid intermodular connections detected in "Top":\n'
            '(b/6O[M] -> a/4I[M])'
        )

    def test_outputs_to_multiple_connections(self):
        class M(pyrtl.Module):
            def __init__(self, name):
                super(M, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a')
                b = self.Input(6, 'b')
                c = self.Output(6, 'c')
                c <<= a * 4 - b

        m = M("M")
        w1 = m.c * 4
        w2 = m.c + 2
        r = pyrtl.Register(8)
        r.next <<= w1
        m.a <<= r
        m.b <<= w2
        with self.assertRaises(pyrtl.PyrtlError) as ex:
            pyrtl.Simulation()
        self.assertEqual(
            str(ex.exception),
            'Invalid intermodular connections detected in "Top":\n'
            '(c/6O[M] -> b/6I[M])'
        )


class TestNestedModulesNBitAdder(unittest.TestCase):

    class OneBitAdder(pyrtl.Module):
        def __init__(self, name=""):
            super(TestNestedModulesNBitAdder.OneBitAdder, self).__init__(name=name)

        def definition(self):
            a = self.Input(1, 'a')
            b = self.Input(1, 'b')
            cin = self.Input(1, 'cin')
            s = self.Output(1, 's')
            cout = self.Output(1, 'cout')
            s <<= a ^ b ^ cin
            cout <<= (a & b) | (a & cin) | (b & cin)

    class NBitAdder(pyrtl.Module):
        def __init__(self, n, name=""):
            assert (n > 0)
            self.n = n
            super(TestNestedModulesNBitAdder.NBitAdder, self).__init__(name=name)

        def definition(self):
            a = self.Input(self.n, 'a')
            b = self.Input(self.n, 'b')
            cin = self.Input(1, 'cin')
            cout = self.Output(1, 'cout')
            s = self.Output(self.n, 's')

            ss = []
            for i in range(self.n):
                oba = TestNestedModulesNBitAdder.OneBitAdder(name="oba_" + str(i))
                oba.a <<= a[i]
                oba.b <<= b[i]
                oba.cin <<= cin
                ss.append(oba.s)
                cin = oba.cout
            s <<= pyrtl.concat_list(ss)
            cout <<= cin

    def setUp(self):
        pyrtl.reset_working_block()
        self.module = TestNestedModulesNBitAdder.NBitAdder(4, name="nba")

    def test_sort_caching_correct(self):
        # For each submodule, verify the wiresorts are correct, meaning we didn't
        # just copy the sort via caching, but actually got the corresponding io
        # wire for each submodule from the cached calculation.
        for oba in self.module.submodules:
            self.assertTrue(isinstance(oba.a.sort, pyrtl.ToPort))
            self.assertTrue(oba.a.sort.output_port_set, {oba.s, oba.cout})
            self.assertTrue(isinstance(oba.b.sort, pyrtl.ToPort))
            self.assertTrue(oba.b.sort.output_port_set, {oba.s, oba.cout})
            self.assertTrue(isinstance(oba.cin.sort, pyrtl.ToPort))
            self.assertTrue(oba.cin.sort.output_port_set, {oba.s, oba.cout})
            self.assertTrue(isinstance(oba.s.sort, pyrtl.FromPort))
            self.assertTrue(oba.s.sort.input_port_set, {oba.a, oba.b, oba.cin})
            self.assertTrue(isinstance(oba.cout.sort, pyrtl.FromPort))
            self.assertTrue(oba.cout.sort.input_port_set, {oba.a, oba.b, oba.cin})


class TestAscriptions(unittest.TestCase):

    def setUp(self):
        pyrtl.reset_working_block()

    def test_good_sort_ascriptions_using_sort_classes(self):
        class L(pyrtl.Module):
            def __init__(self):
                super(L, self).__init__()

            def definition(self):
                a = self.Input(4, 'a', sort=pyrtl.ToSync)
                b = self.Output(6, 'b', sort=pyrtl.FromSync)
                c = self.Input(2, 'c', sort=pyrtl.ToPort)
                d = self.Output(2, 'd', sort=pyrtl.FromPort)
                r = pyrtl.Register(5, 'r')
                r.next <<= a + 1
                b <<= r * 4
                d <<= c - 1

        try:
            L()
        except pyrtl.PyrtlError:
            self.fail("The wire sort ascriptions are correct; "
                      "an error should not have been thrown.")

    def test_good_sort_ascription_using_objects_with_wire_names(self):
        class L(pyrtl.Module):
            def __init__(self, name=""):
                super(L, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a', sort=pyrtl.ToSync)
                b = self.Output(6, 'b', sort=pyrtl.FromSync)
                c = self.Input(2, 'c', sort=pyrtl.ToPort({'d'}))
                d = self.Output(2, 'd', sort=pyrtl.FromPort({'c'}))
                r = pyrtl.Register(5, 'r')
                r.next <<= a + 1
                b <<= r * 4
                d <<= c - 1

        try:
            L()
        except pyrtl.PyrtlError:
            self.fail("The wire sort ascription objects (using names) are correct; "
                      "an error should not have been thrown.")

    def test_bad_general_sort_ascriptions(self):
        """ This fails if we allow subtyped, rather than exact, subscriptions """
        class L(pyrtl.Module):
            def __init__(self, name=""):
                super(L, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a', sort=pyrtl.ToPort)
                b = self.Output(6, 'b', sort=pyrtl.FromSync)
                c = self.Input(2, 'c', sort=pyrtl.ToPort)
                d = self.Output(2, 'd', sort=pyrtl.FromPort)
                r = pyrtl.Register(5, 'r')
                r.next <<= a + 1
                b <<= r * 4
                d <<= c - 1

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            L("L")
        self.assertEqual(
            str(ex.exception),
            "Unmatched sort ascription on wire a/4I[L].\n"
            "User provided ToPort.\n"
            "But we computed ToSync."
        )

    def test_specific_bad_sort_ascriptions(self):
        """ This fails if we allow subtyped, rather than exact, subscriptions """
        class L(pyrtl.Module):
            def __init__(self, name=""):
                super(L, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a', sort=pyrtl.ToSync)
                b = self.Output(6, 'b', sort=pyrtl.FromSync)
                c = self.Input(2, 'c', sort=pyrtl.ToPort({'b'}))
                d = self.Output(2, 'd', sort=pyrtl.FromPort)
                r = pyrtl.Register(5, 'r')
                r.next <<= a + 1
                b <<= r * 4
                d <<= c - 1

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            L("L")
        self.assertEqual(
            str(ex.exception),
            "Unmatched sort ascription on wire c/2I[L].\n"
            "User provided ToPort (output port set: b).\n"
            "But we computed ToPort (output port set: d)."
        )

    def test_invalid_input_sort_ascription(self):
        class L(pyrtl.Module):
            def __init__(self, name=""):
                super(L, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a', sort=pyrtl.FromPort)
                b = self.Output(6, 'b', sort=pyrtl.FromPort)
                b <<= a * 4  # Never reached

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            L()
        self.assertEqual(
            str(ex.exception),
            'Invalid sort ascription for input "a" '
            '(must provide either ToSync or ToPort type name or instance).'
        )

    def test_invalid_output_sort_ascription(self):
        class L(pyrtl.Module):
            def __init__(self, name=""):
                super(L, self).__init__(name=name)

            def definition(self):
                a = self.Input(4, 'a', sort=pyrtl.ToPort)
                b = self.Output(6, 'b', sort=pyrtl.ToPort)
                b <<= a * 4

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            L()
        self.assertEqual(
            str(ex.exception),
            'Invalid sort ascription for output "b" '
            '(must provide either FromSync or FromPort type name or instance).'
        )


class TestNestedModules(unittest.TestCase):

    def setUp(self):
        pyrtl.reset_working_block()

    def test_nested_connection_with_state(self):
        class Inner(pyrtl.Module):
            def __init__(self):
                super(Inner, self).__init__()

            def definition(self):
                x = self.Input(6, 'x')
                r = pyrtl.Register(6)
                r.next <<= x
                y = self.Output(7, 'y')
                y <<= r + 4

        class Outer(pyrtl.Module):
            def __init__(self):
                super(Outer, self).__init__()

            def definition(self):
                i = self.Input(6, 'i')
                o = self.Output(7, 'o')
                b = Inner()
                b.x <<= i
                o <<= b.y

        inner_mod = Inner()
        self.assertTrue(isinstance(inner_mod.x.sort, pyrtl.ToSync))
        self.assertEqual(inner_mod.x.sort.output_port_set, set())
        self.assertTrue(isinstance(inner_mod.y.sort, pyrtl.FromSync))
        self.assertEqual(inner_mod.y.sort.input_port_set, set())
        outer_mod = Outer()
        self.assertTrue(isinstance(outer_mod.i.sort, pyrtl.ToSync))
        self.assertEqual(outer_mod.i.sort.output_port_set, set())
        self.assertTrue(isinstance(outer_mod.o.sort, pyrtl.FromSync))
        self.assertEqual(outer_mod.o.sort.input_port_set, set())

    def test_nested_connection_with_state2(self):
        class Inner(pyrtl.Module):
            def __init__(self, name=""):
                super(Inner, self).__init__(name=name)

            def definition(self):
                w = self.Input(1, 'w')
                x = self.Input(6, 'x')
                r = pyrtl.Register(6)
                r.next <<= x
                y = self.Output(7, 'y')
                y <<= r + 4 + w

        class Outer(pyrtl.Module):
            def __init__(self, name=""):
                super(Outer, self).__init__(name=name)

            def definition(self):
                i = self.Input(6, 'i')
                j = self.Input(1, 'j')
                o = self.Output(7, 'o')
                b = Inner("inner1")
                b.x <<= i
                b.w <<= j
                o <<= b.y

        inner_mod = Inner("inner2")
        self.assertTrue(isinstance(inner_mod.x.sort, pyrtl.ToSync))
        self.assertEqual(inner_mod.x.sort.output_port_set, set())
        self.assertTrue(isinstance(inner_mod.w.sort, pyrtl.ToPort))
        self.assertEqual(inner_mod.w.sort.output_port_set, {inner_mod.y})
        self.assertTrue(isinstance(inner_mod.y.sort, pyrtl.FromPort))
        self.assertEqual(inner_mod.y.sort.input_port_set, {inner_mod.w})
        outer_mod = Outer("outer")
        self.assertTrue(isinstance(outer_mod.i.sort, pyrtl.ToSync))
        self.assertEqual(outer_mod.i.sort.output_port_set, set())
        self.assertTrue(isinstance(outer_mod.j.sort, pyrtl.ToPort))
        self.assertEqual(outer_mod.j.sort.output_port_set, {outer_mod.o})
        self.assertTrue(isinstance(outer_mod.o.sort, pyrtl.FromPort))
        self.assertEqual(outer_mod.o.sort.input_port_set, {outer_mod.j})

    def test_direct_loop_inner_module(self):
        class Inner(pyrtl.Module):
            def __init__(self, name):
                super(Inner, self).__init__(name=name)

            def definition(self):
                x = self.Input(2, 'x')
                y = self.Output(2, 'y')
                y <<= x + 1

        class Outer(pyrtl.Module):
            def __init__(self, name):
                super(Outer, self).__init__(name=name)

            def definition(self):
                i = Inner(name="in_mod")
                i.x <<= i.y
                o = self.Output(1, 'o')
                o <<= 0

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            _o = Outer("Outer")
        self.assertEqual(
            str(ex.exception),
            'Invalid intermodular connections detected in "Outer":\n'
            '(y/2O[in_mod] -> x/2I[in_mod])'
        )

    def test_indirect_loop_inner_module(self):
        class Inner(pyrtl.Module):
            def __init__(self, name):
                super(Inner, self).__init__(name=name)

            def definition(self):
                x = self.Input(2, 'x')
                y = self.Output(2, 'y')
                y <<= x + 1

        class Outer(pyrtl.Module):
            def __init__(self, name):
                super(Outer, self).__init__(name=name)

            def definition(self):
                i = Inner("in_mod")
                o = self.Output(1, "o")
                o <<= 0
                w1 = pyrtl.WireVector(2)
                w2 = pyrtl.WireVector(2)
                w1 <<= i.y
                i.x <<= w2
                w2 <<= w1

        with self.assertRaises(pyrtl.PyrtlError) as ex:
            _o = Outer("Outer")
        self.assertEqual(
            str(ex.exception),
            'Invalid intermodular connections detected in "Outer":\n'
            '(y/2O[in_mod] -> x/2I[in_mod])'
        )


class TestSubsorts(unittest.TestCase):
    def setUp(self):
        pyrtl.reset_working_block()

    @unittest.skip
    def test_ascribe_input_as_supertype(self):
        # Can ascribe as something more strict than it actually is;
        # this allows you to essentially place restrictions on who
        # can connect to you "safely"
        class M(pyrtl.Module):
            def definition(self):
                i = self.Input(1, 'i', pyrtl.ToPort)
                r = pyrtl.Register(1, 'r')
                r.next <<= i
                o = self.Output(1, 'o')
                o <<= r

        try:
            _m = M()
        except pyrtl.PyrtlError:
            self.fail("Should not have failed when ascribing a to-sync input wire as to-port.")

    @unittest.skip
    def test_ascribe_output_as_supertype(self):
        class M(pyrtl.Module):
            def definition(self):
                i = self.Input(1, 'i')
                r = pyrtl.Register(1, 'r')
                r.next <<= i
                o = self.Output(1, 'o', pyrtl.FromPort)
                o <<= r

        try:
            _m = M()
        except pyrtl.PyrtlError:
            self.fail("Should not have failed when ascribing a from-sync output wire as from-port.")

    @unittest.skip
    def test_connecting_to_stricter_ascription(self):
        class M(pyrtl.Module):
            def definition(self):
                i = self.Input(1, 'i', pyrtl.ToPort)
                r = pyrtl.Register(1, 'r')
                r.next <<= i
                o = self.Output(1, 'o')
                o <<= r

        class N(pyrtl.Module):
            def definition(self):
                i = self.Input(1, 'i')
                o = self.Output(1, 'o', pyrtl.FromPort)
                o <<= ~i

        # Even though this connection is logically okay,
        # the user ascribed M.i as ToPort, so we should
        # treat M.i as ToPort despite it really being giving,
        # and produce this error.
        m = M()
        n = N()
        n.i <<= m.o
        m.i <<= n.o

        with self.assertRaises(pyrtl.PyrtlError):
            pyrtl.Simulation()


if __name__ == "__main__":
    unittest.main()
