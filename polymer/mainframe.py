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
import polymer.composer
import polymer.maildrop
import polymer.addressbook
import polymer.scrap
import polymer.personality
import polymer.bookmarks
import infotrope.acap

import email.Utils

import infotrope.datasets.bookmarks

import infotrope.modutf7
import urllib

#import weakref

reply_types = {}
reply_names = {}
ID_FRAME_NEW = wx.NewId()
ID_FRAME_REPLY = wx.NewId()
ID_FRAME_REPLY_SENDER = wx.NewId()
reply_types[ ID_FRAME_REPLY_SENDER ] = polymer.composer.MessageReplySender
ID_FRAME_REPLY_DIRECT = wx.NewId()
reply_types[ ID_FRAME_REPLY_DIRECT ] =  polymer.composer.MessageReplyDirect
ID_FRAME_REPLY_LIST = wx.NewId()
reply_types[ ID_FRAME_REPLY_LIST ] =  polymer.composer.MessageReplyList
ID_FRAME_REPLY_LIST_SENDER = wx.NewId()
reply_types[ ID_FRAME_REPLY_LIST_SENDER ] =  polymer.composer.MessageReplyListSender
ID_FRAME_REPLY_LIST_ONLY_SENDER = wx.NewId()
reply_types[ ID_FRAME_REPLY_LIST_ONLY_SENDER ] = polymer.composer.MessageReplyListOnlySender
ID_FRAME_REPLY_ALL = wx.NewId()
reply_types[ ID_FRAME_REPLY_ALL ] =  polymer.composer.MessageReplyAll
ID_FRAME_FORWARD = wx.NewId()
reply_types[ ID_FRAME_FORWARD ] = polymer.composer.MessageForwardMime
ID_FRAME_FORWARD_QUOTED = wx.NewId()
reply_types[ ID_FRAME_FORWARD_QUOTED ] = polymer.composer.MessageForwardQuoted
ID_FRAME_FORWARD_MIME = wx.NewId()
reply_types[ ID_FRAME_FORWARD_MIME ] = polymer.composer.MessageForwardMime
ID_FRAME_EDIT_DRAFT = wx.NewId()
reply_types[ ID_FRAME_EDIT_DRAFT ] = polymer.composer.MessageDraft
#ID_FRAME_FORWARD_INLINE = wx.NewId()
#ID_FRAME_FORWARD_RESEND = wx.NewId()
ID_FRAME_SAVED_VIEWS = wx.NewId()
ID_FRAME_SAVED_VIEW_UNDELETED = wx.NewId()
ID_FRAME_NOTYET = wx.NewId()
ID_FRAME_HELP = wx.NewId()
ID_FRAME_ABOUT = wx.NewId()
ID_FRAME_EXIT_CLEAN = wx.NewId()

ID_FRAME_EXPUNGE = wx.NewId()
ID_FRAME_CLOSE_TAB = wx.NewId()

criteria = {}
criteria[ID_FRAME_SAVED_VIEW_UNDELETED] = infotrope.imap.crit_undeleted()

