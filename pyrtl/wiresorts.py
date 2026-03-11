"""
Set of classes and functions for expressing the "sort" of a wire.
Here we're currently concerned with defining intermodular dependencies
via the ToSync, ToPort, FromSync, and FromPort wire sorts, and using these
sorts for determining well-connectedness.
"""

from .pyrtlexceptions import PyrtlError, PyrtlInternalError
from .core import working_block
from .wire import Register

Verbose = False


def _verbose_print(s):
    if Verbose:
        print(s)


#############################################
# Paper Section 3.3 "Wire Sort" definitions #
#############################################
class InputSort(object):
    """ Base class for the sorts that can be assigned to module inputs """
    pass


class ToSync(InputSort):
    """ The wire sort for module inputs that are not combinationally connected
        to any its module's outputs """

    def __init__(self, ascription=True):
        self.output_port_set = set()
        self.ascription = ascription

    def __str__(self):
        return "ToSync"


class ToPort(InputSort):
    """ The wire sort for module inputs that *are* combinationally connected
        to one or more of its module's outputs """

    def __init__(self, output_port_set, ascription=True):
        from .module import _ModOutput
        self.output_port_set = output_port_set  # set of strings (wire names) if ascription=True
        self.ascription = ascription
        # Sanity check
        if not self.ascription:
            for w in self.output_port_set:
                assert(isinstance(w, _ModOutput))

    def __str__(self):
        if self.ascription:
            wns = ", ".join(sorted(self.output_port_set))
        else:
            wns = ", ".join(sorted(map(lambda w: w._original_name, self.output_port_set)))
        return "ToPort (output port set: %s)" % wns


class OutputSort(object):
    """ Base class for the sorts that can be assigned to module outputs """
    pass


class FromSync(OutputSort):
    """ A wire sort for module outputs that are not combinationally connected
        to any its module's inputs """

    def __init__(self, ascription=True):
        self.input_port_set = set()
        self.ascription = ascription

    def __str__(self):
        return "FromSync"


class FromPort(OutputSort):
    """ The wire sort for module outputs that *are* combinationally connected
        to one or more of its module's inputs """

    def __init__(self, input_port_set, ascription=True):
        from .module import _ModInput
        self.input_port_set = input_port_set  # set of strings (wire names) if ascription=True
        self.ascription = ascription
        # Sanity check
        if not self.ascription:
            for w in self.input_port_set:
                assert(isinstance(w, _ModInput))

    def __str__(self):
        if self.ascription:
            wns = ", ".join(sorted(self.input_port_set))
        else:
            wns = ", ".join(sorted(map(lambda w: w._original_name, self.input_port_set)))
        return "FromPort (input port set: %s)" % wns


def sanity_check_input_sort(sort, wirename):
    if (sort
            and (sort not in (ToSync, ToPort))
            and (not isinstance(sort, (ToSync, ToPort)))):
        raise PyrtlError(
            'Invalid sort ascription for input "%s" '
            '(must provide either ToSync or ToPort type name or instance).'
            % wirename
        )


def sanity_check_output_sort(sort, wirename):
    if (sort
            and (sort not in (FromSync, FromPort))
            and (not isinstance(sort, (FromSync, FromPort)))):
        raise PyrtlError(
            'Invalid sort ascription for output "%s" '
            '(must provide either FromSync or FromPort type name or instance).'
            % wirename
        )


