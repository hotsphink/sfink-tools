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

    def label(self, token, name):
        self[token] = name

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        self.dirty = True

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self.dirty = True

    def get(self, text, verbose=False):
        rep = self[text]
        return "%s [[%s]]" % (text, rep) if verbose else rep

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
        return re.sub(self.pattern(), lambda m: self.get(m.group(0), verbose), text)

labels = Labels()

class util:
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

class ValueHolderHack(gdb.Function):
    def __init__(self):
        super(ValueHolderHack, self).__init__('__lastval')
        self.value = None

    def invoke(self, *args):
        return self.value

valueHolderHack = ValueHolderHack()

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

        fmt = ''
        if arg.startswith('/'):
            pos = arg.index(" ")
            if pos < 2:
                print("invalid /FMT")
                return
            fmt = arg[1:pos]
            arg = arg[pos+1:]

        verbose = 'v' in fmt
        raw = 'r' in fmt
        fmt = fmt.replace('v', '')

        for e in self.enumerateExprs(arg):
            v = gdb.parse_and_eval(e)
            valueHolderHack.value = v
            fmtStr = "/" + fmt if fmt else ''
            output = gdb.execute("print" + fmtStr + " $__lastval()", from_tty, to_string=True)

            raw = 'r' in fmt
            if not raw:
                output = labels.apply(output, verbose)

            gdb.write(output)

PrintCmd('p')
