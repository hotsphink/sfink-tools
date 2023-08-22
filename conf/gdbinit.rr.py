# $_when_ticks function.
# $_when functions
# set rrprompt on
# now
# set logfile /tmp/mylog.json
# log some message
# log -unsorted
# log -sorted
# log -edit

import gdb
import json
import os
import random
import re
import tempfile

from os.path import abspath, dirname, expanduser
from os import environ as env

gdb.execute("source {}/gdbinit.rr".format(abspath(expanduser(dirname(__file__)))))

RUN_ID = "RRSESSION-" + str(random.random())
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


class PythonWhenTicks(gdb.Function):
    """$_when_ticks - return the numeric output of rr's 'when-ticks' command
Usage:
    $_when_ticks()
"""

    def __init__(self):
        super(PythonWhenTicks, self).__init__('_when_ticks')

    def invoke(self):
        return str(when_ticks())


class PythonWhen(gdb.Function):
    """$_when - return the numeric output of rr's 'when' command
Usage:
    $_when()
"""

    def __init__(self):
        super(PythonWhen, self).__init__('_when')

    def invoke(self):
        return when()


class PythonNow(gdb.Command):
    """Output <when>/<when-ticks>"""
    def __init__(self):
        gdb.Command.__init__(self, "now", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        try:
            gdb.write(now() + "\n")
        except gdb.error:
            gdb.write("?? when/when-ticks unavailable (not running under rr?)\n")


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


# Generator that yields a sequence of actions read from the given log file.
# Each line must be a valid JSON document.
def log_actions(fh):
    lineno = 0
    for line in fh:
        lineno += 1
        data = json.loads(line)
        data['lineno'] = lineno
        yield data


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
            #print("Syncing with log for the first time")
            self.sync_log()
        labels.clear()

        self.LogFile.seek(0)

        # Load all 'label' actions in the log.
        for action in log_actions(self.LogFile):
            if action['type'] == 'label':
                labels.label(action['key'], action['value'], action['datatype'])

        labels.flush_added()
        self.LogFile.record_end()

    def stoplog(self):
        self.LogFile.close()
        self.LogFile = None

    def default_log_filename(self):
        tid = gdb.selected_thread().ptid[0]
        return os.path.join(DEFAULT_LOG_DIR, "rr-session-%s.json" % (tid,))

    def thread_id(self, fs_base=None):
        '''Return the thread id in the format "T<num>" for the given fs_base, or the current value of that register if not given. This is a hack that is not guaranteed to work -- when rr starts a new process under the hood, gdb may shift the thread numbers around. This is a heuristic to grab an id the first time a thread is encountered; there is no guarantee that it won't map multiple threads to the same ID. (That could be fixed, but I haven't bothered yet.)'''
        if fs_base is None:
            fs_base = gdb.parse_and_eval("$fs_base")
        return self.ThreadTable.setdefault(fs_base, "T" + str(gdb.selected_thread().num))

    def sync_log(self):
        '''Add any new labels to the log, and grab any updates if another process updated the file.'''
        if not self.LogFile:
            # Note: can't really just open the log immediately, because we
            # won't have the type info for the replacements when gdb first gets
            # going.
            #
            #print("Checking changed: no log yet")
            return

        added = labels.flush_added()
        #print("grabbing new labels: {}".format([v for k, (v, t) in added]))
        for k, (v, t) in added:
            #print("writing {} -> ({}) {} to log".format(k, t, v))
            json.dump({'type': 'label', 'key': k, 'value': v, 'datatype': t}, self.LogFile)
            self.LogFile.write("\n")

        if self.LogFile.changed():
            #print("Checking changed: yes (or dirty)")
            self.openlog(self.LogFile.name, quiet=False)  # TEMP! FIXME!

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
                dump_args['replace'] = False
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
                gdb_out = gdb.execute("checkpoint", to_string=True)
                action = {'type': 'log', 'event': when(), 'ticks': when_ticks(), 'message': out}
                if m := re.search(r'Checkpoint (\d+)', gdb_out):
                    action['checkpoint'] = m.group(1)
                    action['session'] = RUN_ID
                json.dump(action, self.LogFile)
                self.LogFile.write("\n")

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

    def write_message(self, message, verbose=False):
        (event, ticks, lineno, msg, checkpoint, session) = message
        if verbose:
            gdb.write(f"{event}/{ticks} ")
        if checkpoint is not None:
            if RUN_ID == session:
                gdb.write(f"[c{checkpoint}] ")
        gdb.write(msg + "\n")

    def dump(self, sort=False, replace=True, verbose=False):
        if not self.LogFile:
            gdb.write("No log file open\n")
            return

        self.LogFile.seek(0)

        messages = []
        for action in log_actions(self.LogFile):
            if action['type'] != 'log':
                continue

            message = action['message']
            if replace:
                message = labels.apply(message, verbose)

            messages.append((action['event'], action['ticks'], action['lineno'], message, action.get('checkpoint'), action.get('session')))

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
                gdb.write("=> " if i == place else "   ")
                self.write_message(message, verbose=verbose)
        else:
            for message in messages:
                self.write_message(message, verbose=verbose)

    def edit(self):
        if not self.LogFile:
            gdb.write("No log file open\n")
            return

        filename = self.LogFile.name
        self.LogFile.close()
        if os.environ.get("INSIDE_EMACS"):
            pass  # Use emacsclient if possible.
        os.system(os.environ.get('EDITOR', 'emacs') + " " + filename)
        self.openlog(filename, quiet=True)


class ParameterLogFile(gdb.Parameter):
    def __init__(self, logger):
        super(ParameterLogFile, self).__init__('logfile', gdb.COMMAND_SUPPORT, gdb.PARAM_STRING)
        self.logger = logger

    def get_set_string(self):
        if self.value:
            self.logger.openlog(self.logfile)
            return "logging to %s" % self.logfile
        else:
            return "logging stopped"

    def get_show_string(self, svalue):
        if not self.logger.LogFile:
            return "<no logfile active>"
        return self.logger.LogFile.name


# Create gdb commands.
ParameterLogFile(PythonLog())
if running_rr():
    ParameterRRPrompt()
    PythonWhenTicks()
    PythonWhen()
    PythonNow()