########################################################
# Paper Section 3.5, Stages 2 and 3                    #
#                                                      #
# This is where intermodular connections are checked.  #
########################################################
def check_module_interconnections(supermodule=None, stop_after_first_loop=False, perf_info=None):
    """ Check if all modules in a supermodule (or the block if not given)
        are well-connected to one another.

        Compute the intermodular reachability once to save some computation hopefully.
        If there is more than one bad connection between a pair of modules, we report
        all of them.
    """
    import timeit
    import collections

    if not supermodule:
        SM = collections.namedtuple('SM', ['submodules', 'name', 'class_name', 'inputs', 'outputs'])
        supermodule = SM(working_block().toplevel_modules, "Top", "Top", [], [])

    # Prefer to get the work list of modules bread-first,
    # rather than the simpler recursive descent and build-up.
    def get_all_module_instances(m):
        # For evaluation metrics
        total_mod_count = 0
        unique_mods = set()

        modules = []
        worklist = [m]
        while len(worklist) > 0:
            mod = worklist[0]
            worklist = worklist[1:]
            total_mod_count += 1
            unique_mods.add(mod.class_name)

            ###############################################
            # Paper Section 3.5 Stage 2, enhancement:     #
            #                                             #
            # Modules without any ToPort inputs/FromPort  #
            # outputs don't have to be considered at all. #
            ###############################################
            if any(map(lambda i: isinstance(i.sort, ToPort), mod.inputs)):
                # Don't add module to check interconnection for if all i/o are FromPort/ToPort
                assert any(map(lambda o: isinstance(o.sort, FromPort), mod.outputs))
                modules.append(mod)
            else:
                _verbose_print("No need to check connections in/out of "
                               "%s (%s)" % (mod.name, mod.class_name))
            worklist += list(mod.submodules)
        return modules, total_mod_count, len(unique_mods)

    ts = timeit.default_timer()

    modules, total_mod_count, unique_mod_count = get_all_module_instances(supermodule)
    _verbose_print("Total number of module instances: %d" % total_mod_count)
    if not modules:
        return

    src_map, _ = modules[0].block.net_connections()  # Expensive, so do once
    wires_to_inputs = _build_intermodular_reachability_maps(modules, src_map=src_map)  # Expensive

    bad_connections = []
    for m in modules:
        _verbose_print("Checking %s (%s)" % (m.name, m.class_name))
        bad_conn = find_bad_connection_from_module(m, wires_to_inputs)
        if bad_conn:
            bad_connections.append(bad_conn)
            if stop_after_first_loop:
                break

    te = timeit.default_timer()

    if perf_info is not None:
        perf_info['timing'] = {'start': ts, 'end': te}
        # Following has -1 to omit Top supermodule
        perf_info['submodules'] = {'total': total_mod_count - 1, 'unique': unique_mod_count - 1}

    if bad_connections:
        raise PyrtlError(
            'Invalid intermodular connections detected in "%s":\n%s\nFind Bad Connections: %d'
            % (supermodule.name if supermodule else "Top",
               "\n".join("(%s -> %s)" % (str(output), str(input))
                         for (output, input) in bad_connections),
               len(bad_connections))
        )


###################################################################################
# Paper Section 3.5, Stage 3, and the 'TransitivelyAffect' relation from Figure 6 #
###################################################################################
def find_bad_connection_from_module(module, wires_to_inputs=None, src_map=None):
    """ Check if a single module is well-connected to other modules in the block.
        Returns the first bad connection found originating from it.
    """

    from .module import _ModInput, _ModOutput

    if not wires_to_inputs:
        wires_to_inputs = _build_intermodular_reachability_maps([module], src_map=src_map)

    for output in module.outputs:
        if not output.sort:
            raise PyrtlInternalError(
                'Cannot check well-connectedness of output wire "%s" that '
                'hasn\'t been annotated.' % str(output)
            )
        if isinstance(output.sort, FromSync):
            continue

        for input in wires_to_inputs[output]:
            if not input.sort:
                raise PyrtlInternalError(
                    'Cannot check well-connectedness of input wire "%s" that '
                    'hasn\'t been annotated.' % str(input)
                )
            # Note that ascriptions are fine, because by this point they should have
            # been validated as correct, or thrown an error otherwise

            ##################################################
            # Paper: Transitively-Affects relation, Figure 6 #
            ##################################################
            if isinstance(input.sort, ToPort):
                for input_port_w in output.sort.input_port_set:
                    assert isinstance(input_port_w, _ModInput)
                    for output_port_w in input.sort.output_port_set:
                        assert isinstance(output_port_w, _ModOutput)
                        if input_port_w in wires_to_inputs[output_port_w]:
                            return (output, input)
    return None


def _build_intermodular_reachability_maps(modules, src_map=None):
    """ Right now, just computes for each module output and wire outside a module,
        the set of module inputs it reaches combinationally

        It's much better to not have to recompute src_map if possible, so pass it in
        if nothing's changed since the last call.
    """
    from .module import _ModOutput

    # map from wire to set of module inputs it forward affects, combinationally
    wires_to_inputs = {}

    block = list(modules)[0].block
    if src_map is None:
        src_map, _ = block.net_connections()

    for module in modules:

        for o in module.outputs:
            wires_to_inputs[o] = set()

        for input in module.inputs:
            work_list = [input]
            seen = set()

            while work_list:
                s = work_list.pop()
                if s in seen:
                    continue
                seen.add(s)

                if s is not input:
                    wires_to_inputs.setdefault(s, set()).add(input)

                # Must take advantage of module annotations so we
                # don't need to descend into more nets than needed
                if isinstance(s, _ModOutput):
                    work_list.extend(s.sort.input_port_set)
                else:
                    # Registers break the combinational chain
                    if isinstance(s, Register):
                        continue

                    if s not in src_map:
                        continue
                    src_net = src_map[s]
                    assert src_net.dests[0] is s

                    if src_net.op == 'm' and not src_net.op_param[1].asynchronous:
                        continue
                    if src_net.op == '@':
                        continue
                    work_list.extend(src_net.args)

    # Just return the outputs
    wires_to_inputs = {o: s for o, s in wires_to_inputs.items() if isinstance(o, _ModOutput)}
    return wires_to_inputs


