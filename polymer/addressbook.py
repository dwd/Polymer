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
import wx
import polymer.treenav
import wx.lib.scrolledpanel
import wx.stc
import infotrope.datasets.base
import infotrope.acap
import polymer.encode
import email.Utils

"""
ACAP Addressbook WX support stuff.

Has useful things like a Recipient Control, addressbook views and TreeNodes.
"""

class Listing(wx.ListCtrl):
    """Control to list the results of a search."""
    def __init__( self, parent, search ):
        wx.ListCtrl.__init__( self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL )
        self.InsertColumn( 0, "Type" )
        self.InsertColumn( 1, "Name" )
        self.InsertColumn( 2, "Email Address" )
        self.InsertColumn( 3, "Nickname" )
        self._search = search
        self._searches = {}
        self._count = 0;

    def set_count( self ):
        c = len( self._search )
        #print `c`,`self._count`
        if self._count!=c:
            self._count = c
            self.SetItemCount( c )

    def get_item( self, which ):
        search_which = which/25
        if search_which not in self._searches:
            self._search.wait()
            self._searches[search_which] = infotrope.acap.search( connection=self._search.connection(), base=self._search.context(), context='%s::%d' % ( self._search.context(), search_which ), sort=self._search.sort(), enum=True, ret=['*'], criteria='RANGE %d %d "%s"' % ( 25*search_which+1, 25*search_which+25, self._search.modtime() ) )
            self._searches[search_which].send()
            self._searches[search_which].wait()
        return self._searches[search_which][which%25]
        

    def get_item_name( self, which ):
        search_which = which/25
        if search_which not in self._searches:
            self._search.wait()
            self._searches[search_which] = infotrope.acap.search( connection=self._search.connection(), base=self._search.context(), context='%s::%d' % ( self._search.context(), search_which ), sort=self._search.sort(), enum=True, ret=['*'], criteria='RANGE %d %d "%s"' % ( 25*search_which+1, 25*search_which+25, self._search.modtime() ) )
            self._searches[search_which].send()
            self._searches[search_which].wait()
        return self._searches[search_which].entries()[which%25]
        

    def OnGetItemImage( self, which ):
        return -1

    def OnGetItemAttr( self, which ):
        return None
    
    def OnGetItemText( self, which, what ):
        if which >= len(self._search):
            return u'...'
        entry = self.get_item( which )
        txt = u''
        if what==0:
            if 'addressbook.References' in entry:
                txt = 'Reference'
            elif 'addressbook.List' in entry:
                txt = 'Group'
            elif 'addressbook.List.ID' in entry:
                txt = 'List'
            elif 'addressbook.Email' in entry:
                txt = 'Single'
        elif what==1:
            if 'addressbook.CommonName' in entry:
                txt = entry['addressbook.CommonName']['value'].decode( 'utf-8' )
        elif what==2:
            if 'addressbook.Email' in entry:
                txt = entry['addressbook.Email']['value'].decode( 'utf-8' )
        elif what==3:
            if 'addressbook.Alias' in entry:
                txt = entry['addressbook.Alias']['value'].decode( 'utf-8' )
        return polymer.encode.encode_ui(txt)
    
    def GetVisibleRange( self ):
        start = self.GetTopItem()
        end = self.GetCountPerPage()
        if end >= self.GetItemCount():
            end = self.GetItemCount()-1
        return start,end

    def notify_addto( self, entryname, pos ):
        self.set_count()
        start,end = self.GetVisibleRange()
        if pos <= end:
            if start <= pos:
                self.RefreshItems( pos, end )
            else:
                self.RefreshItems( start, end )

    def notify_removefrom( self, entryname, pos ):
        self.notify_addto( entryname, pos )

    def notify_change( self, entryname, oldpos, newpos ):
        pos = min( oldpos, newpos )
        self.notify_addto( entryname, pos )


