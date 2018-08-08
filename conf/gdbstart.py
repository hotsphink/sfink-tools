import os
SFINK_TOOLS_DIR=os.path.abspath(os.path.dirname(os.path.expanduser(__file__)))

gdb.execute("source {}/gdbinit".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.symbols.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.pahole.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.gecko".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.gecko.py".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.misc".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.rr".format(SFINK_TOOLS_DIR))
gdb.execute("source {}/gdbinit.rr.py".format(SFINK_TOOLS_DIR))
