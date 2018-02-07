# $_when_ticks function.
# $_when functions
# set rrprompt on
# now
# set logfile /tmp/mylog.txt
# log some message
# log -dump
# log -sorted
# log -edit

import gdb
import os
import re

from collections import defaultdict
from importlib import reload  # For interactive use

RUNNING_RR = None

def running_rr():
    '''Detect whether running under rr.'''
    global RUNNING_RR
    if RUNNING_RR is not None:
        return RUNNING_RR
    RUNNING_RR = os.environ.get('GDB_UNDER_RR', False)
    return RUNNING_RR

def when():
    when = gdb.execute("when", False, True)
    m = re.search(r'(\d+)', when)
    if not m:
        raise Exception("when returned invalid string")
    return int(m.group(1))

def when_ticks():
    when = gdb.execute("when-ticks", False, True)
    m = re.search(r'(\d+)', when)
    if not m:
        raise Exception("when-ticks returned invalid string")
    return int(m.group(1))

def now():
    return "%s/%s" % (when(), when_ticks())

def nowTuple():
    return (when(), when_ticks())

def rrprompt(current_prompt):
    return ("(rr %d/%d) " % (when(), when_ticks()))

class ParameterRRPrompt(gdb.Parameter):
    def __init__(self):
        super(ParameterRRPrompt, self).__init__('rrprompt', gdb.COMMAND_SUPPORT, gdb.PARAM_BOOLEAN)
        self.orig_prompt = gdb.prompt_hook

    def get_set_string(self):
        gdb.prompt_hook = self.orig_prompt
        if self.value:
            if running_rr():
                gdb.prompt_hook = rrprompt
                return "rr-aware prompt enabled"
            else:
                return "not running rr"
        else:
            return "rr-aware prompt disabled"

    def get_show_string(self, svalue):
        return svalue

ParameterRRPrompt()

class PythonWhenTicks(gdb.Function):
    """$_when_ticks - return the numeric output of rr's 'when-ticks' command
Usage:
    $_when_ticks()
"""

    def __init__(self):
        super(PythonWhenTicks, self).__init__('_when_ticks')

    def invoke(self):
        return str(when_ticks())

PythonWhenTicks()

class PythonWhen(gdb.Function):
    """$_when - return the numeric output of rr's 'when' command
Usage:
    $_when()
"""

    def __init__(self):
        super(PythonWhen, self).__init__('_when')

    def invoke(self):
        return str(when())

class PythonNow(gdb.Command):
    """Output <when>/<when-ticks>"""
    def __init__(self):
        gdb.Command.__init__(self, "now", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        try:
            print(now())
        except gdb.error:
            print("?? when/when-ticks unavailable (not running under rr?)")

PythonNow()

class PythonLog(gdb.Command):
    """Append current event/tick-count with message to log file"""
    def __init__(self):
        gdb.Command.__init__(self, "log", gdb.COMMAND_USER)
        self.LogFile = None

    def openlog(self, filename, quiet=False):
        self.LogFile = open(filename, "a+")
        if not quiet:
            print("Logging to %s" % (self.LogFile.name,))

    def stoplog(self):
        self.LogFile = False

    def default_log_filename(self):
        tid = gdb.selected_thread().ptid[0]
        return os.path.join(os.environ['HOME'], "rr-session-%s.log" % (tid,))

    def invoke(self, arg, from_tty):
        if self.LogFile is None:
            self.openlog(self.default_log_filename())

        if arg.startswith('-'):
            if '-sorted'.startswith(arg):
                # log -s : same as log with no options, display log in execution order.
                self.dump(sort=True)
            elif '-dump'.startswith(arg):
                # log -d : display log in entry order
                self.dump()
            elif '-edit'.startswith(arg):
                # log -e : edit the log in $EDITOR
                self.edit()
            else:
                print("unknown log option")
            return

        if not arg:
            self.dump(sort=True)
            return

        if not self.LogFile:
            return

        # Replace {expr} with the result of evaluating the (gdb) expression expr.
        # Allow one level of curly bracket nesting within expr.
        out = re.sub(r'\{((?:\{[^\}]*\}|\\\}|[^\}])*)\}',
                     lambda m: str(gdb.parse_and_eval(m.group(1))),
                     arg)

        # Replace $thread with "T3", where 3 is the gdb's notion of thread number.
        out = out.replace("$thread", "T" + str(gdb.selected_thread().num))

        # Let gdb handle other $ vars.
        out = re.sub(r'(\$\w+)', lambda m: str(gdb.parse_and_eval(m.group(1))), out)

        self.LogFile.write("%s %s\n" % (now(), out))

        # If any substitutions were made, display the resulting log message.
        if out != arg:
            print(out)

    def dump(self, sort=False):
        if not self.LogFile:
            print("No log file open")
            return

        self.LogFile.seek(0)

        messages = []
        for lineno, line in enumerate(self.LogFile):
            line = line.strip()
            (timestamp, message) = line.split(" ", 1)
            (event, ticks) = timestamp.split("/", 1)
            messages.append((int(event), int(ticks), lineno, line))

        now = nowTuple()
        place = -1
        if sort:
            messages.sort()
            place = len(messages)
            for i, message in enumerate(messages):
                if (message[0], message[1]) > now:
                    place = i - 1
                    break
            for i, message in enumerate(messages):
                print("%s%s" % ("=> " if i == place else "   ", message[3]))
        else:
            for message in messages:
                print(message[3])

    def edit(self):
        if not self.LogFile:
            print("No log file open")
            return

        filename = self.LogFile.name
        self.LogFile.close()
        os.system(os.environ.get('EDITOR', 'emacs') + " " + filename)
        self.openlog(filename, quiet=True)

class ParameterLogFile(gdb.Parameter):
    def __init__(self, logger):
        super(ParameterLogFile, self).__init__('logfile', gdb.COMMAND_SUPPORT, gdb.PARAM_STRING)
        self.logfile = None
        self.logger = logger

    def get_set_string(self):
        if self.value:
            self.logfile = self.value
            self.logger.openlog(self.logfile)
            return "logging to %s" % self.logfile
        else:
            return "logging stopped"

    def get_show_string(self, svalue):
        return self.logfile

if running_rr():
    ParameterLogFile(PythonLog())

class PythonPrint(gdb.Command):
    """Print the value of the python expression given"""
    def __init__(self):
        gdb.Command.__init__(self, "pp", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        print(eval(arg))

PythonPrint()

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

if False:
    for o in gdb.objfiles():
        print("objfile: " + o.filename)
        base = os.path.basename(o.filename)
        if base.startswith("mmap_hardlink_") and base.endswith("_js"):
            if False: mozilla.autoload.register(o)
