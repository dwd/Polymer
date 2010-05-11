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
import polymer.dialogs
import polymer.progress
import infotrope.url

class MessageHistory(wx.HtmlListBox):
    def __init__( self, parent ):
        self.messages = []
        self.colours = {}
        wx.HtmlListBox.__init__( self, parent, -1 )
        self.SetItemCount( 0 )

    def OnGetItem( self, n ):
        whom, txt, html = self.messages[n]
        if whom not in self.colours:
            self.colours[whom] = '#FF0000'
        if html:
            return '<font color="%s">%s:</font> %s' % ( self.colours[whom], whom, html )
        return '<font color="%s">%s:</font> %s' % ( self.colours[whom], whom, txt )

    def add_message( self, whom, txt, html=None ):
        self.messages.append( (whom,txt,html) )
        self.messages = self.messages[-25:]
        self.SetItemCount( len(self.messages) )
        self.ScrollToLine( self.GetLineCount() )
        self.Refresh()

class XMPPMessageOut(polymer.dialogs.Base):
    def __init__( self, parent, node, conn, whom ):
        self.node = node
        self.conn = conn
        self.whom = whom
        self.thread_id = None
        polymer.dialogs.Base.__init__( self, parent, 'Chat with %s' % whom.full_jid() )

    def add_prompts( self, p ):
        self.msg_hist = MessageHistory( self )
        self.message = wx.TextCtrl( self, -1, style=wx.TE_MULTILINE )
        self.AddGeneric( self.msg_hist, wx.EXPAND )
        self.AddGeneric( self.message, wx.EXPAND )

    def incoming_message( self, stanza ):
        body = None
        body_html = None
        for x in stanza.childNodes:
            if x.nodeType == x.ELEMENT_NODE and x.localName == 'body':
                if x.getAttribute('type')=='html':
                    body_html = x.childNodes[0].nodeValue
                else:
                    body = x.childNodes[0].nodeValue
        if body or body_html:
            self.msg_hist.add_message( stanza.getAttribute('from'), body, body_html )
        else:
            self.msg_hist.add_message( stanza.getAttribute('from'), 'Unknown content' )

    def sent_message( self, txt ):
        self.msg_hist.add_message( 'foo', 'bar' )
        self.msg_hist.add_message( self.conn.local_id, txt )

    def Okay( self, event ):
        self.msg_hist.add_message( self.conn.local_id, self.message.GetValue() )
        self.conn.message( self.whom.full_jid(), polymer.encode.decode_ui( self.message.GetValue() ) )
        self.message.SetValue('')

    def Cancel( self, event ):
        self.node.remove_chat( self )
        self.End( wx.ID_CANCEL )

class JidProps(polymer.dialogs.Base):
    def __init__( self, parent, conn, whom ):
        self.conn = conn
        self.whom = whom
        self.txt = None
        polymer.dialogs.Base.__init__( self, parent, 'Properties for %s' % whom.full_jid() )

    def add_prompts( self, p ):
        self.txt = wx.TextCtrl( self, -1, style=wx.TE_MULTILINE|wx.TE_READONLY )
        self.AddGeneric( self.txt, wx.EXPAND )
        diq = self.conn.send_iq( 'get', '<query xmlns="http://jabber.org/protocol/disco#info"/>', self.whom.bare_jid() )
        diq.oncomplete( self.oncomplete )
        if self.whom.resource:
            jiq = self.conn.send_iq( 'get', '<query xmlns="http://jabber.org/protocol/disco#info"/>', self.whom.full_jid() )
            jiq.oncomplete( self.oncomplete )
        self.conn.flush()
        
    def oncomplete( self, iq, stanza ):
        self.txt.AppendText( "Got more data.\n" )

ID_PROPS = wx.NewId()

class TreeNodeContact(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, conn, jid ):
        u = infotrope.url.URL( 'xmpp:' + jid )
        self._jid = u.bare_jid()
        self._server = conn
        self._resource = u.resource
        self._uri = u
        polymer.treenav.TreeNode.__init__( self, tree, pid, jid, images={wx.TreeItemIcon_Normal:'icons/tree/mailserver.png'} )
        self.signal_change()

    def signal_change( self ):
        entry = self._server.roster().all['xmpp:'+self._jid]
        show = entry.best_avail()
        if self._resource:
            show = entry.presence[self._resource].show or 'available'
        if show in ['chat','available']:
            imgs={wx.TreeItemIcon_Normal:'icons/tree/servernewmail.png'}
        elif show in ['away']:
            imgs={wx.TreeItemIcon_Normal:'icons/tree/orange-light.png'}
        elif show in ['xa']:
            imgs={wx.TreeItemIcon_Normal:'icons/tree/purple-light.png'}
        elif show in ['dnd']:
            imgs={wx.TreeItemIcon_Normal:'icons/tree/red-light.png'}
        else:
            imgs={wx.TreeItemIcon_Normal:'icons/tree/mailserver.png'}
        self.set_images( imgs )
        name = self._resource or entry.name or self._jid
        if self._resource:
            pres = entry.presence[self._resource]
            if pres.status:
                if pres.show:
                    name += ' (' + pres.show + ': ' + pres.status + ')'
                else:
                    name += ' (' + pres.status + ')'
            elif pres.show:
                name += ' (' + pres.show + ')'
        self.tree().SetItemText( self._id, name )
        if not self._resource:
            for xx,x in self.child_nodes().items():
                x.Delete()
            for resource,pres in entry.presence.items():
                node = TreeNodeContact( self.tree(), self._id, self._server, self._jid+'/'+resource )

    def Activated( self, event ):
        self.GetParent().get_chat( self._uri )

    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            self._menu.Append( ID_PROPS, "Properties" )
            wx.EVT_MENU( self._menu, ID_PROPS, self.menu_props )
        self.tree().PopupMenu( self._menu, event.GetPoint() )

    def menu_props( self, event ):
        dlg = JidProps( self.tree(), self._server, self._uri )
        dlg.Show( True )

    def get_chat( self, uri ):
        return self.GetParent().get_chat( uri )

