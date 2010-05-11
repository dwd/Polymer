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
import polymer.imap
import infotrope.modutf7
import infotrope.base
import polymer.dialogs
import polymer.sieve
import polymer.progress

SIEVE_ATTR = 'vendor.infotrope.email.server.managesieve'

class TreeNodeNamespace(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, server, namespace, scope, name, sep ):
        polymer.treenav.TreeNode.__init__( self, tree, pid, name, True, {wx.TreeItemIcon_Normal:'icons/tree/subfolder.png'} )
        self.namespace = namespace
        self._server = server
        self._sep = sep

    def try_expand( self, event=None ):
        self._server.mailbox_listing( self.namespace, self._id, namespace_processing=True )
        self.update( True )
        return True

class ServerProps(polymer.dialogs.Base):
    _cap_desc = {
        'IMAP4': ("Base version of IMAP4",True,'IMAP4REV1'),
        'IMAP4REV1' : ("Latest version of IMAP",True,None),
        'NAMESPACE': ("Better discovery of mailboxes",True,None),
        'ACL': ("Basic ACL extension",True,'ACL2'),
        'RIGHTS': ("Extra rights for ACLs supported",True,'ACL2'),
        'QUOTA': ("Quota support",False,None),
        'CHILDREN': ("Child mailbox discovery",True,'LIST-EXTENDED'),
        'LITERAL+': ("Faster sending of large data",True,None),
        'UIDPLUS': ("Better synchronization",True,None),
        'BINARY': ("Better attachment handling",True,None),
        'IDLE': ("Push notifications",True,None),
        'ID': ("Server identification",True,None),
        'THREAD': ("Server-side threading",False,None),
        'MULTIAPPEND': ("Multiple message uploading",True,None),
        'UNSELECT': ("Deselection without close",True,None),
        'SORT': ("Server-side sorting",False,None),
        'LIST-EXTENDED': ("Advanced mailbox listing",True,None),
        'ANNOTATEMORE': ("Mailbox level metadata",False,None),
        'ANNOTATE': ("Message level metadata",False,None),
        'LOGINDISABLED': ("No plaintext logins",True,True),
        'AUTH': ("Secure logins and sessions",True,True),
        'STARTTLS': ("Encrypted sessions",True,None),
        'ACL2': ("Advanced ACL support",True,None),
        'SASL-IR': ("Faster authentication",True,None),
        'ESEARCH': ("Advanced searching",True,None),
        'MAILBOX-REFERRALS': ("Server clustering",True,True),
        'POSTADDRESS': ("FCC optimization",True,None),
        'CATENATE': ("Server-side message assembly",True,None),
        'URLAUTH': ("Forward-with-download optimization",True,None),
        'LIST-SUBSCRIBED': ("Older subscription discovery",True,'LIST-EXTENDED'),
        'LISTEXT': ("Older advanced mailbox listing",True,'LIST-EXTENDED'),
        'CONDSTORE': ("Message metadata delta",True,None),
        'NO_ATOMIC_RENAME': ("Cyrus IMAPd (or derivative) limitation",False,False),
        'COMPRESS': ("Compressed sessions",True,None),
        'ENABLE': ("Advanced extension support",True,None),
        'QRESYNC': ("Single RTT sync",True,None),
        'WITHIN': ("Time Window SEARCH keys",True,None),
        'CONTEXT': ("Updating search results",True,None),
        }
    def __init__( self, parent, banner, server_id, caps, bandwidth ):
        self._server_id = server_id
        self._banner = banner
        self._caps = caps
        self._bandwidth = bandwidth
        polymer.dialogs.Base.__init__( self, parent.tree(), "Properties for " + parent.name() )

    def add_prompts( self, p ):
        if self._server_id:
            self.AddPreamble( p, "The server identifies itself and report capabilities as follows:" )
            self.AddGeneric2( p, "Server Identification", wx.StaticText( p, -1, "" ) )
            if 'vendor' in self._server_id:
                self.AddGeneric2( p, " - Vendor", wx.StaticText( p, -1, self._server_id['vendor'] ) )
            self.AddGeneric2( p, " - Name", wx.StaticText( p, -1, self._server_id['name'] ) )
            self.AddGeneric2( p, " - Version", wx.StaticText( p, -1, self._server_id['version'] ) )
        else:    
            self.AddPreamble( p, "The server's banner was '%s', it does not identify itself." % self._banner )
        bw = self._bandwidth
        if bw is None:
            bw = 'Unknown'
        else:
            mod = ''
            if bw > 10000:
                mod = 'k'
                bw /= 1000
                if bw > 1000:
                    mod = 'M'
                    bw /= 1000
            bw = '%.1f%sbps' % ( bw, mod )
        self.AddGeneric2( p, "Bandwidth estimate", wx.StaticText( p, -1, bw ) )
        l = wx.ListCtrl(p, -1, style=wx.LC_REPORT)
        l.InsertColumn(0, "Capability")
        l.InsertColumn(1, "Description")
        l.InsertColumn(2, "Status")
        count = 0
        caps = []
        ck = self._cap_desc.keys()
        ck.sort()
        for cap in ck:
            desc = self._cap_desc[cap]
            if cap not in self._caps:
                for c in infotrope.imap.extension_aliases.get(cap,[]):
                    if c in self._caps:
                        cap = c
            caps.append(cap)
            bgcolour = None
            l.InsertStringItem(count, cap)
            l.SetStringItem(count, 0, cap)
            l.SetStringItem(count, 1, desc[0])
            status = None
            if desc[1]: # Polymer supported
                if cap in self._caps: # Both
                    bgcolour = wx.GREEN
                    status = 'Both'
                elif desc[2]:
                    if desc[2] is True:
                        status = 'Polymer (non-critical)'
                    elif desc[2] in self._caps:
                        status = 'Polymer (using %s)' % desc[2]
                    else:
                        status = 'Polymer (obsoleted by %s)' % desc[2]
                        bgcolour = wx.RED
                else:
                    status = 'Polymer'
                    bgcolour = wx.RED
            elif cap in self._caps:
                if desc[2] is not False:
                    status = 'Server'
                    bgcolour = wx.BLUE
                else:
                    status = 'Server (ignored)'
            if bgcolour is not None:
                l.SetItemBackgroundColour(count, bgcolour)
            l.SetStringItem(count, 2, status or 'None')
            count += 1
            if cap in self._caps and self._caps[cap]:
                l.InsertStringItem(count,cap)
                l.SetStringItem(count, 0, 'Suboptions')
                l.SetStringItem(count, 1, ', '.join(self._caps[cap]))
                if bgcolour is not None:
                    l.SetItemBackgroundColour(count, bgcolour)
                count += 1
        for cap,stuff in self._caps.items():
            if cap not in caps:
                l.InsertStringItem(count,cap)
                l.SetStringItem(count, 0, cap)
                l.SetStringItem(count, 1, 'Unknown extension')
                l.SetStringItem(count, 2, 'Server')
                l.SetItemBackgroundColour(count, wx.BLUE)
                count += 1
                if cap in self._caps and self._caps[cap]:
                    l.InsertStringItem(count,cap)
                    l.SetStringItem(count, 0, 'Suboptions')
                    l.SetStringItem(count, 1, ', '.join(self._caps[cap]))
                    l.SetItemBackgroundColour(count, wx.BLUE)
                    count += 1
        l.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        l.SetColumnWidth(1, wx.LIST_AUTOSIZE)
        l.SetColumnWidth(2, wx.LIST_AUTOSIZE)
        self.AddGeneric(l, wx.EXPAND)

