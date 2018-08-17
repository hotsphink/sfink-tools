# 'pahole' and 'offset' commands for examining types

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

def type_to_string(type):
    # I had some complicated code to display template parameters here, but it
    # doesn't work quite right and on further reflection the actual problem is
    # a gdb bug anyway. So stop trying.
    #
    # See https://sourceware.org/bugzilla/show_bug.cgi?id=23545

    name = str(type)
    csu = 'struct' if type.code == gdb.TYPE_CODE_STRUCT else 'union'
    if name.startswith(csu + ' '):
        return name
    else:
        return '%s %s' % (csu, name)

def traverse_type(type, max_level=0, name_anon=False):

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
        stripped_type = type.strip_typedefs()

        if parent is None:
            path = 'this'
        elif field_name:
            path = parent['path'] + '.' + field_name
        else:
            if name_anon:
                anon = '<union>' if type.code == gdb.TYPE_CODE_UNION else '<struct>'
                path = parent['path'] + '.' + anon
            else:
                path = parent['path']

        info = {
            'type': type,
            #'name': type.name or type.tag or stripped_type.name or stripped_type.tag,
            'name': type_to_string(type),
            'field_name': field_name,
            'level': level,
            'parent': parent,
            'top_bitpos': top_bitpos,
            'bitpos': bitpos,
            'size_bits': size_bits,
            'path': path,
            'truncated': (max_level and level >= max_level),
        }

        if stripped_type.code not in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
            # For now, treat everything but class/struct/union as a simple type.
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

            # Allow limiting the depth of traversal.
            if max_level and info['level'] >= max_level:
                continue

            ftype = field.type.strip_typedefs()
            fsize = calc_sizeof(ftype)
            fbitpos = field.bitpos if fsize > 0 else bitpos
            if bitpos != fbitpos:
                yield {
                    'node_type': TraversalNodeType.HOLE,
                    'type': '<hole>',
                    'name': '<%d-bit hole>' % (fbitpos - bitpos),
                    'field_name': None,
                    'level': level + 1,
                    'parent': info,
                    'top_bitpos': top_bitpos + bitpos,
                    'bitpos': bitpos,
                    'size_bits': fbitpos - bitpos,
                    'path': path,
                    'next_field': field.name,
                }

            # Advance past the hole, to the start of the field.
            bitpos = fbitpos

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

            if stripped_type.code == gdb.TYPE_CODE_STRUCT:
                bitpos += fieldsize

        info['node_type'] = TraversalNodeType.END_STRUCT
        yield info

    yield from traverse(type,
                        parent=None,
                        level=0,
                        field_name=None,
                        top_bitpos=0,
                        size_bits=type.sizeof*8,
                        bitpos=0)

class Pahole (gdb.Command):
    """Show the holes in a structure.
This command takes a single argument, a type name.
It prints the type, including any holes it finds.
It accepts an optional max-depth argument:
  `pahole/1 mytype` will not recurse into contained structs."""

    def __init__ (self):
        super (Pahole, self).__init__ ("pahole", gdb.COMMAND_NONE,
                                       gdb.COMPLETE_SYMBOL)

    def invoke (self, arg, from_tty):
        max_level = 0
        if arg.startswith("/"):
            m = re.match(r'^/(\d+) +', arg)
            if m:
                max_level = int(m.group(1), 0)
                arg = arg[m.span()[1]:]

        type = gdb.lookup_type(arg)
        type = type.strip_typedefs ()
        if type.code not in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
            raise TypeError('%s is not a class/struct/union type' % arg)

        info_pattern = '    %4d %4d : '
        inner_info_pattern = '%4d%+4d %4d : '
        empty_inner_info_pattern = '         %4d : '
        header_len = len(inner_info_pattern % (0, 0, 0))
        print('  offset size')
        for info in traverse_type(type, max_level=max_level):
            nt = info['node_type']
            sofar = 0
            if nt != TraversalNodeType.END_STRUCT:
                bytepos = int(info['bitpos'] / 8)
                top_bytepos = int(info['top_bitpos'] / 8)
                bytesize = int(info['size_bits'] / 8)
                if info['level'] > 1:
                    if bytesize == 0:
                        out = empty_inner_info_pattern % bytesize
                    else:
                        out = inner_info_pattern % (top_bytepos - bytepos, bytepos, bytesize)
                else:
                    out = info_pattern % (bytepos, bytesize)
                sofar = len(out)
                print(out, end="")

            indent = ' ' * (2 * info['level'])
            if nt == TraversalNodeType.START_STRUCT:
                desc = indent
                if info['field_name']:
                    desc += '%s : ' % info['field_name']
                desc += info['name']
                if not info['truncated']:
                    desc += ' {'
                print(desc)
            elif nt == TraversalNodeType.END_STRUCT:
                if not info['truncated']:
                    print('%s%s} %s' % (' ' * (header_len - sofar), indent, info['name'] or ''))
            elif nt == TraversalNodeType.SIMPLE:
                print('%s%s : %s' % (indent, info['field_name'], info['type']))
            elif nt == TraversalNodeType.HOLE:
                parent_name = (info['parent'] or {}).get('name', None)
                where = 'in ' + parent_name if parent_name else ''
                print("--> %d bit hole %s <--" % (info['size_bits'], where))

Pahole()

class TypeOffset (gdb.Command):
    """Displays the fields at the given offset (in bytes) of a type.
The optional /N parameter determines the size of the region inspected;
defaults to the size of a pointer."""

    default_width = gdb.lookup_type("void").pointer().sizeof

    def __init__ (self):
        super (TypeOffset, self).__init__ ("offset", gdb.COMMAND_NONE,
                                       gdb.COMPLETE_SYMBOL)

    def invoke (self, arg, from_tty):
        width = gdb.lookup_type("void").pointer().sizeof
        m = re.match(r'/(\d+) ', arg)
        if m:
            width = int(m.group(1), 0)
            arg = arg[m.span()[1]:]
        (offset, typename) = arg.split(" ")
        offset = int(offset, 0)
        type = gdb.lookup_type(typename)
        type = type.strip_typedefs ()
        if type.code not in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
            raise TypeError('%s is not a class/struct/union type' % arg)

        begin, end = offset, offset + width - 1
        print("Scanning byte offsets %d..%d" % (begin, end))
        for info in traverse_type(type, name_anon=True):
            if info['node_type'] == TraversalNodeType.END_STRUCT:
                continue
            if 'top_bitpos' not in info or 'size_bits' not in info:
                continue
            # Not all that interesting to say that the whole type overlaps.
            if info['level'] == 0:
                continue
            (bytepos, bytesize) = (int(info['top_bitpos']/8), int(info['size_bits']/8))
            fend = bytepos + bytesize - 1
            #print("checking {}+{} of type {}".format(bytepos, bytesize, info['node_type']))
            if fend < begin:
                continue
            if bytepos > end:
                continue
            name_of_type = info.get('name') or type_to_string(info['type'])
            if info['node_type'] == TraversalNodeType.HOLE:
                name_of_type += " in " + (info['parent'] or {}).get('name', 'struct')
                if info['next_field']:
                    name_of_type += " before field '" + info['next_field'] + "'"
            print('overlap at byte %d..%d with %s : %s' % (bytepos, fend, info['path'], name_of_type))

TypeOffset()
