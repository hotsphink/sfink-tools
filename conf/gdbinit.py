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
                print("(pdo) " + cmd)
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

class Labels(dict):
    def __init__(self):
        self.dirty = True
        self.pattern()
        self.added = []

    def label(self, token, name):
        self[token] = name

    def __setitem__(self, key, value):
        print("setting %s to %s, was %s" % (key, value, self.get(key)))
        if dict.get(self, key) == value:
            return
        dict.__setitem__(self, key, value)
        self.added.append(key)
        self.dirty = True

    def canon(self, s):
        try:
            n = int(s, 0)
            if n < 0:
                return "%#x" % (n & 0xffffffffffffffff)
            else:
                return "%#x" % n
        except:
            return s

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self.dirty = True

    def __getitem__(self, key):
        return dict.__getitem__(self, self.canon(key))

    def __contains__(self, key):
        return dict.__contains__(self, self.canon(key))

    def get(self, text, default=None, verbose=False):
        rep = dict.get(self, text, default)
        return "%s [[%s]]" % (text, rep) if verbose else rep

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
                # TODO: Match both hex and numeric representations.
                # (Or perhaps insert both in __setitem__?)
                self.repPattern = re.compile('|'.join(self.keys()))
            self.dirty = False

        return self.repPattern

    def apply(self, text, verbose=False):
        return re.sub(self.pattern(), lambda m: self.get(m.group(0), None, verbose), text)

class ValueHolderHack(gdb.Function):
    def __init__(self):
        super(ValueHolderHack, self).__init__('__lastval')
        self.value = None

    def invoke(self, *args):
        return self.value

valueHolderHack = ValueHolderHack()

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
            gdb.write(labels[name] + "\n")
        else:
            gdb.write("Label not found\n")

    def set_label(self, name, value):
        if re.fullmatch(r'0x[0-9a-fA-F]+', name) or name.lstrip('-').isdecimal():
            labels[name] = value
            return

        v = gdb.parse_and_eval(name)
        m = re.search(r'0x[0-9a-fA-F]+', str(v))
        if not m:
            m = re.search(r'-?[0-9]{4,20}', str(v))
        if not m:
            gdb.write("No labelable value found in " + str(v) + "\n")
            return

        gdb.write("gots %s, setting labels[%s] = %s\n" % (str(v), m.group(0), value))

        labels[m.group(0)] = value
        # eg label $3 SOMETHING
        # should set $SOMETHING to the actual value of $3
        valueHolderHack.value = v
        gdb.execute("set ${}=$__lastval()".format(value), from_tty=False, to_string=True)

    def show_all_labels(self):
        for name, value in labels.items():
            gdb.write("{} = {}\n".format(name, value))

LabelCmd('label')

class UnlabelCmd(gdb.Command):
    def __init__(self, name):
        super(UnlabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    def invoke(self, arg, from_tty):
        del labels[arg]  # FIXME: Remove the other variants too.

UnlabelCmd('unlabel')

class util:
    def split_command_arg(arg, allow_dash=False):
        options = ''
        if arg.startswith("/"):
            pos = arg.index(" ") if " " in arg else len(arg)
            options = arg[1:pos]
            arg = arg[pos+1:]
        elif allow_dash and arg.startswith("-"):
            pos = arg.index(" ") if " " in arg else len(arg)
            options = arg[1:pos]
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

        fmt, arg = util.split_command_arg(arg)
        verbose = 'v' in fmt
        raw = 'r' in fmt

        fmt = fmt.replace('v', '')
        fmtStr = "/" + fmt if fmt else ''

        for e in self.enumerateExprs(arg):
            # in gdb 8.2, this could be done with gdb.set_convenience_variable.
            try:
                v = gdb.parse_and_eval(e)
            except gdb.error as exc:
                gdb.write(str(exc) + "\n")
                return
            valueHolderHack.value = v
            output = gdb.execute("print" + fmtStr + " $__lastval()", from_tty, to_string=True)
            if not raw:
                output = labels.apply(output, verbose)
            gdb.write(output)

PrintCmd('p')