ID_ADDR_UPDATE = wx.NewId()
ID_ADDR_RESET = wx.NewId()
ID_ADDR_MAILTO = wx.NewId()
ID_ADDR_DELETE = wx.NewId()

class PanelDisplayAddressbookEntry( wx.Notebook ):
    attributes = (
        ('Basic', (
        ("Name","addressbook.CommonName",),
        ("Organisation","addressbook.Organisation"),
        ("Alias","addressbook.Alias"),
        ("Email Address","addressbook.Email"),
        ("Description","addressbook.Description")
        )),
        ('Internet', (
        ("Home Page","addressbook.HomePage"),
        ("Header","addressbook.CommonName.MIME"),
        ("List ID","addressbook.List.ID"),
        ("Subscription","addressbook.List.Subscribe"),
        ("Unsubscription","addressbook.List.Unsubscribe"),
        ("List Help","addressbook.List.Help"),
        ("Subscribed","addressbook.Subscribed")
        )),
        ('Contact', (
        ("Title","addressbook.Prefix"),
        ("First Name","addressbook.GivenName"),
        ("Middle Name","addressbook.MiddleName"),
        ("Surname","addressbook.Surname"),
        ("Suffix","addressbook.Suffix"),
        ("Telephone","addressbook.Telephone"),
        ("Postal Address","addressbook.Postal")
        )),
        ('Information',(
        ("Comments","addressbook.Comment"),
        ("Job Title","addressbook.Title"),
        ("Locality","addressbook.Locality"),
        ("Country Code","addressbook.Country"),
        ("Preferred Language Code","addressbook.Language")
        ))
    )
    
    def __init__( self, parent ):
        wx.Notebook.__init__( self, parent, -1 )
        self._stuff = {}
        self._sizers = {}
        self._entry = None
        self._entryname = None
        wx.EVT_BUTTON( self, ID_ADDR_UPDATE, self.update )
        wx.EVT_BUTTON( self, ID_ADDR_RESET, self.cancel )
        wx.EVT_BUTTON( self, ID_ADDR_MAILTO, self.mailto )
        wx.EVT_BUTTON( self, ID_ADDR_DELETE, self.delete )

    def mailto( self, event ):
        import urllib
        wx.GetApp().process_url( 'mailto:' + urllib.quote( self._entry['addressbook.Email']['value'] ) )

    def delete( self, event ):
        acap = wx.GetApp().connection( self.GetParent().uri )
        p = self.GetParent().uri.path
        if p[-1] != '/':
            p += '/'
        acap.store( p + self._entryname, {'entry':None} )

    def update( self, event ):
        entry = {}
        for collection in self.attributes:
            for x,attr in collection[1]:
                tmp = polymer.encode.decode_ui( self._stuff[attr].GetValue() ).encode('utf-8')
                if tmp=='':
                    tmp = None
                if tmp is None:
                    if attr in self._entry:
                        entry[attr] = tmp
                else:
                    entry[attr] = tmp
        acap = wx.GetApp().connection( self.GetParent().uri )
        acap.store( self.GetParent().uri.path + self._entryname, entry )

    def cancel( self ):
        self.select( self._entry, self._entryname )

    def populate( self ):
        self.Show( False )
        for cat,attrs in self.attributes:
            p1 = wx.Panel( self, -1 )
            #p1 = wx.lib.scrolledpanel.ScrolledPanel( self, -1 )
            s2 = wx.BoxSizer( wx.VERTICAL )
            p2 = wx.lib.scrolledpanel.ScrolledPanel( p1, -1 )
            s = wx.FlexGridSizer( cols = 2, vgap = 5, hgap = 5 )
            for name,attr in attrs:
                s.Add( wx.StaticText( p2, -1, name ) )
                self._stuff[attr] = wx.TextCtrl( p2, -1, "Foooooooooooooooooooooooooooooooooooooooooooooo!" )
                s.Add( self._stuff[attr], 99, wx.EXPAND|wx.ALL )
            s.AddGrowableCol(1)
            p2.SetSizer( s )
            p2.SetAutoLayout(1)
            s.Fit(p2)
            s2.Add( p2, 1, wx.EXPAND|wx.ALL, border=5 )
            #s2.Add( wx.StaticLine( p1, -1 ), -1, wx.EXPAND )
            s3 = wx.BoxSizer( wx.HORIZONTAL )
            s3.Add( wx.Button( p1, ID_ADDR_DELETE, "Delete" ), 1, wx.GROW|wx.ALL, border=5 )
            s3.Add( wx.Button( p1, ID_ADDR_UPDATE, "Update" ), 1, wx.GROW|wx.ALL, border=5 )
            s3.Add( wx.Button( p1, ID_ADDR_RESET, "Cancel" ), 1, wx.GROW|wx.ALL, border=5 )
            s3.Add( wx.Button( p1, ID_ADDR_MAILTO, "Send Mail" ), 1, wx.GROW|wx.ALL, border=5 )
            s2.Add( s3 )
            self.AddPage( p1, cat, select=True )
            p1.SetSizer( s2 )
            p1.SetAutoLayout( 1 )
            s2.Fit( p1 )
            p2.SetupScrolling( scroll_x = False )
            self._sizers[ cat ] = s2
            p1.SetSize( (self.GetClientSize()[0]-10, -1) )
        self.SetSelection( 0 )
        self.Show( True )
        
    def select( self, entry, entryname ):
        #print "SELECT ADDR 2"
        self._entry = entry
        self._entryname = entryname
        if len(self._stuff)==0:
            self.populate()
        #print "Setting data."
        for attr in self._stuff:
            if attr in entry and entry[attr]['value'] is not None:
                self._stuff[attr].SetValue( polymer.encode.encode_ui( entry[attr]['value'].decode('utf-8') ) )
            else:
                self._stuff[attr].SetValue( '' )
        for s in self._sizers.values():
            s.Layout()
        self.Layout()


