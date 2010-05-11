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
import infotrope.serverman

class personality(infotrope.datasets.base.dataset_class):
    def __init__( self, url ):
        infotrope.datasets.base.dataset_class.__init__( self, url )

    def get_search_return( self ):
        return ['*']

    def get_search_criteria( self ):
        return 'NOT EQUAL "entry" "i;octet" ""'

    def factory( self, e ):
        if 'subdataset' in e:
            return folder
        return pers

    def new( self, t=None, entryname=None ):
        if t is None:
            t = 'entry'
        raw = {}
        if entryname is not None:
            raw = {'entry':{'value':entryname}}
        if t == 'folder':
            return folder( raw, self.url )
        return pers( raw, self.url )

class folder(infotrope.datasets.base.entry):
    def __init__( self, e, url ):
        infotrope.datasets.base.entry.__init__( self, e, url )

class pers(infotrope.datasets.base.entry):
    def __init__( self, e, url ):
        infotrope.datasets.base.entry.__init__( self, e, url )

    def decode( self, attr, raw ):
        if attr=='personality.Auto.Encrypt' or attr=='personality.Auto.Sign':
            return raw=='1'
        if attr in ['personality.Cert-DN','personality.File-Into.Local','personality.Real-Name','personality.Signature.Text']:
            return raw.decode('utf-8')
        if attr in ['personality.File-Into.IMAP','vendor.infotrope.personality.Drafts.IMAP']:
            return infotrope.url.URL( raw )

    def encode( self, attr, polish ):
        if attr in ['personality.Auto.Encrypt','personality.Auto.Sign']:
            return bool(attr)

infotrope.datasets.base.register_dataset_type( 'personality', personality )
