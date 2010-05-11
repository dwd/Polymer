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
import infotrope.acap
import polymer.addressbook
import wx.stc
import email.Utils
import email.Header
import email.Parser
#import email.MIMEText
import time
import StringIO
import polymer.encode
import polymer.dialogs
import infotrope.encoding
import infotrope.message
import weakref

stcargs = 2

ID_TO = wx.NewId()
ID_CC = wx.NewId()
ID_BCC = wx.NewId()
recipient_to_name = {
    ID_TO: 'To',
    ID_CC: 'Cc',
    ID_BCC: 'Bcc'
}

ID_MESSAGE_SEND = wx.NewId()
ID_MESSAGE_CLOSE = wx.NewId()
ID_MESSAGE_SAVE = wx.NewId()
ID_MESSAGE_QUIT = wx.NewId()

ID_MESSAGE_TO = wx.NewId()

ID_MESSAGE_CHECK = wx.NewId()
ID_MESSAGE_FORMAT = wx.NewId()
ID_MESSAGE_ATTACH = wx.NewId()
ID_MESSAGE_SAVESIG = wx.NewId()

class Attachment:
    def __init__( self, path, filename=None ):
        self.path = path
        self.filename = filename
        if self.filename is None and self.path is not None:
            import os.path
            self.filename = os.path.basename(self.path)
        self.type = None
        self.subtype = None
        self.description = None
        self.disposition = 'attachment'
        self.encoding = None
        self.transfer_encoding = None
        self.uris = []

    def set_type( self, mime_type ):
        ( self.type, self.subtype ) = mime_type.split('/')

    def find_mime( self ):
        import imghdr
        self.extension = imghdr.what( open( self.path, "rb" ) )
        if self.extension is not None:
            self.type = 'image'
        else:
            import sndhdr
            self.extension = sndhdr.what( self.path )
            if self.extension is not None:
                self.type = 'audio'
                self.extension = self.extension[0]
            else:
                import mimetypes
                extbr = self.path.rfind( '.' )
                self.extension = self.path[extbr+1:]
                t = mimetypes.guess_type( self.path )
                if t[0] is not None:
                    self.set_type( t[0] )
                    self.encoding = t[1]
                else:
                    ft = wx.TheMimeTypesManager.GetFileTypeFromExtension( self.extension )
                    if ft is not None:
                        self.set_type( ft.GetMimeType() )
                    else:
                        self.type = 'application'
                        self.subtype = 'octet-stream'
        if self.subtype is None:
            ft = wx.TheMimeTypesManager.GetFileTypeFromExtension( self.extension )
            self.subtype = ft.GetMimeType()[ft.GetMimeType().index('/')+1:]
        if self.type == 'text':
            f = open( self.path )
            s = f.read(1024) + f.readline()
            self.charset = 'x-unknown'
            for x in ['us-ascii','utf8','iso-8859-1']:
                try:
                    s.decode( x )
                    self.charset = x
                    break
                except:
                    pass

    def part( self ):
        if self.type is None:
            self.find_mime()
        p = infotrope.message.BasePart()
        if self.type =='text':
            p.raw_data = open(self.path).read()
            p.raw_data = p.raw_data.decode( self.charset )
        else:
            p.raw_data = open(self.path,"rb").read()
        p.mtype = self.type
        p.msubtype = self.subtype
        p.dtype = self.disposition
        p.dparams['filename'] = self.filename
        if self.description is not None:
            p.description = self.description
        for u in self.uris:
            p.saved_as( u )
        return p

    def image( self ):
        if self.type is None:
            self.find_mime()
        return wx.GetApp().get_mime_icon(self.type, self.subtype)

    def saved_as( self, u ):
        self.uris = u

class AttachmentMessage(Attachment):
    def __init__( self, msg, part=None ):
        descr = msg.envelope().Subject
        if descr is None:
            descr = u'Forwarded message'
        filename = None
        if part is not None:
            filename = part.filename()
            descr = part.description
        Attachment.__init__( self, None, filename or descr )
        self.filename = filename
        self.msg = msg
        self.spart = part or msg.parts()
        self.description = descr
        self.mpart = infotrope.message.MessagePart( self.msg, self.spart )

    def find_mime( self ):
        self.set_type( self.spart.type.lower()+'/'+self.spart.subtype.lower() )
        
    def part( self ):
        return self.mpart

    def saved_as( self, us ):
        for u in us:
            self.mpart.saved_as( u )

class AttachDropTarget( wx.PyDropTarget ):
    def __init__(self, msgbase):
        import polymer.dragdrop
        wx.PyDropTarget.__init__(self)
        self.msgbase = weakref.ref(msgbase)
        self.data = polymer.dragdrop.URLDataObject()
        self.SetDataObject(self.data)

    def OnDragOver(self, x, y, d):
        return wx.DragCopy

    def OnDrop(self, x, y):
        return True

    def OnData(self, x, y, r):
        try:
            import infotrope.url
            if not self.GetData():
                return wx.DragNone
            ut = self.data.GetURLs()
            uris = [infotrope.url.URL(utx) for utx in ut]
            for u in uris:
                if u.scheme in ['imap','imaps']:
                    if u.type not in ['MESSAGE','SECTION','PARTIAL']:
                        continue
                    srv = wx.GetApp().connection(u)
                    mbx = srv.mailbox(u.mailbox)
                    if mbx.uidvalidity()!=u.uidvalidity:
                        continue
                    msg = mbx[u.uid]
                    part = None
                    if u.section:
                        part = msg.parts().find_id(u.section)
                    self.msgbase().add_attachment(AttachmentMessage(msg, part))
                elif u.scheme == 'file':
                    if u.server:
                        import socket
                        if u.server!='localhost' and u.server!=socket.getfqdn():
                            continue
                    self.msgbase().add_attachment(Attachment(u.path.decode('urlencode')))
                else:
                    continue
            return wx.DragCopy
        except:
            pass
        return wx.DragNone

