#!/usr/bin/python

import cmd
import os
import re
import readline
import shelve
import sys

history_filename = os.path.expanduser("~/.traverse")
def_ident_re = re.compile(r'^#(\d+) ((.*?)(?:\$(.*))?)$')
edge_re = re.compile(r'^[DR] (SUPPRESS_GC |/\d+ )?(\d+) (\d+)')
stem_re = re.compile(r'([\w_]+)\(')

data = None

gAvoidFuncs = set(["NS_DebugBreak"])
gAvoid = set()  # Filled in by load_file

try:
    readline.read_history_file(history_filename)
except IOError:
    pass

class FunctionNotFound(Exception): pass

class MultipleFunctionsFound(Exception):
    def __init__(self, spec, functions):
        self.spec = spec
        self.functions = functions

    def report(self, verbose=True, count_callers=False, count_callees=False):
        print("'%s' matches %d functions:" % (self.spec, len(self.functions)))
        for f in functions:
            print("  " + describe(f, raw=verbose,
                                  count_callers=count_callers,
                                  count_callees=count_callees))

def stem(f):
    func = data['names'][f]
    m = stem_re.search(func)
    return m.group(1) if m else func

def load_file(callgraph_filename):
    callers = data['callers'] = {}
    callees = data['callees'] = {}

    # Give these dummy entries to count from one
    names = data['names'] = [None]
    readable = data['readable'] = [None]

    with open(callgraph_filename) as callgraph_file:
        for line in callgraph_file:
            m = def_ident_re.match(line)
            if m:
                ident, fullname, mangled, unmangled = m.groups()
                names.append(fullname)
                readable.append(unmangled or mangled)
            else:
                m = edge_re.match(line)
                if m:
                    suppress, caller, callee = m.groups()
                    caller = int(caller)
                    callee = int(callee)
                    if not suppress:
                        limits = 0
                    elif "SUPPRESS_GC" in suppress:
                        limits = 1
                    else:
                        limits = int(suppress[1:])
                    callers.setdefault(callee, {})[caller] = limits
                    callees.setdefault(caller, {})[callee] = limits

    gAvoid = set()
    for f in gAvoidFuncs:
        gAvoid.update(resolve(f))

# TODO: match against the stem, not the whole string (getting noise from param types)
def resolve_single(pattern):
    try:
        return [ int(pattern.replace('#', '')) ]
    except:
        pass
    pattern = pattern.strip('\'"')

    # First check for an exact match. Note that this will also catch C linkage
    # function names.
    try:
        idx = data['names'].index(pattern)
        return [idx]
    except:
        pass

    # Now look for a simple substring match.
    funcs = [ i for i, name in enumerate(data['names'][1:], 1) if pattern in name ]

    # Hack, should escape the rest of the string. And deal with eg
    # foo<T>::bar(param<U>)
    if len(funcs) == 0 and ('<>' in pattern or '<T>' in pattern):
        # Now try allowing <> to mean a template.
        funcs = []
        matcher = re.compile(pattern.replace('<>', '<.*?>').replace('<T>', '<.*?>'))
        for i, name in enumerate(data['names'][1:], 1):
            if re.search(matcher, name):
                funcs.append(i)

    # If we find multiple and it's a simple function name:
    if len(funcs) > 1 and not re.search(r'[^:\w]', pattern):
        # Look for "\bfuncname("
        r = re.compile(r'\b' + pattern + r'\(')
        justfuncs = [ i for i in funcs if r.search(data['readable'][i]) ]

        # ...and if that finds anything, return only those instead.
        if len(justfuncs) > 0:
            return justfuncs

    return funcs

def resolve(pattern):
    funcs = []
    for pattern in pattern.split(" and "):
        funcs += resolve_single(pattern)
    return funcs

data = {}
load_file(sys.argv[1])

print("len(callers) = %d" % (len(data['callers'].keys())))

def findRoute(src, dst, avoid):
    avoid = gAvoid.union(avoid or [])
    if isinstance(src, list):
        work = src[:]
    else:
        work = [src]
    edges = {}
    while len(work) > 0:
        caller = work.pop(0)
        for callee in data['callees'].get(caller, {}).keys():
            if callee == dst:
                edges[callee] = caller
                route = [callee]
                while route[0] != src:
                    route.insert(0, edges[route[0]])
                return route
            elif (callee not in avoid) and (callee not in edges):
                edges[callee] = caller
                work.append(callee)

    return []