class TreeNodeIdentity(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, entry ):
        self._pers_entry = entry
        kids = False #entry['vendor.infotrope.personality.xmpp'] is not None
        polymer.treenav.TreeNode.__init__( self, tree, pid, entry['entry'], kids, images={wx.TreeItemIcon_Normal:'icons/address/bcard.png'} )
        self._server = None
        self.chats = {}
        if entry['vendor.infotrope.personality.xmpp'] is not None:
            s = wx.GetApp().sm.get( 'xmpp://' + entry['vendor.infotrope.personality.xmpp'] )
            s.notify_ready( self.got_connection )
            s.add_notify( self )
            s.listen( self.incoming )

    def got_connection( self, conn ):
        self._server = conn

    def menu_add_new( self, event ):
        d = IdentityEditCreate( self.tree() )
        d.Show()

    def menu_edit( self, event ):
        d = IdentityEditCreate( self.tree(), self._pers_entry )
        d.Show()

    def menu_delete( self, event ):
        d = polymer.dialogs.MessageDialog( self.tree(), u"Warning! This will erase the identity %s\nAre you sure?" % ( self._pers_entry['entry'] ), "Infotrope Polymer", wx.ICON_WARNING|wx.YES_NO )
        if wx.ID_YES==d.ShowModal():
            wx.GetApp().acap_home().store( "/personality/~/" + self._pers_entry['entry'].encode('utf-8'), {'entry':None} )
        
    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            self._menu.Append( ID_IDENTITY_ADD, "Add New" )
            wx.EVT_MENU( self._menu, ID_IDENTITY_ADD, self.menu_add_new )
            self._menu.Append( ID_IDENTITY_EDIT, "Edit" )
            wx.EVT_MENU( self._menu, ID_IDENTITY_EDIT, self.menu_edit )
            self._menu.Append( ID_IDENTITY_DELETE, "Delete" )
            wx.EVT_MENU( self._menu, ID_IDENTITY_DELETE, self.menu_delete )
        self.tree().PopupMenu( self._menu, event.GetPoint() )

    def try_expand( self, event ):
        return True

    def notify_addto( self, conn, jid ):
        node = TreeNodeContact( self.tree(), self._id, conn, jid )

    def notify_removefrom( self, conn, jid ):
        node = self.find( jid )
        node.Delete()

    def notify_change( self, conn, jid ):
        node = self.find( jid )
        node.signal_change()

    def notify_complete( self, conn ):
        pass

    def incoming( self, conn, stanza ):
        jid = stanza.getAttribute('from')
        chat = self.get_chat( jid, True )
        chat.incoming_message( stanza )

    def get_chat( self, uri, incoming=False ):
        if not isinstance( uri, infotrope.url.URL_base ):
            uri = infotrope.url.URL( 'xmpp:' + uri )
        if uri.full_jid() in self.chats:
            return self.chats[uri.full_jid()]
        if incoming and uri.resource is not None:
            if uri.bare_jid() in self.chats:
                self.chats[uri.full_jid()] = self.chats[uri.bare_jid()]
                self.chats[uri.full_jid()].whom = uri
                return self.chats[uri.full_jid()]
        dlg = XMPPMessageOut( self.tree(), self, self._server, uri )
        dlg.Show( True )
        self.chats[uri.full_jid()] = dlg
        return dlg

    def remove_chat( self, chat ):
        names = []
        for v,val in self.chats.items():
            if val is chat:
                names.append(v)
        for v in names:
            del self.chats[v]