class TreeNodeDrop(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, entry, spoofed=False ):
        polymer.treenav.TreeNode.__init__( self, tree, pid, entry['entry'], True, {wx.TreeItemIcon_Normal:'icons/tree/mailserver.png'} )
        self._imap = None
        self._menu = None
        self._username = None
        self._spoofed = spoofed
        self._mi = None
        self.change( entry )
        self._operation = None

    def change( self, entry ):
        self._email_entry = entry
        self.check_interval = entry['email.check-interval']
        if self.check_interval is None:
            self.check_interval = -1
        
    def menu_add_new( self, event ):
        d = DropEditCreate( self.tree() )
        d.Show()

    def menu_edit( self, event ):
        d = DropEditCreate( self.tree(), self._email_entry )
        d.Show()

    def menu_add_this( self, event ):
        d = polymer.dialogs.TextEntryDialog( self.tree(), "Choose a name", "Infotrope Polymer" )
        if wx.ID_OK==d.ShowModal():
            import infotrope.datasets.base
            ds = infotrope.datasets.base.get_dataset( self._email_entry.cont_url )
            del self._email_entry['entry']
            ds[d.GetValue().encode('utf-8')] = self._email_entry
            self.Delete()

    def menu_delete( self, event ):
        d = polymer.dialogs.MessageDialog( self.tree(), u"Really delete the mail server '%s'?" % self._email_entry['entry'], 'Infotrope Polymer', wx.YES_NO|wx.ICON_QUESTION )
        if d.ShowModal()==wx.ID_YES:
            import infotrope.datasets.base
            ds = infotrope.datasets.base.get_dataset( self._email_entry.cont_url )
            del ds[self._email_entry['entry']]

    def menu_filters( self, event ):
        if self._email_entry[SIEVE_ATTR] is not None:
            c = wx.GetApp().connection( self._email_entry[SIEVE_ATTR] )
            ds = polymer.sieve.sieve_open( self.tree(), c )
            if ds.ShowModal()==wx.ID_OK:
                foo = polymer.sieve.Editor( self.tree(), c, ds.script )
                foo.Show( True )

    def menu_properties( self, event ):
        self.connect()
        server_id = None
        if self._imap.have_capability( 'ID' ):
            server_id = self._imap.identity()
        banner = self._imap.banner
        dlg = ServerProps( self, banner, server_id, self._imap.capability(), self._imap.bandwidth )
        dlg.Show()

    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            if not self._spoofed:
                self._menu.Append( ID_DROP_ADD, "Add New" )
                wx.EVT_MENU( self._menu, ID_DROP_ADD, self.menu_add_new )
                self._menu.Append( ID_DROP_EDIT, "Edit" )
                wx.EVT_MENU( self._menu, ID_DROP_EDIT, self.menu_edit )
                self._menu.Append( ID_DROP_DELETE, "Delete" )
                wx.EVT_MENU( self._menu, ID_DROP_DELETE, self.menu_delete )
                self._menu.Append( ID_DROP_FILTERS, "Filters" )
                wx.EVT_MENU( self._menu, ID_DROP_FILTERS, self.menu_filters )
            else:
                self._menu.Append( ID_ADD_THIS, "Add this server" )
                wx.EVT_MENU( self._menu, ID_ADD_THIS, self.menu_add_this )
            self._menu.Append( ID_DROP_PROPS, "Properties" )
            wx.EVT_MENU( self._menu, ID_DROP_PROPS, self.menu_properties )
        self.tree().PopupMenu( self._menu, event.GetPoint() )

    def got_connection( self, c ):
        if not c.ready:
            self._operation.stop()
            return
        if self._imap is None:
            self._imap = c
            self._mi = self.connect().mbox_info()
            self._mi.add_notify( self )
            if self._operation:
                self._operation.update( "Listing mailboxes", 1 )
            self._mi.expand_children()

    def mi_notify_add( self, k, mi ):
        if self.find(k) is not None:
            return self.mi_notify_change(k, mi)
        foo = self
        if mi.full_path and mi.full_path.upper() == 'INBOX':
            foo = (self,0)
        node = polymer.imap.TreeNodeMailbox( self.tree(), foo, self, mi )
        if self._operation is not None:
            self.Expand()

    def mi_notify_complete( self, *args ):
        if len(self._mi.children()) == 0:
            self.tree().SetItemHasChildren( self.id(), False )
            return False
        self.tree().SetItemHasChildren( self.id(), True )
        if self._operation:
            self._operation.stop()
            self._operation = None

    def mi_notify_change( self, k, mi ):
        k = self.find( k )
        if k is not None:
            k.set_mi(mi)
            k.set_mailbox_flags()
        else:
            self.mi_notify_add(k, mi)

    def mi_notify_del( self, k ):
        k = self.find( k )
        k.Delete()
    
    def try_expand( self, event ):
        if self._imap is None:
            self._operation = polymer.progress.operation( self.name(), status="Connecting", pmax=2 )
            url = infotrope.url.URL( self._email_entry['email.server.IMAP'] )
            self._url = url
            c = wx.GetApp().sm.get( self._url )
            c.notify_ready( self.got_connection )
            self._imap = c
        import socket
        try:
            if self._mi is None:
                if self._operation is None:
                    self._operation = polymer.progress.operation( self.name(), status="Listing mailboxes" )
                else:
                    self._operation.update( "Listing mailboxes", 1 )
                self._mi = self._imap.mbox_info()
                self._mi.add_notify( self )
            self._mi.expand_children()
            self.update( True )
            return True
        except socket.error, e:
            wx.GetApp().alert( infotrope.url.URL( self._email_entry['email.server.IMAP'] ), str(e) )
            return False

    def local_update( self, force=False ):
        if self._imap is not None:
            self._imap.flush()
    
    def connect( self ):
        if self._imap is None:
            url = infotrope.url.URL( self._email_entry['email.server.IMAP'] )
            self._url = url
            self._imap = wx.GetApp().connection( self._url )
        return self._imap

    def find_mailbox( self, name, find_closest_parent=False ):
        self.Expand()
        mi = self.connect().mbox_info( name )
        while mi is None:
            if find_closest_parent:
                t,n,sep = self.connect().guess_namespace( name )
                name = sep.join( name.split(sep)[:-1] )
                if name == None:
                    return None
                else:
                    mi = self.connect().mbox_info( name )
        foo = self
        for x in mi.displaypath:
            foo = foo.find( x )
            foo.force_expand()
            foo.Expand()
        return foo

    def drag_over( self, how ):
        if self._imap is not None:
            self.Expand()
        return wx.DragNone

