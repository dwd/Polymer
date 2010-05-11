#
# Copyright 2004 - 2006 Dave Cridland <dave@cridland.net>
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

class caller:
    def __init__( self, callee, *args, **kw ):
        self.callee = callee
        self.args = args
        self.kw = kw

    def __call__( self ):
        self.callee( *self.args, **self.kw )
        self.callee = None
        self.args = None
        self.kw = None

class environment:
    def __init__( self, logging=False, protologging=None ):
        self.logging = logging
        self.protologging = protologging
        if self.protologging is None:
            self.protologging = self.logging
        self.sock_delay = None
        self.sock_bandwidth = None
        self.sock_readable = None
        self.sock_writable = None
        self.defcall = False

    def defer_call( self, obj, *args, **kw ):
        obj( *args, **kw )

    def callback( self, mech, vals ):
        raise "__ABSTRACT__"

    def logger( self, *txt ):
        pass

    def proto_logger( self, uri, time, txt ):
        self.logger( str(uri), str(time), str(txt) )

    def alert( self, uri, text ):
        raise "__ABSTRACT__"

    def secquery( self, mech, question ):
        raise "__ABSTRACT__"

    def status( self, text ):
        pass

    def make_operation( self, title, status=None, pmax=None ):
        return None

class cli_environment(environment):
    def __init__( self, logging=False, protologging=None ):
        environment.__init__( self, logging, protologging )
    
    def callback( self, mech, vals ):
        print "Need user information for",mech.mechname,"login to",mech.sasl.service,"on",mech.uri().server
        import getpass
        for x,v in vals.items():
            if x == 'password':
                vals[x] = getpass.getpass( 'Password: ' )
            else:
                vals[x] = raw_input( x+': ' )
        return vals
    
    def logger( self, *txt ):
        print "LOG : ",`txt`
    
    def alert( self, uri, text ):
        print "** Alert from %s!" % uri
        print "   %s" % text

    def secquery( self, mech, question ):
        print "Security Question\n%s" % question
        a = raw_input( "y/N?" )
        if a and a[0].upper() == 'Y':
            return True
        return False

    def status( self, text ):
        if self.logging:
            self.logger( text )