class PanelAddressbook(wx.SplitterWindow,polymer.treenav.NavPanel):
    def __init__( self, notebook, controller ):
        self._pagename = "Addresses in %s" % controller._name
        polymer.treenav.NavPanel.__init__( self, notebook, self._pagename, wx.SplitterWindow.__init__, controller )
        self.uri = controller.uri
        self._context = 'polymer.addr-listing.' + self.uri.path
        self._search = infotrope.acap.search( base=self.uri.path, context=self._context, ret=('*'), sort=("addressbook.CommonName","i;ascii-casemap","addressbook.Email","i;ascii-casemap"), criteria='AND NOT EQUAL "entry" "i;octet" "" OR OR OR NOT EQUAL "addressbook.List" "i;octet" NIL NOT EQUAL "addressbook.Email" "i;octet" NIL NOT EQUAL "addressbook.Reference" "i;octet" NIL NOT EQUAL "addressbook.List.ID" "i;octet" NIL', enum = True, notify = self, connection=wx.GetApp().connection( self.uri ), limit=0 )
        self._search.send()
        wx.GetApp().status( 'Fetching addressbook entries...' )
        self._listing = Listing( self, self._search )
        self._selected = None
        self._display = PanelDisplayAddressbookEntry( self )
        self.SplitHorizontally( self._listing, self._display, self.GetParent().GetSize()[1]/4 )
        wx.EVT_LIST_ITEM_SELECTED( self._listing, -1, self.select )

    def notify_addto( self, entryname, pos ):
        wx.GetApp().status( 'New addressbook entry...' )
        self._listing.notify_addto( entryname, pos )

    def notify_removefrom( self, entryname, pos ):
        self._listing.notify_removefrom( entryname, pos )
        if self._selected is not None:
            if self._selected==entryname:
                print "Something for removed current entry."

    def notify_change( self, entryname, oldpos, newpos ):
        self._listing.notify_change( entryname, oldpos, newpos )
        if self._selected is not None:
            if self._selected==entryname:
                print "Something for changed current entry."

    def select( self, event ):
        #print "SELECT ADDR"
        idx = event.GetIndex()
        self._selected = self._listing.get_item_name( idx )
        self._display.select( self._listing.get_item( idx ), self._selected )

    def notify_complete( self, status ):
        self._listing.set_count()
        wx.GetApp().status( 'Addressbook load complete: '+status )

