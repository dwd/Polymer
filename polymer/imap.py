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
import polymer.render
from polymer.encode import *
import email.Parser
#import email.Header
import email.Utils
import StringIO
import time
import infotrope.url
import polymer.dragdrop
import os
import polymer.dialogs
import polymer.progress
import weakref

message_menu = None
defer_refreshes = 500

class Filterator:
    def __init__( self ):
        self._filters = wx.GetApp().filters()
        self._subnotify = []
        self._filters.add_notify( self )
        self._listcrit = {}
        self._filters_cache = {}

    def add_notify( self, o ):
        self._subnotify.append( weakref.ref( o ) )
        self._subnotify = [ x for x in self._subnotify if x() is not None ]

    def notify_addto( self, arg ):
        try:
            del self._filters_cache[arg]
        except:
            pass
        self.do_flush()
    def notify_removefrom( self, arg ):
        try:
            del self._filters_cache[arg]
        except:
            pass
        self.do_flush()
    def notify_change( self, arg ):
        try:
            del self._filters_cache[arg]
        except:
            pass
        self.do_flush()
    def notify_complete( self, *arg ):
        self.do_flush()

    def do_flush( self ):
        self._listcrit = {}
        for x in self._subnotify:
            y = x()
            if y is not None:
                y.filterator_notify()

    def getlistattr( self, msg ):
        attr = None
        font = None
        for x in self._filters.entries():
            if x not in self._filters_cache:
                self._filters_cache[x] = self._filters[x]
            f = self._filters_cache[x]
            if x not in self._listcrit:
                self._listcrit[x] = None
                try:
                    self._listcrit[x] = infotrope.imap.parse_criteria( f['vendor.infotrope.filter.program'], wx.GetApp().connection( msg.uri() ) )
                except:
                    pass
            if self._listcrit[x] is None:
                continue
            if not ( f['vendor.infotrope.filter.colour.background'] or
                     f['vendor.infotrope.filter.colour.foreground'] or
                     f['vendor.infotrope.filter.bold'] or
                     f['vendor.infotrope.filter.italic'] ):
                continue
            if self._listcrit[x].check_match( msg ):
                if f['vendor.infotrope.filter.colour.foreground']:
                    if attr is None:
                        attr = wx.ListItemAttr()
                    attr.SetTextColour( f['vendor.infotrope.filter.colour.foreground'] )
                if f['vendor.infotrope.filter.colour.background']:
                    if attr is None:
                        attr = wx.ListItemAttr()
                    attr.SetBackgroundColour( f['vendor.infotrope.filter.colour.background'] )
                if f['vendor.infotrope.filter.italic']:
                    if font is None:
                        font = wx.SystemSettings.GetFont( wx.SYS_DEFAULT_GUI_FONT )
                    font.SetStyle( wx.ITALIC )
                if f['vendor.infotrope.filter.bold']:
                    if font is None:
                        font = wx.SystemSettings.GetFont( wx.SYS_DEFAULT_GUI_FONT )
                    font.SetWeight( wx.BOLD )
        if font is not None:
            if attr is None:
                attr = wx.ListItemAttr()
            attr.SetFont( font )
        return attr

_filterator = None

def get_filterator( who ):
    global _filterator
    if _filterator is None:
        _filterator = Filterator()
    _filterator.add_notify( who )
    return _filterator

COL_FLAGS = 0
COL_FROM = 1
COL_SUBJECT = 2
COL_DATE = 3
COL_UID = 4

ID_FMSG_FROM = wx.NewId()
ID_FMSG_SUBJECT = wx.NewId()
ID_FMSG_THREAD = wx.NewId()
import re
subj_strip_re = re.compile('^ *re: *', re.I)
ID_FMSG_LIST = wx.NewId()