class TreeNodeDropList(polymer.treenav.TreeNode):
    def __init__( self, tree, pid ):
        polymer.treenav.TreeNode.__init__( self, tree, pid, "Mail Servers" )
        self._pending = []
        self._nodes = {}
        self._operation = polymer.progress.operation( "Mail Servers" )
        wx.GetApp().email().add_notify( self )
        self.update_every = 0
        if self._operation:
            if self._nodes:
                self._operation.update( "Refreshing configuration" )
            else:
                self._operation.update( "Fetching configuration" )

    def menu_add_new( self, event ):
        d = DropEditCreate( self.tree() )
        d.ShowModal()
    
    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            self._menu.Append( ID_DROP_ADD, "Add New" )
            wx.EVT_MENU( self._menu, ID_DROP_ADD, self.menu_add_new )
        frame.PopupMenu( self._menu, event.GetPoint() )

    def process_pending( self ):
        had_kids = self.have_children()
        if self._id is not None:
            pending = self._pending
            self._pending = []
            for entry in pending:
                node = TreeNodeDrop( self.tree(), self._id, wx.GetApp().email()[ entry ] )
                self._nodes[entry] = node
            if not had_kids and self.have_children():
                self.set_images( {wx.TreeItemIcon_Normal:'icons/news/servernews.png'} )
            self.tree().Refresh()
    
    def set_id( self, id ):
        self._id = id

    def notify_addto( self, entryname ):
        self._pending.append( entryname )
        self.process_pending()

    def notify_removefrom( self, entryname ):
        if entryname in self._pending:
            self._pending.remove( entryname )
        if entryname in self._nodes:
            self._nodes[entryname].Delete()
            del self._nodes[entryname]
        if not self.have_children():
            self.set_images()

    def notify_change( self, entryname ):
        if entryname in self._pending:
            self.notify_removefrom( entryname )
            self.notify_addto( entryname )
        elif entryname in self._nodes:
            self._nodes[entryname].change( wx.GetApp().email()[ entryname ] )
        else:
            self.notify_addto( entryname )

    def notify_complete( self, status ):
        if self._operation is not None:
            self._operation.stop()
        if len(self._nodes)==0:
            d = polymer.dialogs.MessageDialog( self.tree(), "You appear to have no information on the ACAP server\nabout where your mailservers are.\nYou'll need your account details ready.\n", "Warning - Infotrope Polymer", wx.OK|wx.ICON_INFORMATION )
            d.ShowModal()
            d = DropEditCreate( self.tree() )
            d.ShowModal()
            
    def try_expand( self, event ):
        return True