class TreeNodeAddressbook(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, uri=None, entry=None ):
        name = 'Addressbooks'
        icon = 'icons/address/adbook.png'
        if entry is not None:
            name = entry.displayname()
            if isinstance( entry, infotrope.datasets.addressbook.group ):
                icon = 'icons/address/bclist.png'
        polymer.treenav.TreeNode.__init__( self, tree, pid, name, images={wx.TreeItemIcon_Normal:icon} )
        self._pending = []
        self._nodes = {}
        self.uri = uri
        self._panel = None
        if self.uri is None:
            self.uri = infotrope.url.URL( wx.GetApp().home )
            self.uri.path = '/addressbook/~/'
            self.uri = infotrope.url.URL( self.uri.asString() )
        #print "Addressbook context is ",`self._context`
        self._tried = 0
        self.search = None
        self.do_search()

    def do_search( self ):
        import infotrope.datasets.addressbook
        wx.GetApp().status( 'Scanning for addressbooks at '+self.uri.asString() )
        self.search = infotrope.datasets.base.get_dataset( self.uri )
        self.search.add_notify( self )
    
    def process_pending( self ):
        #print "Processing, id is",`self._id`
        if self._id is not None:
            pending = self._pending
            self._pending = []
            for entry in pending:
                #print "Adding entry ", entry
                e = self.search[entry]
                node = TreeNodeAddressbook( self.tree(), self._id, e.subdataset_url(), self.search[entry] )
                self._nodes[entry] = node
            self.tree().Refresh()
    
    def set_id( self, id ):
        self._id = id

    def notify_addto( self, entryname ):
        #print 'ADDR ADDTO'
        self._pending.append( entryname )
        self.process_pending()

    def notify_removefrom( self, entryname ):
        if entryname in self._pending:
            self._pending.remove( entryname )
        if entryname in self._nodes:
            self._nodes[entryname].Delete()
            del self._nodes[entryname]
            
    def notify_change( self, entryname ):
        self.notify_removefrom( entryname )
        self.notify_addto( entryname )

    def notify_complete( self, status ):
        #print 'ADDR COMPLETE'
        if status!='ok':
            if self._tried==0:
                # Oh dear, probably doesn't exist.
                self._tried = 1
                if self.uri.path=='/addressbook/~/':
                    wx.GetApp().status( 'Creating default addressbook.' )
                    wx.GetApp().connection( self.uri ).send( 'STORE ("/addressbook/~/" "vendor.infotrope.polymer.search" "1")' )
                    self.do_search()
        
    def try_expand( self, event ):
        return True

    def get_panel( self ):
        return PanelAddressbook( self.tree().notebook(), self )

