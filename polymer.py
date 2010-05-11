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

"""
Infotrope Polymer

Main 'executable' script.

Call with --help for possible arguments.
"""

import sys
sys.path = ['/usr/local/lib/python2.6/dist-packages/', '/usr/local/lib/python2.6/site-packages/'] + sys.path

__revision__ = '$revision:$'

def main():
    """
    Create application object, execute main loop.
    """
    import polymer.app
    app = polymer.app.MyApp( redirect=False )
    app.MainLoop()

def run():
    """
    A wrapper around main(), which handles profiling if requested.
    """
    import polymer.options
    opts = polymer.options.handle_options()[0]
    if opts.wxversion is not None:
        import wxversion
        if opts.wxversion == 'help':
            for x in wxversion.getInstalled():
                print "Installed:", x
            import sys
            sys.exit()
        else:
            wxversion.select( opts.wxversion )
    if opts.profile:
        import profile
        profile.run( 'main()', opts.profile )
        import pstats
        prof = pstats.Stats( opts.profile )
        prof.sort_stats( 'cumulative', 'calls' ).print_stats( 50 )
    else:
        main()
    return opts.debug

if __name__ == '__main__':
    if run():
        import gc
        gc.set_debug( gc.DEBUG_LEAK )
        gc.collect()

