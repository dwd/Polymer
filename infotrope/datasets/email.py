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
import infotrope.url

class email(infotrope.datasets.base.dataset_class):
    def __init__( self, url ):
        infotrope.datasets.base.dataset_class.__init__( self, url )

    def get_search_criteria( self ):
        return 'AND NOT EQUAL "entry" "i;octet" "" NOT EQUAL "email.server.IMAP" "i;octet" NIL'

    def get_search_return( self ):
        return ['entry', 'email.check-interval', 'email.personality', 'email.server.IMAP', 'vendor.infotrope.*']

    def get_search_sort( self ):
        return ['entry', 'i;ascii-casemap']

    def factory( self, e ):
        if 'subdataset' in e:
            return folder
        return entry

    def new( self, t=None, entryname=None ):
        if t is None:
            t = 'entry'
        raw = {}
        if entryname is not None:
            raw = {'entry':{'value':entryname}}
        if t == 'folder':
            return folder( raw, self.url )
        return entry( raw, self.url )

class folder(infotrope.datasets.base.entry):
    def __init__( self, entry, url ):
        infotrope.datasets.base.entry.__init__( self, entry, url )

class entry(infotrope.datasets.base.entry):
    def __init__( self, entr, url ):
        infotrope.datasets.base.entry.__init__( self, entr, url )

    def decode( self, attr, raw ):
        if attr=='email.server.IMAP':
            u = infotrope.url.URL( raw )
            if u.username is None and 'vendor.infotrope.email.server.IMAP.username' in self:
                u.username = self['vendor.infotrope.email.server.IMAP.username']
            return u
        elif attr=='email.check-interval':
            return int( raw )
        elif attr=='email.personality':
            u = self.entry_url().add_relative( raw )
            if u.dataset_class!='personality':
                u = infotrope.url.URL( self.cont_url )
                u.path = '/personality/~/' + raw
                return infotrope.url.URL( u.asString() )
            return u
        else:
            return raw

    def encode( self, attr, polish ):
        raw = polish
        if attr=='email.server.IMAP':
            raw = infotrope.url.URL( polish ).asString()
        elif attr=='email.personality':
            if isinstance( polish, infotrope.url.URL_base ):
                if self.cont_url.root_user()==polish.root_user():
                    if polish.dataset_class == 'personality':
                        if polish.path.startswith('/byowner/'):
                            f = polish.path.index('personality/')
                            return polish.path[f+len('personality/'):]
                        elif polish.path.startswith('/personality/~/'):
                            return polish.path[len('/personality/~/'):]
                    return polish.path
        return raw

infotrope.datasets.base.register_dataset_type( 'email', email )