class ChooseRecipients(wx.Dialog):
    ''' Dialog to help the user select between multiple possible recipient expansions. '''
    def __init__( self, parent, id, field, search ):
        wx.Dialog.__init__( self, parent, id, "Choose Recipient - Infotrope Polymer", style = wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER )
        self._field = field
        self._search = search
        p = wx.Panel( self, -1 )
        self._sizer = wx.BoxSizer( wx.VERTICAL )
        self._sizer.Add( wx.StaticText( p, -1, "Multiple matches were found for %s" % ( `self._field` ) ), 0,  wx.ALL, border=5 )
        self._entries = wx.ListCtrl( p, -1, style=wx.LC_REPORT )
        self._entries.InsertColumn( 0, "Name" )
        self._entries.InsertColumn( 1, "Email Address" )
        self._entries.InsertColumn( 2, "Alias" )
        self._entries.InsertColumn( 3, "Source" )
        foo = 0
        for en in self._search.entries():
            source = en
            slash = source.rfind( '/' )
            if slash!=-1:
                source = source[0:slash]
            self._entries.InsertStringItem( foo, source )
            entry = self._search.get_entry( en )
            if 'addressbook.CommonName' in entry:
                self._entries.SetStringItem( foo, 0, polymer.encode.encode_ui( entry['addressbook.CommonName']['value'].decode('utf-8') ) )
            else:
                self._entries.SetStringItem( foo, 0, " - " )
            if 'addressbook.Email' in entry:
                self._entries.SetStringItem( foo, 1, polymer.encode.encode_ui( entry['addressbook.Email']['value'].decode('utf-8') ) )
            else:
                self._entries.SetStringItem( foo, 1, ' - ' )
            if 'addressbook.Alias' in entry:
                self._entries.SetStringItem( foo, 2, polymer.encode.encode_ui( entry['addressbook.Alias']['value'].decode('utf-8') ) )
            else:
                self._entries.SetStringItem( foo, 2, ' - ' )
            self._entries.SetStringItem( foo, 3, polymer.encode.encode_ui(source) )
            foo += 1
        for i in range(4):
            self._entries.SetColumnWidth( i, wx.LIST_AUTOSIZE )
        self._sizer.Add( self._entries, 1, wx.EXPAND|wx.GROW|wx.ALL, border=5 )
        s2 = wx.BoxSizer( wx.HORIZONTAL )
        self._set_alias = wx.CheckBox( p, -1, "Set alias on selected entry to:" )
        self._set_alias.SetValue( False )
        s2.Add( self._set_alias, 0, wx.ALIGN_CENTER|wx.ALL, border=5 )
        self._alias = wx.TextCtrl( p, -1, self._field )
        s2.Add( self._alias, 1, wx.ALIGN_CENTER|wx.GROW|wx.EXPAND|wx.ALL, border=5 )
        s2.Add( wx.Button( p, wx.ID_OK, "OK" ), 0, wx.ALIGN_CENTER|wx.ALL, border=5 )
        #self._sizer.Add( wx.Button( self, wx.ID_OK, "OK" ), 0, wx.ALL, border=5 )
        self._sizer.Add( s2, 0, wx.GROW|wx.EXPAND )
        wx.EVT_LIST_ITEM_SELECTED( self._entries, -1, self.select )
        wx.EVT_BUTTON( self, wx.ID_OK, self.okay )
        p.SetSizer( self._sizer )
        p.SetAutoLayout( 1 )
        self._sizer.Fit( p )
        self.index = None

    def select( self, event ):
        self.index = event.GetIndex()
        #print "Set which."

    def okay( self, event ):
        if self.index is None:
            self.SetReturnCode( wx.ID_CANCEL )
            self.EndModal( wx.ID_CANCEL )
            return
        #print "Okay, valid selection, processing."
        if self._set_alias.GetValue():
            #print "Oh, wants to set the alias."
            alias = polymer.encode.decode_ui( self._alias.GetValue() )
            en = self._search.entries()[self.index]
            #print "Setting alias of %s to %s" % ( en, alias )
            self._search.connection().store( en, {'addressbook.Alias': alias.encode('utf8')} )
        self.SetReturnCode( wx.ID_OK )
        self.EndModal( wx.ID_OK )

