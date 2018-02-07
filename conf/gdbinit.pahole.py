# pahole command for gdb

# Copyright (C) 2008, 2009, 2012 Free Software Foundation, Inc.

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gdb

class Pahole (gdb.Command):
    """Show the holes in a structure.
This command takes a single argument, a type name.
It prints the type and displays comments showing where holes are."""

    def __init__ (self):
        super (Pahole, self).__init__ ("pahole", gdb.COMMAND_NONE,
                                       gdb.COMPLETE_SYMBOL)

    def maybe_print_hole(self, bitpos, field_bitpos):
        if bitpos != field_bitpos:
            hole = field_bitpos - bitpos
            print ('  /* XXX %d bit hole, try to pack */' % hole)

    def pahole (self, type, level, name):
        if name is None:
            name = ''
        tag = type.tag
        if tag is None:
            tag = ''
        print ('%sstruct %s {' % (' ' * (2 * level), tag))
        bitpos = 0
        for field in type.fields ():
            # Skip static fields.
            if not hasattr (field, ('bitpos')):
                continue

            ftype = field.type.strip_typedefs()

            self.maybe_print_hole(bitpos, field.bitpos)
            bitpos = field.bitpos
            if field.bitsize > 0:
                fieldsize = field.bitsize
            else:
                # TARGET_CHAR_BIT here...
                fieldsize = 8 * ftype.sizeof

            # TARGET_CHAR_BIT
            print (' /* %3d %3d */' % (int (bitpos / 8), int (fieldsize / 8)), end = "")
            bitpos = bitpos + fieldsize

            if ftype.code == gdb.TYPE_CODE_STRUCT:
                self.pahole (ftype, level + 1, field.name)
            else:
                print (' ' * (2 + 2 * level), end = "")
                print ('%s %s' % (str (ftype), field.name))

        if level == 0:
            self.maybe_print_hole(bitpos, 8 * type.sizeof)

        print (' ' * (14 + 2 * level), end = "")
        print ('} %s' % name)

    def invoke (self, arg, from_tty):
        type = gdb.lookup_type (arg)
        type = type.strip_typedefs ()
        if type.code != gdb.TYPE_CODE_STRUCT:
            raise (TypeError, '%s is not a struct type' % arg)
        print (' ' * 14, end = "")
        self.pahole (type, 0, '')

Pahole()