# The idea is to do a single traversal, and during that traversal record enough
# information to generate the full set of routes that you're going to return
# (rather than eg repeating the traversal N times and forcing it to go a
# different way each time).
#
# Not the current code:
#
# Step 1: BFS from src to everything reachable. Except that the BFS starts from
# the immediate src.callees, and you know which callee you're working on during
# the traversal. When you see a back edge, mark the target node as a "join
# node" and tag it with the incoming src.callee.
#
# Step 2: Walk up from each dst.caller. When a join node is detected, update
# that node to say "this node can be reached from these src.callees". (Do not
# propagate that info anywhere during this pass.)
#
# Step 3: Redo the BFS in step 1, except don't search -- just traverse the
# paths used in step 2. Push the src.callees sets down throughout the tree.
#
# Step 4: Create a set of walkers, at least one for each src.callee and
# dst.caller. Each one is specific to a src.callee. Walk back up the full BFS
# tree, following branches for the relevant src.callee.
#
# Step 1 is linear in the number of nodes reachable from src. Step 2 is linear
# in the sum of the lengths of the shortest paths from src to each of
# dst.callers. Step 3 is linear in the size of the subgraph that is reachable
# from src and can reach any of dst.callers. Step 4 is linear in the total
# lengths of all the paths to output.
#
# In other words, all of the time is in step 1. Unfortunately, step 1 has to do
# a full BFS from src; it can't early-terminate when it finds dst. On the
# browser callgraph, it ends up visiting about half the total number of nodes
# (208k out of 520k). Then again, it's pretty fast, much faster than loading
# the graph from disk. (The whole traversal takes about a second.)

def getManyRoutes(src, dst, avoid):
    if src == dst:
        return [[src]]

    print("From %r to %r avoiding %r" % (src, dst, avoid))

    # Step 1: Do a BFS from each src_callee, adding caller backedges labeled
    # with the src_callee.
    src_callees = set(data['callees'].get(src, {}).keys()) - set([src]) - set(avoid)
    callers = {}
    for src_callee in src_callees:
        work = [src_callee]
        while work:
            caller = work.pop(0)
            for callee in data['callees'].get(caller, {}).keys():
                if callee == src:
                    continue
                if callee in avoid:
                    continue
                if callee not in callers:
                    callers[callee] = {}
                    work.append(callee)
                if src_callee not in callers[callee]:
                    callers[callee][src_callee] = caller

    # Step 2: Walk backwards from each dst_caller
    boingo = 0
    paths = []
    todo_src_callees = set(src_callees)
    for dst_caller in data['callers'].get(dst, {}).keys():
        # Check whether this dst_caller is src-reachable at all
        if dst_caller not in callers and dst_caller not in src_callees:
            continue
        if dst_caller in avoid:
            continue

        work = [(dst_caller,None,[dst])]
        done_labels = set()
        while work:
            callee, label, path = work.pop(0)
            if label in done_labels:
                continue
            #while callee not in src_callees and callee != src:
            while True:
                if callee == src:
                    break
                elif label is None:
                    if callee in src_callees:
                        break
                else:
                    if callee == label:
                        break

                boingo += 1
                if boingo > 25000:
                    print(callee)

                path.append(callee)
                my_callers = callers[callee]
                if len(my_callers.keys()) == 1:
                    # Generic back edge. Follow it.
                    callee = my_callers.values()[0]
                elif label is not None:
                    # Traversal is specific to a src_callee
                    if label in my_callers:
                        # Have an edge for that src_callee. Follow it.
                        callee = my_callers[label]
                    else:
                        # End of the road (how does this happen?!)
                        path = None
                        break
                else:
                    # Generic traversal with multiple back edges. Spawn
                    # traversals for any untaken src_callees, but always
                    # continue with one traversal (now labeled), even if it is
                    # not in todo_src_callees. (This ensures that we generate
                    # one path per dst_caller.)

                    assert None not in my_callers
                    choices = set(my_callers.keys())
                    if not choices:
                        continue

                    # Queue up any src_callees we still need (forking the
                    # search for the different src_callees)
                    for backedge_src_callee in (choices & todo_src_callees):
                        my_caller = my_callers[backedge_src_callee]
                        work.append((my_caller, backedge_src_callee, path[:]))
                        print("Forking off src_callee %d scan at %d -> %d" % (backedge_src_callee, my_caller, callee))
                        todo_src_callees.remove(backedge_src_callee)

                    # Only continue the unspecialized scan if there are any
                    # src_callees left. Continue onto the first caller, for
                    # very suspicious reasons.
                    if todo_src_callees:
                        callee = my_callers.values()[0]
                    else:
                        path = None
                        break

            if path is not None:
                path.append(callee)
                if callee != src:
                    path.append(src)
                if label is not None:
                    done_labels.add(label)
                path.reverse()
                paths.append(path)

    return paths

    # Step 1: Extract the subgraph reachable from src into 'callers'
    work = [src]
    callers = {}
    while work:
        caller = work.pop(0)
        for callee in data['callees'].get(caller, {}).keys():
            if callee not in callers:
                callers[callee] = set()
            if caller not in callers[callee]:
                callers[callee].add(caller)
                work.append(callee)

    if dst not in callers:
        print("No path from #%d -> #%d found" % (src, dst))
        return

    print("Trimming down to everything that can reach dst")

    # Step 2: Extract out canreach-dst subgraph out of the src-reachable graph
    # from the previous step.
    work = [dst]
    callees = {}
    while work:
        callee = work.pop(0)
        for caller in callers.get(callee, set()):
            if caller not in callees:
                callees[caller] = set()
            if callee not in callees[caller]:
                callees[caller].add(callee)
                work.append(caller)

    print("Printing out graph")

    # Step 3: Do a DFS through the subgraph to print it out. Any extra edges
    # will be queued up and their callgraphs displayed (up until something that
    # has already been shown.)
    toshow = set(callees.keys())
    toshow.add(dst)
    key = []
    work = [[src]]
    while work:
        path = work.pop(0)
        assert len(path) == 1
        if path[0] not in toshow:
            continue
        while len(path) > 0:
            caller = path.pop()
            sys.stdout.write("#%s=%s" % (caller, stem(caller)))
            toshow.remove(caller)
            key.append(caller)
            mainEdge = True
            for callee in callees.get(caller, set()):
                if callee not in toshow:
                    sys.stdout.write(" #%s=%s" % (callee, stem(callee)))
                    key.append(callee)
                else:
                    if mainEdge:
                        mainEdge = False
                        path.append(callee)
                    else:
                        work.append([callee])
                        sys.stdout.write(" #%s=%s" % (callee, stem(callee)))
                        toshow.remove(callee)
                        key.append(callee)
            print("")
        print("----")

    print("Function name table:")
    shown = set()
    for f in key:
        if f not in shown:
            print(describe(f, raw=True))
            shown.add(f)