class Recipient:
    def __init__( self, parent, field=None, email=None, addressbook_entry=None, addressbook_entry_path=None ):
        ''' Construct a recipient. This might be constructed around something the user entered, or a specific addressbook entry. '''
        self._field = None
        if field is not None and field!='':
            self._field = field.encode( 'utf-8' )
        self._addressbook_entry = addressbook_entry
        self._addressbook_entry_path = addressbook_entry_path
        self._parent = parent
        self._email_address = email
        
    def check_resolved(self, frame):
        if self._parent is not None:
            return True
        self._parent = frame
        if not self._addressbook_entry:
            return False
        return True
    
    def check_for_address(self):
        #print "Check for address"
        if self._field is not None:
            if self._field.find('news:')==0:
                self._email_address = self._field
                return None
        if self._email_address is None:
            if self._field is not None:
                if self._field.find('@')!=-1:
                    #print "Entry field contains valid email address, using it."
                    if self._field.find(' ')!=-1:
                        #print "Entry contains space, assuming real entry and parsing."
                        tmp = email.Utils.parseaddr( self._field )
                        #print `tmp`
                        if len(tmp[0]) == 0:
                            #print "Ah, not valid RFC2822. Ho hum."
                            atpos = self._field.rfind('@')
                            post_space = self._field.find(' ',atpos)
                            pre_space = self._field.rfind(' ',0,atpos)
                            if pre_space == -1:
                                pre_space = 0
                            if post_space == -1:
                                post_space = len(self._field)
                            self._email_address = self._field[pre_space:post_space].strip(' <>')
                            self._field = self._field[0:pre_space].strip() + ' ' + self._field[post_space:].strip()
                            self._field = self._field.strip()
                            tmp = (self._field, self._email_address)
                        self._email_address = tmp[1]
                        self._field = tmp[0]
                        if self._field=='':
                            self._field = None
                    else:
                        self._email_address = self._field
                        self._field = None
        
    def addressbook_entry( self ):
        if self._addressbook_entry is None:
            #print "Finding ACAP entry..."
            # Do we have a valid email address?
            self.check_for_address()
            if wx.GetApp().home not in wx.GetApp().sm:
                try:
                    acap = wx.GetApp().sm[wx.GetApp().home]
                    tmp = wx.GetApp().acap_home()
                except:
                    return None
            if self._email_address is not None:
                #print "Have valid supplied email address.",`self._email_address`
                # We have a supplied email address, we assume this is correct.
                search = infotrope.acap.search( 'SEARCH "/addressbook/~/" DEPTH 0 RETURN ("entry" "addressbook.*") EQUAL "addressbook.Email" "i;octet" "%s"' % ( self._email_address ), connection=wx.GetApp().acap_home() )
                t,r,s = search.wait()
                #print "Email search complete with ",`t`,`r`,`s`,len(search)
                if len(search)>0:
                    #print "Got results. Hoorah."
                    self._addressbook_entry = search[0]
                    self._addressbook_entry_path = search.entries()[0]
                    #print "First result is ",`self._addressbook_entry`
                    return self._addressbook_entry
                #print "Nothing found."
                self._addressbook_entry = False
                return None
            # Best find it.
            # Look for aliases matching what the user entered.
            search = infotrope.acap.search( 'SEARCH "/addressbook/~/" DEPTH 0 RETURN ("entry" "addressbook.*") OR EQUAL "addressbook.Alias" "i;octet" "%s" EQUAL "addressbook.Alias" "i;ascii-casemap" "%s"' % ( self._field, self._field ), connection=wx.GetApp().acap_home() )
            search.wait()
            if len(search)>0:
                self._addressbook_entry = search[0]
                self._addressbook_entry_path = search.entries()[0]
                return self._addressbook_entry
            # Look for names matching what the user entered.
            add_bits = ""
            if self._parent is None:
                add_bits = " LIMIT 1 1"
            search = infotrope.acap.search( 'SEARCH "/addressbook/~/" DEPTH 0%s RETURN ("entry" "addressbook.*") OR OR SUBSTRING "addressbook.CommonName" "i;octet" "%s" SUBSTRING "addressbook.CommonName" "i;ascii-casemap" "%s" OR SUBSTRING "addressbook.AlternateNames" "i;ascii-casemap" "%s" SUBSTRING "addressbook.Email" "i;ascii-casemap" "%s"' % ( add_bits, self._field, self._field, self._field, self._field ), connection=wx.GetApp().acap_home() )
            search.wait()
            if len(search)==0:
                self._addressbook_entry = False
                return None
            if len(search)==1:
                self._addressbook_entry = search[0]
                self._addressbook_entry_path = search.entries()[0]
                return self._addressbook_entry
            if len(search)>1:
                if self._parent is not None:
                    dlg = ChooseRecipients( self._parent, -1, self._field, search )
                if self._parent is None or wx.ID_OK != dlg.ShowModal():
                    self._addressbook_entry = False
                    return
                self._addressbook_entry = search[dlg.index]
                self._addressbook_entry_path = search.entries()[dlg.index]
        return self._addressbook_entry or None

    def display( self ):
        entry = self.addressbook_entry()
        if not entry:
            if self._field is None:
                return self._email_address.decode('utf-8')
            return self._field.decode('utf-8')
        else:
            if 'addressbook.CommonName' in entry:
                return entry['addressbook.CommonName']['value'].decode('utf-8')
            elif 'addressbook.Alias' in entry:
                return entry['addressbook.Alias']['value'].decode('utf-8')
            elif 'addressbook.Email' in entry:
                return entry['addressbook.Email']['value'].decode('utf-8')
        return u'<< Unknown >>'

    def header( self ):
        entry = self.addressbook_entry()
        if not entry:
            if self._field is None:
                return ['<' + self._email_address.encode('us-ascii') + '>']
            else:
                return [email.Utils.formataddr( (self._field, self._email_address) )]
        else:
            if 'addressbook.Expand.Complete' in entry:
                return entry['addressbook.Expand.Complete']['value'].split('\r\n')
            else:
                if 'addressbook.List' in entry:
                    s = infotrope.acap.search( 'SEARCH "%s" DEPTH 0 RETURN ("entry" "addressbook.*") OR NOT EQUAL "addressbook.List" "i;octet" NIL NOT EQUAL "addressbook.Email" "i;octet" NIL' % ( self._addressbook_entry_path ), connection=wx.GetApp().acap_home() )
                    s.send()
                    t,r,s = s.wait()
                    rcpts = []
                    if r.lower()=='ok':
                        for x in s.entries():
                            rcpts.append( Recipient( addressbook_entry=s[x], addressbook_entry_path=x ) )
                    hdr = []
                    for x in rcpts:
                        hdr += rcpts.header()
                    return hdr
                if 'addressbook.CommonName.MIME' in entry:
                    return [entry['addressbook.CommonName.MIME']['value'] + ' <' + entry['addressbook.Email']['value'] + '>']
                elif 'addressbook.CommonName' in entry:
                    return [email.Utils.formataddr( (entry['addressbook.CommonName']['value'].decode('utf-8'), entry['addressbook.Email']['value']) )]
                else:
                    return [entry['addressbook.Email']]
        return 'Undisclosed-recipients:;'

    def email_addresses( self, nosearch=False ):
        if self._email_address:
            return [self._email_address]
        if nosearch:
            self.check_for_address()
            if self._email_address:
                return [self._email_address]
            if self._addressbook_entry:
                entry = self._addressbook_entry
            else:
                return None
        else:
            entry = self.addressbook_entry()
        if entry:
            if 'addressbook.Expand.Address' in entry:
                return entry['addressbook.Expand.Address']['value'].split('\r\n')
            elif 'addressbook.List' in entry:
                s = infotrope.acap.search( 'SEARCH "%s" DEPTH 0 RETURN ("entry" "addressbook.*") OR NOT EQUAL "addressbook.List" "i;octet" NIL NOT EQUAL "addressbook.Email" "i;octet" NIL' % ( self._addressbook_entry_path ), connection=wx.GetApp().acap_home() )
                s.send()
                t,r,s = s.wait()
                rcpts = []
                if r.lower()=='ok':
                    for x in s.entries():
                        rcpts.append( Recipient( addressbook_entry=s[x], addressbook_entry_path=x ) )
                hdr = []
                for x in rcpts:
                    hdr += rcpts.email_addresses()
                return hdr
            elif 'addressbook.Email' in entry:
                return [entry['addressbook.Email']['value']]
        return None

