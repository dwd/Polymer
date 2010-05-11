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

def flag( source, flag, which, verbose, unflag ):
    summary_save = infotrope.imap.message.summary
    try:
        infotrope.imap.message.summary = []
        sm = infotrope.serverman.serverman( infotrope.serverman.cli_callback )
        
        src = sm[source]
        
        src_mbox = src.mailbox(source.mailbox)
        if not src_mbox.flag_available( flag ):
            raise "Sorry, flag unavailable."

        uids = []
        for set in which:
            uids += src.decompose_set( set, src_mbox.seqno( len(src_mbox) ) )
        freezer = src_mbox.freeze()
        for x in range(len(uids)):
            uid = uids[x]
            if src_mbox.uid(uid) is None:
                continue
            msg = src_mbox[uid]
            if unflag:
                msg.unflag( flag )
            else:
                msg.flag( flag )
            if verbose and ( x % 100 ) == 0:
                sys.stdout.write( "\rFlagged: %d%% - %d of %d  " % ( ( x*100 ) / len(uids), x, len(uids) ) )
                sys.stdout.flush()
        if verbose:
            sys.stdout.write( "\nCommitting... " )
            sys.stdout.flush()
        freezer = None
        if verbose:
            sys.stdout.write( "Done.\n" )
            sys.stdout.flush()
    finally:
        infotrope.imap.message.summary = summary_save

if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser( "usage: \%prog [-f FLAG] [-v] imapurl message sets..." )
    parser.add_option( "-v", "--verbose", action='store_true', help="Be noisy", default=False )
    parser.add_option( "-f", "--flag", action='store', type="string", help="Use this flag instead of \\Flagged", default='\\Flagged' )
    parser.add_option( "-r", "--remove", action='store_true', help="Remove flag instead of adding", default=False )
    opts, args = parser.parse_args()
    if len(args) < 2:
        print "Need URL and at least one message set"
    else:
        flag( infotrope.url.URL( args[0] ), opts.flag, args[1:], opts.verbose, opts.remove )

