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
