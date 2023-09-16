# $_when_ticks function.
# $_when functions
# set rrprompt on
# now
# set logfile /tmp/mylog.txt
# log some message
# log -d[ump]
# log -s[orted]
# log -e[dit]

import gdb
import os
import re

class PythonPrint(gdb.Command):
    """Print the value of the python expression given"""
    def __init__(self, name="pp"):
        gdb.Command.__init__(self, name, gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        print(eval(arg))

PythonPrint("pp")
PythonPrint("pprint")

######################################################################

# pdo expr
# Example: pdo p data[[i for i in range(10,20)]].key
# Example: pdo p {i for i in range(10,20)}*{j for j in [1, -1]}
# Special forms:
#  10..20 - equivalent to [i for i in range(10, 20)]
class PDo(gdb.Command):
    """Repeat gdb command, substituted with Python list expressions"""
    def __init__(self, name):
        gdb.Command.__init__(self, name, gdb.COMMAND_USER)

    def commands(self, cmd):
        inbrackets = True
        m = re.match(r'^(.*?)\[\[(.*?)\]\](.*)$', cmd)
        if not m:
            m = re.match(r'^(.*?)\{(.*?)\}(.*)$', cmd)
            if not m:
                yield(cmd)
                return
            inbrackets = False
        (pre, expr, post) = m.groups()

        values = None
        m = re.match(r'(.*?)\.\.(.*)', expr)
        if m:
            start, limit = int(m.group(1)), int(m.group(2))
            values = range(start, limit)
        else:
            values = eval('[' + expr + ']')

        for v in values:
            if inbrackets:
                yield from self.commands(pre + '[' + str(v) + ']' + post)
            else:
                yield from self.commands(pre + str(v) + post)

    def invoke(self, arg, from_tty):
        opts = ""
        if arg.startswith("/"):
            rest = arg.index(" ")
            opts = arg[1:rest]
            arg = arg[rest+1:]
        verbose = "v" in opts

        for cmd in self.commands(arg):
            if verbose:
                gdb.write("(pdo) " + cmd + "\n")
            gdb.execute(cmd)

PDo("pdo")

######################################################################

# reappend "stem" "tail" [limit]
# Example: reappend "p obj->shape" "->parent" 3
class RepeatedAppend(gdb.Command):
  """Run a command, appending a "tail" to the command on every iteration, until an error or [limit] is reached"""
  def __init__(self, name="reappend"):
    gdb.Command.__init__(self, name, gdb.COMMAND_USER)

  def invoke(self, arg, from_tty):
    args = gdb.string_to_argv(arg)
    cmd = args[0]
    tail = args[1]
    limit = int(args[2]) if len(args) > 2 else 9999
    for i in range(limit):
      # print("Executing %s + %s x %d" % (args[0], args[1], limit))
      gdb.execute(cmd)
      cmd = cmd + tail

RepeatedAppend("reappend")

######################################################################

# Polyfill gdb.set_convenience_variable()

# The gdb version I was developing with originally did not have the convenience
# variable APIs that were added later. So this is a workaround, where I create
# a gdb function that returns a value, and set it via gdb.execute.
class ValueHolderHack(gdb.Function):
    def __init__(self):
        super(ValueHolderHack, self).__init__('__lastval')
        self.value = None

    def invoke(self, *args):
        return self.value

valueHolderHack = ValueHolderHack()

def set_convenience_variable_hack(name, value):
    valueHolderHack.value = value
    gdb.execute("set ${}=$__lastval()".format(name), from_tty=False, to_string=True)

if not hasattr(gdb, 'set_convenience_variable'):
    setattr(gdb, 'set_convenience_variable', set_convenience_variable_hack)

######################################################################

class Labels(dict):
    def __init__(self):
        # Substitution pattern maintenance -- this class keeps a compiled regex
        # 'pattern' up to date with its set of keys. The pattern is lazily
        # generated whenever it's needed and the set of keys has changed since
        # the last time it was rebuilt.
        self.dirty = True
        self.pattern()

        # This class supports a single external consumer that feeds off a "log"
        # of added keys. Every key added will be appended to a list that is
        # cleared out when flush_added() is called to retrieve all adds since
        # the previous call. (If the class is clear()ed, 'added' will be
        # reset.)
        self.added = []

        self.pending_labels = []

    def label(self, token, name, typestr, gdbval=None):
        """Set a label named `name` to the value `token` (probably a numeric
        value) cast according to `typestr`, which is a raw cast expression.
        gdbval is... figuring that out now."""
        print("Setting label {} := {} of type {} gdbval={}".format(token, name, typestr, gdbval))
        if gdbval is None:
            try:
                # Look for a pointer type, eg in `(JSObject *) 0xdeadbeef`
                if m := re.match(r'(.*?)(  *\**)$', typestr):
                    t, ptrs = m.groups()
                else:
                    t, ptrs = (typestr, '')
                gdbval = gdb.parse_and_eval(f"('{t}'{ptrs}) {token}")
            except gdb.error as e:
                # This can happen if we load in a set of labels before the type
                # exists.
                gdb.write("unknown type: " + str(e) + "\n")
                self.pending_labels.append((token, name, typestr))
                return False
        self[token] = (name, typestr)
        gdb.set_convenience_variable(name, gdbval)
        return True

    def __setitem__(self, key, value):
        key = self.canon(key)
        if dict.get(self, key) == value:
            return
        # print("setting {} : {} -> {}".format(key, self.get(key), value))
        dict.__setitem__(self, key, value)
        self.added.append(key)
        self.dirty = True

    def clear(self):
        dict.clear(self)
        self.dirty = True

    def canon(self, s):
        try:
            n = int(s, 0)
            if n < 0:
                return "%#x" % (n & 0xffffffffffffffff)
            else:
                return "%#x" % n
        except ValueError:
            return s

    def flush_added(self):
        '''Retrieve the list of entries added since the last call to this method.'''
        ret = [(k, self[k]) for k in self.added]
        self.added = []
        return ret

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self.dirty = True

    def __getitem__(self, key):
        return dict.__getitem__(self, self.canon(key))

    def __contains__(self, key):
        return dict.__contains__(self, self.canon(key))

    def get(self, text, default=None, verbose=False):
        rep = dict.get(self, self.canon(text), default)
        if rep == default:
            return default
        return "%s [[$%s]]" % (text, rep[0]) if verbose else "$" + rep[0]

    def copy(self):
        c = Labels()
        c.update(self)
        return c

    def pattern(self):
        if self.dirty:
            #print("Rebuilding pattern with {} replacements".format(len(self)))
            if len(self) == 0:
                # Pattern that never matches
                self.repPattern = re.compile(r'^(?!.).')
            else:
                # This requires word boundaries, and does not match words
                # starting with '$' (to avoid replacing eg $3, though honestly
                # if you set a label for 3 you kind of deserve what you get.)
                reps = []
                for key in self.keys():
                    reps.append(key)
                    reps.append(str(int(key, 16)))
                self.repPattern = re.compile(r'\b(?<!\$)(?:' + '|'.join(reps) + r')\b')
            self.dirty = False

        return self.repPattern

    def apply(self, text, verbose=False):
        return re.sub(
            self.pattern(),
            lambda m: self.get(m.group(0), None, verbose),
            text)

    def on_objfile_load(self, event):
        if self.pending_labels:
            gdb.write("objfile load detected, reprocessing {} labels\n".format(len(self.pending_labels)))
        pending = self.pending_labels
        self.pending_labels = []
        for (token, name, typestr) in pending:
            # There really ought to be a better way to look up a type
            # expression.
            if self.label(token, name, typestr):
                gdb.write("  succeeded in setting pending label {}\n".format(name))

labels = Labels()

def new_objfile_handler(event):
    labels.on_objfile_load(event)

gdb.events.new_objfile.connect(new_objfile_handler)

def index_of_first(s, tokens, start=0):
    bestpos = None
    for token in tokens:
        try:
            pos = s.index(token, start)
            if bestpos is None or pos < bestpos:
                bestpos = pos
        except ValueError:
            pass
    return bestpos

class LabelCmd(gdb.Command):
    def __init__(self, name):
        super(LabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    def invoke(self, arg, from_tty):
        if len(arg) == 0:
            self.show_all_labels()
            return

        if arg.startswith('variable '):
            start=len('variable ')
            pos = index_of_first(arg, [' ', '='], start)
            if pos is None:
                gdb.write("invalid usage\n")
                return
            self.set_label(arg[start:pos], arg[pos+1:])
            return

        pos = index_of_first(arg, [' ', '='])
        if pos is not None:
            name, val = (arg[0:pos], arg[pos+1:])
            self.set_label(name, val.lstrip())
            return

        self.get_label(arg)

    def get_label(self, name):
        if name in labels:
            gdb.write(labels[name][0] + "\n")
        else:
            gdb.write("Label '{}' not found\n".format(name))

    def prefer_prettyprinted(self, t):
        return str(t).startswith("JS::Handle")

    def set_label(self, name, value):
        if re.fullmatch(r'0x[0-9a-fA-F]+', value) or value.lstrip('-').isdecimal():
            if int(value) != 0:
                labels[value] = (name, 'void*')
                return

        v = gdb.parse_and_eval(value)

        # FIXME! If there is a pretty printer for v that displays a different
        # hex value than its address, then we will label using that instead.
        # (Example: Symbol displays its desc address, though in the 0x0 case we
        # will now skip that..)

        # First, attempt to cast to void*, unless the special case code says this
        # type should prefer prettyprinting.
        valstr = None
        try:
            if not self.prefer_prettyprinted(v.type):
                valstr = str(v.cast(gdb.lookup_type('void').pointer()))
        except Exception as e:
            pass

        if valstr is None:
            # Fall back on the (possibly prettyprinted) output.
            valstr = str(v)

        m = re.search(r'0x[0-9a-fA-F]+', valstr)
        if not m:
            m = re.search(r'-?[0-9]{4,20}', valstr)
        if not m or m.group(0) == '0' or m.group(0) == '0x0':
            gdb.write("No labelable value found in " + valstr + "\n")
            return

        # gdb.write("gots %s, setting labels[%s] = %s\n" % (str(v), m.group(0), value))

        # label $3 SOMETHING
        # should set $SOMETHING to the actual value of $3
        labels.label(m.group(0), name, str(v.type), gdbval=v)

    # FIXME! Getting duplicate labels
    def show_all_labels(self):
        for name, (value, t) in labels.items():
            gdb.write("${} = ({}) {}\n".format(value, t, name))

LabelCmd('label')

class UnlabelCmd(gdb.Command):
    def __init__(self, name):
        super(UnlabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    # FIXME! Gtting KeyError, yet 'label' still shows
    def invoke(self, arg, from_tty):
        del labels[arg]

UnlabelCmd('unlabel')

class util:
    def split_command_arg(arg, allow_dash=False):
        options = []
        if arg.startswith("/"):
            pos = arg.index(" ") if " " in arg else len(arg)
            options.extend(arg[1:pos])
            arg = arg[pos+1:]
        elif allow_dash and arg.startswith("-"):
            # Support multiple options: -foo -bar
            all_options = []
            while arg.startswith('-'):
                pos = arg.index(" ") if " " in arg else len(arg)
                options.append(arg[1:pos])
                if pos == len(arg):
                    arg = ''
                    break
                arg = arg[pos+1:]

        return options, arg

    def evaluate(expr, replace=True, brieftype=True):
        try:
            v = gdb.parse_and_eval(expr)
        except gdb.error as e:
            print("Invalid embedded expression «{}»".format(expr))
            raise e
        s = str(v)
        t = v.type
        ts = str(t)

        # Ugh. In some situations, the value will be prefixed with its type,
        # and others it will not. Enough will not that I wanted to add it in.

        if s.startswith("("):
            return s
        BORING_TYPES = ("int", "unsigned int", "uint32_t", "int32_t", "uint64_t", "int64_t")
        if ts in BORING_TYPES:
            return s
        # If the type name is in the value, as in js::gc::CellColor::Black,
        # then we don't need to see the cast.
        if ts in s:
            return s
        if brieftype:
            ots = ts
            ts = ts.replace('const ', '')
            ts = ts.replace(' const', '')
            ts = re.sub(r'\w+::', '', ts)
            ts = ts.replace(' *', '*')
            # Same check as above, but sometimes the type gets aliased into a
            # different namespace. So try even harder to throw it out.
            if ts in s:
                return s
        return "(%s) %s" % (ts, s)

class PrintCmd(gdb.Command):
    """\
like gdb's builtin 'print' function, with label replacements and special syntax.

Any substring that matches a label SOMELABEL will be replaced with the
literal string `$SOMELABEL`.

If `m..n` is found anywhere in the string, the print will be repeated for
every number in that range.

If `{substr}**n` is found in the string, then substr will be repeated n
times.
"""

    def __init__(self, name):
        super(PrintCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_COMMAND)

    def enumerateExprs(self, expr):
        m = re.match(r'(.*?)(\w+)\.\.(\w+)(.*)', expr)
        if m:
            start = gdb.parse_and_eval(m.group(2))
            end = gdb.parse_and_eval(m.group(3))
            for i in range(start, end):
                newExpr = m.group(1) + str(i) + m.group(4)
                yield from self.enumerateExprs(newExpr)
            return

        m = re.match(r'(.*?)\{(.*?)\}\*\*(\d+)(.*)', expr)
        if m:
            start, subexpr, n, rest = m.groups()
            n = int(n)
            newExpr = start + ''.join(subexpr for _ in range(n)) + rest
            yield from self.enumerateExprs(newExpr)
            return

        yield expr
        return

    def invoke(self, arg, from_tty):
        # Format for x command is: <repcount> oxdutfaicsz bhwg
        # but print command is only 1oxdutfaicsz
        # ...but /r also exists; it skips pretty printers.
        # We add
        #   v = verbose
        # and augment
        #   r = raw
        # to skip label substitutions.

        opts, arg = util.split_command_arg(arg)
        fmt = ''.join(o[0] for o in opts)
        verbose = 'v' in fmt
        raw = 'r' in fmt

        fmt = fmt.replace('v', '')
        fmtStr = "/" + fmt if fmt else ''

        for e in self.enumerateExprs(arg):
            try:
                v = gdb.parse_and_eval(e)
            except gdb.error as exc:
                gdb.write(str(exc) + "\n")
                return
            gdb.set_convenience_variable('__expr', v)
            output = gdb.execute("print" + fmtStr + " $__expr",
                                 from_tty, to_string=True)
            if not raw:
                output = labels.apply(output, verbose)
            gdb.write(output)

PrintCmd('p')