class MessageBase( wx.Frame ):
    def __init__( self, parent ):
        wx.Frame.__init__( self, parent, -1, "New Message - Infotrope Polymer", size=(600,400), name='polymer' )
        self.CreateStatusBar()
        self.SetIcon( wx.GetApp().icon )

        menu = wx.Menu()
        menu.Append( ID_MESSAGE_SEND, "&Send", "Send this message" )
        menu.Append( ID_MESSAGE_SAVE, "Sa&ve", "Save this message as a draft and continue" )
        menu.Append( ID_MESSAGE_CLOSE, "&Close", "Save this message as a draft and close" )
        menu.Append( ID_MESSAGE_QUIT, "&Discard", "Discard this message and close" )

        tools = wx.Menu()
        tools.Append( ID_MESSAGE_CHECK, "&Check Addresses", "Check addresses in this message" )
        tools.AppendCheckItem( ID_MESSAGE_FORMAT, "&Flowed Format", "Use Flowed Format" )
        tools.Check( ID_MESSAGE_FORMAT, True )
        tools.Append( ID_MESSAGE_ATTACH, "&Attach File", "Attach a file to this message" )
        tools.Append( ID_MESSAGE_SAVESIG, "&Save Signature", "Save this signature" )
        
        menuBar = wx.MenuBar()
        menuBar.Append( menu, "&File" )
        menuBar.Append( tools, "&Tools" )
        
        self.SetMenuBar( menuBar )

        p = wx.Panel( self, -1 )
        
        self._sizer = wx.BoxSizer( wx.VERTICAL )
        
        self._header_sizer = wx.FlexGridSizer( cols = 2, hgap = 5, vgap = 5 )
        
        self._header_sizer.Add( wx.StaticText( p, -1, "From" ) )
        froms = wx.GetApp().personalities().entries()
        while len(froms)==0:
            # No identies setup, but we want to send email.
            dlg = polymer.dialogs.MessageDialog( parent, "You're trying to send an email, but I don't know your email address yet.\nYou'll need these details handy.", "Warning - Infotrope Polymer", wx.OK|wx.ICON_INFORMATION )
            dlg.ShowModal()
            dlg = polymer.personality.IdentityEditCreate( self )
            dlg.ShowModal()
            l = len(wx.GetApp().personalities())
            froms = wx.GetApp().personalities().entries()
        self._from_sel_id = wx.NewId()
        froms_ui = [ polymer.encode.encode_ui( x.decode('utf-8') ) for x in froms ]
        from_ch = self.select_identity()
        self._from_sel = wx.Choice( p, self._from_sel_id, choices=froms_ui )
        self._from_sel.SetStringSelection( froms_ui[ from_ch ] )
        e = wx.GetApp().personalities()[ froms[ from_ch ] ]
        tmp_from =  email.Utils.formataddr( (e['personality.Real-Name'], e['personality.Return-Address']) )
        self._from = wx.TextCtrl( p, -1, tmp_from, style=wx.TE_READONLY )
        self._from_sizer = wx.BoxSizer( wx.HORIZONTAL )
        self._from_sizer.Add( self._from_sel, 0 )
        self._from_sizer.Add( self._from, 99, wx.EXPAND )
        self._from_sizer.Add( wx.Button( p, ID_MESSAGE_SEND, "Send" ), 0, wx.LEFT, border=5 )
        self._header_sizer.Add( self._from_sizer, 1, wx.EXPAND )

        all_recips = []
        self.headers = []
        for id in ID_TO,ID_CC,ID_BCC:
            rs = self.get_recipients( id )
            rsb = self.get_base_recipients( id, e )
            if rs is None:
                rs = rsb
            elif rsb is not None:
                rs += rsb
            if rs is not None:
                rs = [ r for r in rs if r._email_address not in all_recips ]
                all_recips += [ r._email_address for r in rs ]
                for r in rs:
                    ch = wx.Choice( p, -1, choices=recipient_to_name.values(), name=recipient_to_name[id])
                    recip = polymer.addressbook.RecipientCtrl( p, -1, r )
                    self._header_sizer.Add( ch, 0, wx.ALIGN_RIGHT )
                    self._header_sizer.Add( recip, 1, wx.EXPAND )
                    self.headers.append( (ch,recip) )
        self.add_header(p,None)
        subj = self.get_subject()
        self._subject = wx.TextCtrl( p, -1, subj )
        self._header_sizer.Add( wx.StaticText( p, -1, "Subject" ) )
        self._header_sizer.Add( self._subject, 1, wx.EXPAND )
        self.update_title()
        self._subject_changed = False

        self._header_sizer.AddGrowableCol( 1 )
        
        self._sizer.Add( self._header_sizer, 0, wx.ADJUST_MINSIZE|wx.EXPAND|wx.ALL, 10 )
        #self._text = wx.TextCtrl( p, -1, txte, style = wx.TE_MULTILINE|wx.TE_PROCESS_TAB|wx.TE_NOHIDESEL )
        self._sash = wx.SplitterWindow( p, -1 )
        self._text = wx.stc.StyledTextCtrl( self._sash, -1 )
        self._text.SetWrapMode( wx.stc.STC_WRAP_WORD )
        self._text.SetMargins( 0, 0 )
        for i in range(3):
            self._text.SetMarginWidth( i, 0 )
        if 'unicode' in wx.PlatformInfo:
            self._text.SetCodePage( wx.stc.STC_CP_UTF8 )
        self._text.SetText( '' )
        self.add_text( self._text )
        self.update_sig()
        self._text.SetSavePoint()
        self._attachments = self.get_attachments()
        self._attach_drop1 = AttachDropTarget(self)
        self._attach_panel = wx.Panel( self._sash, -1, style=wx.SUNKEN_BORDER )
        self._attach_sizer = wx.BoxSizer( wx.VERTICAL )
        p1 = wx.Panel( self._attach_panel, -1, style=wx.RAISED_BORDER )
        ss = wx.BoxSizer( wx.HORIZONTAL )
        ss.Add( wx.StaticText( p1, -1, "Attachments. Show as:" ), 0, wx.ALL, border=5 )
        c = wx.Choice( p1, -1, choices=[ 'Icons','List','Detail' ] )
        wx.EVT_CHOICE( c, -1, self.change_attach_display )
        ss.Add( c, 0, wx.ALL, border=5 )
        p1.SetSizer( ss )
        ss.Fit( p1 )
        p1.SetAutoLayout( True )
        self._attach_sizer.Add( p1, 0, wx.EXPAND )
        self._attach_list = wx.ListCtrl( self._attach_panel, -1, style=wx.LC_SMALL_ICON )
        self._attach_sizer.Add( self._attach_list, 1, wx.EXPAND )
        self._attach_panel.SetSizer( self._attach_sizer )
        self._attach_panel.SetAutoLayout( True )
        self._attach_sizer.Fit( self._attach_panel )
        self._attach_panel.SetDropTarget(self._attach_drop1)
        self._sizer.Add( self._sash, 1, wx.ADJUST_MINSIZE|wx.GROW|wx.EXPAND )
        self._attach_placeholder = wx.Panel( p, -1, style=wx.RAISED_BORDER )
        ss = wx.BoxSizer( wx.HORIZONTAL )
        ss.Add( wx.StaticText( self._attach_placeholder, -1, "No attachments (drag to here)",  ), 1, wx.ALL|wx.EXPAND, border=5 )
        self._attach_placeholder.SetSizer(ss)
        self._attach_placeholder.SetAutoLayout(True)
        self._attach_drop2 = AttachDropTarget(self)
        self._attach_placeholder.SetDropTarget(self._attach_drop2)
        ss.Fit(self._attach_placeholder)
        self._sizer.Add( self._attach_placeholder, 0, wx.EXPAND )
        self._sash.SplitHorizontally( self._text, self._attach_panel, -50 )

        p.SetSizer( self._sizer )
        p.SetAutoLayout( 1 )
        self._sizer.Fit( p )
        self._content_panel = p

        wx.EVT_MENU( self, ID_MESSAGE_SEND, self.message_send )
        wx.EVT_MENU( self, ID_MESSAGE_CLOSE, self.message_close )
        wx.EVT_MENU( self, ID_MESSAGE_SAVE, self.message_close )
        wx.EVT_MENU( self, ID_MESSAGE_QUIT, self.message_quit )
        wx.EVT_MENU( self, ID_MESSAGE_CHECK, self.message_check )
        wx.EVT_MENU( self, ID_MESSAGE_ATTACH, self.message_attach )
        wx.EVT_MENU( self, ID_MESSAGE_SAVESIG, self.save_sig )
        wx.EVT_CHOICE( self, -1, self.set_from_field )
        wx.EVT_BUTTON( self, ID_MESSAGE_TO, self.expand_addresses )
        wx.EVT_KEY_DOWN( self._text, self.key_down )
        wx.EVT_TEXT( self._subject, -1, self.update_title )
        wx.EVT_BUTTON( self, ID_MESSAGE_SEND, self.message_send )
        wx.EVT_CLOSE( self, self.close )
        self.Layout()
        if len(self._attachments)==0:
            self._sash.Unsplit()
        else:
            self.display_attach()
        self._attachments_changed = False
        self.set_saved()
        self._saved = None
        self._text_savedas_uri = []
        #self.set_from_field()

    def message_check( self, *args ):
        for ch, r in self.headers:
            r.resolve(self)
            
    def add_header( self, p, whom ):
        if whom is not None and whom is not self.headers[-1][-1]:
            return
        name = recipient_to_name[ID_TO]
        if whom and self.headers:
            name = self.headers[-1][0].GetStringSelection()
        ch = wx.Choice( p, -1, choices=recipient_to_name.values(), name=name)
        recip = polymer.addressbook.RecipientCtrl( p, -1 )
        self._header_sizer.Insert( 2 + (2*len(self.headers)), ch, 0, wx.ALIGN_RIGHT )
        self._header_sizer.Insert( 3 + (2*len(self.headers)), recip, 1, wx.EXPAND )
        self.headers.append( (ch,recip) )
        self._header_sizer.Layout()
        self._sizer.Layout()
        self.Refresh()

    def close( self, event ):
        if self.discard_check():
            event.Skip()

    def discard_check( self ):
        if not self.unchanged():
            if wx.ID_YES == polymer.dialogs.MessageDialog( self, "Draft unsaved, really quit?", "Infotrope Polymer", wx.ICON_INFORMATION|wx.YES_NO ).ShowModal():
                return True
            return False
        return True

    def unchanged( self ):
        if self._from_changed:
            return False
        if self._subject_changed:
            return False
        if self._attachments_changed:
            return False
        if self._text.GetModify():
            return False
        #for x in self.recipients.values():
        #    if x.GetModify():
        #        return False
        #return True
        return False

    def set_saved( self ):
        self._from_changed = False
        self._subject_changed = False
        self._attachments_changed = False
        self._text.SetSavePoint()
        #for x in self.recipients.values():
        #    x.SetSavePoint()

    def update_title( self, event=None ):
        txt = self._subject.GetValue()
        if len(txt)==0:
            txt = polymer.encode.encode_ui( u'New Message' )
        txt += polymer.encode.encode_ui( u' - Infotrope Polymer' )
        self.SetTitle( txt )

    def message_attach( self, event ):
        dlg = wx.FileDialog( self, "Attachment", style=wx.OPEN )
        if wx.ID_OK==dlg.ShowModal():
            self.add_attachment(Attachment(dlg.GetPath(), dlg.GetFilename()))

    def add_attachment(self, a):
        self._attachments.append(a)
        self._attachments_changed = True
        self.display_attach()
        
    def display_attach( self, event=None ):
        self._attach_list.ClearAll()
        if len(self._attachments)!=0:
            sample = self._attachments[0].image()
            self._attach_img_list = None
            off = 0
            atts = []
            for x in self._attachments:
                icon = x.image()
                if icon is not None:
                    if self._attach_img_list is None:
                        self._attach_img_list = wx.ImageList( 16, 16 )
                    off = self._attach_img_list.AddIcon( icon )
                    atts.append( ( x, off ) )
                else:
                    atts.append( ( x, None ) )
            if self._attach_img_list is not None:
                self._attach_list.SetImageList( self._attach_img_list, wx.IMAGE_LIST_NORMAL )
                self._attach_list.SetImageList( self._attach_img_list, wx.IMAGE_LIST_SMALL )
            poing = 0
            for x in atts:
                descr = x[0].description
                if descr is None:
                    descr = x[0].filename
                if descr is None:
                    descr = x[0].type + '/' + x[0].subtype
                if x[1] is None:
                    self._attach_list.InsertStringItem( poing, descr )
                else:
                    self._attach_list.InsertImageStringItem( poing, descr, x[1] )
                poing += 1
            self._attach_panel.Show(True)
            self._attach_panel.Update()
            self._sash.SplitHorizontally( self._text, self._attach_panel, -100 )
            self._sizer.Show(self._attach_placeholder, False)
            self._sizer.Layout()
        else:
            self._attach_panel.Show(False)
            self._attach_panel.Update()
            self._sash.UnSplit()
            self._sizer.Show(self._attach_placeholder)
            self._sizer.Layout()

    def change_attach_display( self, event ):
        pass

    def split_quote( self, st ):
        start,end = self._text.GetSelection()
        adding = ''
        #print "Splitting quite, ending at",`unichr(self._text.GetCharAt( end-1 ))`,`unichr(self._text.GetCharAt( end ))`, `unichr(self._text.GetCharAt( end + 1 ))`
        if self._text.GetCharAt( end-1 )!=ord('\n'):
            txt = u'>'*st + u' '
            adding = polymer.encode.encode_ui( txt )
        cr = polymer.encode.encode_ui( u'\n' )
        self._text.ReplaceSelection( cr )
        self._text.StartStyling( start, 0xFF )
        self._text.SetStyling( len(cr), st )
        start,end = self._text.GetSelection()
        self._text.ReplaceSelection( cr+adding )
        self._text.StartStyling( start+len(cr), 0xFF )
        self._text.SetStyling( len(adding), st )
        self._text.SetSelection( start, end )

    def key_down( self, event ):
        kk = event.GetKeyCode()
        start,end = self._text.GetSelection()
        st = self._text.GetStyleAt( end )
        if kk > wx.WXK_START:
            event.Skip()
            return
        if st:
            if kk==wx.WXK_RETURN or kk==wx.WXK_NUMPAD_ENTER:
                self.split_quote( st )
                return
            if kk==wx.WXK_DELETE or kk==wx.WXK_BACK:
                if start!=end:
                    self._text.ReplaceSelection('')
                    self.split_quote( st )
                    return
            wx.Bell()
            return
        #if kk>127 and kk < 256:
        #    self._text.ReplaceSelection( polymer.encode.encode_ui( unichr(kk) ) )
        #    return
        event.Skip()
        return

    def expand_addresses( self, event ):
        r = polymer.addressbook.Recipient( self.GetParent(), self._to.GetValue() )
        self._to.SetValue( r.header()[0] )

    def overflow( self, event ):
        pass

    def remove( self, event ):
        pass

    def set_from_field( self, event=None ):
        e = wx.GetApp().personalities()[ polymer.encode.decode_ui( self._from_sel.GetStringSelection() ).encode( 'utf-8' ) ]
        self._from.SetValue( email.Utils.formataddr( (e['personality.Real-Name'], e['personality.Return-Address']) ) )
        if event is not None:
            event.Skip()
        self._from_changed = True
        self.update_sig()

    def add_text( self, stc ):
        ''' Adds the initial message text '''
        pass

    def get_recipients( self, id ):
        ''' Return initial recipients '''
        return None

    def get_base_recipients( self, id, e ):
        ''' Return default recipients '''
        if id == ID_CC:
            if e['personality.Header.CC'] is not None:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=x[0], email=x[1] ) for x in email.Utils.getaddresses( e['personality.Header.CC'] ) ]
        elif id == ID_BCC:
            if e['personality.Header.BCC'] is not None:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=x[0], email=x[1] ) for x in email.Utils.getaddresses( e['personality.Header.BCC'] ) ]            

    def get_attachments( self ):
        return []

    def AppendText( self, s ):
        '''Different versions use a different number of arguments.'''
        global stcargs
        if stcargs==3:
            self._text.AppendText( len(s), s )
        else:
            try:
                self._text.AppendText( s )
            except TypeError:
                stcargs = 3
                self.AppendText( s )

    def update_sig( self, sep_always=True, with_sig=None ):
        sigpos = -1
        sigsep = '-- \n'
        for n in range( self._text.GetLineCount() ):
            if self._text.GetLine( n ) == '-- \n':
                sigpos = self._text.PositionFromLine( n )
        if sigpos != -1:
            sels,sele = self._text.GetSelection()
            self._text.SetSelection( sigpos, self._text.GetLength() )
            self._text.ReplaceSelection( '' )
            self._text.SetSelection( sels,sele )
        else:
            lastline = self._text.GetLine( self._text.GetLineCount() )
            if lastline[-1:]!='\n':
                sigsep = '\n-- \n'
        e = wx.GetApp().personalities()[ self._from_sel.GetSelection() ]
        if sep_always:
            self.AppendText( sigsep )
        if with_sig is None:
            with_sig = e['personality.Signature.Text']
            if with_sig is not None:
                with_sig.replace( '\r', '' )
        if with_sig:
            if not sep_always:
                self.AppendText( sigsep )
            self.AppendText( with_sig )

    def get_sig( self ):
        sigpos = -1
        sig = None
        for n in range( self._text.GetLineCount() ):
            if self._text.GetLine( n ) == '-- \n':
                sigpos = self._text.PositionFromLine( n+1 )
        if sigpos != -1:
            sels,sele = self._text.GetSelection()
            self._text.SetSelection( sigpos, self._text.GetLength() )
            sig = self._text.GetSelectedText()
            self._text.SetSelection( sels,sele )
        return sig

    def save_sig( self, event ):
        e = wx.GetApp().personalities()[ self._from_sel.GetSelection() ]
        if e.cont_url.root_user() not in wx.GetApp().sm:
            return
        sig = self.get_sig()
        sig = sig.replace('\n','\r\n')
        if e['personality.Signature.Text'] is not None:
            if sig is None:
                wx.GetApp().connection( e.cont_url ).store( e.entry_url().path, {'personality.Signature.Text': None} )
                return
        if sig != e['personality.Signature.Text']:
            wx.GetApp().connection( e.cont_url ).store( e.entry_url().path, {'personality.Signature.Text': sig.encode('utf-8')} )
            
    def message_send( self, event ):
        import infotrope.url
        e = wx.GetApp().personalities()[ self._from_sel.GetSelection() ]
        emails = []
        emails = [x['email.server.IMAP'] for x in wx.GetApp().email() if str(x['email.personality']) == str(e.entry_url())]
        msg,addresses = self.prepare_message( e )
        if msg is None:
            return
        if len(addresses)==0:
            dlg = polymer.dialogs.MessageDialog( self, "No recipients", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            dlg.ShowModal()
            return
        smtp = wx.GetApp().sm.get( e['personality.Server.SMTP'] )
        sender = e['personality.Return-Address']
        import infotrope.transmit
        tran = infotrope.transmit.Transmit( msg, wx.GetApp(), smtp, sender, drafts=e['vendor.infotrope.personality.Drafts.IMAP'], localimap=emails )
        for x in addresses:
            tran.add_recipient( x )
        u = e['personality.File-Into.IMAP']
        if u is not None:
            if u.username is None:
                u.username = e['vendor.infotrope.personality.File-Into.IMAP.username']
            tran.add_recipient( u )
            msg.msg_flags = ['$MDNSent','\\Seen','\\Draft']
        tran.transmit( self.transmit_complete )
        self.temp_personality = e
        self.temp_msg = msg
        self.Show( False )

    def transmit_complete( self, st, error=None ):
        if st:
            #print "Processing submitted message."
            mu = self.temp_personality['personality.File-Into.IMAP']
            if mu is not None and mu.username is None:
                mu.username = e['vendor.infotrope.personality.File-Into.IMAP.username']
            if mu is not None:
                #print "Scanning URIs for match with",`mu`
                #print "URIs are",`self.temp_msg.uri`
                for u in self.temp_msg.uri:
                    #print " Checking",`u`,`u.root_user()`,`mu.root_user()`
                    if str(u.root_user()) == str(mu.root_user()):
                        #print " root_user match"
                        if u.mailbox == mu.mailbox:
                            #print " mailbox match"
                            server = wx.GetApp().connection(u)
                            mbox = server.mailbox(u.mailbox)
                            msg = mbox[u.uid]
                            msg.flag('$Submitted')
                            #print "Flagged message"
                            break
            self.post_send( self.temp_personality, self.temp_msg )
            wx.GetApp().status( "Message sent" )
            self.set_saved()
            self.Close( False )
        else:
            self.Show( True )
            if not error:
                error = u'Unknown failure'
            if isinstance(error,list):
                error = '\n'.join(error)
            d = polymer.dialogs.MessageDialog( self, error, "Send Failure", wx.ICON_ERROR|wx.OK )
            d.ShowModal()
        
    def prepare_message( self, e ):
        """
        Create format/flowed message, and hand it to an ESMTP submission server.
        """
        if self.unchanged() and self._saved is not None:
            return self._saved,self._saved_addresses
        import infotrope.message
        msg = infotrope.message.Message()
        msg.froms.append( infotrope.message.Address( e['personality.Return-Address'], e['personality.Real-Name'] ) )
        which = {}
        sane = True
        rev = {}
        for id,name in recipient_to_name.items():
            rev[name] = id
            which[id] = []
        for ch,r in self.headers:
            id = rev[ch.GetStringSelection()]
            if r.GetValue() == '':
                continue
            v = r.resolve( self )
            if v is None or v.email_addresses() is None:
                sane = False
                continue
            which[id].append(v)
        if not sane:
            dlg = polymer.dialogs.MessageDialog( self, "Not all recipients are known", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            dlg.ShowModal()
            return None,None
        addresses = []
        for r in which[ID_TO]:
            if r.email_addresses()[0].startswith('news:'):
                msg.newsgroups += [x[5:] for x in r.email_addresses()]
            else:
                msg.to.append( infotrope.message.Address( None, header=r.header() ) )
            addresses += r.email_addresses()
        for r in which[ID_CC]:
            if r.email_addresses()[0].startswith('news:'):
                msg.newsgroups += [x[5:] for x in r.email_addresses()]
            else:
                msg.cc.append( infotrope.message.Address( None, header=r.header() ) )
            addresses += r.email_addresses()
        for r in which[ID_BCC]:
            if r.email_addresses()[0].startswith('news:'):
                msg.newsgroups += [x[5:] for x in r.email_addresses()]
            addresses += r.email_addresses()
        msg.subparts.append( infotrope.message.FlowedTextPart( polymer.encode.decode_ui( self._text.GetText() ) ) )
        if self._text_savedas_uri and not self._text.GetModify():
            for n in self._text_savedas_uri:
                msg.subparts[0].saved_as( n )
        msg.subparts += [ x.part() for x in self._attachments ]
        subj = polymer.encode.decode_ui( self._subject.GetValue() )
        if len(subj):
            msg['Subject'] = subj
        self.add_headers( msg )
        return msg,addresses
        
    def message_close( self, event ):
        e = wx.GetApp().personalities()[ self._from_sel.GetSelection() ]
        if e['vendor.infotrope.personality.Drafts.IMAP'] is None:
            dlg = polymer.dialogs.ErrorDialog( self, "No drafts folder defined for this personality.", "Infotrope Polymer" )
            dlg.ShowModal()
            return
        msg,addresses = self.prepare_message( e )
        if msg is None:
            return
        u = e['vendor.infotrope.personality.Drafts.IMAP']
        drsrv = wx.GetApp().connection( u )
        mi = drsrv.mbox_info( u.mailbox )
        msg.msg_flags = ['\\Draft', '$MDNSent', '\\Seen']
        mi.append( msg )
        self._saved = msg
        self._saved_addresses = addresses
        self._text_savedas_uri = msg.subparts[0].uri
        for x in range( len(self._attachments) ):
            self._attachments[x].saved_as( msg.subparts[x+1].uri )
        self.set_saved()
        if event.GetId()==ID_MESSAGE_CLOSE:
            self.Close( False )

    def message_quit( self, event ):
        self.Close( False )

    def add_headers( self, msg ):
        ''' Add any extra headers. '''
        pass

    def get_subject( self ):
        ''' Return a suitable default subject line '''
        return u''

    def post_send( self, p, m ):
        ''' Do anything needed after message has been submitted for sending. '''
        pass

    def select_identity( self ):
        ''' Pick an identity to use by default. '''
        if self.GetParent() is not None:
            a = self.GetParent().notebook.GetSelection()
            if a!=-1:
                b = self.GetParent().notebook.GetPage(a)
                if isinstance(b,polymer.imap.PanelMailbox):
                    c = b._controller.server()
                    d = c._email_entry
                    if 'email.personality' not in d:
                        return 0
                    e = d['email.personality']
                    if e is None:
                        return 0
                    f = e.path.split('/')[-1]
                    if f not in wx.GetApp().personalities():
                        return 0
                    return wx.GetApp().personalities().index( f )
        return 0

    #def __del__( self ):
    #    print " ** ** COMPOSER CLOSE ** ** "
    #    print `self`

class NewMessage( MessageBase ):
    def __init__( self, parent ):
        MessageBase.__init__( self, parent )

class MailtoMessage( NewMessage ):
    def __init__( self, parent, url ):
        import urllib
        self.url = infotrope.url.URL( url )
        self.params = {}
        if self.url.query is not None:
            for x in self.url.query.split( '&' ):
                y = x.split('=')
                self.params[urllib.unquote(y[0]).lower()] = urllib.unquote(y[1])
        NewMessage.__init__( self, parent )

    def add_text( self, tc ):
        if 'body' in self.params:
            tc.AddText( self.params['body'] )

    def get_subject( self ):
        if 'subject' in self.params:
            return self.params['subject'].decode('utf-8')
        return u''

    def get_recipients( self, id ):
        import urllib
        if id==ID_TO:
            t = [ polymer.addressbook.Recipient( self.GetParent(), field=x[0], email=x[1] ) for x in email.Utils.getaddresses( [urllib.unquote(self.url.path)] ) ]
            if 'to' in self.params:
                t += [ polymer.addressbook.Recipient( self.GetParent(), field=x[0], email=x[1] ) for x in email.Utils.getaddresses( [self.params['to']] ) ]
            return t
        if id==ID_CC:
            if 'cc' in self.params:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=x[0], email=x[1] ) for x in email.Utils.getaddresses( [self.params['cc']] ) ]
        if id==ID_BCC:
            if 'bcc' in self.params:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=x[0], email=x[1] ) for x in email.Utils.getaddresses( [self.params['bcc']] ) ]

    def add_headers( self, msg ):
        for x,y in self.params.items():
            if x not in ['body','subject','to','cc','bcc']:
                msg[x] = y

