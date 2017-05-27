# $_when_ticks function.
# $_when functions
# set rrprompt on

import gdb
import os
import re

RUNNING_RR = None

print(os.environ)

def running_rr():
    global RUNNING_RR
    if RUNNING_RR is not None:
        return RUNNING_RR
    try:
        gdb.execute("when", False, True)
        RUNNING_RR = True
    except gdb.error:
        RUNNING_RR = False
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
        return when_ticks()

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

    def openlog(self, filename):
        self.LogFile = open(filename, "a+")
        print("Opened %s" % (self.LogFile.name,))

    def stoplog(self):
        self.LogFile = False

    def invoke(self, arg, from_tty):
        if '-sorted'.startswith(arg):
            self.dump(sort=True)
        elif '-dump'.startswith(arg):
            self.dump()
        elif '-edit'.startswith(arg):
            self.edit()
        else:
            if self.LogFile is None:
                self.openlog(os.path.join(os.environ['HOME'], "rr-session.log"))
            if self.LogFile:
                self.LogFile.write("%s %s\n" % (now(), arg))

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

        current = nowTuple()
        place = -1
        if sort:
            messages.sort()
            place = 0
            for i, message in enumerate(messages):
                if current < (message[0], message[1]):
                    place = i
                    break

        for i, message in enumerate(messages):
            print("%s%s" % ("=> " if i == place else "   ", message[3]))

    def edit(self):
        if not self.LogFile:
            print("No log file open")
            return

        filename = self.LogFile.name
        self.LogFile.close()
        os.system(os.environ.get('EDITOR', 'emacs') + " " + filename)
        self.openlog(filename)

class ParameterLogFile(gdb.Parameter):
    def __init__(self):
        super(ParameterLogFile, self).__init__('logfile', gdb.COMMAND_SUPPORT, gdb.PARAM_STRING)
        self.logfile = None

    def get_set_string(self):
        if self.value:
            self.logfile = self.value
            logger.openlog(self.logfile)
            return "logging to %s" % self.logfile
        else:
            return "logging stopped"

    def get_show_string(self, svalue):
        return self.logfile

if running_rr():
    logger = PythonLog()
    ParameterLogFile()

print("RUNNING RR = %s" % (running_rr()))
