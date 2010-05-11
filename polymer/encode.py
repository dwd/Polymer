#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of Infotrope Polymer.
#
# Infotrope Polymer is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Infotrope Polymer is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Infotrope Polymer; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
import wx
import locale

ui_encoding = None
ui_decoding = ['us-ascii']
if not wx.USE_UNICODE:
    ui_encoding = [locale.getpreferredencoding().lower(),'us-ascii']
    ui_decoding = [locale.getpreferredencoding().lower(),'us-ascii']

#print "UI Encoding: %s, Decoding: %s" % ( `ui_encoding`, `ui_decoding` )

def decode_ui( s ):
    'Used for retrieving data from text boxes, etc. Returns a unicode.'
    #print "UI Decoding %s %s" % ( s.__class__, `s` )
    if isinstance( s, str ):
        #print "Byte string, needs decoding."
        for ch in ui_decoding:
            #print "Trying",ch
            try:
                return s.decode(ch)
            except UnicodeDecodeError, e:
                #print "Fail:",e
                pass
    #print "Fallback."
    return s

def encode_ui( s ):
    'Used for translating a unicode into whatever the text boxes seem to take. Returns a str'
    if isinstance( s, str ):
        return s
    if ui_encoding is not None:
        for ch in ui_encoding:
            try:
                return s.encode(ch)
            except UnicodeEncodeError, e:
                pass
    return s
