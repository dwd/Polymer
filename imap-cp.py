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
#!/usr/bin/python

import infotrope.imap
import infotrope.url
import infotrope.serverman
import sys

def copy( source, which, destination, flag ):
    summary_save = infotrope.imap.message.summary
    try:
        infotrope.imap.message.summary = []
        sm = infotrope.serverman.serverman( infotrope.serverman.cli_callback )
        
        src = sm[source]
        dest = sm[destination]
        
        src_mbox = src.mailbox(source.mailbox)
        dest_mi = dest.mbox_info(destination.mailbox)
        
        seqnos = range(1,len(src_mbox)+1)
        if which is not None:
            seqnos = src.decompose_set( which )
        for x in range(len(seqnos)):
            uid = src_mbox.seqno( seqnos[x] )
            msg = src_mbox[uid]
            flags = [ y for y in msg.flags() if y.lower()!='\\recent' ]
            if flag is not None:
                flags.append( flag )
            dest_mi.append( msg, flags )
            sys.stdout.write( "\rCopied: %d%% - %d of %d  " % ( ( x*100 ) / len(seqnos), x, len(seqnos) ) )
            sys.stdout.flush()
    finally:
        infotrope.imap.message.summary = summary_save

if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option( "-s", "--set", type="string", help="Copy only these messages" )
    parser.add_option( "-f", "--flag", type="string", help="Add this flag on APPEND", default=None )
    opts, args = parser.parse_args()
    if len(args) < 2:
        print "Need source URL and destination URL"
    else:
        copy( infotrope.url.URL( args[0] ), opts.set, infotrope.url.URL( args[1] ), opts.flag )