def findRouteMulti(srcs, dst, avoid):
    edges = {}
    srcset = set(srcs)  # For hopefully faster lookup
    avoid = set(avoid)
    found = set()

    work = [dst]
    while len(work) > 0:
        callee = work.pop(0)
        for caller in data['callers'].get(callee, {}).keys():
            if caller in avoid:
                continue

            if caller not in edges:
                edges[caller] = callee
                work.append(caller)

            if caller in srcset:
                found.add(caller)

                # Optimization for simple cases
                if len(found) == len(srcs):
                    work = []
                    break

    routes = []
    for src in found:
        route = [src]
        routes.append(route)
        while route[-1] != dst:
            route.append(edges[route[-1]])

    return routes

def rootPaths(dst):
    edges = {}
    found = []

    work = [dst]
    while len(work) > 0:
        callee = work.pop(0)
        callers = data['callers'].get(callee, {}).keys()
        if len(callers) == 0:
            found.append(callee)
        else:
            for caller in callers:
                if caller not in edges:
                    edges[caller] = callee
                    work.append(caller)

    routes = []
    for caller in found:
        route = [caller]
        routes.append(route)
        while route[-1] != dst:
            route.append(edges[route[-1]])

    return routes

def reachable(srcs, avoid):
    edges = {}
    found = []

    work = list(srcs)
    while len(work) > 0:
        caller = work.pop(0)
        callees = data['callees'].get(caller, {}).keys()
        if len(callees) == 0:
            found.append(caller)
        else:
            for callee in callees:
                if (callee not in avoid) and (callee not in edges):
                    edges[callee] = caller
                    work.append(callee)

    routes = []
    for callee in found:
        route = [callee]
        routes.append(route)
        while route[-1] not in srcs:
            route.append(edges[route[-1]])

    return routes

def describe(f, raw=False, count_callers=True, count_callees=False):
    names = data['readable']
    if raw:
        names = data['names']
    s = "#%d = %s" % (f, names[f])
    if count_callers:
        s += " (%d callers)" % len(data['callers'].get(f, {}).keys())
    if count_callees:
        s += " (%d callees)" % len(data['callees'].get(f, {}).keys())
    return s

