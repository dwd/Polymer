#!/usr/bin/env python
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
        
def handle_options():
    """
    Handle options.
    """
    import socket
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option( "-k", "--kiosk", action="store_true", help="Kiosk mode, no stash, no cache", default=False )
    parser.add_option( "-s", "--stash", type="string", help="Where Polymer should keep your credentials, if at all" )
    parser.add_option( "-c", "--cache", type="string", help="Where Polymer should keep offline data" )
    parser.add_option( "-m", "--mailto", type="string", help="Mailto URL processing mode only" )
    parser.add_option( "-u", "--url", type="string", help="General URL processing" )
    parser.add_option( "-l", "--locality", type="string", help="Your locality, used to select location specific options.", default=socket.gethostname() )
    parser.add_option( "-g", "--debug", action="store_true", help="Debug mode", default=False )
    parser.add_option( "-t", "--trace", type="string", help="Protocol Trace", default="" )
    parser.add_option( "-x", "--console", action="store_true", help="Send debug log to console", default=None )
    parser.add_option( "-e", "--exceptions", action="store_false", help="Don't catch exceptions, let them go to console.", default=True )
    parser.add_option( "-f", "--fatal", action="store_true", help="Treat all unhandled exceptions as fatal.", default=False )
    parser.add_option( "-a", "--acap", type="string", help="ACAP server, server:port, or URL." )
    parser.add_option( "-I", "--ban-imap", type="string", help="Ban these comma seperated IMAP extensions." )
    parser.add_option( "-S", "--ban-esmtp", type="string", help="Ban these comma seperated ESMTP extensions." )
    parser.add_option( "-p", "--profile", type="string", help="Run profiler, output to this file." )
    parser.add_option( "-d", "--delay", type="int", help="Emulate high latency by adding DELAYms." )
    parser.add_option( "-w", "--bandwidth", type="string", help="Emulate lower bandwdith, capping at BANDWIDTHb/s" )
    parser.add_option( "-n", "--appname", type="string", default="Polymer", help="Override default application name" )
    parser.add_option( "-V", "--wxversion", type="string", help="Select wxPython version, use help to list." )
    parser.add_option( "--sync", action="store_true", default=False, help="Do Sync." )
    return parser.parse_args()
        
