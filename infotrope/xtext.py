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

def decode_xtext( foo ):
    mid_buffer = ''
    in_safe = 0
    safe = 0
    for x in foo:
        if in_safe:
            in_safe -= 1
            if in_safe==1:
                safe += 16*int( x, 16 )
            else:
                safe += int(x,16)
                mid_buffer += chr(safe)
                safe = 0
        else:
            if x=='+':
                in_safe = 2
            else:
                mid_buffer += x
    try:
        return mid_buffer.decode('utf-8')
    except:
        return mid_buffer

def encode_xtext( foo, errors = 'strict' ):
    if isinstance(foo,unicode):
        foo = foo.encode('utf-8')
    outbuf = ''
    for x in foo:
        if x in '+=' or ord(x) < ord('!') or ord( x ) > ord('~'):
            outbuf += '+%02X' % ( ord(x) )
        else:
            outbuf += x
    return outbuf

def encoder( foo, errors='strict' ):
    return encode_xtext( foo ), len(foo)
def decoder( foo, errors='strict' ):
    return decode_xtext( foo ), len(foo)

class Codec(codecs.Codec):
    encode = encoder
    decode = decoder

class StreamReader(Codec,codecs.StreamReader):
    pass
class StreamWriter(Codec,codecs.StreamWriter):
    pass

def search_function( encoding ):
    if encoding not in ['xtext','esmtp-xtext']:
        return None
    return ( encoder, decoder, StreamReader, StreamWriter )
codecs.register( search_function )
            
    
