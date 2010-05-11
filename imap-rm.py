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

def mark( source ):
    summary_save = infotrope.imap.message.summary
    try:
        infotrope.imap.message.summary = []
        sm = infotrope.serverman.serverman( infotrope.serverman.cli_callback )
        
        src = sm[source]
        
        src_mbox = src.mailbox(source.mailbox)

        seqnos = range(1,len(src_mbox)+1,3)
        for x in range(len(seqnos)):
            uid = src_mbox.seqno( seqnos[x] )
            msg = src_mbox[uid]
            msg.flag( '\\Deleted' )
            sys.stdout.write( "\rMarked: %d%% - %d of %d       " % ( ( x*100 ) / len(seqnos), x, len(seqnos) ) )
            sys.stdout.flush()
    finally:
        infotrope.imap.message.summary = summary_save

if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser()
    opts, args = parser.parse_args()
    if len(args) < 1:
        print "Need source URL and destination URL"
    else:
        mark( infotrope.url.URL( args[0] ) )