def _build_intramodular_reachability_maps(module, src_map=None):
    """ Constructs the reachable output port set/reachable input port set maps
        limited to the module given.

        Assumes that modules are well-constructed in that all internal wires are
        really internal (i.e. not connected to wires defined outside the module).

        The advantage of this is that annotating each module input/output
        only requires traversing the module once at the beginning to build these maps,
        rather than for each io.

        The intention of this is purely for intramodular dependency calculation;
        checks for valid intermodular connections is done in is_well_connected_module
        (which uses the _build_intermodular_reachability_maps).

        Pass in src_map if the block hasn't changed (i.e., we've already imported
        all the modules and are now just annotating).
    """
    from .module import _ModInput, _ModOutput

    # map from any wire to the outputs it affects, combinationally;
    # we track every wire's affected output for effiency during
    # traversal, but by the end we'll just return a map whose keys are just *input*,
    # so let's make sure the inputs are at least present right now
    output_port_sets = {i: set() for i in module.inputs}

    # map from *output* to the inputs that reach it combinationally;
    # this is calculated using output_port_set for efficiency.
    input_port_sets = {o: set() for o in module.outputs}

    block = module.block
    # DON'T ALWAYS DO THIS HERE; this is an expensive operation.
    # Do it *once* outside of all of this mess, and pass it in.
    if src_map is None:
        src_map, _ = block.net_connections()

    for output in module.outputs:
        _verbose_print("Output " + str(output))
        work_list = [output]
        seen = set()

        while work_list:
            a = work_list.pop()
            if a in seen:
                continue
            seen.add(a)
            _verbose_print("checking " + str(a))

            # Registers break the combinational chain
            if isinstance(a, Register):
                continue

            # NOTE: check for None to deal with subckt from BLIF
            if (a.module is not None) and (a.module != output.module):
                # Skip over the submodule by going backwards to its inputs
                if not isinstance(a, _ModOutput):
                    raise PyrtlInternalError(
                        'The sanity checks should have detected this invalid '
                        'connection originating from "%s.%s" in module "%s" by now.'
                        % (a.module.name, a.name, output.module.name)
                    )
                if not a.sort:
                    raise PyrtlInternalError(
                        'All submodules should be annotated before attempting to '
                        'annotate their supermodule. Here, submodule "%s" in "%s" '
                        'is not yet annotated.' % (a.module.name, output.module.name)
                    )
                assert isinstance(a.sort, OutputSort)
                for affector in a.sort.input_port_set:
                    if affector in src_map:
                        work_list.extend(src_map[affector].args)
            else:
                if a is not output:  # For simplicity, we added the initial output to the work list
                    output_port_sets.setdefault(a, set()).add(output)
                if a not in src_map:
                    continue
                src_net = src_map[a]
                assert src_net.dests[0] is a

                if src_net.op == 'm' and not src_net.op_param[1].asynchronous:
                    continue
                if src_net.op == '@':
                    raise PyrtlError("memwrites should not have a destination wire")
                if isinstance(a, _ModInput):  # Stay within the module
                    continue

                work_list.extend(src_net.args)

    # Just care about output port set of the inputs
    output_port_sets = {i: s for i, s in output_port_sets.items() if i in module.inputs}

    # Now create the input_port_sets map, which is essentially the inverse
    for input in module.inputs:
        for output in output_port_sets[input]:
            assert isinstance(output, _ModOutput) and output.module == input.module
            input_port_sets[output].add(input)

    return output_port_sets, input_port_sets


def sort_matches(ascription, sort):
    # User can just supply classname (e.g. sort=ToPort) without specifying _what_
    # the output wire it combinationally reaches; that's fine, we just won't compare
    # against the wires in its output port set
    if isinstance(ascription, type):
        return isinstance(sort, ascription)

    # Otherwise user supplied an instance of the InputSort/OutputSort class:
    assert ascription.ascription
    if isinstance(ascription, ToSync) and isinstance(sort, ToSync):
        return True
    if isinstance(ascription, FromSync) and isinstance(sort, FromSync):
        return True
    if isinstance(ascription, ToPort) and isinstance(sort, ToPort):
        expected_names = ascription.output_port_set
        actual_names = set({w._original_name for w in sort.output_port_set})
        return expected_names == actual_names
    if isinstance(ascription, FromPort) and isinstance(sort, FromPort):
        expected_names = ascription.input_port_set
        actual_names = set({w._original_name for w in sort.input_port_set})
        return expected_names == actual_names

    return False


