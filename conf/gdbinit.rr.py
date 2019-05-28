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
import tempfile

from os.path import abspath, dirname, expanduser
from os import environ as env

gdb.execute("source {}/gdbinit.rr".format(abspath(expanduser(dirname(__file__)))))

RUNNING_RR = None

def running_rr():
    '''Detect whether running under rr.'''
    global RUNNING_RR
    if RUNNING_RR is not None:
        return RUNNING_RR
    RUNNING_RR = os.environ.get('GDB_UNDER_RR', False)
    return RUNNING_RR

def setup_log_dir():
    share_dir = None
    if 'RR_LOGS' in env:
        share_dir = env['RR_LOGS']
    else:
        # If ~/.local/share exists, use that as the default location of
        # rr-logs/. (If it does not exist, don't create it!)
        share_root = os.path.join(env['HOME'], ".local", "share")
        if os.path.exists(share_root):
            share_dir = os.path.join(share_root, "rr-logs")

    if share_dir is not None:
        os.makedirs(share_dir, exist_ok=True)
        return share_dir

    return os.environ['HOME']

DEFAULT_LOG_DIR = setup_log_dir()

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
        return when()

PythonWhen()

class PythonNow(gdb.Command):
    """Output <when>/<when-ticks>"""
    def __init__(self):
        gdb.Command.__init__(self, "now", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        try:
            gdb.write(now() + "\n")
        except gdb.error:
            gdb.write("?? when/when-ticks unavailable (not running under rr?)\n")

PythonNow()

class SharedFile(io.TextIOWrapper):
    def __init__(self, filename):
        self.fh = open(filename, "ba+")
        super(SharedFile, self).__init__(self.fh)
        self.last_known_size = self.seek(0, 2)

    def changed(self):
        return self.last_known_size != self.seek(0, 2)

    def record_end(self):
        self.last_known_size = self.tell()

    def write(self, buffer):
        nbytes = super(SharedFile, self).write(buffer)
        self.record_end()
        return nbytes

class PythonLog(gdb.Command):
    """Append current event/tick-count with message to log file"""
    def __init__(self):
        gdb.Command.__init__(self, "log", gdb.COMMAND_USER)
        self.LogFile = None
        self.ThreadTable = {}
        self.ExpectedSize = None
        gdb.events.before_prompt.connect(lambda: self.sync_log())

    def openlog(self, filename, quiet=False):
        first_open = not self.LogFile

        if self.LogFile:
            self.LogFile.close()

        self.LogFile = SharedFile(filename)
        if not quiet:
            gdb.write("Logging to %s\n" % (self.LogFile.name,))

        if first_open:
            self.sync_log()
        labels.clear()

        self.LogFile.seek(0)

        for lineno, line in enumerate(self.LogFile):
            if not line.startswith("! "):
                continue

            rest = line[2:].rstrip()
            cmd = rest.split(" ", 1)[0]
            rest = rest[len(cmd)+1:]
            if cmd == "replace":
                k, v, t = rest.split(" ", 2)
                labels.label(k, v, t)
                continue

            gdb.write("Unhandled log command: {}\n".format(line))

        self.LogFile.record_end()

    def stoplog(self):
        self.LogFile.close()
        self.LogFile = None

    def default_log_filename(self):
        tid = gdb.selected_thread().ptid[0]
        return os.path.join(DEFAULT_LOG_DIR, "rr-session-%s.log" % (tid,))

    def thread_id(self, fs_base=None):
        '''Return the thread id in the format "T<num>" for the given fs_base, or the current value of that register if not given. This is a hack that is not guaranteed to work -- when rr starts a new process under the hood, gdb may shift the thread numbers around. This is a heuristic to grab an id the first time a thread is encountered; there is no guarantee that it won't map multiple threads to the same ID. (That could be fixed, but I haven't bothered yet.)'''
        if fs_base is None:
            fs_base = gdb.parse_and_eval("$fs_base")
        return self.ThreadTable.setdefault(fs_base, "T" + str(gdb.selected_thread().num))

    def sync_log(self):
        '''Add any new labels to the log, and grab any updates if another process updated the file.'''
        if not self.LogFile:
            #print("Checking changed: no log yet")
            return

        if labels.dirty:
            for k, (v, t) in labels.flush_added():
                #print("writing {} -> ({}) {} to log".format(k, t, v))
                self.LogFile.write("! replace {} {} {}\n".format(k, v, t))

        if self.LogFile.changed():
            #print("Checking changed: yes (or dirty)")
            self.openlog(self.LogFile.name)

    def invoke(self, arg, from_tty):
        # We probably ought to flush out dirty labels here.
        if self.LogFile is None:
            self.openlog(self.default_log_filename())

        opts, arg = util.split_command_arg(arg, allow_dash=True)
        # print("after split, opt={} arg={}".format(opts, arg))

        do_addentry = False
        dump_args = {'sort': True}
        do_print = False
        do_dump = True
        raw = False

        if arg:
            do_addentry = True
            do_dump = False

        for opt in opts:
            if 'sorted'.startswith(opt):
                # log/s : same as log with no options, display log in execution order.
                dump_args['sort'] = True
                do_dump = True
            elif 'verbose'.startswith(opt):
                # log/v : display log in execution order, with replacements and originals
                dump_args['sort'] = True
                dump_args['replace'] = True
                dump_args['verbose'] = True
            elif 'unsorted'.startswith(opt):
                # log/u : display log in entry order
                dump_args['sort'] = False
                do_dump = True
            elif 'noreplace'.startswith(opt):
                # log/n : display log in execution order, without processing replacements
                dump_args['sort'] = True
                dump_args['replace'] = False
                do_dump = True
            elif 'edit'.startswith(opt):
                # log/e : edit the log in $EDITOR
                self.edit()
                do_dump = False
            elif 'raw'.startswith(opt):
                # log/r : do not do any label replacements in message
                raw = True
            elif 'print-only'.startswith(opt):
                # log/p : display the log message without logging it permanently
                do_print = True
                do_dump = False
            else:
                gdb.write("unknown log option '{}'\n".format(opt))

        if do_addentry:
            out = self.process_message(arg)
            if not raw:
                out = labels.apply(out, verbose=False)
            # If any substitutions were made, display the resulting log message.
            if out != arg:
                do_print = True
            if self.LogFile:
                self.LogFile.write("%s %s\n" % (now(), out))

        if do_dump:
            self.dump(**dump_args)

        if do_print:
            gdb.write(out + "\n")

    def process_message(self, message):
        # Replace {expr} with the result of evaluating the (gdb) expression expr.
        # Allow one level of curly bracket nesting within expr.
        out = re.sub(r'\{((?:\{[^\}]*\}|\\\}|[^\}])*)\}',
                     lambda m: util.evaluate(m.group(1)),
                     message)

        # Replace $thread with "T3", where 3 is the gdb's notion of thread number.
        out = out.replace("$thread", self.thread_id())

        # Let gdb handle other $ vars.
        return re.sub(r'(\$\w+)', lambda m: util.evaluate(m.group(1)), out)

    def dump(self, sort=False, replace=True, verbose=False):
        if not self.LogFile:
            gdb.write("No log file open\n")
            return

        self.LogFile.seek(0)

        messages = []
        for lineno, line in enumerate(self.LogFile):
            if line.startswith("! "):
                continue
            line = line.strip()

            (timestamp, message) = line.split(" ", 1)
            (event, ticks) = timestamp.split("/", 1)

            if replace:
                line = labels.apply(line, verbose)

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
                gdb.write("%s%s\n" % ("=> " if i == place else "   ", message[3]))
        else:
            for message in messages:
                gdb.write(message[3] + "\n")

    def edit(self):
        if not self.LogFile:
            gdb.write("No log file open\n")
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