class RecipientCtrl(wx.TextCtrl):
    def __init__( self, parent, id, value=None ):
        self._value = value
        self._saved_txt = ''
        self._saved_frame = False
        wx.TextCtrl.__init__( self, parent, id, style=wx.SUNKEN_BORDER )
        self.resolved()
        self.Bind(wx.EVT_KILL_FOCUS, self.blur)
        self._checking = False
        self.Bind(wx.EVT_TEXT, self.check)
        
    def blur(self, event):
        self.resolve(None)
        
    def check(self, *args):
        if self._checking == False:
            try:
                self._checking = True
                self.SetOwnBackgroundColour('#FFFFE0')
                self.resolved(False)
                if self.GetValue() != '':
                    self.GetGrandParent().add_header(self.GetParent(), self)
            finally:
                self._checking = False

    def resolve( self, frame=None ):
        ''' Turn a comma delimited list of recipients into a list of Recipients. '''
        #print "Resolving: ",`frame`
        mod = self.IsModified()
        if self.GetValue() == '':
            self._value = None
            self._saved_txt = ''
            self.SetOwnBackgroundColour('#FFFFFF')
            return
        self.SetOwnBackgroundColour('#FFFFE0')
        if self._value is None or self.GetValue() != self._saved_txt or \
                (frame is not None and self._saved_frame == False):
            #print "-> Trying new resolution."
            self._saved_txt = self.GetValue()
            self._value = Recipient(frame, field=self._saved_txt)
            if frame is not None:
                self._saved_frame = True
        self.resolved()
        if mod:
            self.MarkDirty()
        return self._value
    
    def SetSaved(self):
        self.SetValue(self.GetValue())

    def GetHeader( self ):
        ''' Get the header value '''
        self.resolve()
        return self._value.header()

    def GetRecipient( self ):
        return self.resolve()
    
    def resolved( self, update=True ):
        if self._value is not None:
            if self._value.email_addresses():
                if update:
                    self._saved_txt = u"%s <%s>" % (self._value.display(), ', '.join(self._value.email_addresses()))
                    self.SetValue(self._saved_txt)
                self.SetOwnBackgroundColour('#E0FFE0')
            else:
                self.SetOwnBackgroundColour('#FFE0E0')

