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


def thread_id():
    gtid = gdb.selected_thread().global_num
    return f"T{gtid}"


def thread_detail():
    return gdb.selected_thread().details


def target_id():
    return gdb.selected_thread().ptid[0]


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
    return "%s:%s/%s" % (thread_id(), when(), when_ticks())


def nowTuple():
    return (when(), thread_id(), when_ticks())


def rrprompt(current_prompt):
    return "rr " + now()


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
    """Output <thread>:<when>/<when-ticks>"""
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


class ParameterLogQuiet(gdb.Parameter):
    quiet = False

    def __init__(self):
        # FIXME: Rename from 'logging', try to use nested command stuff?
        super(ParameterLogQuiet, self).__init__('logquiet', gdb.COMMAND_SUPPORT, gdb.PARAM_BOOLEAN)

    def get_set_string(self):
        ParameterLogQuiet.quiet = self.value
        return "logging is " + ("quiet" if ParameterLogQuiet.quiet else "noisy")

    def get_show_string(self, svalue):
        return "logging is " + ("quiet" if ParameterLogQuiet.quiet else "noisy")


class PythonLog(gdb.Command):
    """Append current event/tick-count with message to log file"""
    def __init__(self):
        gdb.Command.__init__(self, "log", gdb.COMMAND_USER)
        self.LogFile = None
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
                labels.label(action['key'], action['value'], action['datatype'], report=False)

        labels.flush_added()
        self.LogFile.record_end()

    def stoplog(self):
        self.LogFile.close()
        self.LogFile = None

    def default_log_filename(self):
        return os.path.join(DEFAULT_LOG_DIR, f"rr-session-{target_id()}.json")

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
            elif 'delete'.startswith(opt):
                # log/d : delete log messages containing substring
                self.delete(arg)
                return
            elif 'raw'.startswith(opt):
                # log/r : do not do any label replacements in message
                dump_args['replace'] = False
                raw = True
            elif 'print-only'.startswith(opt):
                # log/p : display the log message without logging it permanently
                do_print = True
                do_dump = False
            elif 'goto'.startswith(opt):
                # log/g : seek to the time of a log entry
                self.goto(arg)
                return
            else:
                gdb.write("unknown log option '{}'\n".format(opt))

        if do_addentry:
            out = self.process_message(arg)
            if not raw:
                out = labels.apply(out, verbose=False)
            # If any substitutions were made, display the resulting log message.
            do_print = not ParameterLogQuiet.quiet
            if out != arg:
                do_print = True
            if self.LogFile:
                gdb_out = gdb.execute("checkpoint", to_string=True)
                action = {'type': 'log', 'event': when(), 'thread': thread_id(), 'tname': thread_detail(), 'ticks': when_ticks(), 'message': out}
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
        out = out.replace("$thread", thread_id())

        # Let gdb handle other $ vars.
        return re.sub(r'(\$\w+)', lambda m: util.evaluate(m.group(1)), out)

    def write_message(self, message, index=None, verbose=False):
        if len(message) == 7:
            (event, thread, ticks, lineno, msg, checkpoint, session) = message
        elif len(message) == 6:
            (event, ticks, lineno, msg, checkpoint, session) = message
            thread = "T?"

        if verbose:
            gdb.write(f"{thread}:{event}/{ticks} ")
        if checkpoint is not None and RUN_ID == session:
            gdb.write(f"[c{checkpoint}] ")
        elif index is not None:
            gdb.write(f"[@{index}] ")

        gdb.write(msg + "\n")

    def build_messages(self, replace=True, verbose=False):
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
            action.setdefault('thread', 'T?')

            messages.append((action['event'], action['thread'], action['ticks'], action['lineno'], message, action.get('checkpoint'), action.get('session')))

        return messages

    def dump(self, sort=False, replace=True, verbose=False):
        messages = self.build_messages(replace=replace, verbose=verbose)
        if messages is None:
            return

        now = nowTuple()
        place = -1
        if sort:
            messages.sort()
            for i, message in enumerate(messages):
                when = message[0:3]
                if when == now:
                    gdb.write("=> ")
                elif now is not None and when > now:
                    gdb.write("=>\n   ")
                    now = None
                else:
                    gdb.write("   ")
                self.write_message(message, index=i, verbose=verbose)
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

    def delete(self, filter_out):
        if not self.LogFile:
            gdb.write("No log file open\n")
            return

        count = 0

        filename = self.LogFile.name
        self.LogFile.close()
        tempfilename = filename + ".tmp"
        with open(tempfilename, "wt") as outfh, open(filename, "rt") as infh:
            for action in log_actions(infh):
                if action['type'] == 'log' and filter_out in action['message']:
                    count += 1
                else:
                    json.dump(action, outfh)
                    outfh.write("\n")
        os.rename(filename, filename + ".old")
        os.rename(tempfilename, filename)
        self.openlog(filename, quiet=True)

        gdb.write(f"Deleted {count} {'entry' if count == 1 else 'entries'}\n")

    def goto(self, where):
        if where.startswith("@"):
            index = int(where[1:])
            messages = self.build_messages(replace=False, verbose=False)
            if messages is None:
                return
            messages.sort()
            event, thread, ticks = messages[index][0:3]
            if thread_id() != thread:
                gdb.execute(f"thread {thread[1:]}")
            gdb.execute(f"seek {ticks}")
            return

        if where.startswith("c"):
            checkpoint = int(where[1:])
        else:
            checkpoint = int(where)
        gdb.execute(f"restart {checkpoint}")


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
ParameterLogQuiet()
if running_rr():
    ParameterRRPrompt()
    PythonWhenTicks()
    PythonWhen()
    PythonNow()
