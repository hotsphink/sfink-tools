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
import re

from enum import Enum

class TraversalNodeType(Enum):
    SIMPLE = 1,
    START_STRUCT = 2,
    END_STRUCT = 3,
    HOLE = 4

def traverse_type(type, max_level=0):

    def calc_sizeof(type):
        '''Same as type.sizeof, except do not inflate empty structs to 1 byte.'''
        type = type.strip_typedefs()
        if type.sizeof != 1 or type.code != gdb.TYPE_CODE_STRUCT:
            return type.sizeof
        size = 0
        for field in type.fields():
            size += calc_sizeof(field.type)
        return size

    def traverse(type, parent, level, field_name, top_bitpos, size_bits, bitpos):
        # print("Calling level=%d field_name=%s tpos=%s sz=%s pos=%x" % (level, field_name, top_bitpos, size_bits, bitpos))
        stripped_type = type.strip_typedefs()

        info = {
            'type': type,
            'name': type.name or type.tag or stripped_type.name or stripped_type.tag,
            'field_name': field_name,
            'size_bits': size_bits,
            'level': level,
            'parent': parent,
            'top_bitpos': top_bitpos,
            'bitpos': bitpos,
        }

        if stripped_type.code != gdb.TYPE_CODE_STRUCT:
            # For now, treat everything but class/struct as a simple type.
            info['node_type'] = TraversalNodeType.SIMPLE
            yield info
            return

        info['node_type'] = TraversalNodeType.START_STRUCT
        yield info

        base_counter = 0
        bitpos = 0
        for field in stripped_type.fields():
            # Skip static fields.
            if not hasattr(field, 'bitpos'):
                continue

            if info['level'] >= max_level:
                continue

            ftype = field.type.strip_typedefs()
            fsize = calc_sizeof(ftype)
            fbitpos = field.bitpos if fsize > 0 else bitpos
            if bitpos != fbitpos:
                yield {
                    'node_type': TraversalNodeType.HOLE,
                    'level': level + 1,
                    'parent': parent,
                    'next_field': field.name,
                    'bitpos': bitpos,
                    'size_bits': fbitpos - bitpos,
                    'field_bitpos': fbitpos,
                }

            if field.bitsize > 0:
                fieldsize = field.bitsize
            else:
                # TARGET_CHAR_BIT here...
                fieldsize = 8 * fsize

            field_name = field.name
            if field.is_base_class:
                field_name = '<base>'
                base_counter += 1
            yield from traverse(field.type, info, level + 1, field_name, top_bitpos + bitpos, fieldsize, bitpos)

            bitpos = fbitpos + fieldsize

        info['node_type'] = TraversalNodeType.END_STRUCT
        yield info

    yield from traverse(type, None, 0, None, 0, 0, 0)

class Pahole (gdb.Command):
    """Show the holes in a structure.
This command takes a single argument, a type name.
It prints the type and displays comments showing where holes are."""

    def __init__ (self):
        super (Pahole, self).__init__ ("pahole", gdb.COMMAND_NONE,
                                       gdb.COMPLETE_SYMBOL)

    def invoke (self, arg, from_tty):
        max_level = 0
        if arg.startswith("/"):
            m = re.match(r'^/(\d+) +', arg)
            if m:
                max_level = int(m.group(1))
                arg = arg[m.span()[1]:]
        type = gdb.lookup_type (arg)
        type = type.strip_typedefs ()
        if type.code != gdb.TYPE_CODE_STRUCT:
            raise (TypeError, '%s is not a struct type' % arg)

        info_pattern = '%4d %4d : '
        header_len = len(info_pattern % (0, 0))
        for info in traverse_type(type, max_level=max_level):
            nt = info['node_type']
            sofar = 0
            if nt != TraversalNodeType.END_STRUCT:
                (bytepos, bytesize) = (int(info['bitpos']/8), int(info['size_bits']/8))
                out = info_pattern % (bytepos, bytesize)
                sofar = len(out)
                print(out, end="")

            indent = ' ' * (2 * info['level'])
            if nt == TraversalNodeType.START_STRUCT:
                desc = ('%s : ' % (info['field_name'],)) if info['field_name'] else ''
                print('%s%sstruct %s {' % (indent, desc, info['name']))
            elif nt == TraversalNodeType.END_STRUCT:
                print('%s%s} %s' % (' ' * (header_len - sofar), indent, info['name']))
            elif nt == TraversalNodeType.SIMPLE:
                print('%s%s : %s' % (indent, info['field_name'], info['type']))
            elif nt == TraversalNodeType.HOLE:
                parent_name = (info['parent'] or {}).get('name', None)
                where = 'in ' + parent_name if parent_name else ''
                print("--> %d bit hole %s <--" % (info['size_bits'], where))

Pahole()