class MessageReply( MessageBase ):
    def __init__( self, parent, replyto ):
        self.replyto = replyto
        MessageBase.__init__( self, parent )

    def select_identity( self ):
        frmap = {}
        idx = 0
        for e in wx.GetApp().personalities().entries():
            frmap[ wx.GetApp().personalities()[e]['personality.Return-Address'] ] = idx
            idx += 1
        # First, search TO. Then CC, etc. Then FROM.
        for em in self.replyto.envelope().To:
            if em.address in frmap:
                return frmap[em.address]
        for em in self.replyto.envelope().CC:
            if em.address in frmap:
                return frmap[em.address]
        for em in self.replyto.envelope().BCC:
            if em.address in frmap:
                return frmap[em.address]
        for em in self.replyto.envelope().From:
            if em.address in frmap:
                return frmap[em.address]
        return MessageBase.select_identity( self )

    def add_text( self, tc ):
        tc.StyleSetForeground( 1, "#009C46" )
        tc.StyleSetForeground( 2, "#DA6A00" )
        tc.StyleSetForeground( 3, "#6404B5" )
        tc.AddText( polymer.encode.encode_ui( u"On %s, %s wrote:\n" % ( time.asctime( self.replyto.get_sent_date_real() ), self.replyto.get_from_name() ) ) )
        part = self.replyto.parts()
        for p in part.children:
            if p.part_id=='TEXT':
                part = p
                break
        best,pref = part.find( 'TEXT', {'HTML':1,'PLAIN':2} )
        if best is not None:
            if best.subtype=='PLAIN':
                if 'FORMAT' in best.params and best.params['FORMAT'].upper()=='FLOWED':
                    paras = infotrope.flowed.parse( self.replyto.body( best ) )
                    txt = u''
                    for p in paras:
                        p.quote_depth += 1
                        txt = polymer.encode.encode_ui( p.asText() )
                        st = p.quote_depth
                        if st > 3:
                            st = 3
                        l = tc.GetLength()
                        tc.AddText( txt )
                        tc.StartStyling( l, 31 )
                        tc.SetStyling( len(txt), st )
                else:
                    f = StringIO.StringIO( self.replyto.body( best ) )
                    for l in f:
                        l = l.rstrip(' \r\n')
                        txt = polymer.encode.encode_ui( u'> ' + l + '\n' )
                        l = tc.GetLength()
                        tc.AddText( txt )
                        tc.StartStyling( l, 31 )
                        tc.SetStyling( len(txt), 1 )
            else:
                txt = polymer.encode.encode_ui( u'> [' + best.type + '/' + best.subtype + ' body]\n' )
                l = tc.GetLength()
                tc.AddText( txt )
                tc.StartStyling( l, 31 )
                tc.SetStyling( len(txt), 1 )

    def add_headers( self, msg ):
        refs = self.replyto.reply_header('references')
        if refs is not None:
            refs = refs.replace('\r',' ')
            refs = refs.replace('\n',' ')
            refs = ' '.join( [ x for x in refs.split(' ') if len(x) ] )
        mid = self.replyto.envelope().MessageID
        if refs is None:
            msg['References'] = mid
        else:
            msg['References'] = refs + ' ' + mid
        msg['In-Reply-To'] = mid

    def get_recipients( self, id ):
        raise "Abstract MessageReply called."

    def get_subject( self ):
        subj = self.replyto.envelope().Subject
        if subj is None:
            subj = 'Your Message'
        if subj.strip()[0:3].upper()!='RE:':
            subj = 'Re: '+subj
        return subj

    def post_send( self, personality, msg ):
        try:
            self.replyto.flag( '\\Answered' )
        except:
            d = wx.MessageDialog( self, "Warning: Couldn't set an Answered flag.\nYour mail has still been sent, however.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()

class MessageReplySender( MessageReply ):
    def __init__( self, parent, replyto ):
        MessageReply.__init__( self, parent, replyto )

    def get_recipients( self, id ):
        """ We want to reply to the sender, using the reply-to address if it's set. """
        if id==ID_TO:
            # Conventiently, this is stored all ready in the envelope.
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().ReplyTo ]