class TreeNodeIdentityList(polymer.treenav.TreeNode):
    def __init__( self, tree, pid ):
        polymer.treenav.TreeNode.__init__( self, tree, pid, 'Identities' )
        self._pending = []
        self._nodes = {}
        self._operation = polymer.progress.operation( "Identities" )
        wx.GetApp().personalities().add_notify( self )
        if self._operation:
            if self._nodes:
                self._operation.update( "Refreshing configuration" )
            else:
                self._operation.update( "Fetching configuration" )
        
    def menu_add_new( self, event ):
        d = IdentityEditCreate( self.tree() )
        d.Show()
    
    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            self._menu.Append( ID_IDENTITY_ADD, "Add New" )
            wx.EVT_MENU( self._menu, ID_IDENTITY_ADD, self.menu_add_new )
        self.tree().PopupMenu( self._menu, event.GetPoint() )

    def notify_addto( self, entry ):
        had_kids = self.have_children()
        node = TreeNodeIdentity( self.tree(), self._id, wx.GetApp().personalities()[entry] )
        self._nodes[ entry ] = node
        if not had_kids and self.have_children():
            self.set_images( {wx.TreeItemIcon_Normal:'icons/address/bclist.png'} )
    
    def set_id( self, id ):
        self._id = id
        
    def notify_removefrom( self, entryname ):
        if entryname in self._nodes:
            self._nodes[entryname].Delete()
            del self._nodes[entryname]
        if not self.have_children():
            self.set_images()
            
    def notify_change( self, entryname ):
        self.notify_removefrom( entryname )
        self.notify_addto( entryname )

    def notify_complete( self, state ):
        if self._operation is not None:
            self._operation.stop()
        
    def try_expand( self, event ):
        return True

    def select( self, event ):
        return
        if self._panel is None:
            self._panel = PanelAddressbook( self._tree.notebook(), self )
        self._tree.update()
        self._panel.foreground()


class IdentityEditCreate( polymer.dialogs.EntryDialogNew ):
    def __init__( self, parent, identry=None, dataset=None ):
        if dataset is None:
            dataset = wx.GetApp().personalities()
        polymer.dialogs.EntryDialogNew.__init__( self, parent, "Add New Identity", identry, dataset )
        
    def add_prompts( self, p ):
        self._name = self.AddPrompt( p, "Name for this identity", 'entry' )
        self._full_name = self.AddPrompt( p, "Full Name", 'personality.Real-Name' )
        self._email_address = self.AddPrompt( p, "Email Address", 'personality.Return-Address' )
        self._xmpp_id = self.AddPrompt( p, 'XMPP Id', 'vendor.infotrope.personality.xmpp' )
        s = ''
        m = None
        un = None
        if 'personality.Server.SMTP' in self.entry:
            u = infotrope.url.URL( self.entry['personality.Server.SMTP'] )
            s = u.server
            if u.port is not None:
                s = "%s:%d" % ( u.server, u.port )
            un = u.username
            m = u.mechanism
        if m is not None:
            m = self.decode_sasl_method( m )
        self._smtp_server = self.AddPrompt( p, "Outgoing SMTP Server", '_smtp_host', s )
        self.AddSecurityPrompt( p, "SMTP Authentication", "SMTP Username", '_smtp_auth', m, un )
        self.AddMailboxPrompt( p, "Drafts Mailbox", "vendor.infotrope.personality.Drafts.IMAP", self.entry['vendor.infotrope.personality.Drafts.IMAP'] )
        self.AddMailboxPrompt( p, "Sent Mail Mailbox", "personality.File-Into.IMAP", self.entry['personality.File-Into.IMAP'] )
        
    def decode_ui( self ):
        name = polymer.encode.decode_ui( self._name.GetValue() )
        try:
            orig = self.entry['entry'].encode('utf-8')
            if not self.new:
                if orig != name.encode('utf-8'):
                    self.rename = orig
        except AttributeError:
            pass
        self.entry['entry'] = name
        self.entry['personality.Real-Name'] = polymer.encode.decode_ui( self._full_name.GetValue() )
        self.entry['personality.Return-Address'] = polymer.encode.decode_ui( self._email_address.GetValue() )
        self.entry['vendor.infotrope.personality.xmpp'] = polymer.encode.decode_ui( self._xmpp_id.GetValue() ) or None
        smtp_server = polymer.encode.decode_ui( self._smtp_server.GetValue() )
        sasl_method = self.encode_sasl_method( self.prompts['_smtp_auth_method'].GetStringSelection() )
        url = infotrope.url.URL( 'smtp:' + smtp_server.encode('us-ascii') )
        url.mechanism = sasl_method
        if sasl_method!='ANONYMOUS':
            url.username = polymer.encode.decode_ui( self.prompts['_smtp_auth_username'].GetValue() ).encode( 'utf8' )
        self.entry['personality.Server.SMTP'] = url
        self.entry['personality.File-Into.IMAP'] = self.prompts['personality.File-Into.IMAP'].GetValue()
        self.entry['vendor.infotrope.personality.Drafts.IMAP'] = self.prompts['vendor.infotrope.personality.Drafts.IMAP'].GetValue()

ID_IDENTITY_ADD = wx.NewId()
ID_IDENTITY_EDIT = wx.NewId()
ID_IDENTITY_DELETE = wx.NewId()