class PolymerMainFrame( wx.Frame ):
    def __init__( self, size, debug=False ):
        wx.Frame.__init__( self, None, -1, "Infotrope Polymer", size=size, name='polymer' )
        self.CreateStatusBar()
        self.SetStatusText( "Initializing..." )

        menu = wx.Menu()
        menu.Append( ID_FRAME_NEW, "&New", "Compose a new message" )
        menu.AppendSeparator()
        menu.Append( wx.ID_EXIT, "E&xit", "Exit Polymer" )
        menu.Append( ID_FRAME_EXIT_CLEAN, "Exit &Clean", "Exit Polymer, remove all files" )

        menuBar = wx.MenuBar()
        menuBar.Append( menu, "&File" )

        menu = wx.Menu()
        menu.Append( ID_FRAME_NEW, "&New Message", "Compose a new message" )
        menu.Append( ID_FRAME_REPLY, "&Reply", "Reply to current message, using the default reply method" )

        reply_menu = wx.Menu()
        reply_menu.Append( ID_FRAME_REPLY_SENDER, "to &Sender", "Reply to the sender, honouring Reply-To" )
        reply_menu.Append( ID_FRAME_REPLY_DIRECT, "&Direct", "Reply directly to the sender, do not honour Reply-To" )
        reply_menu.Append( ID_FRAME_REPLY_ALL, "to &All", "Reply to the sender, honouring Reply-To, and CC all recipients." )
        reply_menu.Append( ID_FRAME_REPLY_LIST, "to &List", "Reply to the list only." )
        reply_menu.Append( ID_FRAME_REPLY_LIST_SENDER, "to L&ist and Sender", "Reply to the list and CC the sender" )
        reply_menu.Append( ID_FRAME_REPLY_LIST_ONLY_SENDER, "to S&ender only from list message", "Reply only to the sender, checking for list ReplyTo." )

        menu.AppendItem( wx.MenuItem( menu, ID_FRAME_NOTYET, "Repl&y...", "Advanced reply methods", subMenu=reply_menu ) )

        forward_menu = wx.Menu()
        forward_menu.Append( ID_FRAME_FORWARD_MIME, "as &MIME", "Forward the message intact, with all headers and attachments" )
        forward_menu.Append( ID_FRAME_FORWARD_QUOTED, "&Quoted", "Forward the message quoted inline to your covering note" )
        #forward_menu.Append( ID_FRAME_FORWARD_INLINE, "&Inline", "Forward the message appended to the end of your covering note, with some headers" )
        #forward_menu.Append( ID_FRAME_FORWARD_RESEND, "&Silently", "Resend the message, leaving headers intact, as from the original user" )

        menu.Append( ID_FRAME_FORWARD, "&Forward", "Forward the current message, using default forwarding method" )
        menu.AppendItem( wx.MenuItem( menu, ID_FRAME_NOTYET, "For&ward...", "Advanced forward methods", subMenu=forward_menu ) )

        menu.Append( ID_FRAME_EDIT_DRAFT, "Edit &draft", "Edit this message as draft" )
        
        menuBar.Append( menu, "&Message" )
        

        menu = wx.Menu()
        menu.Append( ID_FRAME_EXPUNGE, "&Expunge", "Destroy messages marked as deleted" )
        menu.Append( ID_FRAME_CLOSE_TAB, "&Close", "Remove this tab." )
        self.Bind( wx.EVT_MENU, self.edit_filters, menu.Append( -1, "&Views...", "Edit views" ) )
        self.Bind( wx.EVT_MENU, self.toggle_uid, menu.AppendCheckItem( -1, "Show &Uid", "Show IMAP UID" ) )
        #menu.Append( ID_FRAME_NOTYET, "&Search", "Apply a search to the mailbox" )
        #menu.Append( ID_FRAME_NOTYET, "S&ort", "Apply a sort to the mailbox" )
        #menu.AppendSeparator()
        #menu.Append( ID_FRAME_NOTYET, "Save &View", "Save this view for later" )
        #menu2 = wx.Menu()
        #menu2.Append( ID_FRAME_SAVED_VIEWS, "Saved Views", "Views you have saved" )
        #menu2.Enable( ID_FRAME_SAVED_VIEWS, False )
        #menu2.AppendSeparator()
        #menu2.Append( ID_FRAME_SAVED_VIEW_UNDELETED, "Undeleted", "Messages not marked Deleted" )
        #menu.AppendItem( wx.MenuItem( menu, ID_FRAME_NOTYET, "Saved Views", "Views you have saved", subMenu = menu2 ) )
        menuBar.Append( menu, "&Tools" )

        menu = wx.Menu()
        menu.Append( ID_FRAME_HELP, "&Help", "Help with Polymer" )
        menu.Append( ID_FRAME_ABOUT, "&About", "About Polymer" )
        menuBar.Append( menu, "&Help" )

        self.SetMenuBar( menuBar )

        wx.EVT_MENU( self, wx.ID_EXIT, self.OnExit )
        self._splitter = wx.SplitterWindow( self, -1 )
        #self.panel = wx.Panel( self._splitter, -1 )
        self.notebook = wx.Notebook( self._splitter, -1 )
        
        self.tree = polymer.treenav.Navigator( self._splitter, self, self.notebook )
        self.tree.add_main( polymer.maildrop.TreeNodeDropList )
        self.tree.add_main( polymer.addressbook.TreeNodeAddressbook )
        #self.tree.add_main( polymer.scrap.TreeNodeScrap )
        self.tree.add_main( polymer.bookmarks.TreeNodeBookmarks )
        self.tree.add_main( polymer.personality.TreeNodeIdentityList )
        if self.tree.root_shown:
            self.tree.root.Expand()
        self._splitter.SplitVertically( self.tree, self.notebook, self.GetSize()[0]/4 )
        self._splitter.SetMinimumPaneSize(20)
        
        self._sending = []
        
        wx.EVT_CLOSE( self, self.OnClose )
        
        #wx.EVT_MENU( self, ID_DROP_ADD, self.AddDrop )
        #wx.EVT_MENU( self, ID_DROP_DELETE, self.DeleteDrop )
        #wx.EVT_MENU( self, ID_DROP_EDIT, self.EditDrop )
        #
        #wx.EVT_MENU( self, ID_IDENTITY_ADD, self.AddIdentity )
        #wx.EVT_MENU( self, ID_IDENTITY_DELETE, self.DeleteIdentity )
        #wx.EVT_MENU( self, ID_IDENTITY_EDIT, self.EditIdentity )
        wx.EVT_MENU( self, ID_FRAME_EXIT_CLEAN, self.ExitClean )
        
        wx.EVT_MENU( self, ID_FRAME_NEW, self.new_message )
        wx.EVT_MENU( self, ID_FRAME_REPLY, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_ABOUT, self.about )
        
        wx.EVT_MENU( self, ID_FRAME_REPLY_SENDER, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_REPLY_DIRECT, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_REPLY_LIST, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_REPLY_LIST_SENDER, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_REPLY_LIST_ONLY_SENDER, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_REPLY_ALL, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_FORWARD, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_FORWARD_QUOTED, self.reply_message )
        wx.EVT_MENU( self, ID_FRAME_FORWARD_MIME, self.reply_message )

        wx.EVT_MENU( self, ID_FRAME_EDIT_DRAFT, self.reply_message )
        
        wx.EVT_MENU( self, ID_FRAME_SAVED_VIEW_UNDELETED, self.filter )
        wx.EVT_MENU( self, ID_FRAME_EXPUNGE, self.expunge )
        wx.EVT_MENU( self, ID_FRAME_CLOSE_TAB, self.close_tab )

        wx.EVT_NOTEBOOK_PAGE_CHANGED( self.notebook, -1, self.notebook_change )
        wx.EVT_RIGHT_DOWN( self.notebook, self.notebook_rclick )
        
        self._timer_tick = 0
        self._status_text = None
        self._timer = wx.GetApp().timer( self.flush_status )
        self._timer.Start( 500 )
        #polymer.status.EVT_STATUS_UPDATE( self, self.add_status )
        #EVT_MAILDROP_NONE( self, self.no_maildrop )

    def edit_filters( self, evt=None ):
        import polymer.filters
        dlg = polymer.filters.FilterList( self )
        if dlg.ShowModal()==wx.ID_OK:
            if dlg.selected is None or dlg.selected['vendor.infotrope.filter.name']!=dlg.prompts['filter'].GetValue():
                dlg2 = polymer.filters.EditFilter( self, name=dlg.prompts['filter'].GetValue() )
            else:
                dlg2 = polymer.filters.EditFilter( self, dlg.selected )
            dlg2.Show()

    def notebook_rclick( self, evt ):
        tab = self.notebook.HitTest( evt.GetPosition() )[0]
        if tab > -1:
            panel = self.notebook.GetPage( tab )
            panel.ShowPopupMenu( evt.GetPosition() )

    def notebook_change( self, evt ):
        evt.Skip()
        pid = evt.GetSelection()
        if pid < 0:
            return
        p = self.notebook.GetPage( pid )
        if p is not None:
            p.update( True )
        
    def update( self ):
        pass
        
    def add_status( self, event ):
        self.add_status_text( event.message() )

    def add_status_text( self, txt ):
        self._status_text = txt
        self._timer_tick = 5
        self.flush_status()
        #self._timer.Start( 1000 )

    def flush_status( self ):
        if self._timer_tick > 0:
            self._timer_tick -= 1
        else:
            self._status_text = None
        import infotrope.socketry
        up,upc = infotrope.socketry.up_counter()
        down,downc = infotrope.socketry.down_counter()
        if self._status_text:
            self.SetStatusText( "[%1.1f%s/%1.1f%s] %s" % ( up, upc, down, downc, self._status_text ) )
        else:
            s = ' [Pre TLS]'
            if infotrope.socketry.tls_stats():
                s = ''
            self.SetStatusText( "Bandwidth up: %.2f%sB (%d%%), down: %2.2f%sB (%d%%)%s" % ( up, upc, infotrope.socketry.up_ratio(), down, downc, infotrope.socketry.down_ratio(), s ) )

    def about( self, event ):
        d = polymer.dialogs.MessageDialog( self, "Infotrope Polymer, an ACAP based IMAP client.\n\nCopyright 2003-2006 Dave Cridland <dave@cridland.net>\nCopyright 2004-2006 Inventure Systems Ltd\n\nInfotrope Polymer is intended to be a relatively lightweight, but full featured IMAP client, driven by ACAP.", "About Infotrope Polymer", wx.OK|wx.ICON_INFORMATION )
        d.ShowModal()
        d.Destroy()

    def expunge( self, event ):
        a = self.notebook.GetSelection()
        if a==-1:
            return
        b = self.notebook.GetPage( a )
        if isinstance(b,polymer.imap.PanelMailbox):
            b.expunge()

    def toggle_uid( self, event ):
        for a in range(self.notebook.GetPageCount()):
            b = self.notebook.GetPage( a )
            if isinstance( b, polymer.imap.PanelMailbox ):
                b.uid_column_displayed( event.IsChecked() )
        wx.GetApp().set_option( 'uid-column-displayed', event.IsChecked() )

    def close_tab( self, event=None ):
        a = self.notebook.GetSelection()
        if a==-1:
            return
        b = self.notebook.GetPage( a )
        if isinstance(b,polymer.treenav.NavPanel):
            b.delete()
        return True
    
    def reply_message( self, event ):
        id = event.GetId()
        a = self.notebook.GetSelection()
        if a==-1:
            return
        b = self.notebook.GetPage( a )
        if isinstance(b,polymer.imap.PanelMailbox):
            s = b._selected
            if s is None:
                return
            self.reply_handle( s, id )

    def reply_handle( self, s, id ):
        if id == ID_FRAME_EDIT_DRAFT:
            if not s.flagged( '\\Draft' ):
                dlg = polymer.dialogs.ErrorDialog( self, "This message is not a draft.", "Infotrope Polymer" )
                dlg.ShowModal()
                return
        if id == ID_FRAME_REPLY:
            list_id = email.Utils.parseaddr( s.list_header('list-id') )[1]
            if list_id != '' and wx.GetApp().home in wx.GetApp().sm:
                rt_attr = 'vendor.infotrope.polymer.list.reply-type'
                conn = wx.GetApp().acap_home()
                srch = infotrope.acap.search( 'SEARCH "/addressbook/~/" DEPTH 0 RETURN ("%s" "addressbook.Email" "addressbook.CommonName") EQUAL "addressbook.List.ID" "i;ascii-casemap" "%s"' % ( rt_attr, list_id ), connection=conn )
                t,r,ss = srch.wait()
                nxid = None
                rt = None
                pth = None
                me = None
                if len(srch):
                    for en in srch.entries():
                        e = srch[en]
                        pth = en
                        me = e
                        trt = e[rt_attr]['value']
                        if trt is not None and isinstance(trt,str) and trt in ['list','list-sender','sender','all']:
                            rt = trt
                            break
                    if rt is None and me['addressbook.Email']['value'] is not None:
                        d = polymer.dialogs.QueryDialog( self, "When replying to the list\n%s\ndo you want to reply to:" % e['addressbook.CommonName']['value'].decode('utf-8'), "List Reply", (("The list",'list'), ("The sender",'sender'), ("Both",'list-sender'), ("Everyone",'all')) )
                        if wx.ID_OK == d.ShowModal():
                            rt = d.result
                            conn.store( pth, {'vendor.infotrope.polymer.list.reply-type':d.result} )
                    if rt is not None:
                        if rt == 'list':
                            nxid = ID_FRAME_REPLY_LIST
                        elif rt == 'list-sender':
                            nxid = ID_FRAME_REPLY_LIST_SENDER
                        elif rt == 'sender':
                            nxid = ID_FRAME_REPLY_LIST_ONLY_SENDER
                        elif rt == 'all':
                            nxid = ID_FRAME_REPLY_ALL
                    if nxid is not None:
                        id = nxid
        if id == ID_FRAME_REPLY:
            id = ID_FRAME_REPLY_SENDER
        m = reply_types[id]( self, s )
        m.Show( True )

    def new_message( self, event ):
        m = polymer.composer.NewMessage( self )
        m.Show( True )
        
    def OnExit( self, event ):
        self.Close( True )

    def OnClose( self, event ):
        wx.GetApp().logger( "Killing menu bar" )
        mb = self.GetMenuBar()
        self.SetMenuBar( wx.MenuBar() )
        mb.Destroy()
        wx.GetApp().logger( "Pre shutdown" )
        wx.GetApp().pre_shutdown()
        wx.GetApp().logger( "Tree shutdown" )
        self.tree.shutdown()
        self.tree.root.Delete()
        wx.GetApp().logger( "Closing tabs" )
        while self.close_tab():
            pass
        wx.GetApp().logger( "Skip" )
        event.Skip()
        wx.GetApp().logger( "Exit main loop" )
        wx.GetApp().ExitMainLoop()
        
    def ExitClean( self, event ):
        dlg = polymer.dialogs.MessageDialog( self, "This will remove your local cache.\nThis will lose any pending changes, and make\nPolymer slower to start.\nAlso, it'll forget your ACAP server.\nAre you sure you want to do this?", "Infotrope Polymer", wx.YES_NO|wx.CANCEL )
        res = dlg.ShowModal()
        if res == wx.ID_CANCEL:
            return
        wx.GetApp().exit_clean_flag = ( res == wx.ID_YES )
        self.Close( True )

    def process_bookmark( self, event ):
        if not isinstance( event.GetEventObject(), BookmarksMenu ):
            dlg = polymer.dialogs.MessageDialog( self, "Sorry, this isn't implemented quite yet.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            dlg.ShowModal()
            return
        bm = event.GetEventObject().find_bookmark( event.GetId() )
        if bm is not None:
            if bm['bookmarks.URL'] is not None:
                wx.GetApp().process_url( bm['bookmarks.URL'] )

    def new_bookmark( self, event=None, tgt_u=None ):
        if tgt_u is None:
            tgt_u = event.GetEventObject().url()
        ( curl, title ) = self.get_current_url()
        if curl is None:
            d = polymer.dialogs.MessageDialog( self, "No idea how to make a bookmark to this.\nNot even sure what this is.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()
            return
        bm = infotrope.datasets.base.get_dataset( tgt_u )
        en = bm.new( 'link' )
        en['bookmarks.URL'] = curl
        en['bookmarks.Name'] = title

    def get_current_url( self ):
        a = self.notebook.GetSelection()
        if a==-1:
            return (None,None)
        b = self.notebook.GetPage( a )
        if isinstance(b,polymer.imap.PanelMailbox):
            s = b._selected
            if s is not None:
                name = s.envelope().Subject
                if name is None:
                    name = s.envelope().From[0].hname
                return (s.uri(),name)
        return (None,None)

    def filter( self, event ):
        id = event.GetId()
        page_i = self.notebook.GetSelection()
        if page_i == -1:
            return
        page = self.notebook.GetPage( page_i )
        if isinstance( page, polymer.imap.PanelMailbox ):
            np = polymer.imap.PanelMailbox( self.notebook, page._controller, infotrope.imap.mailbox_filter( page._mailbox, criteria[id] ) )

    def process_imap_url( self, url ):
        u = infotrope.url.URL( url )
        if u.port is not None:
            if u.port==143:
                u.port = None
        self.tree.root.find('Mail Servers').Expand()
        for ee in wx.GetApp().email():
            if ee['email.server.IMAP'].server == u.server:
                if ee['email.server.IMAP'].port == u.port:
                    use_this = True
                    if u.username is not None and u.username!=ee['email.server.IMAP'].username:
                        use_this = False
                    elif u.mechanism is not None and u.mechanism!=ee['email.server.IMAP'].mechanism:
                        use_this = False
                    if use_this:
                        self.tree.root.find( 'Mail Servers' ).Expand()
                        maildrop = self.tree.root.find( 'Mail Servers' ).find( ee['entry'] )
                        mailbox = maildrop.find_mailbox( u.mailbox, type=='LIST' or type=='LSUB' )
                        if type not in ['LIST','LSUB']:
                            mailbox.select( None )
                            if u.uid:
                                mailbox.panel.auto_select( u.uid )
                            elif u.query:
                                mailbox.panel.set_filter( u.query.decode('urlencode') )
                        return
        adhoc = self.tree.root.find( 'Mail Servers' ).find( '*Ad Hoc' )
        if adhoc is None:
            adhoc = polymer.treenav.TreeNode( self.tree, self.tree.root.find( 'Mail Servers' ), '*Ad Hoc' )
        adh_name = '%s@%s' % ( u.username, u.server )
        if u.port is not None:
            if u.port != 143:
                adh_name += ':%d' % u.port
        e = {}
        e['entry'] = adh_name
        e['email.server.IMAP'] = infotrope.url.URL(u)
        e['email.check-interval'] = None
        maildrop = adhoc.find( adh_name )
        self.tree.root.find( 'Mail Servers' ).Expand()
        adhoc.Expand()
        if maildrop is None:
            d = polymer.dialogs.MessageDialog( self, "You asked to open an IMAP URL, but it's not one of your\nmail servers. Do you want to add it?", "Infotrope Polymer", wx.YES_NO|wx.YES_DEFAULT|wx.ICON_QUESTION )
            if wx.ID_YES==d.ShowModal():
                d = polymer.dialogs.TextEntryDialog( self, "Choose a name for this mail server.", "Infotrope Polymer - Name" )
                if wx.ID_OK==d.ShowModal():
                    u2 = infotrope.url.URL( u )
                    u2.path = '/'
                    u2.query = ''
                    wx.GetApp().acap_home().store( '/email/~/' + polymer.encode.decode_ui( d.GetValue() ).encode('utf-8'), {'email.server.IMAP': u2.asString()} )
                    return self.process_imap_url( url )
            else:
                maildrop = polymer.maildrop.TreeNodeDrop( self.tree, adhoc, e, spoofed=True )
        mailbox = maildrop.find_mailbox( u.mailbox, type=='LIST' or type=='LSUB' )
        if type not in ['LIST','LSUB']:
            mailbox.select( None )
            if u.uid:
                mailbox.panel.auto_select( u.uid )
            elif u.query:
                mailbox.panel.set_filter( u.query.decode('urlencode') )
        return
