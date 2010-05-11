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
import infotrope.xtp
import infotrope.message

# NNTP [RFC977] class, designed for submission only.

class post(infotrope.xtp.command):
    def __init__( self, server, payload ):
        infotrope.xtp.command.__init__( self, server.env, None, 'DATA' )
        self.server = weakref.ref( server )
        self.payload = payload

    def feed( self, resp, erc, txt ):
        f = StringIO.StringIO( self.payload )
        for l in f:
            l = l.rstrip('\r\n')
            if l and l[0]=='.':
                l = '.' + l
            self.server().s.write( l )
            self.server().s.write( '\r\n' )
        self.server().s.write( '.\r\n' )
        self.server().flush()

class connection(infotrope.xtp.connection):
    def __init__( self, uri, env ):
        infotrope.xtp.connection.__init__( self, uri, 119, env )
        self.caps = {}
        self._idle = False
        self.do_connect()

    def cmd_post( self, mail=None, then=None ):
        cmd = self.send( post( mail ) )
        if then is not None:
            cmd.oncomplete( then )
        else:
            self.wait( cmd )
        
    def login( self, user=None, password=None ):
        if user == 'anonymous':
            return
        raise "NNTP doesn't support authentication"
