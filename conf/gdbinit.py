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
import json
import os
import re

from pathlib import Path

if not hasattr(gdb, "commands"):
    gdb.commands = {}

class PythonPrint(gdb.Command):
    """Print the value of the python expression given"""
    def __init__(self, name="pp"):
        gdb.Command.__init__(self, name, gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        print(eval(arg))

gdb.commands["pp"] = PythonPrint("pp")
gdb.commands["pprint"] = PythonPrint("pprint")

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

gdb.commands["pdo"] = PDo("pdo")

######################################################################

# reappend "stem" "tail" [limit]
# Example: reappend "p obj->shape" "->parent" 3
class RepeatedAppend(gdb.Command):
  """Run a command, appending a "tail" to the command on every iteration, until an error or [limit] is reached"""
  def __init__(self, name="reappend"):
    gdb.Command.__init__(self, name, gdb.COMMAND_USER)

  def invoke(self, arg, from_tty):
    args = gdb.string_to_argv(arg)
    cmd = args[0]
    tail = args[1]
    limit = int(args[2]) if len(args) > 2 else 9999
    for i in range(limit):
      # print("Executing %s + %s x %d" % (args[0], args[1], limit))
      gdb.execute(cmd)
      cmd = cmd + tail

gdb.commands["reappend"] = RepeatedAppend("reappend")

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
        # Substitution pattern maintenance -- this class keeps a compiled regex
        # 'pattern' up to date with its set of keys. The pattern is lazily
        # generated whenever it's needed and the set of keys has changed since
        # the last time it was rebuilt.
        self.dirty = True
        self.pattern()

        # This class supports a single external consumer that feeds off a "log"
        # of added keys. Every key added will be appended to a list that is
        # cleared out when flush_added() is called to retrieve all adds since
        # the previous call. (If the class is clear()ed, 'added' will be
        # reset.)
        self.added = []

        # When initially loading a log file, we might have labels with types
        # that have not been loaded yet. Keep these labels in a pending list
        # and try to apply them again every time we load a new objfile.
        self.pending_labels = []

    def label(self, token, name, typestr, gdbval=None, report=True):
        """Set a label named `name` to the value `token` (probably a numeric
        value) cast according to `typestr`, which is a raw cast expression.
        gdbval is... figuring that out now."""
        print("Setting label {} := {} of type {} gdbval={}".format(token, name, typestr, gdbval))
        if gdbval is None:
            try:
                # Look for a pointer type, eg in `(JSObject *) 0xdeadbeef`
                if m := re.match(r'([^ ]*?)( *\**)$', typestr):
                    t, ptrs = m.groups()
                else:
                    t, ptrs = (typestr, '')
                #print("scanning `" + valstr + "` for " + re.escape(typestr) + ' ((?:0x)?[0-9a-f]{1,16})')
                #if m := re.search(re.escape(typestr) + ' ((?:0x)?[0-9a-f]{1,16})', valstr):
                #    gdbval = gdb.parse_and_eval(f"('{t}'{ptrs}) {m.group(1)}")
                #else:
                #    gdbval = gdb.parse_and_eval(f"('{t}'{ptrs}) {token}")
                gdbval = gdb.parse_and_eval(f"('{t}'{ptrs}) {token}")
            except gdb.error as e:
                # This can happen if we load in a set of labels before the type
                # exists.
                #
                # TODO: Report on unkonwn types at a reasonable time.

                #gdb.write("unknown type: " + str(e) + "\n")
                #gdb.write(" -->" + f"('{t}'{ptrs}) {token}" + "<--\n")
                self.pending_labels.append((token, name, typestr))
                return False
        self[token] = (name, typestr)
        if report:
            print(f"all occurrences of {token} will be replaced with ${name} of type {typestr}")
        gdb.set_convenience_variable(name, gdbval)
        return True

    def __setitem__(self, key, pair):
        key = self.canon(key)
        if dict.get(self, key) == pair:
            return
        #print(f"all occurrences of {key} will be replaced with ${pair[0]} of type {pair[1]}")

        # Remove all old keys referring to $name so that the old key will not be replaced
        # with the updated $name.
        deadkeys = {key for key, (name, t) in labels.items() if name == pair[0]}
        for deadkey in deadkeys:
            del self[deadkey]

        dict.__setitem__(self, key, pair)
        self.added.append(key)
        self.dirty = True

    def clear(self):
        dict.clear(self)
        self.dirty = True

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
        '''Retrieve the list of entries added since the last call to this method.'''
        ret = [(k, self[k]) for k in self.added if k in self]
        self.added = []
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
            #print("Rebuilding pattern with {} replacements".format(len(self)))
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
                self.repPattern = re.compile(r'\b(?<![\$\-])(?:' + '|'.join(reps) + r')\b')
            self.dirty = False

        return self.repPattern

    def apply(self, text, verbose=False):
        return re.sub(
            self.pattern(),
            lambda m: self.get(m.group(0), None, verbose),
            text)

    def on_objfile_load(self, event):
        if self.pending_labels:
            gdb.write("objfile load detected, reprocessing {} labels\n".format(len(self.pending_labels)))
        pending = self.pending_labels
        self.pending_labels = []
        for (token, name, typestr) in pending:
            # There really ought to be a better way to look up a type
            # expression.
            if self.label(token, name, typestr):
                gdb.write("  succeeded in setting pending label {}\n".format(name))

labels = Labels()

def new_objfile_handler(event):
    labels.on_objfile_load(event)

gdb.events.new_objfile.connect(new_objfile_handler)

def index_of_first(s, tokens, start=0):
    bestpos = None
    for token in tokens:
        try:
            pos = s.index(token, start)
            if bestpos is None or pos < bestpos:
                bestpos = pos
        except ValueError:
            pass
    return bestpos

class LabelCmd(gdb.Command):
    """Replace numeric values in the output with their labels.

    Usage: label [NAME=[VALUE]]

    With no arguments, display all current labels.

    With just a NAME argument, do the same as `label NAME=$` (label the
    previous gdb value).

    With NAME=VALUE, evaluate VALUE and then extract the first numeric value seen
    from it. All further `p` command output will have that numeric value replaced
    with $<NAME>. Also, the convenience variable $<NAME> will be set to VALUE.

    Example:

      label GLOBAL=cx->global()

    will evalute the expression `cx->global()` to something like

      (JSObject*) 0xabcd0123efef0800

    and now later on when the expression `obj` happens to evaluate to the same object,

      gdb> p obj
      $1 = (JSObject *) $GLOBAL
      gdb> p $GLOBAL
      $2 = (JSObject *) $GLOBAL

    """

    CAST_TO_POINTER = r'\(([^\(\)]+ *\*+)\) *'

    def __init__(self, name):
        super(LabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    def invoke(self, arg, from_tty):
        if len(arg) == 0:
            self.show_all_labels()
            return

        # label variable MYVAL=<expr>
        # label variable MYVAL <expr>
        if arg.startswith('variable '):
            start=len('variable ')
            pos = index_of_first(arg, [' ', '='], start)
            if pos is None:
                gdb.write("invalid usage\n")
                return
            self.set_label(arg[start:pos], arg[pos+1:])
            return

        # label MYVAR=expr
        # label MYVAR expr
        pos = index_of_first(arg, [' ', '='])
        if pos is None:
            name = arg
            val = '$'
        else:
            name, val = (arg[0:pos], arg[pos+1:])
        self.set_label(name, val.lstrip())

    def get_label(self, name):
        for key, (n, t) in labels.items():
            if n == name:
                gdb.write(f"{name} = ({t}) {key}\n")
                break
        else:
            gdb.write("Label '{}' not found\n".format(name))

    def prefer_prettyprinted(self, t):
        s = str(t)
        return s.startswith("JS::Handle") or s.startswith("JS::Value")

    def set_label(self, name, value):
        if re.fullmatch(r'0x[0-9a-fA-F]+', value) or value.lstrip('-').isdecimal():
            if int(value) != 0:
                labels[value] = (name, 'void*')
                return

        v = gdb.parse_and_eval(value)
        # FIXME! If there is a pretty printer for v that displays a different
        # hex value than its address, then we will label using that instead.
        # (Example: Symbol displays its desc address, though in the 0x0 case we
        # will now skip that..)

        # First, attempt to cast to void*, unless the special case code says this
        # type should prefer prettyprinting.
        valstr = None
        try:
            if not self.prefer_prettyprinted(v.type):
                valstr = str(v.cast(gdb.lookup_type('void').pointer()))
        except Exception as e:
            pass

        if valstr is None:
            # Fall back on the (possibly prettyprinted) output.
            valstr = str(v)

        m = re.search(r'0x[0-9a-fA-F]+', valstr)
        if not m:
            m = re.search(r'-?[0-9]{4,20}', valstr)
        if not m or m.group(0) == '0' or m.group(0) == '0x0':
            gdb.write("No labelable value found in " + valstr + "\n")
            return
        numeric = m.group(0)

        # gdb.write("gots %s, setting labels[%s] = %s\n" % (str(v), m.group(0), value))

        # label $3 SOMETHING
        # should set $SOMETHING to the actual value of $3

        # If the numeric value is preceded by something that looks like a cast to a pointer, use the cast as the type.
        pattern = self.CAST_TO_POINTER + numeric
        gdb.write("pattern = " + pattern + "\n");
        gdb.write("valstr = " + valstr + "\n");
        if mm := re.search(pattern, valstr):
            gdb.write("  type = " + mm.group(1) + "\n")
            labels.label(numeric, name, mm.group(1))
        else:
            labels.label(m.group(0), name, str(v.type), gdbval=v)

    def show_all_labels(self):
        seen = set()
        for key, (name, t) in labels.items():
            if name not in seen:
                seen.add(name)
                gdb.write(f"${name} = ({t}) {key}\n")

gdb.commands["label"] = LabelCmd('label')

class UnlabelCmd(gdb.Command):
    def __init__(self, name):
        super(UnlabelCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_NONE)

    def invoke(self, arg, from_tty):
        deadname = arg
        deadkeys = {k: name for k, (name, t) in labels.items() if name == deadname}
        for key in deadkeys.keys():
            del labels[key]

gdb.commands["unlabel"] = UnlabelCmd('unlabel')

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

    def evaluate(expr, replace=True, brieftype=True):
        fmt = {}
        if m := re.search(r':(\w+)$', expr):
            expr = expr[:-len(m[0]):]
            flags = m[1]
            if 'r' in flags:
                fmt['raw'] = True
                flags = flags.replace('r', '')
            if len(flags) == 1:
                fmt['format'] = flags
        try:
            v = gdb.parse_and_eval(expr)
        except gdb.error as e:
            print("Invalid embedded expression «{}»".format(expr))
            raise e
        s = v.format_string(**fmt)
        t = v.type
        ts = str(t)

        # Ugh. In some situations, the value will be prefixed with its type,
        # and others it will not. Enough will not that I wanted to add it in.

        if s.startswith("("):
            return s
        BORING_TYPES = ("int", "unsigned int", "uint32_t", "int32_t", "uint64_t", "int64_t")
        if ts in BORING_TYPES:
            return s
        # If the type name is in the value, as in js::gc::CellColor::Black,
        # then we don't need to see the cast.
        if ts in s:
            return s
        if brieftype:
            ots = ts
            ts = ts.replace('const ', '')
            ts = ts.replace(' const', '')
            ts = re.sub(r'\w+::', '', ts)
            ts = ts.replace(' *', '*')
            # Same check as above, but sometimes the type gets aliased into a
            # different namespace. So try even harder to throw it out.
            if ts in s:
                return s
        return "(%s) %s" % (ts, s)

    def grab_commands(start=0):
        gdb_cmd = "show commands"
        if start > 0:
            gdb_cmd += f" {start}"
        out = gdb.execute(gdb_cmd, to_string=True)
        def parse_line(s):
            m = re.match(r'\s*(\d+)\s+(.*)', s)
            idx, cmd = m.groups()
            return (int(idx), cmd)
        result = [parse_line(line) for line in out.splitlines()]
        print(f"Got {result[0][0]}..{result[-1][0]} from {start}: {gdb_cmd}")
        return result

    def history_commands(indexes=False):
        '''generator for commands from the history, in reverse order (most
        recent to oldest aka first), optionally with indexes'''
        cmd_buffer = util.grab_commands()
        chunksize = None
        if cmd_buffer[0][0] != 1 and not chunksize:
            # if `show commands` begins with > 1, it isn't truncated.
            chunksize = len(cmd_buffer)

        while True:
            idx, command = cmd_buffer.pop()
            if indexes:
                yield (idx, command)
            else:
                yield command
            if idx == 1:
                return
            if cmd_buffer:
                continue
            start = max(1, idx - chunksize // 2)
            #print(f"start = max(1, {idx} - {chunksize} / 2) = {start}")
            cmd_buffer = util.grab_commands(start)
            # First batch (starting at command 1) may give commands we've already seen.
            while cmd_buffer[-1][0] >= idx:
                cmd_buffer.pop()

    def parse_ranges(spec, lastidx=None):
        earliest = lastidx or 1e12
        indexes = []
        for r in spec.split(','):
            if r.endswith('-'):
                start = int(r.rstrip("-"))
                if lastidx is None:
                    raise ValueError("unterminated range requires lastidx")
                end = lastidx
            elif (pos := r.find("-")) != -1:
                start = int(r[0:pos])
                end = int(r[pos+1:])
            else:
                start = end = int(r)
            indexes.extend(range(start, end + 1))
            earliest = min(earliest, start)
        return (indexes, earliest)

class PrintCmd(gdb.Command):
    """\
like gdb's builtin 'print' function, with label replacements and special syntax.

Any substring that matches a label SOMELABEL will be replaced with the
literal string `$SOMELABEL`.

If `m..n` is found anywhere in the string, the print will be repeated for
every number in that range.

If `{substr}**n` is found in the string, then substr will be repeated n
times.
"""

    def __init__(self, name):
        super(PrintCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_COMMAND)

    def enumerateExprs(self, expr):
        m = re.match(r'(.*?)(\w+)\.\.(\w+)(.*)', expr)
        if m:
            start = gdb.parse_and_eval(m.group(2))
            end = gdb.parse_and_eval(m.group(3))
            for i in range(start, end):
                newExpr = m.group(1) + str(i) + m.group(4)
                yield from self.enumerateExprs(newExpr)
            return

        m = re.match(r'(.*?)\{(.*?)\}\*\*(\d+)(.*)', expr)
        if m:
            start, subexpr, n, rest = m.groups()
            n = int(n)
            newExpr = start + ''.join(subexpr for _ in range(n)) + rest
            yield from self.enumerateExprs(newExpr)
            return

        yield expr
        return

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

gdb.commands["p"] = PrintCmd('p')

class MacroCmd(gdb.Command):
    """\
Record and restore persistent command macros.

macro start NAME - start macro recording
macro end - end macro recording, save to persistent store
macro grab NAME START [END] - grab out the commands between START and END (substrings) and save as NAME
macro run NAME - execute macro
macro list - list all macro names
macro show NAME - display commands in the named macro
macro delete NAME - delete the named macro
macro commands - list full command history\
"""

    def __init__(self, name):
        super(MacroCmd, self).__init__(name, gdb.COMMAND_USER, gdb.COMPLETE_COMMAND)

    def state_file(self):
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        dirpath = base / "gdb-macros"
        dirpath.mkdir(parents=True, exist_ok=True)
        return dirpath / "macros.json"

    def _load_macros(self):
        try:
            return json.loads(self.state_file().read_text())
        except OSError as e:
            return {}

    def _save_macros(self, macros):
        path = self.state_file()
        path.write_text(json.dumps(macros, indent=2))

    def invoke(self, arg, from_tty):
        _opts, arg = util.split_command_arg(arg)
        # _fmt = ''.join(o[0] for o in opts)

        parts = arg.split(' ')
        if not parts:
            gdb.write("usage: macro {start,end,load} args...\n")
            return

        if parts[0] in ("start", "begin"):
            name = parts[1]  # FIXME: error checking
            gdb.write(f"Recording macro '{name}'\n")
            # Nothing to do.
        elif parts[0] == "end":
            rmacro = []
            for cmd in util.history_commands():
                print(f"considering: {cmd}")
                if m := re.match(r"macro.*\s+start\s+([\w\-]+)$", cmd):
                    name = m.group(1)
                    self.record_macro(name, reversed(rmacro))
                    gdb.write(f"recorded macro '{name}' with {len(rmacro)} commands\n")
                    return
                elif m := re.match(r"macro\b", cmd):
                    pass
                else:
                    rmacro.append(cmd)
            gdb.write("no `macro start NAME` command found\n")
            return
        elif parts[0] == "grab":
            name = parts[1]

            reverse_commands = util.history_commands(indexes=True)
            (lastidx, _) = next(reverse_commands)  # Skip this macro grab command
            lastidx -= 1  # The biggest index we might want

            (indexes, earliest) = util.parse_ranges(parts[2], lastidx)

            commands = {}
            for (idx, cmd) in reverse_commands:
                commands[idx] = cmd
                if idx <= earliest:
                    break

            macro = [commands[idx] for idx in indexes]
            self.record_macro(name, macro)
            gdb.write(f"recorded macro '{name}' with {len(macro)} commands\n")
        elif parts[0] == "run":
            name = parts[1]  # FIXME
            macro = self.load_macro(name)
            self.run(macro)
        elif parts[0] in ("list", "ls"):
            self.list_macros()
        elif parts[0] in ("delete", "rm"):
            name = parts[1]  # FIXME
            self.delete(name)
        elif parts[0] == "show":
            self.show(parts[1])
        elif parts[0] == "commands":
            self.show_commands()
        elif parts[0] == "path":
            gdb.write(self.state_file() + "\n")
        else:
            gdb.write("unknown subcommand\n")

    def record_macro(self, name, commands):
        macros = self._load_macros()
        macros[name] = commands
        self._save_macros(macros)

    def load_macro(self, name):
        macros = self._load_macros()
        return macros.get(name)

    def run(self, commands):
        for cmd in commands:
            gdb.execute(cmd, from_tty=False)

    def list_macros(self):
        macros = self._load_macros()
        if macros:
            gdb.write("defined macros:\n")
            for macro in macros.keys():
                gdb.write(f"  {macro}\n")
        else:
            gdb.write("no macros defined in " + str(self.state_file()) + "\n")

    def show(self, name):
        macros = self._load_macros()
        macro = macros.get(name)
        if macro:
            for line in macro:
                gdb.write(line + "\n")
        else:
            gdb.write(f"macro '{name}' not found\n")

    def delete(self, name):
        macros = self._load_macros()
        if name in macros:
            del macros[name]
            self._save_macros(macros)
        else:
            gdb.write(f"macro '{name}' not found\n")

    def show_commands(self, limit=1000):
        reverse_commands = util.history_commands(indexes=True)
        next(reverse_commands)  # Skip this macro command
        commands = []
        for pair in reverse_commands:
            if limit == 0:
                break
            commands.append(pair)
        for (idx, cmd) in reversed(commands):
            gdb.write(f"{idx} {cmd}\n")

gdb.commands["macro"] = MacroCmd("macro")