class MessageReplyDirect( MessageReply ):
    def __init__( self, parent, replyto ):
        MessageReply.__init__( self, parent, replyto )

    def get_recipients( self, id ):
        """ We want to reply to the sender, ignoring any Reply-To header. """
        if id==ID_TO:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().From ]

class MessageReplyList( MessageReply ):
    def __init__( self, parent, replyto ):
        self.list_address = None
        self.list_name = None
        self.newsgroups = None
        if replyto.list_header( 'List-Post' ) is not None:
            uris = [ infotrope.url.URL( xx.strip( ' \r\n\t<>' ) ) for xx in replyto.list_header( 'List-Post' ).split(',') ]
            for x in uris:
                if x.scheme == 'mailto':
                    self.list_address = x.path
        if self.list_address is None:
            ng = replyto.list_header( 'Newsgroups', True )
            if ng is not None:
                self.newsgroups = ['news:'+x for x in ng.split(',')]
        if self.list_address is None and self.newsgroups is None:
            a = wx.GetApp().acap_home()
            s = infotrope.acap.search( 'SEARCH "/option/~/vendor.infotrope/polymer/folders/" RETURN ("option.vendor.infotrope.mailing-list") EQUAL "option.vendor.infotrope.folder-name" "i;octet" "%s"' % replyto.mailbox().uri().asString(), connection=a )
            s.wait()
            if len(s)>0:
                e = s[0]
                if e['option.vendor.infotrope.mailing-list']['value'] is not None:
                    self.list_address = e['option.vendor.infotrope.mailing-list']['value']
        if self.list_name is None and self.newsgroups is None:
            if replyto.list_header( 'List-ID' ) is not None:
                x = email.Utils.parseaddr( replyto.list_header( 'List-ID' ) )
                if x[0]=='':
                    if x[1]!='':
                        self.list_name = x[1]
                else:
                    self.list_name = x[0]
        if self.list_name is None:
            self.list_name = self.list_address
        if self.list_address is None and self.newsgroups is None:
            dlg = wx.MessageDialog( parent, "There are no mailing list headers, and the folder has no default. I'm stuck. Things will now crash.", "Infotrope Polymer", wx.ICON_INFORMATION )
            dlg.ShowModal()
        MessageReply.__init__( self, parent, replyto )

    def list_recipients( self ):
        """ We want to reply only to the list address. """
        if self.newsgroups is not None:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=x ) for x in self.newsgroups ]
        else:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=self.list_name, email=self.list_address ) ]

    def get_recipients( self, id ):
        if id == ID_TO:
            return self.list_recipients()