###############################
# Paper: Section 3.5, Stage 1 #
###############################
def annotate_module(module, assume_ascriptions=False, src_map=None):
    """ Annotate the wire sorts for all the I/O ports
    :param assume_ascriptions: if True, treat the ascriptions as truth,
    and *don't* check if their correctness by analyzing intramodular connections
    (i.e. treat the module as a black box).
    """
    _verbose_print("Annotating module %s{module.name} with %d inputs and %d outputs."
                   % (module.name, len(module.inputs), len(module.outputs)))
    modname = module.class_name

    # For efficiency, only calculate the wire sorts of a module once;
    # save the information in the block
    if modname in module.block.module_sorts:
        _verbose_print("Using cached sort information for %s" % modname)
        sorts = module.block.module_sorts[modname]
        for io in module.inputs.union(module.outputs):
            # Now make sure our particular instance of this module refers
            # to our own ModInputs/ModOutputs
            def update_set(s):
                r = set()
                for w in s:
                    r.add(getattr(module, w._original_name))
                return r

            if io._original_name not in sorts:
                # TODO: right now, there's an issue with indirected clks, so handle special
                _verbose_print("Assuming this is a clock: '%s'" % io._original_name)
                io.sort = ToSync(ascription=False)
                continue
                # raise PyrtlInternalError(f"{io._original_name} is not i/o port for {modname}")
            sort = sorts[io._original_name]
            if isinstance(sort, ToSync):
                io.sort = ToSync(ascription=False)
            elif isinstance(sort, FromSync):
                io.sort = FromSync(ascription=False)
            elif isinstance(sort, ToPort):
                io.sort = ToPort(update_set(sort.output_port_set), ascription=False)
            else:
                io.sort = FromPort(update_set(sort.input_port_set), ascription=False)
    elif assume_ascriptions:
        # Convert ascription names to actual wires.
        sortmap = {}
        for i in module.inputs:
            sort = i.sort
            if isinstance(sort, type):
                if sort is FromPort or sort is ToPort:
                    # We aren't overapproximating
                    raise PyrtlError('For assumed ascriptions which are FromPort or ToPort, '
                                     'must supply the input-port-set or output-port-set set of '
                                     'wires, respectively.')
                sortmap[i._original_name] = sort()
            else:
                sort.output_port_set = set(getattr(module, n) for n in sort.output_port_set)
                sortmap[i._original_name] = sort
        for o in module.outputs:
            sort = o.sort
            if isinstance(sort, type):
                sortmap[i._original_name] = sort()
            else:
                sort.input_port_set = set(getattr(module, n) for n in sort.input_port_set)
                sortmap[o._original_name] = sort
        module.block.module_sorts[modname] = sortmap
    else:
        _verbose_print("Calculating sort information for %s from scratch" % modname)
        sortmap = {}
        reachable_output_ports, reachable_input_ports =\
            _build_intramodular_reachability_maps(module=module, src_map=src_map)

        for io in module.inputs.union(module.outputs):
            sort = _make_wire_sort(io, reachable_output_ports, reachable_input_ports)

            # If wire.sort was ascribed, check it and report if not matching.
            # The user can provide the classname of the sort or an actual instance of the class.
            if io.sort and not sort_matches(io.sort, sort):
                if isinstance(io.sort, type):
                    ascribed_str = io.sort.__name__
                else:
                    ascribed_str = str(io.sort)
                raise PyrtlError(
                    "Unmatched sort ascription on wire %s.\n"
                    "User provided %s.\n"
                    "But we computed %s."
                    % (str(io), ascribed_str, str(sort)))
            io.sort = sort

            sortmap[io._original_name] = sort

        module.block.module_sorts[modname] = sortmap


def _make_wire_sort(wire, reachable_output_ports, reachable_input_ports):
    from .module import _ModInput, _ModOutput

    if isinstance(wire, _ModInput):
        input = wire
        nb_set = reachable_output_ports[input]
        if nb_set:
            return ToPort(nb_set, ascription=False)
        else:
            return ToSync(input)
    elif isinstance(wire, _ModOutput):
        output = wire
        do_set = reachable_input_ports[output]
        if do_set:
            return FromPort(do_set, ascription=False)
        else:
            return FromSync(output)
