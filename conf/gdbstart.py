import os
SFINK_TOOLS_DIR=os.path.abspath(os.path.dirname(os.path.expanduser(__file__)))

gdb.execute("source {}/gdbinit".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.symbols.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.pahole.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.gecko.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.misc".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.rr.py".format(SFINK_TOOLS_DIR))

def breakpoint_handler(event):
    if not isinstance(event, gdb.BreakpointEvent):
        return
    bpnums = [b.number for b in event.breakpoints]
    old = getattr(event, "old_val", "(N/A)")
    new = getattr(event, "new_val", "(N/A)")
    nums = ' '.join(str(n) for n in bpnums)
    print(f"stopped at breakpoint {nums}: {old} -> {new}")

gdb.events.stop.connect(breakpoint_handler)
