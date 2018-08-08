######################################################################

def find_nearest_index(searchkey, collection, key=lambda x: x):
    '''Find the last index in the list with an entry not greater than the given item, but if multiple indexes have the same key, return the index of the first one. There must be a better way of saying that.'''
    for i, element in enumerate(collection):
        extracted = key(element)
        if extracted == searchkey:
            return i
        elif extracted > searchkey:
            return i - 1
    return len(collection) - 1

def find_nearest(searchkey, collection, key=lambda x: x, default=None):
    s = sorted(collection, key=key)
    nearest = find_nearest_index(searchkey, s, key)
    if nearest < 0:
        return default

    if isinstance(collection, list):
        # key maps an element of the collection to its sort key
        # s is a sorted version of collection
        return s[nearest]
    else:
        # key() maps a key in the collection to its sort key
        # s is a sorted list of keys from collection
        return collection[s[nearest]]

class JITInstructionMap(gdb.Command):
    """Given a log file generated with ION_SPEW_FILENAME=spew.log and IONFLAGS=codegenmap, look at the current $pc and set a breakpoint on the code that generated it."""
    def __init__(self):
        gdb.Command.__init__(self, "jitwhere", gdb.COMMAND_USER)
        self.scripts = None
        self.codemap = None

        # Load from ION_SPEW_FILENAME, which is not at all guaranteed to be the
        # same value that was used when the file was generated.
        self.spewfile = os.getenv("ION_SPEW_FILENAME", "spew.log")

        self.editor = os.environ.get('EDITOR', 'emacs')

        self.kidpids = set()

    def load_spew(self):
        scripts = {}
        self.codemap = defaultdict(dict)

        current_compilation = None
        with open(self.spewfile, "r") as spew:
            lineno = 0
            for line in spew:
                lineno += 1
                m = re.search(r'\[Codegen\].*\(raw ([\da-f]+)\) for compilation (\d+)', line)
                if m:
                    scripts[int(m.group(1), 16)] = current_compilation
                m = re.search(r'\[Codegen\] # Emitting .*compilation (\d+)', line)
                if m:
                    current_compilation = int(m.group(1))
                m = re.search(r'\[Codegen\] \@(\d+)', line)
                if m:
                    self.codemap[current_compilation][int(m.group(1))] = lineno

        return [(code,scripts[code]) for code in sorted(scripts.keys())]

    def reap(self):
        while True:
            try:
                (pid, status, rusage) = os.wait3(os.WNOHANG)
                if pid == 0:
                    # Have child that is still running.
                    break
                self.kidpids.remove(pid)
            except ChildProcessError:
                break
            except KeyError:
                # Not ours, but oh well.
                pass

    def invoke(self, arg, from_tty):
        self.reap()

        self.scripts = self.scripts or self.load_spew()
        if not self.scripts:
            print("no compiled scripts found")
            return
        pc = int(gdb.selected_frame().read_register("pc"))
        (code, compilation) = find_nearest(pc, self.scripts,
                                           key=lambda x: x[0],
                                           default=(None, None))
        if code is None:
            print("No compiled script found")
            return

        offset = pc - code
        lineno = find_nearest(offset, self.codemap[compilation])
        print("pc %x at %x + %d, compilation id %d, is on line %s" % (pc, code, offset, compilation, lineno))
        args = [ self.editor ]
        if 'emacs' in self.editor and lineno is not None:
            args.append("+" + str(lineno))
        args.append(self.spewfile)
        pid = os.spawnlp(os.P_NOWAIT, self.editor, *args)
        self.kidpids.add(pid)

JITInstructionMap()
