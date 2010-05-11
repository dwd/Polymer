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

class addressbook_base(infotrope.datasets.base.dataset_class):
    def __init__( self, url ):
        infotrope.datasets.base.dataset_class.__init__( self, url )

    def factory( self, e ):
        if 'addressbook.Reference' in e:
            if e['addressbook.Reference']['value'] is not None:
                try:
                    u = infotrope.url.URL( entry['addressbook.Reference']['value'] )
                    if u.scheme == 'acap':
                        return acap_reference
                except:
                    return acap_reference
                return reference
        if 'addressbook.List' in e:
            if e['addressbook.List']['value'] is not None:
                return group
        return entry

class listing(addressbook_base):
    def __init__( self, url ):
        addressbook_base.__init__( self, url )

    def foo_do_search_local( self ):
        return infotrope.acap.search( 'SEARCH "%s" MAKECONTEXT NOTIFY ENUMERATE "infotrope.addressbook.listing.%s" RETURN ("*") SORT ("addressbook.CommonName" "i;ascii-casemap" "entry" "i;octet") NOT EQUAL "entry" "i;octet" ""' % ( self.url.path, self.url.path ), context="infotrope.addressbook.listing."+self.url.path, connection=infotrope.serverman.get_serverman()[self.url], notify=self )

    def get_search_return( self ):
        return '*'

class search(addressbook_base):
    def __init__( self, url, name=None, email=None ):
        self.name = name
        self.email = email
        if name is None and email is None:
            raise "Must supply name or email."
        addressbook_base.__init__( self, url )

    def foo_do_search_local( self ):
        if self.email is not None:
            return infotrope.acap.search( 'SEARCH "%s" MAKECONTEXT NOTIFY ENUMERATE "infotrope.addressbook.search.%s" RETURN ("*") AND NOT EQUAL "entry" "i;octet" "" OR PREFIX "addressbook.Email" "i;ascii-casemap" "%s" PREFIX "addressbook.EmailOther" "i;ascii-casemap" "%s"' % ( self.url.path, self.url.path, self.email, self.email ), context="infotrope.addressbook.search."+self.url.path, connection=infotrope.serverman.get_serverman()[self.url], notify=self )

class addressbooks(addressbook_base):
    def __init__( self, url ):
        addressbook_base.__init__( self, url )

    def foo_do_search_local( self ):
        return infotrope.acap.search( 'SEARCH "%s" MAKECONTEXT NOTIFY "infotrope.addressbook.addressbooks.%s" RETURN ("entry" "subdataset" "addressbook.*") NOT EQUAL "subdataset" "i;octet" NIL' % ( self.url.path, self.url.path ), context="infotrope.addressbook.addressbooks.%s" % self.url.path, connection=infotrope.serverman.get_serverman()[self.url], notify=self )

    def get_search_return( self ):
        return ['entry','subdataset','addressbook.*']

    def get_search_criteria( self ):
        return 'NOT EQUAL "subdataset" "i;octet" NIL'

def val_desc( s, chset ):
    'Split an ACAP addressbook value/description string into the value and descriptions.'
    sp = s.split('\0')
    return (sp[0].decode(chset),tuple([x.decode('utf-8').lower() for x in sp[1:]]))

class entry(infotrope.datasets.base.entry):
    _utf8_attrs = ['addressbook.CommonName','addressbook.Surname','addressbook.GivenName','addressbook.MiddleName','addressbook.Prefix','addressbook.Suffix','addressbook.Alias','addressbook.Comment','addressbook.Description','addressbook.Organization','addressbook.Title','addressbook.Locality','addressbook.Country']
    _valdesc_utf8_attrs = ['addressbook.AlternateNames','addressbook.Telephone','addressbook.TelephoneOther','addressbook.Postal','addressbook.PostalOther']
    _valdesc_ascii_attrs = ['addressbook.EmailOther']
    _uri_attrs = ['addressbook.Reference','addressbook.List.Subscribe','addressbook.List.Unsubscribe','addressbook.List.Help','addressbook.HomePage','addressbook.HomePageOther']
    _ascii_attrs = ['addressbook.CommonName.MIME','addressbook.Email']
    _bool_attrs = ['addressbook.List','addressbook.Subscribed']
    _crlf_ascii_attrs = ['addressbook.Expand.Address','addressbook.Expand.Complete']
    _lang_attrs = ['addressbook.Language','addressbook.LanguageOther']
    
    def __init__( self, e, url ):
        infotrope.datasets.base.entry.__init__( self, e, url )

    def decode( self, attr, raw ):
        if attr in self._utf8_attrs:
            return raw.decode( 'utf-8' )
        if attr in self._ascii_attrs:
            return raw.decode( 'us-ascii' )
        if attr in self._valdesc_utf8_attrs:
            return val_desc( raw, 'utf-8' )
        if attr in self._valdesc_ascii_attrs:
            return val_desc( raw, 'usascii' )
        if attr in self._bool_attrs:
            return '1'==raw
        if attr in self._crlf_ascii_attrs:
            return raw.split('\r\n')
        if attr in self._uri_attrs:
            return infotrope.url.URL( raw )
        if attr in self._lang_attrs:
            return raw
        return raw

    def encode( self, attr, polish ):
        if attr in self._utf8_attrs:
            return polish.encode( 'utf-8' )
        if attr in self._ascii_attrs:
            return polish.encode( 'us-ascii' )
        if attr in self._valdesc_utf8_attrs:
            return '\0'.join( [ polish[0].encode( 'utf-8' ) ] + polish[1] )
        if attr in self._valdesc_ascii_attrs:
            return '\0'.join( [ polish[0].encode( 'usascii' ) ] + polish[1] )
        if attr in self._bool_attrs:
            if polish:
                return "1"
            return None
        if attr in self._crlf_ascii_attrs:
            return '\r\n'.join( polish )
        if attr in self._lang_attrs:
            return polish
        if attr in self._uri_attrs:
            if isinstance( polish, str ):
                return polish
            if isinstance( polish, unicode ):
                return polish.encode('usascii')
            return polish.asString()
        return polish

    def email( self, crit=None ):
        emails = []
        if self['addressbook.Email'] is not None:
            emails.append( self['addressbook.Email'] )
        if self['addressbook.EmailOther'] is not None:
            emails += self['addressbook.EmailOther']
        if len(emails)==0:
            return None
        if crit is None:
            return emails[0]
        for e in emails:
            if crit.lower() in e[1]:
                return e
        return None

    def displayname( self ):
        if self['addressbook.CommonName'] is not None:
            return self['addressbook.CommonName']
        if self['addressbook.Alias'] is not None:
            return self['addressbook.Alias']
        return self['entry']

class acap_reference( entry ):
    def __init__( self, e, url ):
        entry.__init__( self, e, url )

class reference( entry ):
    def __init__( self, e, url ):
        entry.__init__( self, e, url )

class group( entry ):
    def __init__( self, e, url ):
        entry.__init__( self, e, url )

infotrope.datasets.base.register_dataset_type( 'addressbook', addressbooks )