class MessageReplyListSender( MessageReplyList ):
    def __init__( self, parent, replyto ):
        MessageReplyList.__init__( self, parent, replyto )

    def get_recipients( self, id ):
        """ We want to reply to the sender, using the reply-to address if it's set. """
        if id==ID_CC:
            # This might be in headers. Or might not. Or might be guessable given the sender. It's all such hard work.
            return self.list_recipients()
        if id==ID_TO:
            # If the list has reply-to set, we should probably ignore it here.
            if self.replyto.envelope().ReplyTo[0].address==self.list_address:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().From ]
            else:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().ReplyTo ]

class MessageReplyListOnlySender( MessageReplyList ):
    def __init__( self, parent, replyto ):
        MessageReplyList.__init__( self, parent, replyto )

    def get_recipients( self, id ):
        """ We want to reply to the sender, using the reply-to address if it's set. """
        if id==ID_TO:
            # If the list has reply-to set, we should probably ignore it here.
            if self.replyto.envelope().ReplyTo[0].address==self.list_address:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().From ]
            else:
                return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().ReplyTo ]

class MessageReplyAll( MessageReply ):
    def __init__( self, parent, replyto ):
        self.my_addresses = [ wx.GetApp().personalities()[ x ]['personality.Return-Address'] for x in wx.GetApp().personalities().entries() ]
        MessageReply.__init__( self, parent, replyto )

    def get_recipients( self, id ):
        """ We want to reply to the sender, using the reply-to address if it's set. """
        if id==ID_TO:
            # Conventiently, this is stored all ready in the envelope.
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().ReplyTo ]
        if id==ID_CC:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.replyto.envelope().CC + self.replyto.envelope().To if xx.address not in self.my_addresses ]

