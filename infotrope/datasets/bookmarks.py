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
import infotrope.datasets.base
import infotrope.serverman
import infotrope.url

class bookmarks(infotrope.datasets.base.dataset_class):
    def __init__( self, url ):
        infotrope.datasets.base.dataset_class.__init__( self, url )

    def get_search_sort( self ):
        return ['vendor.infotrope.sort-key', 'i;ascii-casemap', 'entry', 'i;ascii-casemap']

    def get_search_return( self ):
        return '*'

    def get_search_criteria( self ):
        return 'OR EQUAL "entry" "i;octet" "" OR NOT EQUAL "bookmarks.URL" "i;octet" NIL OR NOT EQUAL "subdataset" "i;octet" NIL NOT EQUAL "bookmarks.Type" "i;octet" NIL'

    def factory( self, e ):
        if 'bookmarks.Type' in e:
            type = e['bookmarks.Type']['value'].lower()
            if type=='folder':
                return folder
            elif type=='link':
                return link
            elif type=='separator':
                return entry
            elif type=='frameset':
                return entry
            elif type=='alias':
                return alias
        if 'subdataset' in e:
            return folder
        elif 'bookmarks.URL' in e:
            return link
        return entry

    def new( self, t=None, entryname=None ):
        if t is None:
            t = 'link'
        if entryname is None:
            import time
            import socket
            entryname = str(time.time()) + '@' + socket.gethostname()
        raw = {'entry':{'value':entryname}}
        if t == 'link':
            return link( raw, self.url )
        elif t=='folder':
            return folder( raw, self.url )
        elif t=='alias':
            return alias( raw, self.url )
        raise KeyError, "Unknown type, sorry."

class entry(infotrope.datasets.base.entry):
    def __init__( self, e, url ):
        infotrope.datasets.base.entry.__init__( self, e, url )
        self._setting = {}

    def decode( self, attr, raw ):
        if attr=='bookmarks.URL':
            return infotrope.url.URL( raw )
        elif attr=='bookmarks.Name' or attr=='bookmarks.Description' or attr=='bookmarks.Type':
            return raw.decode( 'utf-8' )
        elif attr=='bookmarks.Date.Added' or attr=='bookmarks.Last.Visited':
            return datetime.datetime( int(raw[0:4]), int(raw[4:6]), int(raw[6:8]), int(raw[8:10]), int(raw[10:12]), int(raw[12:14]) );
        else:
            return raw

    def encode( self, attr, polish ):
        raw = None
        if attr=='bookmarks.URL':
            if isinstance( polish, infotrope.url.URL_base ):
                raw = polish.asString()
            else:
                raw = polish
        else:
            raw = polish
        return raw

    def type( self ):
        return self['bookmarks.Type']
    
    def name( self ):
        name = self['bookmarks.Name']
        if name is not None:
            return name
        return self['entry']

    def description( self ):
        d = self['bookmarks.Description']
        if d is not None:
            return d
        d = self['bookmarks.URL']
        if d is not None:
            return d.asString()
        return ''

class link(entry):
    def __init__( self, e, url ):
        entry.__init__( self, e, url )

    def url( self ):
        return self['bookmarks.URL']

class folder(entry):
    def __init__( self, e, url ):
        entry.__init__( self, e, url )

class alias(entry):
    def __init__( self, e, url ):
        entry( e, url )

    def resolve( self ):
        return None

infotrope.datasets.base.register_dataset_type( 'bookmarks', bookmarks )