class Commander(cmd.Cmd):
    quit = False
    stdout = None
    verbose = False

    def do_verbose(self):
        '''Toggle verbosity (including mangled function names)'''
        self.verbose = not self.verbose
        if self.verbose:
            print("displaying mangled function names together with readable versions")
        else:
            print("displaying only readable portions of function names")

    def do_test(self, what):
        '''Just a test function'''
        print("testing %r" % (what,))

    def do_resolve(self, s):
        '''Resolve a function identifier or a substring of a function name to the full function name(s)'''
        functions = self.parse_functions(s, required=False)
        if functions:
            print(describe(functions))
        else:
            print("No matching function found")

    def do_callcounts(self, s):
        '''Display all functions, preceded by caller count then callee count'''
        for i in range(1, len(data['names'])):
            callers = len(data['callers'].get(i, {}).keys())
            callees = len(data['callees'].get(i, {}).keys())
            print "%d %d %s" % (callers, callees, data['names'][i])

    def do_callers(self, s):
        '''Display all callers of FUNCTION'''
        try:
            f = self.parse_function(s)
        except FunctionNotFound:
            return
        callers = data['callers'].get(f, {})
        print("%d callers of #%d = %s" % (len(callers.keys()), f, data['readable'][f]))
        for caller, suppressed in callers.iteritems():
            print("  #%d = %s%s" % (caller, "(SUPPRESSED) " if suppressed else "", data['readable'][caller]))

    def do_caller(self, s):
        return self.do_callers(s)

    def do_callees(self, s):
        '''Display all callees of FUNCTION (all functions called by FUNCTION)'''
        try:
            f = self.parse_function(s)
        except FunctionNotFound:
            return
        except MultipleFunctionsFound as e:
            e.report(self.verbose, count_callees=True, count_callers=False)
            return

        callees = data['callees'].get(f, {})
        print("%d callees of #%d = %s" % (len(callees.keys()), f, data['readable'][f]))
        for callee, suppressed in callees.iteritems():
            print("  #%d = %s%s" % (callee, "(SUPPRESSED) " if suppressed else "", data['readable'][callee]))

    def do_callee(self, s):
        return self.do_callees(s)

    # required: whether the spec must match *something* (though see also none_ok)
    # single: fail if multiple functions match. Implies required.
    # none_ok: spec may be None (will return None)
    #
    # Returns list of functions found, or None if spec was None and none_ok was set.
    def parse_functions_impl(self, spec, required=True, single=True, none_ok=False):
        if spec is None:
            if not none_ok:
                print("function name is required")
                raise FunctionNotFound()
            return

        patterns = [spec] if single else spec.split(" and ")
        functions = []
        for pattern in patterns:
            functions += resolve_single(pattern)

        if len(functions) == 0:
            if required or single:
                print("nothing matching '%s' found" % (spec,))
                raise FunctionNotFound()
            return []

        if single and len(functions) > 1:
            raise MultipleFunctionsFound(spec, functions)

        return functions

    # Returns a list of matching functions.
    def parse_functions(self, spec, required=True, none_ok=False):
        return self.parse_functions_impl(spec, required=required, single=False, none_ok=none_ok)

    # Returns matching function, or None if none_ok was true and spec was None.
    def parse_function(self, spec):
        functions = self.parse_functions_impl(spec, single=True, none_ok=False)
        return functions[0]

    def do_route(self, s):
        '''Find a route from SOURCE to DEST [avoiding FUNC]'''
        m = re.match(r'^(?:from )?(.*) to (.*?)(?: avoiding (.*))?$', s)
        if not m:
            m = re.match(r'^(.*?) (.*?)(?: (.*))?$', s)
            if not m:
                print("Invalid syntax. Usage: route <src> to <dst>[ avoiding <func>]")
                return
        src, dst, avoid = m.groups()
        try:
            src = self.parse_functions(src)
            dst = self.parse_function(dst)
            avoid = self.parse_functions(avoid, none_ok=True)
        except FunctionNotFound:
            return
        except MultipleFunctionsFound as e:
            e.report(self.verbose)
            return

        path = findRoute(src, dst, avoid)
        if path:
            str = "Path from #%d to #%d:" % (src, dst)
            if avoid:
                str += " avoiding %r" % (avoid,)
            print(str)
            laststep = None
            for step in path:
                limit_str = ""
                if laststep is not None:
                    limits = data['callees'][laststep][step]
                    if limits:
                        limit_str = "(IN LIMITED %d) " % limits
                print("  %s#%d = %s" % (limit_str, step, data['readable'][step]))
                laststep = step
        elif avoid:
            print("No route from #%d to #%d found without going through %s" % (src, dst, avoid))
        else:
            print("No route from #%d to #%d found" % (src, dst))

    def do_reachable(self, s):
        '''Find all functions reachable from anything matching FUNCTION [avoiding FUNCTION]'''
        m = re.match(r'^(?:from )?(.*?)(?: avoiding (.*))?$', s)
        if not m:
            print("Invalid syntax. Usage: reachable from <src>[ avoiding <func>]")
            return
        src_spec, avoid_spec = m.groups()
        try:
            srcs = self.parse_functions(src_spec)
            avoid = self.parse_functions(avoid_spec, none_ok=True)
        except FunctionNotFound:
            return

        routes = reachable(srcs, avoid)
        if len(routes) == 0:
            print("No paths found??!")
            return

        print("%d total reachable functions found" % (len(routes),))

        if routes:
            print("All reachable functions:")
            for route in routes:
                print(describe(route[0]))
            print("Route from source to every reachable function:")
            for route in routes:
                for func in reversed(route):
                    print(describe(func, count_callers=False))
                print("")

    def do_roots(self, s):
        '''Find all roots that eventually call FUNCTION'''
        try:
            dst = self.parse_function(s)
        except FunctionNotFound:
            return
        routes = rootPaths(dst)
        if len(routes) == 0:
            print("No paths found??!")
            return

        for route in routes:
            print(describe(route[0]))

        print("%d total roots found" % (len(routes),))

    def do_rootpaths(self, s):
        '''Find paths from all roots to FUNCTION'''
        try:
            dst = self.parse_function(s)
        except FunctionNotFound:
            return
        routes = rootPaths(dst)
        if len(routes) == 0:
            print("No paths found??!")
            return

        for route in routes:
            print("Root:")
            for f in route:
                print("  #%d = %s" % (f, data['readable'][f]))

    def do_routes(self, s):
        '''Find a route from anything matching SOURCE to DEST (must be unique)'''
        m = re.match(r'^(?:from )?(.*) to (.*?)(?: avoiding (.*))?$', s)
        if not m:
            m = re.match(r'^(.*) (.*)()$', s)
            if not m:
                print("Invalid syntax. Usage: route <src> to <dst>[ avoiding <func>]")
                return
        src, dst, avoid = m.groups()
        try:
            srcs = self.parse_functions(src)
            dst = self.parse_function(dst)
            avoid = self.parse_functions(avoid, none_ok=True)
        except FunctionNotFound:
            return
        except MultipleFunctionsFound as e:
            e.report(self.verbose)
            return

        routes = findRouteMulti(srcs, dst, avoid)
        for path in routes:
            print("Path:")
            for step in path:
                print("  #%d = %s" % (step, data['readable'][step]))

    def do_manyroutes(self, s):
        '''Show several routes from SOURCE to DEST (both must be unique)'''
        m = re.match(r'^(?:from )?(.*) to (.*?)(?: avoiding (.*))?$', s)
        if not m:
            m = re.match(r'^(.*) (.*?)(?: avoiding (.*))?$', s)
            if not m:
                print("Invalid syntax. Usage: manyroutes from <src> to <dst>[ avoiding <sym>]")
                return
        src, dst, avoid = m.groups()
        try:
            src = self.parse_function(src)
            dst = self.parse_function(dst)
            avoid = self.parse_functions(avoid, none_ok=True)
        except FunctionNotFound:
            return
        except MultipleFunctionsFound as e:
            e.report(self.verbose)
            return

        routes = getManyRoutes(src, dst, avoid)

        keys = []
        seen_keys = set()
        for route in routes:
            for node in route:
                print("%s(#%d)" % (stem(node), node))
                if node not in seen_keys:
                    seen_keys.add(node)
                    keys.append(node)
            print("------")
        print("Lookup key:")
        for node in keys:
            print(describe(node, count_callers=False))

    def do_EOF(self, s):
        self.quit = True

    def do_quit(self, s):
        self.quit = True

    def postcmd(self, stop, line):
        return self.quit

    def do_output(self, s):
        if self.stdout is None:
            self.stdout = sys.stdout
        if s == '-':
            sys.stdout = self.stdout
            print >>self.stdout, "Redirected output to stdout"
        else:
            sys.stdout = open(s, "w")
            print >>self.stdout, "Redirected output to " + s

    def do_edges(self, s):
        nodesets = [ resolve(p) for p in s.split(" ") ]
        if [] in nodesets:
            return
        nodes = reduce(lambda a, b: a+b, nodesets)
        known = set(nodes)
        for src in nodes:
            for dst in data['callees'].get(src, {}).keys():
                if dst in known:
                    print("#%d -> #%d" % (src, dst))

    def completedefault(self, text, line, begidx, endidx):
        return [n for n in data['names'][1:] if n.startswith(text)]

c = Commander()
c.cmdloop()
readline.write_history_file(history_filename)