class MailboxSummary(wx.ListCtrl):
    def __init__( self, parent, mailbox, master ):
        wx.ListCtrl.__init__( self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL )
        self._master = master
        self._init = False
        self._refresh = 0
        self._refresh_timer = wx.GetApp().timer( self.deferred_refresh )
        self._attr_lru = []
        self._attr_cache = {}
        self.InsertColumn( COL_FLAGS, " " )
        self.InsertColumn( COL_FROM, "From" )
        self.InsertColumn( COL_SUBJECT, "Subject" )
        self.InsertColumn( COL_DATE, "Date" )
        #self.InsertColumn( COL_UID, "UID/seqno" )
        self._mailbox = mailbox
        self._mailbox.register_notify( self )
        self._count = 0
        self._rclicked = None
        self._menu = None
        self._menu_flags = {}
        self._multi_menu = None
        self._filterator = get_filterator( self )
        self.set_count()
        self.Update()
        if self.GetItemCount() > ( self._mailbox.logical_start_position() - 1 ) >= 0:
            self.EnsureVisible( self._mailbox.logical_start_position() - 1 )
        wx.EVT_KEY_DOWN( self, self.on_key_down )
        wx.EVT_LIST_BEGIN_DRAG( self, -1, self.begin_drag )
        wx.EVT_LIST_ITEM_RIGHT_CLICK( self, -1, self.right_click )
        EVT_SET_COUNT( self, self.process_set_count )
        #wx.EVT_PAINT( self, self.process_set_count )
        self._prefetch_range = None
        self._prefetch_last = None
        self._prefetch_tags = []
        self._prefetch_timer = wx.GetApp().timer( self.prefetch_real )
        wx.EVT_LIST_CACHE_HINT( self, -1, self.prefetch )
        wx.EVT_SIZE( self, self.size_columns )
        self.size_columns()

    def uid_column_displayed( self, isit ):
        if isit:
            if self.GetColumnCount()==4:
                self.InsertColumn( COL_UID, "UID/seqno" )
        elif self.GetColumnCount()==5:
            self.DeleteColumn( COL_UID )
        self.size_columns()

    def size_columns( self, event=None ):
        if event is not None:
            event.Skip()
        width = self.GetClientSize()[0]
        width -= wx.SystemSettings.GetMetric( wx.SYS_VSCROLL_X )
        self.SetColumnWidth( 0, 40 )
        width -= 40
        self.SetColumnWidth( 3, 80 )
        width -= 80
        if self.GetColumnCount()==5:
            width -= 120
            self.SetColumnWidth( 4, 120 )
        self.SetColumnWidth( 1, width / 4 )
        self.SetColumnWidth( 2, 3*width / 4 )

    def process_set_count( self, event ):
        self.set_count()

    def flag_menu_handler( self, event ):
        msg = self._mailbox[self._rclicked]
        for flag,item in self._menu_flags.items():
            if item.GetId() == event.GetId():
                if msg.flagged( flag ):
                    msg.unflag( flag )
                else:
                    msg.flag( flag )

    def flag_define( self, event ):
        d = polymer.dialogs.TextEntryDialog( self, "Enter new keyword", "Infotrope Polymer" )
        if wx.ID_OK == d.ShowModal():
            if d.GetValue():
                msg = self._mailbox[self._rclicked]
                msg.flag( d.GetValue() )

    def reply_menu( self, event ):
        if isinstance(self._rclicked,list):
            msg = [self._mailbox[x] for x in self._rclicked]
        else:
            msg = self._mailbox[self._rclicked]
        wx.GetApp().frame.reply_handle( msg, event.GetId() )

    def get_selected( self ):
        selected = []
        foo = self.GetFirstSelected()
        while foo>-1:
            selected.append( foo )
            foo = self.GetNextSelected( foo )
        return selected
    
    def right_click( self, event ):
        idx = event.GetIndex()
        selected = self.get_selected()
        if idx in selected and len(selected)>1:
            self.multi_right_click(selected, event)
        else:
            self.single_right_click( 1+idx, event )

    def multi_flag_set(self, event):
        obj = event.GetEventObject()
        obj = obj.FindItemById(event.GetId())
        fr = self._mailbox.freeze()
        for x in self._rclicked:
            self._mailbox[x].flag(obj.GetText().encode('usascii'))
        fr = None

    def multi_flag_unset(self, event):
        obj = event.GetEventObject()
        obj = obj.FindItemById(event.GetId())
        fr = self._mailbox.freeze()
        for x in self._rclicked:
            self._mailbox[x].unflag(obj.GetText().encode('usascii'))
        fr = None
        
    def multi_flag_define(self, event):
        d = polymer.dialogs.TextEntryDialog( self, "Enter new keyword", "Infotrope Polymer" )
        if wx.ID_OK == d.ShowModal():
            if d.GetValue():
                fr = self._mailbox.freeze()
                for x in self._rclicked:
                    self._mailbox[x].flag(d.GetValue())
                fr = None

    def multi_expunge_range(self, event):
        if self._mailbox.server().have_capability('UIDPLUS'):
            fr = self._mailbox.freeze()
            self._mailbox.expunge(self._rclicked)
            fr = None
    
    def multi_kill_range(self, event):
        if self._mailbox.server().have_capability('UIDPLUS'):
            fr = self._mailbox.freeze()
            for x in self._rclicked:
                self._mailbox[x].flag('\\deleted')
            self._mailbox.expunge(self._rclicked)
            fr = None
    
    def multi_right_click( self, selected, event ):
        self._rclicked = [self._mailbox.seqno(x+1) for x in selected]
        if self._multi_menu is None:
            import polymer.mainframe
            self._multi_menu = wx.Menu()
            self.Bind( wx.EVT_MENU, self.reply_menu, self._multi_menu.Append( polymer.mainframe.ID_FRAME_FORWARD, "Forward All", "Forward as digest" ) )
            self.Bind( wx.EVT_MENU, self.multi_expunge_range, self._multi_menu.Append( -1, "Expunge Range", "Remove all deleted messages" ) )
            self.Bind( wx.EVT_MENU, self.multi_kill_range, self._multi_menu.Append( -1, "Kill Range", "Remove all messages" ) )
            if self._mailbox.permflags():
                menu = wx.Menu()
                menu2 = wx.Menu()
                for flag in self._mailbox.permflags():
                    txt = flag
                    if flag[0]=='\\':
                        txt = '\\' + flag[1].upper() + flag[2:]
                    elif flag[0]=='$':
                        txt = '$' + flag[1].upper() + flag[2:]
                    else:
                        txt = flag[0].upper() + flag[1:]
                    self.Bind(wx.EVT_MENU, self.multi_flag_set, menu.Append( -1, txt, "Set flag %s" % txt ))
                    self.Bind(wx.EVT_MENU, self.multi_flag_unset, menu2.Append( -1, txt, "Clear flag %s" % txt ))
                if self._mailbox.newflags():
                    mi = menu.Append( -1, "New...", "Define and set new keyword" )
                    self.Bind( wx.EVT_MENU, self.multi_flag_define, mi )
                self._multi_menu.AppendMenu( -1, "Set Flags", menu, "Set flag" )
                self._multi_menu.AppendMenu( -1, "Clear Flags", menu2, "Clear flag" )
        self.PopupMenu( self._multi_menu, event.GetPoint() )

    def single_right_click( self, seqno, event ):
        uid = self._mailbox.seqno( seqno )
        if not uid:
            return
        self._rclicked = uid
        if self._menu is None:
            import polymer.mainframe
            self._menu = wx.Menu()
            self._menu_flags = {}
            self.Bind( wx.EVT_MENU, self.reply_menu, self._menu.Append( polymer.mainframe.ID_FRAME_REPLY, "Reply", "Reply using default method" ) )
            reply_menu = wx.Menu()
            self.Bind( wx.EVT_MENU, self.reply_menu, reply_menu.Append( polymer.mainframe.ID_FRAME_REPLY_SENDER, "to &Sender", "Reply to the sender, honouring Reply-To" ) )
            self.Bind( wx.EVT_MENU, self.reply_menu, reply_menu.Append( polymer.mainframe.ID_FRAME_REPLY_DIRECT, "&Direct", "Reply directly to the sender, do not honour Reply-To" ) )
            self.Bind( wx.EVT_MENU, self.reply_menu, reply_menu.Append( polymer.mainframe.ID_FRAME_REPLY_ALL, "to &All", "Reply to the sender, honouring Reply-To, and CC all recipients." ) )
            self._list_options = []
            self._list_options.append( reply_menu.Append( polymer.mainframe.ID_FRAME_REPLY_LIST, "to &List", "Reply to the list only." ) )
            self._list_options.append( reply_menu.Append( polymer.mainframe.ID_FRAME_REPLY_LIST_SENDER, "to L&ist and Sender", "Reply to the list and CC the sender" ) )
            self._list_options.append( reply_menu.Append( polymer.mainframe.ID_FRAME_REPLY_LIST_ONLY_SENDER, "to S&ender only from list message", "Reply only to the sender, checking for list ReplyTo." ) )
            for x in self._list_options:
                self.Bind( wx.EVT_MENU, self.reply_menu, x )
            self._menu.AppendMenu( -1, "Reply...", reply_menu )
            self.Bind( wx.EVT_MENU, self.reply_menu, self._menu.Append( polymer.mainframe.ID_FRAME_FORWARD, "Forward", "Forward using default method" ) )
            forward_menu = wx.Menu()
            self.Bind( wx.EVT_MENU, self.reply_menu, forward_menu.Append( polymer.mainframe.ID_FRAME_FORWARD_MIME, "as &MIME", "Forward the message intact, with all headers and attachments" ) )
            self.Bind( wx.EVT_MENU, self.reply_menu, forward_menu.Append( polymer.mainframe.ID_FRAME_FORWARD_QUOTED, "&Quoted", "Forward the message quoted inline to your covering note" ) )
            self._menu.AppendMenu( -1, "Forward...", forward_menu )
            self.Bind( wx.EVT_MENU, self.savemsg, self._menu.Append( wx.NewId(), "&Save As...", "Save the message to a file") )
            self._menu_draft = self._menu.Append( polymer.mainframe.ID_FRAME_EDIT_DRAFT, "Edit draft", "Edit the message as draft" )
            self.Bind( wx.EVT_MENU, self.reply_menu, self._menu_draft )
            if self._mailbox.permflags():
                menu = wx.Menu()
                for flag in self._mailbox.permflags():
                    txt = flag
                    if flag[0]=='\\':
                        txt = '\\' + flag[1].upper() + flag[2:]
                    elif flag[0]=='$':
                        txt = '$' + flag[1].upper() + flag[2:]
                    else:
                        txt = flag[0].upper() + flag[1:]
                    self._menu_flags[flag] = menu.AppendCheckItem( -1, txt, "Toggle flag %s" % txt )
                    self.Bind(wx.EVT_MENU,self.flag_menu_handler,self._menu_flags[flag])
                if self._mailbox.newflags():
                    mi = menu.Append( -1, "New...", "Define and set new keyword" )
                    self.Bind( wx.EVT_MENU, self.flag_define, mi )
                self._menu.AppendMenu( -1, "Flags", menu, "Set and clear flags" )
            filter_menu = wx.Menu()
            self.Bind(wx.EVT_MENU, self.filter_on_msg, filter_menu.Append(ID_FMSG_FROM, "on &Sender", "Filter based on sender"))
            self.Bind(wx.EVT_MENU, self.filter_on_msg, filter_menu.Append(ID_FMSG_SUBJECT, "on S&ubject", "Filter based on subject"))
            self.Bind(wx.EVT_MENU, self.filter_on_msg, filter_menu.Append(ID_FMSG_THREAD, "on &Thread", "Filter based on thread"))
            self._list_filter = filter_menu.Append(ID_FMSG_LIST, "on &List", "Filter based on list")
            self.Bind(wx.EVT_MENU, self.filter_on_msg, self._list_filter)
            self._menu.AppendMenu(-1, "Filter...", filter_menu, "Filter based on this message")
        msg = self._mailbox[uid]
        for flag,item in self._menu_flags.items():
            item.Check( msg.flagged( flag ) )
        lh = msg.list_header('list-post',True)
        li = msg.list_header('list-id',True)
        if lh is None:
            lh = msg.list_header('newsgroups',True)
        for item in self._list_options:
            item.Enable( lh is not None )
        self._list_filter.Enable(li is not None)
        self._menu_draft.Enable( msg.flagged( '\\Draft' ) )
        self.PopupMenu( self._menu, event.GetPoint() )

    def savemsg(self, evt):
        uid = self._mailbox.seqno(1 + self.get_selected()[0])
        print "Saving message",uid
        fdlg = wx.FileDialog(self, "Save Message", style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if polymer.dialogs.save_dir:
            fdlg.SetDirectory(polymer.dialogs.save_dir)
        if fdlg.ShowModal() == wx.ID_OK:
            path = fdlg.GetPath()
            polymer.dialogs.save_dir = fdlg.GetDirectory()
            f = open(path, "w")
            s = StringIO.StringIO(self._mailbox[uid].body_raw(''))
            for l in s:
                l = l.rstrip('\r\n')
                f.write(l)
                f.write('\n')
            f.close()

    def filter_on_msg(self, evt):
        self._master.filter_on_msg(evt.GetId(), self._mailbox.seqno(1 + self.get_selected()[0]))

    def prefetch( self, evt ):
        if self._prefetch_range:
            self._prefetch_timer.Stop()
            self._prefetch_range = None
        if self._mailbox.server().dead():
            return
        blocksize = 10
        seqno_from = int(evt.GetCacheFrom() / blocksize) * blocksize + 1
        seqno_to = int( evt.GetCacheTo() / blocksize + 1 ) * blocksize
        while seqno_to <= seqno_from:
            seqno_to += blocksize
        if seqno_from > len(self._mailbox):
            self.set_count()
            return
        if seqno_to > len(self._mailbox):
            seqno_to = len(self._mailbox)
        self._prefetch_range = (seqno_from,seqno_to)
        if self._prefetch_range == self._prefetch_last:
            self._prefetch_range = None
            return
        if 2 > len( self._mailbox.server().inprog ):
            self.prefetch_real()
            return
        self._prefetch_timer.Start( 100 )

    def prefetch_real( self ):
        if not self._prefetch_range:
            self._prefetch_timer.Stop()
            return
        if 1 < len( self._mailbox.server().inprog ):
            return
        self._prefetch_timer.Stop()
        self._prefetch_last = self._prefetch_range
        self._prefetch_range = None
        self._mailbox.convert_sequence_then( self.prefetch_run, range( self._prefetch_last[0], self._prefetch_last[1]+1 ) )

    def prefetch_run( self, stuff ):
        self._prefetch_cache = [ self._mailbox[ x ] for x in stuff ]
        tmp = [uid for uid in stuff if self._mailbox[uid].fetch_flags()]
        if tmp:
            self._mailbox.prefetch( tmp, self.prefetch_complete )
        else:
            self.prefetch_complete(None)
        
    def prefetch_complete( self, *args ):
        self.prefetch_real()
        if args[0] is not None:
            self._refresh_timer.Stop()
            self._refresh = time.time()
            self.Refresh()

    def set_filter( self, m ):
        if self.GetItemCount():
            self.EnsureVisible( 0 )
        self._prefetch_last = None
        self._mailbox.delete_notify( self )
        self._mailbox = m
        self._mailbox.register_notify( self )
        self._count = 0
        self.SetItemCount( 0 )
        self.GetParent().GetParent().hide_listing( True )
        self.set_count()
        self.Update()
        if self.GetItemCount() > ( m.logical_start_position()-1 ) >= 0:
            self.EnsureVisible( m.logical_start_position()-1 )

    def begin_drag( self, event ):
        selected = self.get_selected()
        if not selected:
            selected = [event.GetIndex()]
        if len(selected)>1:
            uids = []
            for i in selected:
                uid = self._mailbox.seqno( i+1 )
                if uid is None:
                    continue
                uids.append(uid)
            uris = []
            for u in uids:
                uris.append( str(self._mailbox.master_uri()) + '/;UID=' + str(u) )
            dobj = polymer.dragdrop.URLDataObject( uris )
        else:
            uid = self._mailbox.seqno( selected[0]+1 )
            if uid is None:
                return
            msg = self._mailbox[uid]
            dobj = polymer.dragdrop.URLDataObject( msg.uri(), msg.envelope().Subject )
        ds = wx.DropSource( self )
        ds.SetData( dobj )
        res = ds.DoDragDrop( wx.Drag_DefaultMove )
        if res == wx.DragMove:
            self.set_count()

    def on_key_down( self, event ):
        kk = event.GetKeyCode()
        if wx.WXK_DELETE==kk:
            self.flag_selected( event.ShiftDown(), '\\deleted' )
            return
        if ord('S') == kk:
            self.flag_selected( event.ShiftDown(), '\\seen' )
            return
        if ord('U') == kk:
            self.flag_selected( not event.ShiftDown(), '\\seen' )
            return
        '''if ord('1') >= kk and ord('9') <= kk:
            self.flag_selected( event.ShiftDown(), '$Label%d' % kk-48 )
            return''' # Can't do this! Doesn't work for shared mailboxes.
        if ord('J') == kk:
            self.flag_selected( event.ShiftDown(), '$junk' )
            return
        if ord('F') == kk:
            self.flag_selected( event.ShiftDown(), '\\flagged' )
            return
        event.Skip()
        return

    def flag_selected( self, remove, flag ):
        selected = []
        foo = self.GetFirstSelected()
        while foo>-1:
            selected.append( foo )
            foo = self.GetNextSelected( foo )
        if len(selected)==0:
            return
        flag = self._master.check_flag_perm( flag )
        if flag is None:
            return
        uids = []
        for x in selected:
            uid = self._mailbox.seqno( x+1 )
            if uid is not None:
                uids.append( uid )
        advance = None
        if 1==len(uids) and flag in ['\\deleted','junk','$junk']:
            advance = True
        else:
            advance = False
        freezer = self._mailbox.freeze()
        for x in uids:
            if remove:
                self._mailbox[x].unflag( flag )
            else:
                self._mailbox[x].flag( flag )
        freezer = None
        if advance is not None:
            self._master.relocate( uids[0], advance )
        #for x in selected:
        #    self.RefreshItem( x )

    def set_count( self ):
        c = len( self._mailbox )
        if self._count!=c:
            wx.GetApp().logger( "Updating count from %d to %d" % ( self._count, c ) )
            self._count = c
            self._last_prefetch = None
            self._attr_lru = []
            self._attr_cache = {}
            self.SetItemCount( c )
            if self._init:
                self.GetParent().GetParent().hide_listing( c==0 )

    def init( self ):
        self.GetParent().GetParent().hide_listing( len(self._mailbox)==0 )
        self._init = True

    def notify_change( self, mbx, which ):
        if 0 in which:
            self._attr_lru = []
            self._attr_cache = {}
        self.set_count()
        if 0 in which:
            return
        bottom = self.GetTopItem() + 1 + self.GetCountPerPage()
        done_refresh = False
        for x in which:
            if x == 0:
                continue
            s = self._mailbox.uid( x )
            if s is not None:
                if x in self._attr_cache:
                    del self._attr_cache[x]
                    self._attr_lru.remove( x )
                if not done_refresh and s <= bottom:
                    self.deferred_refresh()
                    done_refresh = True
                
    def deferred_refresh( self ):
        self._refresh_timer.Stop()
        t = time.time()
        if t - self._refresh > ( defer_refreshes / 1000.0 ):
            self._refresh = t
            self.Refresh()
        else:
            self._refresh_timer.Start( defer_refreshes )

    def refresh_now( self ):
        self._refresh = time.time()
        self.Refresh()

    def filterator_notify( self ):
        self._attr_cache = {}
        self._attr_lru = []
        self.deferred_refresh()

    def OnGetItemImage( self, litem ):
        return -1

    def OnGetItemAttr( self, item ):
        if not self._mailbox.check_seqno( item+1 ):
            return None
        uid = self._mailbox.seqno( item+1 )
        self._refresh = time.time()
        if uid is None:
            self.AddPendingEvent( SetCountEvent() )
            return None
        if self._mailbox[uid].flags( nofetch=True ) is None:
            return None
        if uid in self._attr_cache:
            self._attr_lru.remove(uid)
            self._attr_lru.append(uid)
            return self._attr_cache[uid]
        for x in self._attr_lru[:-self.GetCountPerPage()]:
            del self._attr_cache[x]
        self._attr_lru = self._attr_lru[-self.GetCountPerPage():]
        attr = self._filterator.getlistattr( self._mailbox[uid] )
        self._attr_lru.append( uid )
        self._attr_cache[uid] = attr
        return attr

    def OnGetItemText( self, litem, col ):
        if not self._mailbox.check_seqno( litem+1 ):
            if col==COL_UID:
                return ' ??? '
            else:
                return ' ... '
        txt = ''
        item = self._mailbox.seqno( litem+1 )
        if item is None:
            return ' - '
        if col!=COL_UID and self._mailbox[item].flags(nofetch=True) is None:
            return ' ... '
        if col==COL_FLAGS:
            if self._mailbox[ item ].flagged( '\\Recent' ):
                txt += 'R'
            if not self._mailbox[ item ].flagged( '\\Seen' ):
                txt += 'U'
            if self._mailbox[ item ].flagged( '\\Answered' ):
                txt += 'A'
            if self._mailbox[ item ].flagged( '$Forwarded' ):
                txt += 'F'
            if self._mailbox[ item ].flagged( '\\Flagged' ):
                txt = '!'+txt
            if self._mailbox[ item ].flagged( '$Junk' ) or self._mailbox[ item ].flagged( 'Junk' ):
                txt = '$'+txt
            if self._mailbox[ item ].flagged( '\\Draft' ):
                txt += 'D'
            if self._mailbox[ item ].flagged( '\\Deleted' ):
                txt = '~' + txt
            #if isinstance( self._mailbox[ item ].structure()[0], list ):
            #    txt += '#'
        elif col==COL_FROM:
            if self._mailbox[item].get_from_name() is not None:
                txt = encode_ui( self._mailbox[ item ].get_from_name() )
        elif col==COL_SUBJECT:
            env = self._mailbox[ item ].envelope()
            if env is None:
                txt = ' ... '
            else:
                txtu = self._mailbox[ item ].envelope().Subject
                if txtu is None:
                    txtu = ''
                txt = encode_ui( txtu )
        elif col==COL_DATE:
            d = self._mailbox[ item ].get_sent_date()
            if d is not None:
                q = time.mktime( d )
                now = time.time()
                yesterday = now - 20 * 3600.0
                last_week = now - 6 * 24 * 3600.0
                if q > yesterday:
                    txt = time.strftime( '%X', d )
                elif q > last_week:
                    txt = time.strftime( '%a, %X', d )
                else:
                    txt = time.strftime( '%x %X', d )
        elif col==4:
            txt = "%d :: %d" % ( item, litem+1 )
        return txt

EVT_SET_COUNT_ID = wx.NewId()
class SetCountEvent(wx.PyEvent):
    def __init__( self ):
        wx.PyEvent.__init__( self )
        self.SetEventType(EVT_SET_COUNT_ID)
    def Clone(self):
        return SetCountEvent()
def EVT_SET_COUNT(win,func):
    win.Connect( -1, -1, EVT_SET_COUNT_ID, func )

ID_GO_BACK = wx.NewId()
ID_THREAD_UP = wx.NewId()
ID_GO_NEXT = wx.NewId()
ID_HEADER = wx.NewId()
ID_DELETE = wx.NewId()
ID_JUNK = wx.NewId()

class FilterSelector(wx.Choice):
    def __init__( self, parent, wxid ):
        self.filters = wx.GetApp().filters()
        wx.Choice.__init__( self, parent, wxid, choices=['View all'] )
        self._ready = False
        self.filters.add_notify( self )

    def notify_addto( self, *args ):
        if self._ready:
            self.do_notify()

    def notify_removefrom( self, *args ):
        if self._ready:
            self.do_notify()

    def notify_change( self, *args ):
        if self._ready:
            self.do_notify()

    def notify_complete( self, *args ):
        self._ready = True
        self.do_notify()

    def do_notify( self ):
        old = self.GetValue()
        self.Clear()
        f = self.filters.entries()
        self.Append( 'View all' )
        for ff in f:
            self.Append( self.filters[ff]['vendor.infotrope.filter.name'] )
        self.SetValue( old )

    def GetValue( self ):
        idx = self.GetSelection()
        if idx <= 0:
            return None
        e = self.filters[ idx - 1 ]
        return e

    def SetValue( self, what ):
        idx = 0
        try:
            if what is not None:
                if isinstance( what, polymer.filters.base ):
                    idx = 1 + self.filters.index( what['entry'] )
                elif isinstance( what, str ):
                    idx = 1 + self.filters.index( what )
                elif isinstance( what, int ):
                    idx = what
                else:
                    return
        except:
            pass
        self.SetSelection( idx )

class PanelMailbox(wx.SplitterWindow,polymer.treenav.NavPanel):
    def __init__( self, notebook, controller ):
        self._controller = controller
        self._pagename = "%s :: %s" % ( controller.server()._name, controller.mi().full_path )
        self._master_mbx = None
        self._listing = None
        polymer.treenav.NavPanel.__init__( self, notebook, self._pagename, wx.SplitterWindow.__init__, controller )
        self._menu = None
        self._mailbox = self._controller.server()._imap.mailbox( self._controller.mi().full_path )
        self._master_mbx = self._mailbox
        self._listing_panel = wx.Panel( self, -1 )
        self._listing_sizer = wx.BoxSizer( wx.VERTICAL )
        self._list_captures = []
        self._captures = []
        tb = wx.ToolBar( self._listing_panel, -1 )
        self._filter_choice = FilterSelector( tb, -1 )
        self._current_filter = 0
        wx.EVT_CHOICE( self._filter_choice, -1, self.change_filter )
        
        #tszr.Add( wx.StaticText( tb, -1, "Filter:" ), 0, wx.ALIGN_CENTER|wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT, border=1 )
        #tszr.Add( self._filter_choice, 0, wx.EXPAND|wx.LEFT|wx.RIGHT, border=1 )
        tb.AddControl( self._filter_choice )
        self._filter_active = wx.CheckBox( tb, -1, "Dynamic" )
        self._filter_active.SetValue( True )
        wx.EVT_CHECKBOX( self._filter_active, -1, self.do_filter_active )
        tb.AddControl( self._filter_active )
        #tszr.Add( self._filter_active, 0, wx.EXPAND|wx.LEFT|wx.RIGHT, border=1 )
        #tszr.Add( wx.StaticText( tb, -1, "Active" ), 0, wx.ALIGN_CENTER|wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT, border=1 )
        ID_QS = wx.NewId()
        tb.AddSeparator()
        tb.AddCheckLabelTool( ID_QS, "Quick Search", wx.Bitmap( wx.GetApp().find_image( 'icons/toolbar/search.png' ), wx.BITMAP_TYPE_PNG ), wx.NullBitmap, shortHelp="Show/hide search bar" )
        wx.EVT_TOOL( tb, ID_QS, self.quicksearch_change )
        tb.Realize()
        self._listing_sizer.Add( tb, 0, wx.EXPAND )        
        tbqs = wx.Panel( self._listing_panel, -1 )
        tszr = wx.BoxSizer( wx.HORIZONTAL )
        self._search_what = wx.Choice( tbqs, -1, choices=['From','To/CC','Subject','Body','Tag'] )
        self._search_what.SetSelection( 0 )
        wx.EVT_CHOICE( self._search_what, -1, self.filter_what )
        tszr.Add( self._search_what, 0, wx.LEFT|wx.RIGHT, border=1 )
        self._search_text = wx.TextCtrl( tbqs, -1 )
        tszr.Add( self._search_text, 1, wx.GROW|wx.LEFT|wx.RIGHT, border=1 )
        self._search_tags = wx.Choice( tbqs, -1, choices=[ x.title() for x in self._mailbox.permflags() ] )
        self._search_tags.SetSelection( 0 )
        tszr.Add( self._search_tags, 1, wx.LEFT|wx.RIGHT, border=1 )
        tszr.Show( self._search_tags, False )
        self._search_button = wx.Button( tbqs, -1, "Go" )
        wx.EVT_BUTTON( self._search_button, -1, self.do_search )
        #self._clear_button = wx.Button( tb, -1, "All" )
        #wx.EVT_BUTTON( self._clear_button, -1, self.change_filter )
        tszr.Add( self._search_button, 0, wx.LEFT|wx.RIGHT, border=1 )
        #tszr.Add( self._clear_button, 0, wx.EXPAND|wx.LEFT|wx.RIGHT, border=1 )
        tbqs.SetSizer( tszr )
        tbqs.SetAutoLayout( True )
        tszr.Fit( tbqs )
        self._listing_sizer.Add( tbqs, 0, wx.EXPAND )
        self._quicksearchbar = tbqs
        self._listing_sizer.Show( tbqs, False )
        self._listing = MailboxSummary( self._listing_panel, self._mailbox, self )
        self._listing.uid_column_displayed( wx.GetApp().get_option( 'uid-column-displayed' ) )
        self._listing_sizer.Add( self._listing, 1, wx.EXPAND )
        self._listing_sizer.Show( self._listing, False ) 
        self._listing_display = False
        self._listing_nothing = wx.StaticText( self._listing_panel, -1, "No messages" )
        self._listing_sizer.Add( self._listing_nothing, 1, wx.ALIGN_CENTER )
        self._listing_init = False
        self._listing.init()
        self._listing_init = True
        self._listing_panel.SetSizer( self._listing_sizer )
        self._listing_panel.SetAutoLayout( True )
        self._listing_sizer.Fit( self._listing_panel )
        self._preview_panel = wx.Panel( self, -1 )
        szr = wx.BoxSizer( wx.VERTICAL )
        pvtb = wx.ToolBar( self._preview_panel, -1 )
        from polymer.mainframe import ID_FRAME_REPLY, ID_FRAME_FORWARD
        pvtb.AddLabelTool( ID_FRAME_REPLY, "Reply", wx.Bitmap( wx.GetApp().find_image( 'icons/toolbar/reply.png' ), wx.BITMAP_TYPE_PNG ), shortHelp="Reply to message" )
        pvtb.AddLabelTool( ID_FRAME_FORWARD, "Forward", wx.Bitmap( wx.GetApp().find_image( 'icons/toolbar/forward.png' ), wx.BITMAP_TYPE_PNG ), shortHelp="Forward message" )
        pvtb.AddSeparator()

        pvtb.AddLabelTool( ID_GO_BACK, "Back", wx.ArtProvider.GetBitmap( wx.ART_GO_BACK, wx.ART_TOOLBAR ), shortHelp="Previous message viewed" )
        pvtb.AddLabelTool( ID_THREAD_UP, "Thread Up", wx.ArtProvider.GetBitmap( wx.ART_GO_UP, wx.ART_TOOLBAR ), shortHelp="Parent message of current" )
        pvtb.AddLabelTool( ID_GO_NEXT, "Forward", wx.ArtProvider.GetBitmap( wx.ART_GO_FORWARD, wx.ART_TOOLBAR ), shortHelp="Next message viewed" )
        pvtb.AddSeparator()
        pvtb.AddLabelTool( ID_HEADER, "Header", wx.Bitmap( wx.GetApp().find_image( 'icons/news/newsfolder.png' ), wx.BITMAP_TYPE_PNG ), shortHelp="Show full header" )
        pvtb.AddSeparator()
        pvtb.AddCheckLabelTool( ID_DELETE, "Delete", wx.Bitmap( wx.GetApp().find_image( 'icons/toolbar/Delete.png' ), wx.BITMAP_TYPE_PNG ), wx.NullBitmap, shortHelp="Mark message deleted" )
        pvtb.AddCheckLabelTool( ID_JUNK, "Junk", wx.Bitmap( wx.GetApp().find_image( 'icons/toolbar/junk.png' ), wx.BITMAP_TYPE_PNG ), wx.NullBitmap, shortHelp="Mark message as junk" )
        pvtb.Realize()
        self.pvtb = pvtb
        szr.Add( pvtb, 0, wx.EXPAND )
        self._preview_master = wx.ScrolledWindow( self._preview_panel, -1 )
        self._preview_master_sizer = wx.BoxSizer( wx.VERTICAL )
        szr.Add( self._preview_master, 1, wx.EXPAND )
        self._preview_panel.SetSizer( szr )
        self._preview_panel.SetAutoLayout( True )
        szr.Fit( self._preview_panel )
        print "size:", self.GetParent().GetSize()[1], self.GetParent().GetSize()[1]/3
        self.Update()
        self.SplitHorizontally( self._listing_panel, self._preview_panel, self.GetParent().GetSize()[1]/3 )
        self._preview_master.SetSizer( self._preview_master_sizer )
        self._preview_master_sizer.FitInside( self._preview_master )
        self._preview_master.SetScrollRate( 20, 20 )
        self._messages = []
        wx.EVT_LIST_ITEM_FOCUSED( self._listing, -1, self.select )
        self._selected = None
        self._selected_history = []
        self._selected_pos = -1
        self._history_nav = False
        self._display = None
        self._parts_map = {}
        self._resize_timer = wx.GetApp().timer( self.resize_timer )
        self._resize_timer_running = False
        self._resize_timer_exec = False
        self._capture_list = []
        wx.EVT_TOOL( pvtb, ID_THREAD_UP, self.thread_up )
        wx.EVT_TOOL( pvtb, ID_GO_BACK, self.go_back )
        wx.EVT_TOOL( pvtb, ID_GO_NEXT, self.go_forward )
        wx.EVT_TOOL( pvtb, ID_HEADER, self.full_header )
        wx.EVT_TOOL( pvtb, ID_DELETE, self.tool_delete )
        wx.EVT_TOOL( pvtb, ID_JUNK, self.tool_junk )
        wx.EVT_SIZE( self._preview_master, self.resize_preview )

    def hide_listing( self, x ):
        if self._listing_display != x:
            return
        self._listing_sizer.Show( self._listing, not x )
        self._listing_sizer.Show( self._listing_nothing, x )
        self._listing_display = not x
        if self._listing_init:
            self._listing_sizer.Layout()

    def uid_column_displayed( self, t ):
        self._listing.uid_column_displayed( t )

    def PanelMenu( self ):
        if self._menu is None:
            self._menu = polymer.treenav.NavPanel.PanelMenu( self )
            mi = self._menu.Append( -1, "Expunge", "Permanently erase marked messages" )
            self.GetParent().Bind( wx.EVT_MENU, self.expunge, mi )
        return self._menu

    def update( self, full=False ):
        if self._master_mbx is not None:
            if not self._master_mbx.server().dead():
                self._master_mbx.uidvalidity()
        if full and self._listing:
            self._listing.deferred_refresh()

    def do_filter_active( self, event=None ):
        if self._mailbox is not self._master_mbx:
            self._mailbox.noremove = not self._filter_active.GetValue()

    def quicksearch_change( self, event ):
        self._listing_sizer.Show( self._quicksearchbar, event.IsChecked() )
        self._listing_sizer.Layout()
        self.change_filter()

    def change_filter( self, event=None ):
        self._search_text.SetValue('')
        newfilter = self._filter_choice.GetValue()
        f = None
        if newfilter is not None:
            f = newfilter['vendor.infotrope.filter.program']
        self.set_filter( f )

    def filter_on_msg(self, kind, uid):
        msg = self._master_mbx[uid]
        ## TODO: Clear all existing filter UI
        f = None
        if kind == ID_FMSG_SUBJECT:
            subj = msg.envelope().Subject
            m = subj_strip_re.match(subj)
            if m is not None:
                subj = subj[m.end():]
            f = infotrope.imap.crit_subject(subj)
        elif kind == ID_FMSG_FROM:
            fname = msg.envelope().From[0].hname
            femail = msg.envelope().From[0].address
            f = infotrope.imap.crit_or()
            f.add(infotrope.imap.crit_from(fname))
            f.add(infotrope.imap.crit_from(femail))
        elif kind == ID_FMSG_THREAD:
            ## TODO: Use INTHREAD if possible.
            msgid = msg.envelope().MessageID
            f = infotrope.imap.crit_or()
            f.add(infotrope.imap.crit_headermatch('Message-Id',msgid))
            f.add(infotrope.imap.crit_headermatch('In-Reply-To',msgid))
            f.add(infotrope.imap.crit_headermatch('References',msgid))
        elif kind == ID_FMSG_LIST:
            list_id = email.Utils.parseaddr( msg.list_header('list-id') )[1]
            f = infotrope.imap.crit_headermatch('List-Id',list_id)
        self.set_filter(f)

    def set_filter( self, what ):
        if what is None:
            self._mailbox = self._master_mbx
        else:
            #try:
            self._mailbox = infotrope.imap.mailbox_filter( self._master_mbx, what, not self._filter_active.GetValue() )
            #except str,e:
            #    wx.GetApp().alert( self._master_mbx.uri(), "Filter is invalid:\n" + e )
        self._listing.set_filter( self._mailbox )

    def filter_what( self, event ):
        tszr = self._search_what.GetContainingSizer()
        if self._search_what.GetSelection()==4:
            tszr.Show( self._search_text, False )
            tszr.Show( self._search_tags, True )
        else:
            tszr.Show( self._search_text, True )
            tszr.Show( self._search_tags, False )
        tszr.Layout()

    def do_search( self, event ):
        f = self._filter_choice.GetValue()
        n = self._search_what.GetSelection()
        if n < 4 and len(self._search_text.GetValue())==0:
            return
        if n==0:
            n = infotrope.imap.crit_from( polymer.encode.decode_ui( self._search_text.GetValue() ) )
        elif n==1:
            n = infotrope.imap.crit_or()
            n.add( infotrope.imap.crit_stringmatch( 'TO', polymer.encode.decode_ui( self._search_text.GetValue() ) ) )
            n.add( infotrope.imap.crit_stringmatch( 'CC', polymer.encode.decode_ui( self._search_text.GetValue() ) ) )
        elif n==2:
            n = infotrope.imap.crit_subject( polymer.encode.decode_ui( self._search_text.GetValue() ) )
        elif n==3:
            n = infotrope.imap.crit_stringmatch( 'BODY', polymer.encode.decode_ui( self._search_text.GetValue() ) )
        elif n==4:
            n = infotrope.imap.crit_genflag( self._search_tags.GetStringSelection() )
        q = None
        if f is not None:
            q = infotrope.imap.crit_and()
            q.add( n )
            filter_criteria = infotrope.imap.parse_criteria( f['vendor.infotrope.filter.program'], self._master_mbx.server() )
            q.add( filter_criteria )
        else:
            q = n
        self.set_filter( q )

    def resize_preview( self, event=None ):
        if self._resize_timer_exec:
            x = 0
            while True:
                if x >= len( self._preview_master_sizer.GetChildren() ):
                    break
                p = self._preview_master_sizer.GetItem( x )
                x += 1
                if p is not None:
                    p.GetWindow().resize()
                else:
                    break
        else:
            if self._resize_timer_running:
                self._resize_timer.Stop()
            self._resize_timer_running = True
            self._resize_timer.Start( 500 )

    def resize_timer( self ):
        self._resize_timer_running = False
        self._resize_timer.Stop()
        self._resize_timer_exec = True
        self.resize_preview()
        self._resize_timer_exec = False

    def full_header( self, event ):
        if self._selected is not None:
            p = self._selected.parts()
            for pp in p.children:
                if pp.part_id == 'HEADER':
                    f = StringIO.StringIO( self._selected.body( pp ) )
                    hdr = email.Parser.Parser().parse( f, headersonly = True )
                    d = polymer.dialogs.PropsDialog( self, hdr, infotrope.encoding.decode_header( hdr['Subject'] ), infotrope.encoding.decode_header )
                    d.Show()
                    return

    def thread_up( self, event ):
        if self._selected is not None:
            foo = self._selected.envelope().InReplyTo
            if foo is None:
                rhdr = self._selected.reply_header('references')
                if rhdr is None:
                    return
                refs = rhdr.split( ' ' )
                while foo=='' and len(refs):
                    foo = refs[-1]
                    refs = refs[:-1]
                if foo=='':
                    return
            uid = self._mailbox.find_message_id( foo )
            if uid is None:
                return
            seqno = self._mailbox.uid( uid )
            self.auto_select( uid )

    def tool_delete( self, evt ):
        self.flag_and_move( not evt.IsChecked(), '\\deleted' )
        
    def tool_junk( self, evt ):
        self.flag_and_move( not evt.IsChecked(), '$junk' )

    def flag_and_move( self, remove, flag ):
        if self._selected is not None:
            u = int(self._selected.uid())
            flag = self.check_flag_perm( flag )
            if flag is None:
                return
            if remove:
                self._selected.unflag( flag )
            else:
                self._selected.flag( flag )
            self.relocate( u, True )

    def check_flag_perm( self, flag, silent=False ):
        rights = ''
        if flag=='\\seen':
            rights += 's'
        elif flag=='\\deleted':
            rights += 't'
        else:
            rights += 'w'
        if not self._mailbox.have_rights( rights ):
            if not silent:
                d = polymer.dialogs.ErrorDialog( self, "Permission denied", "Infotrope Polymer" )
                d.ShowModal()
            return None
        if not self._mailbox.flag_available( flag ):
            if flag == '$junk' and self._mailbox.flag_available( 'junk' ):
                flag = 'junk'
            else:
                if not silent:
                    d = polymer.dialogs.ErrorDialog( self, "Can't set the %s flag, sorry." % flag, "Infotrope Polymer" )
                    d.ShowModal()
                return None
        return flag
    
    def relocate( self, u, advance=True ):
        new_seqno = self._mailbox.uid( u, closest=True )
        nu = self._mailbox.seqno( new_seqno )
        if nu is None:
            return
        if advance:
            while nu <= u:
                if new_seqno >= len(self._mailbox):
                    break
                new_seqno += 1
                nnu = None
                try:
                    nnu = self._mailbox.seqno( new_seqno )
                except:
                    pass
                if nnu is not None:
                    nu = nnu
                else:
                    break
        if nu is not None:
            self.auto_select( nu )
        
    def expunge( self, evt=None ):
        # Save the selected message's UID.
        uid = None
        if self._selected is not None:
            uid = int(self._selected.uid())
        # Now expunge.
        self._mailbox.expunge()
        # Find the message and redisplay it.
        if uid is not None:
            new_seqno = self._mailbox.uid( uid, closest=True )
            uid = self._mailbox.seqno( new_seqno )
            if uid is not None:
                self.auto_select( uid )
    
    def auto_select( self, uid, history_nav = False ):
        # Unselect everything.
        seqno = self._mailbox.index( uid )
        if seqno is None:
            return
        seqno -= 1
        selected = []
        foo = self._listing.GetFirstSelected()
        while -1 < foo < self._listing.GetItemCount():
            selected.append( foo )
            foo = self._listing.GetNextSelected( foo )
        for x in selected:
            self._listing.SetItemState( x, 0, wx.LIST_STATE_SELECTED )
        # Now select the one we want.
        self._listing.EnsureVisible( seqno )
        self._history_nav = history_nav
        self._listing.SetItemState( seqno, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED, wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED )

    def select( self, event ):
        uid = self._mailbox.seqno(event.GetIndex()+1)
        self.select_uid( uid )

    def go_back( self, event ):
        if self._selected_pos > 0:
            self._selected_pos -= 1
            self.auto_select( self._selected_history[self._selected_pos], True )

    def go_forward( self, event ):
        if self._selected_pos < ( len( self._selected_history ) - 1 ):
            self._selected_pos += 1
            self.auto_select( self._selected_history[self._selected_pos], True )
        
    def select_uid( self, uid, history_nav = False ):
        if uid is None:
            return
        self._history_nav = self._history_nav or history_nav
        if not self._history_nav:
            if self._selected_pos != -1:
                self._selected_history = self._selected_history[0:self._selected_pos+1]
            self._selected_history.append( uid )
            self._selected_pos = len(self._selected_history) - 1
        self._history_nav = False
        self._selected = self._mailbox[uid]
        self.pvtb.ToggleTool( ID_DELETE, self._selected.flagged( '\\deleted' ) )
        self.pvtb.ToggleTool( ID_JUNK, self._selected.flagged( '$junk' ) )
        self.pvtb.EnableTool( ID_DELETE, self.check_flag_perm( '\\deleted', True ) is not None )
        self.pvtb.EnableTool( ID_JUNK, self.check_flag_perm( '$junk', True ) is not None )
        self.display()
        self.capture_setup( self._selected )
        self._mailbox.server().flush()

    def capture_setup( self, m ):
        self._capture_list.append( m )
        self._capture_list = self._capture_list[-10:]
        wx.GetApp().sm.get( wx.GetApp().home ).notify_ready( self.capture_all )

    def capture_all( self, s ):
        if not s.ready:
            return
        foo = self._capture_list
        self._capture_list = []
        for m in foo:
            m.fetch_capture_headers_and_notify( self.capture )
            m.fetch_list_headers_and_notify( self.list_capture )
            wx.GetApp().acap_home().store_flush( True )

    def capture( self, message ):
        ''' Perform capture of the addresses '''
        # Find the capture addressbook, if any.
        capture = None #get_any_option_str( 'mua.addressbook.capture' )
        # Spoof it for now, since I haven't "done" options.
        if capture is None:
            #self._controller.tree().acap().submit_command( 'STORE ("/addressbook/~/PolymerCapture" "addressbook.CommonName" "Polymer Captures")' )
            cap = infotrope.url.URL( wx.GetApp().home )
            capture = '/addressbook/~/PolymerCapture/'
        # If we have one, pull the from, and reconstruct it into the addressbook.
        if capture is not None:
            if len( message.envelope().From ) == 0:
                return
            email_address = message.envelope().From[0].address
            if email_address in self._captures:
                return
            search = infotrope.acap.search( 'SEARCH "%s" RETURN ("entry" "addressbook.CommonName.MIME" "addressbook.CommonName" "addressboook.Organisation" "addressbook.Email" "vendor.infotrope.addressbook.jabber-id") EQUAL "addressbook.Email" "i;octet" "%s"' % (capture,email_address), connection=wx.GetApp().acap_home(), notify_complete=self.capture_next )
            search.send()
            search.capture_message = message
            search.capture_base = capture
            class garbage_floxicator:
                "Dummy class to floxicate GC"
                def __init__( self, search ):
                    "Hold a reference"
                    self.search = search
                def __del__( self ):
                    "Kill it. GC is confused because __del__ method exists."
                    self.search = None
            search.capture_keeper = garbage_floxicator( search )

    def capture_next( self, search, state ):
        message = search.capture_message
        capture = search.capture_base
        search.capture_keeper = None # Break ref.
        email_address = message.envelope().From[0].address
        from_field = message.envelope().From[0].name
        found_specials = False
        if from_field is not None:
            for c in '\\()<>[]:;@,."': # Specials from RFC2822
                l = 0
                while from_field.find( c, l )!=-1:
                    found_specials = True
                    h = from_field.find( c, l )
                    from_field = from_field[0:h] + '\\' + from_field[h:]
                    l = h + 2
        if found_specials:
            from_field = '"'+from_field+'"'
        if len(search)==0:
            entryname = 'Polymer_' + email_address
            entry = {}
        else:
            entry = search[0]
            entryname = entry['entry']['value']
        store = False
        stuff = {}
        common_name = message.get_from_name().encode( 'utf-8' )
        jid = message.capture_header('jabber-id')
        if 'addressbook.CommonName.MIME' not in entry or entry['addressbook.CommonName.MIME']['value']!=from_field:
            if from_field is not None:
                store = True
                stuff['addressbook.CommonName.MIME'] = from_field
        if 'addressbook.CommonName' not in entry or entry['addressbook.CommonName']['value'] != common_name:
            store = True
            stuff['addressbook.CommonName'] = common_name
        if 'addressbook.Email' not in entry or entry['addressbook.Email']['value'] != email_address:
            store = True
            stuff['addressbook.Email'] = email_address
        if jid is not None and ('vendor.infotrope.addressbook.jabber-id' not in entry or jid != entry['vendor.infotrope.addressbook.jabber-id']['value']):
            store = True
            stuff['vendor.infotrope.addressbook.jabber-id'] = jid
        if store:
            wx.GetApp().acap_home().store( capture+entryname, stuff, True )
        self._captures.append( email_address )
        if len(self._captures)>25:
            self._captures = self._captures[-25:]

    def list_capture( self, message ):
        ''' Perform capture of the list addresses '''
        # Find the capture addressbook, if any.
        #print "LIST CAPTURE"
        capture = None #get_any_option_str( 'mua.addressbook.capture' )
        # Spoof it for now, since I haven't "done" options.
        if capture is None:
            #self._controller.tree().acap().submit_command( 'STORE ("/addressbook/~/PolymerCapture" "addressbook.CommonName" "Polymer Captures")' )
            capture = '/addressbook/~/PolymerCapture/'
        # If we have one, pull the from, and reconstruct it into the addressbook.
        if capture is not None:
            if message.list_header('list-id') is None:
                return
            email_address = email.Utils.parseaddr( message.list_header('list-id') )[1]
            if email_address=='':
                return
            if email_address in self._list_captures:
                return
            search = infotrope.acap.search( 'SEARCH "%s" RETURN ("entry" "addressbook.CommonName.MIME" "addressbook.CommonName" "addressbook.List.ID" "addressbook.Email") EQUAL "addressbook.List.ID" "i;ascii-casemap" "%s"' % (capture,email_address), connection=wx.GetApp().acap_home(), notify_complete=self.list_capture_next )
            search.send()
            search.capture_message = message
            search.capture_base = capture
            search.list_id = email_address
            class garbage_floxicator:
                "Dummy class to floxicate GC"
                def __init__( self, search ):
                    "Hold a reference"
                    self.search = search
                def __del__( self ):
                    "Kill it. GC is confused because __del__ method exists."
                    self.search = None
            search.capture_keeper = garbage_floxicator( search )
            
    def list_capture_next( self, search, state ):
        #print "LIST CAPTURE NEXT"
        capture = search.capture_base
        message = search.capture_message
        search.capture_keeper = None
        from_field = email.Utils.parseaddr( message.list_header('list-id') )[0]
        orig_from_field = from_field
        found_specials = False
        if from_field is not None:
            for c in '\\()<>[]:;@,."': # Specials from RFC2822
                l = 0
                while from_field.find( c, l )!=-1:
                    found_specials = True
                    h = from_field.find( c, l )
                    from_field = from_field[0:h] + '\\' + from_field[h:]
                    l = h + 2
        if found_specials:
            from_field = '"'+from_field+'"'
        post_address = message.list_header('list-post')
        if post_address is not None:
            post_address = [ x.strip()[8:-1] for x in post_address.split(',') if x.strip()[0:8]=='<mailto:' ][0]
        if len(search)==0:
            entryname = 'Polymer_' + search.list_id
            entry = {}
        else:
            entry = search[0]
            entryname = entry['entry']['value']
        store = False
        stuff = {}
        txt0 = orig_from_field
        txtu = u''
        if txt0!='':
            txtu = infotrope.encoding.decode_header( txt0 )
        else:
            txtu = search.list_id
        common_name = txtu.encode( 'utf-8' )
        if 'addressbook.CommonName.MIME' not in entry or entry['addressbook.CommonName.MIME']['value']!=from_field:
            if from_field is not None:
                store = True
                stuff['addressbook.CommonName.MIME'] = from_field
        if 'addressbook.CommonName' not in entry or entry['addressbook.CommonName']['value'] != common_name:
            store = True
            stuff['addressbook.CommonName'] = common_name
        if 'addressbook.List.ID' not in entry or entry['addressbook.List.ID']['value'] != search.list_id:
            store = True
            stuff['addressbook.List.ID'] = search.list_id
        if post_address is not None:
            if 'addressbook.Email' not in entry or entry['addressbook.Email']['value'] != post_address:
                store = True
                stuff['addressbook.Email'] = post_address
        if store:
            wx.GetApp().acap_home().store( capture+entryname, stuff, True )
        self._list_captures.append( search.list_id )
        if len(self._list_captures)>25:
            self._list_captures = self._list_captures[-25:]

    def resize_display( self, foo=False ):
        if foo:
            self._preview_master.SetVirtualSize( self._preview_master.GetMinSize() )
        #self._preview_sizer.Layout()
        #self._preview.Layout()
        self._preview_master_sizer.Layout()
        self._preview_master.Layout()
        self._preview_master.FitInside()
        self._preview_master.SetScrollRate( 20, 20 )
        if not foo:
            self.resize_display(True)

    def display( self, which=None ):
        while True:
            if len(self._preview_master_sizer.GetChildren()) == 0:
                break
            p = self._preview_master_sizer.GetItem( 0 )
            if p is None:
                break
            else:
                w = p.GetWindow()
                p = None
                self._preview_master_sizer.Detach( w )
                w.Destroy()
        self.resize_display( True )
        polymer.render.new_process( self._preview_master, self._selected, self.resize_display, self._preview_master_sizer )
        self.resize_display()
        #self.size_display( True )

    def view_item( self, str, part ):
        ft = wx.TheMimeTypesManager.GetFileTypeFromMimeType( part.type.lower()+'/'+part.subtype.lower() )
        ext = 'dat'
        if len(ft.GetExtensions()):
            ext = ft.GetExtensions()[0]
        filename = os.tempnam( None, "Polymer" ) + '.' + ext
        fp = file( filename, 'w' )
        fp.write( str )
        fp.close()
        wx.Execute( ft.GetOpenCommand( filename ) )



ID_PROPERTIES = wx.NewId()
ID_DELETE = wx.NewId()
ID_CREATE = wx.NewId()
ID_ACL = wx.NewId()


class TreeNodeMailbox(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, server, mi ):
        self._mi = weakref.ref(mi)
        display = mi.displaypath[-1]
        kids = mi.have_children()
        images = {}
        if mi.selectable():
            images[wx.TreeItemIcon_Normal] = 'icons/tree/inbox.png'
        else:
            images[wx.TreeItemIcon_Normal] = 'icons/tree/subfolder.png'
        polymer.treenav.TreeNode.__init__( self, tree, pid, display, kids, images )
        self._server = weakref.ref(server)
        self._page = None
        self._panel = None
        self._menu = None
        self._init = False
        self._operation = None
        self._colour = (0,0,0)
        if server.connect().have_capability('IMAP4REV1'):
            self.update_every = server.check_interval
        self.set_colour()
        mi.add_notify( self )

    def mi_notify_add( self, k, mi ):
        node = TreeNodeMailbox( self.tree(), self, self.server(), mi )
        if self._operation is not None:
            self.Expand()

    def mi_notify_del( self, k ):
        node = self.find( k )
        if node is not None:
            node.Delete()

    def mi_notify_change( self, k, mi ):
        node = self.find( k )
        if node is not None:
            node.set_mailbox_flags()

    def mi_notify_complete( self, *args ):
        if self._operation:
            self._operation.stop()
            self._operation = None
        if len(self.mi().children()) == 0:
            self.tree().SetItemHasChildren( self.id(), False )
            return False
        self.tree().SetItemHasChildren( self.id(), True )

    def mi( self ):
        return self._mi()
    
    def server( self ):
        return self._server()
            
    def drag_over( self, res ):
        self.Expand()
        return res

    def drop( self ):
        return True; # Probably.

    def data( self, stuff, how ):
        dst = self.server()._imap
        urls = [infotrope.url.URL(x) for x in stuff.GetURLs()]
        msgs = []
        msgs_mbx = {}
        print `urls`
        for src_u in urls:
            if src_u.scheme != 'imap':
                continue
            if src_u.uid is None:
                continue
            src = wx.GetApp().connection( src_u )
            src_m = src.mailbox( src_u.mailbox )
            src_msg = src_m[ src_u.uid ]
            if src is dst:
                if src_u.mailbox == self.mi().full_path:
                    continue
            su = str(src_msg.mailbox().uri())
            if su not in msgs_mbx:
                msgs_mbx[su] = [src_msg.mailbox(),[]]
            msgs_mbx[su][1].append(src_msg)
            msgs.append(src_msg)
        print `msgs`,`msgs_mbx`
        if not msgs:
            return wx.DragNone
        done = False
        if len(msgs_mbx)==1:
            for uri,d in msgs_mbx.items():
                mbx,msgs = d
                if self.mi().catenate_uri_ratifier(msgs[0].uri()) is not None:
                    ''' Local! '''
                    mbx.copy(msgs,self.mi().full_path)
                    done = True
        if not done:
            if not self.mi().append( *msgs ):
                return wx.DragNone
        if how==wx.DragMove:
            for uri,d in msgs_mbx.items():
                mbx,msgs = d
                freezer = mbx.freeze()
                for m in msgs:
                    m.flag('\\Deleted')
                freezer = None
        return how

    def begin_drag( self, event ):
        mi = self.mi()
        if mi is None:
            return
        url = mi.uri()
        title = mi.displaypath[-1]
        dobj = polymer.dragdrop.URLDataObject( url, title, self )
        ds = wx.DropSource( self.tree() )
        ds.SetData( dobj )
        res = ds.DoDragDrop( wx.Drag_DefaultMove )

    def set_mailbox_flags( self ):
        kids = self.mi().have_children()
        self.tree().SetItemHasChildren( self.id(), kids )
        self.set_colour()

    def set_colour( self ):
        if self.mi().selectable():
            self.tree().SetItemTextColour( self.id(), self._colour )
        else:
            self.tree().SetItemTextColour( self.id(), (128,128,128) )

    def get_panel( self ):
        if not self.mi().selectable():
            d = wx.MessageDialog( self.tree(), "This mailbox cannot hold messages.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()
            return
        try:
            mbx = self.mi().open() # Force an open here.
            return PanelMailbox( self.tree().notebook(), self )
        except infotrope.base.connection.exception,s:
            d = wx.MessageDialog( self.tree(), "Error while opening mailbox:\n" + str(s), "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()
            return

    def force_expand(self):
        self.mi().children()
        
    def try_expand( self, event ):
        if not self._operation:
            self._operation = polymer.progress.operation( self.name(), "Listing submailboxes" )
        self.mi().expand_children()
        return True

    def local_update( self, force=False ):
        if self.mi().selectable():
            if self.IsVisible() or force:
                status = self.mi().status( ['MESSAGES','UNSEEN'], self.local_update_complete )

    def local_update_complete( self, mailbox, status ):
        if status['UNSEEN'] == '0':
            self._colour = wx.BLACK
            self.tree().SetItemBold( self.id(), False )
        else:
            self._colour = wx.BLUE
            self.tree().SetItemBold( self.id(), True )
        self.set_colour()
        self.tree().SetItemText( self._id, "%s (%s/%s)" % ( self.name(), status['UNSEEN'], status['MESSAGES'] ) )
        self.tree().Refresh()

    def local_delete( self ):
        if self._panel is not None:
            self._panel.delete()
            self._panel = None

    def menu_delete( self, event ):
        if not self.mi().have_rights( 'x' ):
            return
        d = polymer.dialogs.MessageDialog( self.tree(), "Do you really want to delete this mailbox?\nAll messages in %s will be lost!" % self.name(), "Infotrope Polymer", wx.YES_NO )
        if wx.ID_YES!=d.ShowModal():
            return
        try:
            self.mi().delete()
        except infotrope.base.connection.exception, s:
            d = polymer.dialogs.ErrorDialog( self.tree(), "Couldn't delete %s:\n%s" % ( self.name(), s.msg ), "Infotrope Polymer" )
            d.ShowModal()
            return
        self.Delete()

    def menu_create( self, event ):
        if not self.mi().have_rights( 'k' ):
            return
        d = polymer.dialogs.TextEntryDialog( self.tree(), "New mailbox name", "Infotrope Polymer" )
        if wx.ID_OK!=d.ShowModal():
            return
        newname = d.GetValue()
        try:
            self.mi().create( newname )
        except infotrope.base.connection.exception, s:
            return
        self.try_expand( None )

    def menu_properties( self, event ):
        c = 'No'
        if self.mi().selectable():
            mbox = self.mi().open()
            if mbox.condstore_enabled():
                c = 'Yes'
        f = ' '.join( self.mi().get_flags() )
        p = self.mi().postaddress() or 'None'
        d = polymer.dialogs.PropsDialog( self.tree(), {'Mailbox name': self.name(), 'Mailbox path': self.mi().full_path, 'Rights': self.mi().get_rights(),  'Flags': f, 'Condstore': c, 'Postaddress': p}, "Infotrope Polymer" )
        d.ShowModal()
        d.Destroy()

    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            self._menu.Append( ID_CREATE, "Create submailbox" )
            wx.EVT_MENU( self._menu, ID_CREATE, self.menu_create )
            self._menu.Append( ID_DELETE, "Delete" )
            wx.EVT_MENU( self._menu, ID_DELETE, self.menu_delete )
            self._menu.Append( ID_PROPERTIES, "Properties" )
            wx.EVT_MENU( self._menu, ID_PROPERTIES, self.menu_properties )
        self.tree().PopupMenu( self._menu, event.GetPoint() )