class DropEditCreate( polymer.dialogs.EntryDialogNew ):
    def __init__( self, parent, dropentry=None, dataset=None ):
        if dataset is None:
            dataset = wx.GetApp().email()
        polymer.dialogs.EntryDialogNew.__init__( self, parent, "Add New Server", dropentry, dataset )
        
    def add_prompts( self, p ):
        url = infotrope.url.URL( self.entry['email.server.IMAP'] )
        server = url.server
        if url.port is not None and url.port!=143:
            server = "%s:%d" % ( url.server, url.port )
        self._name = self.AddPrompt( p, "Name for this server", "entry" )
        self._imap_server = self.AddPrompt( p, "IMAP Server", "_imap_server", server )
        self._alt_port = self.AddCheckBox( p, "Use old-style alternate port", "_alt_port", url.scheme=='imaps' )
        method = url.mechanism
        username = url.username
        if username is None:
            username = u''
        if method is not None:
            method = self.decode_sasl_method( method )
        self.AddSecurityPrompt( p, "IMAP Authentication", "IMAP Username", '_imap_auth', method, username )
        self._check_interval = self.AddPrompt( p, 'Check Interval (seconds)', 'email.check-interval' )
        if len(wx.GetApp().personalities()):
            pers = ['*none*'] + [ x['entry'] for x in wx.GetApp().personalities() ]
        else:
            pers = ['*none*']
        self._personality = wx.Choice( p, -1, choices=pers )
        if self.entry['email.personality'] is not None:
            try:
                if self.entry['email.personality'].path.split('/')[-1] in pers:
                    self._personality.SetStringSelection( self.entry['email.personality'].path.split('/')[-1] )
            except:
                pass
        self.AddGeneric2( p, "Use Identity", self._personality )
        sieve_server = None
        sieve_port = None
        if SIEVE_ATTR in self.entry:
            sieve_uri = infotrope.url.URL( self.entry[SIEVE_ATTR] )
            sieve_server = sieve_uri.server
            sieve_port = sieve_uri.port
        self.AddPrompt( p, "SIEVE Server", "_sieve_server", sieve_server )
        self.AddPrompt( p, "SIEVE Port", "_sieve_port", sieve_port )
        
    def decode_ui( self ):
        name = polymer.encode.decode_ui( self._name.GetValue() )
        try:
            orig_name = self.entry['entry'].encode('utf-8')
            if not self.new:
                if orig_name != name.encode('utf-8'):
                    self.rename = orig_name
        except AttributeError:
            pass
        self.entry['entry'] = name
        server = polymer.encode.decode_ui( self._imap_server.GetValue() )
        user = None
        meth = self.encode_sasl_method( self.prompts['_imap_auth_method'].GetStringSelection() )
        url = 'imap://' + server + '/'
        if self._alt_port.GetValue():
            url = 'imaps://' + server + '/'
        if meth != 'ANONYMOUS':
            user = polymer.encode.decode_ui( self.prompts['_imap_auth_username'].GetValue() )
            url_t = infotrope.url.URL( url )
            url_t.username = user
            url_t.mechanism = meth
            url = url_t.asString()
        self.entry['email.server.IMAP'] = url
        try:
            self.entry['email.check-interval'] = str(int(self._check_interval.GetValue()))
        except:
            self.entry['email.check-interval'] = None
        sieve_server = polymer.encode.decode_ui( self.prompts['_sieve_server'].GetValue() )
        sieve_port = polymer.encode.decode_ui( self.prompts['_sieve_port'].GetValue() )
        if sieve_server != '':
            sieve_uri_t = infotrope.url.URL( 'x-sieve://foo/' )
            sieve_uri_t.server = sieve_server
            sieve_uri_t.port = int(sieve_port)
            sieve_uri_t.username = user
            sieve_uri_t.mechanism = meth
            self.entry[SIEVE_ATTR] = sieve_uri_t.asString()
        else:
            self.entry[SIEVE_ATTR] = None
        npers = self._personality.GetStringSelection()
        if npers == '*none*':
            self.entry['email.personality'] = None
        else:
            self.entry['email.personality'] = npers

ID_DROP_ADD = wx.NewId()
ID_DROP_EDIT = wx.NewId()
ID_DROP_DELETE = wx.NewId()
ID_DROP_FILTERS = wx.NewId()
ID_DROP_PROPS = wx.NewId()
ID_ADD_THIS = wx.NewId()
