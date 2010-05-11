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
It may seem bizarre to define a usascii charset.
The problem is that Python doesn't - it only defines us-ascii - that hyphen isn't used by IANA,
hence we need to define our own.
"""

def decode_usascii( foo ):
    return foo.decode('us-ascii')

def encode_usascii( foo, errors = 'strict' ):
    return foo.encode('us-ascii')

def encoder( foo, errors='strict' ):
    return encode_usascii( foo ), len(foo)
def decoder( foo, errors='strict' ):
    return decode_usascii( foo ), len(foo)

class Codec(codecs.Codec):
    encode = encoder
    decode = decoder

class StreamReader(Codec,codecs.StreamReader):
    pass
class StreamWriter(Codec,codecs.StreamWriter):
    pass

def search_function( encoding ):
    if encoding not in ['usascii']:
        return None
    return ( encoder, decoder, StreamReader, StreamWriter )
codecs.register( search_function )

