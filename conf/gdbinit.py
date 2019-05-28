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
    def __init__(self):
        gdb.Command.__init__(self, "pp", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        print(eval(arg))

PythonPrint()

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
  def __init__(self):
    gdb.Command.__init__(self, "reappend", gdb.COMMAND_USER)

  def invoke(self, arg, from_tty):
    args = gdb.string_to_argv(arg)
    cmd = args[0]
    tail = args[1]
    limit = int(args[2]) if len(args) > 2 else 9999
    for i in range(limit):
      # print("Executing %s + %s x %d" % (args[0], args[1], limit))
      gdb.execute(cmd)
      cmd = cmd + tail

RepeatedAppend()

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
        self.dirty = True
        self.pattern()
        self.added = []

    def label(self, token, name, type, gdbval=None):
        self[token] = (name, type)

        if gdbval is None:
            gdbval = gdb.parse_and_eval("({}) {}".format(type, token))

        gdb.set_convenience_variable(name, gdbval)

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
        ret = [(k, self[k]) for k in self.added]
        self.added = []
        self.dirty = False
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
                self.repPattern = re.compile(r'\b(?<!\$)' + '|'.join(reps) + r'\b')
            self.dirty = False

        return self.repPattern

    def reloaded(self):
        self.dirty = True
        self.pattern()
        self.added = []

    def apply(self, text, verbose=False):
        return re.sub(
            self.pattern(),
            lambda m: self.get(m.group(0), None, verbose),
            text)

labels = Labels()

class LabelCmd(gdb.Command):
    def __init__(self, name):
        super(LabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    def invoke(self, arg, from_tty):
        if len(arg) == 0:
            self.show_all_labels()
        elif ' ' in arg:
            pos = arg.index(' ')
            self.set_label(arg[0:pos], arg[pos+1:])
        elif '=' in arg:
            pos = arg.index('=')
            self.set_label(arg[0:pos], arg[pos+1:])
        else:
            self.get_label(arg)

    def get_label(self, name):
        if name in labels:
            gdb.write(labels[name][0] + "\n")
        else:
            gdb.write("Label not found\n")

    def set_label(self, name, value):
        if re.fullmatch(r'0x[0-9a-fA-F]+', name) or name.lstrip('-').isdecimal():
            labels[name] = (value, 'void*')
            return

        v = gdb.parse_and_eval(name)
        m = re.search(r'0x[0-9a-fA-F]+', str(v))
        if not m:
            m = re.search(r'-?[0-9]{4,20}', str(v))
        if not m:
            gdb.write("No labelable value found in " + str(v) + "\n")
            return

        # gdb.write("gots %s, setting labels[%s] = %s\n" % (str(v), m.group(0), value))

        # label $3 SOMETHING
        # should set $SOMETHING to the actual value of $3
        labels.label(m.group(0), value, str(v.type), gdbval=v)

    def show_all_labels(self):
        for name, (value, t) in labels.items():
            gdb.write("({}) {} = ${}\n".format(t, name, value))

LabelCmd('label')

class UnlabelCmd(gdb.Command):
    def __init__(self, name):
        super(UnlabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    def invoke(self, arg, from_tty):
        del labels[arg]  # FIXME: Remove the other variants too.

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

    def evaluate(expr, replace=True):
        v = gdb.parse_and_eval(expr)
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
        return "(%s) %s" % (ts, s)

class PrintCmd(gdb.Command):
    """like gdb's builtin 'print' function, with label replacements and special syntax.
"""

    def __init__(self, name):
        super(PrintCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_COMMAND)

    def enumerateExprs(self, expr):
        m = re.match(r'^(.*?)(\w+)\.\.(\w+)(.*)', expr)
        if not m:
            yield expr
            return
        start = gdb.parse_and_eval(m.group(2))
        end = gdb.parse_and_eval(m.group(3))
        for i in range(start, end):
            newExpr = m.group(1) + str(i) + m.group(4)
            yield from self.enumerateExprs(newExpr)

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