class Address:
    CAT = 0
    NAME = 1
    URL = 2
    def __init__(self, ctrl, text):
        self.__ctrl = weakref.ref(ctrl)

    def get_text(self, which):
        if which == Address.CAT:
            return 'To'
        if which == Address.NAME:
            return 'Dave Cridland'
        if which == Address.URL:
            return 'mailto:dave@cridland.net'

class AddressCtrl(wx.ListCtrl):
    def __init__(self, parent):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_EDIT_LABELS|wx.LC_NO_HEADER)
        self.__length = 0
        self.__recipients = []
        self.setup_cols()
        self.SetItemCount(self.__length + 1)
        wx.EVT_LIST_BEGIN_LABEL_EDIT(self, -1, self.begin_edit)
        wx.EVT_LIST_END_LABEL_EDIT(self, -1, self.end_edit)

    def setup_cols(self):
        self.InsertColumn(0, " ", format=wx.LIST_FORMAT_RIGHT)
        self.InsertColumn(1, "Name")
        self.InsertColumn(2, "Address")

    def OnGetItemText(self, row, col):
        if row >= self.__length:
            return "Foo"
        return self.__recipients[row].get_text(col)

    def OnGetItemAttr(self, *args):
        return None

    def OnGetItemImage(self, *args):
        return None

    def begin_edit(self, event):
        self.DeleteColumn(0)
        self.DeleteColumn(2)
        event.Skip()
        #print `event.IsEditCancelled()`

    def end_edit(self, event):
        #print `event.IsEditCancelled()`
        self.setup_cols()
        