class MessageForwardQuoted( MessageReply ):
    def __init__( self, parent, replyto ):
        MessageReply.__init__( self, parent, replyto )

    def get_subject( self ):
        if self.replyto.envelope().Subject is None:
            return "Fwd: Forward"
        else:
            return "Fwd: " + self.replyto.envelope().Subject

    def get_recipients( self, id ):
        pass

    def post_send( self, personality, msg ):
        try:
            self.replyto.flag( '$Forwarded' )
        except:
            d = wx.MessageDialog( self, "Warning: Couldn't set a Forwarded flag.\nYour mail has still been sent, however.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()

class MessageForwardMime( MessageBase ):
    def __init__( self, parent, fwd ):
        self.fwd = fwd
        MessageBase.__init__( self, parent )

    def get_attachments( self ):
        if not isinstance(self.fwd,list):
            return [ AttachmentMessage( self.fwd ) ]
        else:
            return [ AttachmentMessage(x) for x in self.fwd ]
        
    
    def get_subject( self ):
        if not isinstance(self.fwd,list):
            if self.fwd.envelope().Subject is None:
                return "Fwd: Forward"
            else:
                return "Fwd: " + self.fwd.envelope().Subject
        else:
            return "Fwd: Forwarded Messages"

    def post_send( self, personality, msg ):
        fwd = self.fwd
        if not isinstance(fwd,list):
            fwd = [self.fwd]
        def sort_messages(msg1, msg2):
            s1, s2 = msg1.server().uri.asString(), msg2.server().uri.asString()
            if s1 < s2:
                return -1
            if s1 > s2:
                return 1
            s1, s2 = msg1.mailbox().uri().asString(), msg2.mailbox().uri().asString()
            if s1 < s2:
                return -1
            if s1 > s2:
                return 1
            return msg1.uid() - msg2.uid()
        fwd.sort(cmp=sort_messages)
        all_ok = True
        cm = None
        cml = None
        for x in fwd:
            try:
                if cm is not x.mailbox():
                    cm = x.mailbox()
                    cml = cm.freeze()
                x.flag( '$Forwarded' )
            except:
                all_ok = False
        cml = None
        if not all_ok:
            d = wx.MessageDialog( self, "Warning: Couldn't set a Forwarded flag.\nYour mail has still been sent, however.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()

class MessageDraft( MessageBase ):
    def __init__( self, parent, message ):
        self.msg = message
        p = self.msg.parts()
        tp = p.find_id( '1' )
        if tp.type!='TEXT' or tp.subtype!='PLAIN':
            dlg = polymer.dialogs.ErrorDialog( parent, "Message too complex for draft handling.\nSorry.", "Infotrope Polymer" )
            dlg.ShowModal()
            return
        self.text_part = tp
        MessageBase.__init__( self, parent )
        self._text_savedas_uri = [infotrope.url.URL( str(self.msg.uri()) + '/;SECTION=1' )]
        
    def get_attachments( self, p=None ):
        if p is None:
            p = self.msg.parts()
        atts = []
        for sp in p.children:
            if sp.part_id not in ['HEADER','1']:
                if sp.children:
                    atts += self.get_attachments( sp )
                else:
                    atts.append( AttachmentMessage( self.msg, sp ) )
        return atts

    def get_subject( self ):
        return self.msg.envelope().Subject or ''

    def get_recipients( self, id ):
        if id == ID_TO:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.msg.envelope().To ]
        elif id == ID_CC:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.msg.envelope().CC ]
        elif id == ID_BCC:
            return [ polymer.addressbook.Recipient( self.GetParent(), field=xx.name, email=xx.address ) for xx in self.msg.envelope().BCC ]
            
    def select_identity( self ):
        frmap = {}
        idx = 0
        for e in wx.GetApp().personalities().entries():
            frmap[ wx.GetApp().personalities()[e]['personality.Return-Address'] ] = idx
            idx += 1
        # Just search From.
        for em in self.msg.envelope().From:
            if em.address in frmap:
                return frmap[em.address]
        return MessageBase.select_identity( self )

    def add_text( self, tc ):
        tc.StyleSetForeground( 1, "#009C46" )
        tc.StyleSetForeground( 2, "#DA6A00" )
        tc.StyleSetForeground( 3, "#6404B5" )
        best = self.msg.parts().find_id('1')
        if best is not None:
            if best.subtype=='PLAIN':
                if 'FORMAT' in best.params and best.params['FORMAT'].upper()=='FLOWED':
                    paras = infotrope.flowed.parse( self.msg.body( best ) )
                    txt = u''
                    for p in paras:
                        txt = polymer.encode.encode_ui( p.asText() )
                        st = p.quote_depth
                        if st > 3:
                            st = 3
                        l = tc.GetLength()
                        tc.AddText( txt )
                        tc.StartStyling( l, 31 )
                        tc.SetStyling( len(txt), st )
                else:
                    f = StringIO.StringIO( self.msg.body( best ) )
                    for l in f:
                        br = l.find( '\r' )
                        if br!=-1:
                            l = l[0:br]
                        txt = polymer.encode.encode_ui( l + '\n' )
                        l = tc.GetLength()
                        tc.AddText( txt )

    def add_headers( self, msg ):
        refs = self.msg.reply_header( 'references' )
        irt = self.msg.envelope().InReplyTo
        if refs is not None:
            msg['References'] = refs
        if irt is not None:
            msg['In-Reply-To'] = irt

    def post_send( self, personality, msg ):
        try:
            self.msg.flag( '\\Deleted' )
        except:
            d = wx.MessageDialog( self, "Warning: Couldn't delete draft\nYour mail has still been sent, however.", "Infotrope Polymer", wx.ICON_ERROR|wx.OK )
            d.ShowModal()

