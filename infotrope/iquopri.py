#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of the Infotrope Python Library.
#
# The Infotrope Python Library is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# The Infotrope Python Library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with the Infotrope Python Library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#!/usr/bin/python
import codecs

"""
Nokia don't provide quoted-printable.
"""

def decode_iquopri( foo ):
    x = foo.split('=')
    if not x:
        return ''
    out = x[0]
    x = x[1:]
    for s in x:
        if s[0]=='\n':
            s = s[1:]
        else:
            try:
                n = int( s[0:2], 16 )
                out += chr(n)
            except ValueError:
                out += '?'
            s = s[2:]
        out += s
    return out

def encode_iquopri( foo, errors = 'strict' ):
    out = ''
    lc = 0
    for c in foo:
        if c.isalnum() or c in '\'"!$%^&*()_-+[]#~@;:/?.>,<\\|`':
            if lc > 76:
                out += '=\n'
                lc = 0
            out += c
            lc += 1
        elif c=='\n':
            lc = 0
            out += '\n'
        elif c!='\r':
            if lc > 76:
                out += '=\n'
                lc = 0
            out += '=%2.2X' % ord(c)
            lc += 3
    return out

def encoder( foo, errors='strict' ):
    return encode_iquopri( foo ), len(foo)
def decoder( foo, errors='strict' ):
    return decode_iquopri( foo ), len(foo)

class Codec(codecs.Codec):
    encode = encoder
    decode = decoder

class StreamReader(Codec,codecs.StreamReader):
    pass
class StreamWriter(Codec,codecs.StreamWriter):
    pass

def search_function( encoding ):
    if encoding not in ['quopri','quoted-printable','iquopri']:
        return None
    return ( encoder, decoder, StreamReader, StreamWriter )
codecs.register( search_function )

