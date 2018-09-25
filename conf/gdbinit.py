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

# repeat "command" [limit]
# Example: rep $->parent 20
class Repeat(gdb.Command):
  """Repeat command [limit] times or until an error is hit"""
  def __init__(self):
    gdb.Command.__init__(self, "repeat", gdb.COMMAND_USER)

  def invoke(self, arg, from_tty):
    args = gdb.string_to_argv(arg)
    cmd = args[0]
    limit = int(args[1]) if len(args) > 1 else 9999
    for i in range(limit):
      #print("%d: executing %s" % (i, cmd))
      gdb.execute(cmd)

Repeat()

######################################################################

# pdo expr
# Example: pdo p data[[i for i in range(10,20)]].key
# Example: pdo p {i for i in range(10,20)}*{j for j in [1, -1]}
# Special forms:
#  10..20 - equivalent to [i for i in range(10, 20)]
class PDo(gdb.Command):
    """Repeat gdb command, substituted with Python list expressions"""
    def __init__(self):
        gdb.Command.__init__(self, "pdo", gdb.COMMAND_USER)

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

PDo()

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
