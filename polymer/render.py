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
import wx.html
import wx.stc
from polymer.encode import *
import infotrope.encoding
import infotrope.flowed
import infotrope.url
from StringIO import StringIO
import os
import time
from polymer.expando import *

display_factories = { 'TEXT': {}, 'APPLICATION': {}, 'IMAGE': {}, 'AUDIO': {}, 'VIDEO':{}, 'MESSAGE':{}, 'MODEL':{}, 'MULTIPART':{} }
supported_image_types = None

def new_process( parent, msg, resize, sizer ):
    global supported_image_types
    if supported_image_types is None:
        supported_image_types = [ x.upper().encode('us-ascii').split('/')[1] for x in [ x.GetMimeType() for x in [wx.TheMimeTypesManager.GetFileTypeFromExtension(ext[2:]) for ext in wx.Image.GetImageExtWildcard().split('|')[1].split(';')] if x is not None ] if x ]
        for x in supported_image_types:
            display_factories['IMAGE'][x] = image_generic
    added_expander = False
    for p in msg.parts().children:
        added_expander = render_part( parent, msg, p, resize, sizer, added_expander )
    parent.Layout()
    parent.Refresh()

def render_part( parent, msg, part, resize, sizer, added_expander, show_inline=None ):
    x = None
    if show_inline is None:
        show_inline = ( part.disposition=='INLINE' )
        if not part.children and part.part_id!='1' and not part.part_id.startswith( '1.' ):
            if msg.mailbox().server().bandwidth is not None:
                if ( 8 * part.size ) / msg.mailbox().server().bandwidth > 2.0:
                    show_inline = False
            else:
                if part.size > (512*1024): # 512k
                    show_inline = False
    if not show_inline or part.filename() is not None or ( part.type=='MESSAGE' and part.subtype=='RFC822'):
        x = unknown( parent, msg, part, resize, show_inline=show_inline )
        if x is not None:
            ex = 0
            if x.expand==1 and not added_expander:
                ex=1
                ex = 0
                added_expander = True
            sizer.Add( x, ex, wx.ADJUST_MINSIZE|wx.EXPAND )
    if ( part.type!='MESSAGE' or part.subtype!='RFC822' ) and ( show_inline or x is None ):
        x = process( parent, msg, part , resize )
        if part.type=='MULTIPART' and part.subtype=='ALTERNATIVE':
            if x.current_choice is None:
                x.Destroy()
                x = None
                return added_expander
    else:
        x = None
    if x is not None:
        ex = 0
        if x.expand==1 and not added_expander:
            ex = 1
            ex = 0
            added_expander = True
        sizer.Add( x, ex, wx.ADJUST_MINSIZE|wx.EXPAND )
    if part.type=='MULTIPART' and part.subtype=='ALTERNATIVE':
        added_expander = render_part( parent, msg, x.current_choice, resize, sizer, added_expander, show_inline=True )
    elif part.type=='MULTIPART' and part.subtype=='RELATED':
        root = part.children[0]
        if 'START' in part.params:
            root = part.find_cid( part.params['START'] )
        added_expander = render_part( parent, msg, root, resize, sizer, added_expander )
    elif part.type+'/'+part.subtype in ['MESSAGE/RFC822'] or part.type=='MULTIPART':
        for p in part.children:
            added_expander = render_part( parent, msg, p, resize, sizer, added_expander )
    return added_expander

def process( parent, msg, part, resize ):
    global display_factories
    if part.type in display_factories:
        if part.subtype in display_factories[part.type]:
            return display_factories[part.type][part.subtype]( parent, msg, part, resize )
        elif 'x-default' in display_factories[part.type]:
             t = display_factories[part.type]['x-default']( parent, msg, part, resize )
             return t
    return None

def text_plain( parent, msg, part, resize ):
    if 'FORMAT' in part.params:
        if part.params['FORMAT'].upper() == 'FLOWED':
            return text_plain_flowed( parent, msg, part, resize )
    return text_plain_fixed( parent, msg, part, resize )
    if part.size < 2048:
        return text_plain_fx( parent, msg, part, resize )
display_factories['TEXT']['PLAIN'] = text_plain

class base:
    def __init__( self, parent, msg, part, resize ):
        #print "Render creating",`self.__class__.__name__`,"for",`part`
        self.parent = parent
        self.msg = msg
        self.part = part
        self.last_width = None
        self.last_x = None
        self.reported = False
        self.children = []
        self.ctrl = None
        self.reset_sizing()
        self.resize_call = resize
        self.expand = 0
        self._calc_ms = None

    def reset_sizing( self ):
        self.last_width = None
        self.last_x = None
        self.reported = False        

    def noop( self, event ):
        pass

    def post_init( self ):
        wx.EVT_SIZE( self, self.resize )
        self.resize()

    def resize( self, event=None ):
        if event is not None:
            event.Skip()
        x = self.GetContainer().GetParent().GetClientSize()[0] - wx.SystemSettings.GetMetric( wx.SYS_VSCROLL_X )
        if self.last_x != x:
            self._calc_ms = self.GetMinSizeFromWidth( x )
            self.reported = False
            self.last_x = x
        if not self.reported and self._calc_ms is not None:
            #self.SetSizeHints( -1, self._calc_ms[1] )
            self.SetSizeHints( self._calc_ms[0], self._calc_ms[1] )
            self.resize_call()
            self.reported = True

    def GetContainer( self ):
        w = self.parent
        while isinstance( w, base ):
            w = w.GetParent()
        return w

    def GetContainerSizer( self ):
        return self.GetContainer().GetSizer()

    def GetMinSizeFromWidth( self, width ):
        if self.last_width != width:
            self.min_size = self.GetMinSizeFromWidth_impl( width )
            self.last_width = width
        return self.min_size
    
    def GetMinSizeFromWidth_impl( self, width ):
        if self.ctrl is not None or len(self.children):
            cts = [-1,-1]
            if self.ctrl is not None:
                cts = list(self.ctrl.GetMinSize())
            for x in self.children:
                chs = x.GetMinSizeFromWidth_impl( width )
                cts[0] += chs[0]
                if chs[1]>cts[1]:
                    cts[1] = chs[1]
            return wx.Size( cts[0], cts[1] )
        else:
            return self.GetMinSize()

class text_plain_nbase(base,ExpandoTextCtrl):
    def __init__( self, parent, msg, part, re ):
        base.__init__( self, parent, msg, part, re )
        ExpandoTextCtrl.__init__( self, parent, -1, style=wx.TE_MULTILINE|wx.TE_READONLY )
        self.expand = 1
        self.unitext = ''
        self.post_init()
        wx.CallAfter(self.gettext)

    def gettext(self):
        self._proc = self.msg.send_body(self.part, self.newtext)

    def newtext( self, text, partial, full ):
        if full:
            wx.GetApp().status( "Loaded %d%% of part %s" % ( (partial*100)/full, self.part.part_id ) )
        nt = text[len(self.unitext):]
        self.unitext = text
        self.do_text(nt)
        self.Layout()
        self.Refresh()
        self.reset_sizing()
        self.resize()
        self.Refresh()
        self.GetContainer().Refresh()
        self.GetContainerSizer().Layout()
        self.GetContainerSizer().Layout()
        self.GetContainer().Refresh()
        
    def do_text(self, all, new):
        raise "Unimplemented"

    def GetMinSizeFromWidth_impl(self, width):
        self.SetSizeHints(width, -1)
        self.Layout()
        self.Refresh()
        return self.GetVirtualSize()
        #return wx.Size(self.GetVirtualSize()[0], self.GetVirtualSize()[1] + self.GetCharHeight())

class text_plain_fixed(text_plain_nbase):
    def __init__(self, parent, msg, part, re):
        text_plain_nbase.__init__(self, parent, msg, part, re)
        
    def do_text(self, new):
        self.AppendText(new)

class  text_plain_flowed(text_plain_nbase):
    def __init__(self, parent, msg, part, re):
        text_plain_nbase.__init__(self, parent, msg, part, re)
    
    def do_text(self, new):
        self.SetValue('')
        colours = ["#009C46", "#DA6A00", "#6404B5"]
        paras = infotrope.flowed.parse( self.unitext, part=self.part )
        lqd = 0
        for p in paras:
            if lqd != p.quote_depth:
                if lqd != 0:
                    self.EndSymbolBullet()
                    self.EndTextColour()
                if p.quote_depth:
                    self.BeginTextColour(colours[p.quote_depth % len(colours)])
                    self.BeginSymbolBullet(">" * p.quote_depth, 0, 30 * p.quote_depth)
            lqd = p.quote_depth
            self.AddParagraph(p.txt)
        self._adjustCtrl()

class text_plain_base(base,wx.stc.StyledTextCtrl):
    def __init__( self, parent, msg, part, re ):
        base.__init__( self, parent, msg, part, re )
        wx.stc.StyledTextCtrl.__init__( self, parent, -1, style=wx.SUNKEN_BORDER )
        #self.StyleSetFont( 0, wx.SystemSettings.GetFont( wx.SYS_ANSI_FIXED_FONT ) )
        self.SetMargins( 0, 0 )
        for i in range(3):
            self.SetMarginWidth( i, 0 )
        self.StyleClearAll()
        self.SetUseHorizontalScrollBar(0)
        if 'unicode' in wx.PlatformInfo:
            self.SetCodePage( wx.stc.STC_CP_UTF8 )
        self.SetUseVerticalScrollBar(0)
        #self.SetWrapMode( wx.stc.STC_WRAP_WORD )
        self.SetMarginType( 1, wx.stc.STC_MARGIN_NUMBER )
        self.SetText( '' )
        self.hotspot_style = 1
        self.fixed = False
        self.prev_size = None
        self.set_styles()
        self.SetReadOnly( 1 )
        wx.stc.EVT_STC_HOTSPOT_CLICK( self, -1, self.hotspot_click )
        self.expand = 1
        self.unitext = ''
        self._proc = msg.send_body( part, self.newtext )
        self.post_init()

    def newtext( self, text, partial, full ):
        if full:
            wx.GetApp().status( "Loaded %d%% of part %s" % ( (partial*100)/full, self.part.part_id ) )
        self.unitext = text
        self.prev_size = None
        self.reset_sizing()
        self.resize()
        self.GetContainer().Refresh()
        self.GetContainerSizer().Layout()
        self.GetContainerSizer().Layout()
        
    def hotspots( self, tta ):
        spl = tta.encode('utf-8').replace( '\n', ' ' ).replace( '\t', ' ' ).split( ' ' )
        hotspots = []
        cpos = 0
        for word in spl:
            start,end = cpos,cpos+len(word)
            cpos += len(word) + 1
            if len(word):
                while not word[0].isalpha():
                    if word[0] == '(':
                        e = word.rfind(')')
                        if e!=-1:
                            end -= len(word) - e
                            word = word[:e]
                    if word[0] == '<':
                        e = word.rfind('>')
                        if e!=-1:
                            end -= len(word) - e
                            word = word[:e]
                        if word.lower().find('<uri:')==0 or word.lower().find('<url:')==0:
                            start += 5
                            word = word[5:]
                            if 0 == len(word):
                                break
                            continue
                    if word[0] == '[':
                        e = word.rfind(']')
                        if e!=-1:
                            end -= len(word) - e
                            word = word[:e]
                    word = word[1:]
                    start += 1
                    if 0==len(word):
                        break
            if len(word):
                while word[-1] in ',.!':
                    word = word[:-1]
                    end -= 1
                    if 0==len(word):
                        break
            if len(word):
                if word.find('@')!=-1:
                    hotspots.append( (start,end) )
                elif word.find('www.')==0:
                    hotspots.append( (start,end) )
                elif word.find(':')<7 and word.find(':')<(len(word)-4):
                    try:
                        u = infotrope.url.URL( word )
                        if u.scheme:
                            hotspots.append( (start,end) )
                    except:
                        pass
        return hotspots
    
    def hotspot_click( self, event ):
        pos = event.GetPosition()
        start = pos
        end = pos
        while self.hotspot_style == self.GetStyleAt( start ):
            start -= 1
        start += 1
        while self.hotspot_style == self.GetStyleAt( end ):
            end += 1
        txt = self.GetTextRange( start, end )
        try:
            u = infotrope.url.URL( txt )
            if u.scheme:
                wx.GetApp().process_url( u )
                return
        except:
            pass
        if txt.find('www.')==0:
            txt = 'http://' + txt
        elif txt.find('@')!=-1:
            txt = 'mailto:' + txt
        try:
            u = infotrope.url.URL( txt )
            if u.scheme:
                wx.GetApp().process_url( u )
                return
        except:
            pass

    def GetMinSizeFromWidth_impl( self, width ):
        if self.fixed and self.prev_size is not None:
            return self.prev_size
        self.SetReadOnly( 0 )
        self.SetText( '' )
        lines,x,y = self.insert_text( width )
        self.SetReadOnly( 1 )
        y += self.TextHeight(0) * 2
        #x = 0
        #y = 0
        #fudge = 0
        #for i in range( 1 + self.GetLineCount() ):
        #    y += self.TextHeight( i ) + fudge # Fudge factor.
        #    if i==2:
        #        fudge = self.PointFromPosition( self.PositionFromLine( i ) )[1] - self.TextHeight( i )*2
        #    tmp = self.TextWidth( self.GetStyleAt( self.PositionFromLine( i ) ), self.GetLine( i ).strip()+' ' )
        #    if tmp > ( width * 2 ):
        #        continue # Don't be silly. It breaks things anyway.
        #    if x < tmp:
        #        x = tmp
        self.prev_size = ( x, y )
        return ( x, y )

    def insert_wrapped_text( self, txt, tgtx, rwidth, st=0, pfx='' ):
        lines = 0
        x = 0
        y = 0
        fudge = 0
        while len(txt):
            low = 0
            high = len(txt)
            mid = len(txt)
            loop = True
            if self.fixed:
                swidth = len(txt)
            else:
                swidth = self.TextWidth( st, pfx+txt )
            if swidth < tgtx:
                loop = False
            lwidth = 0
            hwidth = swidth
            width = swidth
            loop_count = 0
            while loop:
                loop_count += 1
                #print "Wrapping loop:",`high`,`low`,`hwidth`,`lwidth`,`tgtx`
                midn = int( low + ( high - low ) * ( float( tgtx - lwidth ) / ( hwidth - lwidth ) ) )
                #print "Initial mid:",`mid`,`midn`
                if midn == mid:
                    low = mid
                    high = mid
                mid = midn
                #mid = low + ( high - low ) / 2
                if self.fixed:
                    width = mid
                else:
                    width = self.TextWidth( st, pfx+txt[0:mid] )
                #print "Width:",`mid`,`width`,`pfx+txt[0:mid]`
                if width > tgtx:
                    high = mid
                    hwidth = width
                elif width < tgtx:
                    low = mid
                    lwidth = width
                    if mid >= len(txt):
                        loop = False
                else:
                    low = mid
                    high = mid
                if (low+2) >= high:
                    mid = txt[0:mid].rfind( ' ' )
                    if mid == -1:
                        mid = txt.find( ' ', mid )
                        if mid == -1:
                            mid = len(txt)
                    loop = False
            l = self.GetLength()
            tta = pfx+txt[0:mid]+'\n'
            hotspots = self.hotspots( tta )
            if self.fixed:
                width = self.TextWidth( st, tta )
            if width > x and width < (2*rwidth):
                x = width
            self.AddText( tta )
            self.StartStyling( l, 31 )
            self.SetStyling( self.GetLength()-l, st )
            for start,end in hotspots:
                self.StartStyling( l+start, 31 )
                self.SetStyling( end-start, self.hotspot_style )
            y += self.TextHeight(lines) + fudge
            if lines == 1:
                fudge = self.PointFromPosition(self.PositionFromLine(2))[1] - (y*2)
            txt = txt[mid:]
            if len(txt) and txt[0]==' ':
                txt = txt[1:]
            ++lines
        return lines,x,y


class text_plain_fx(text_plain_base):
    def __init__( self, parent, message, part, re ):
        text_plain_base.__init__( self, parent, message, part, re )

    def set_styles( self ):
        self.StyleSetFaceName( 0, "Courier" )
        self.StyleSetSize( 0, 8 )
        self.StyleSetFaceName( 1, "Courier" )
        self.StyleSetSize( 1, 8 )
        self.StyleSetBackground( 1, "#FFFFCF" )
        self.StyleSetForeground( 1, "#0000FF" )
        self.StyleSetHotSpot( 1, True )
        self.fixed = True
        
    def insert_text( self, width ):
        self.SetText( '' )
        #deswidth = self.TextWidth( 0, '0' * 80 )
        deswidth = 80
        sio = StringIO( self.unitext )
        lines = 0
        pos = 0
        x = 0
        y = 0
        for l in sio:
            l = l.rstrip()
            if len(l):
                ll,xx,yy = self.insert_wrapped_text( l, deswidth, width )
                lines += ll
                if xx > x:
                    x = xx
                y += yy
            else:
                self.AddText( '\n' )
                y += self.TextHeight(lines)
                lines += 1
        return lines,x,y

display_factories['TEXT']['x-default'] = text_plain_fx
display_factories['MESSAGE']['x-default'] = text_plain_fx
#display_factories['x-default'] = text_plain_fx

class text_plain_ff(text_plain_base):
    def __init__( self, parent, msg, part, re ):
        text_plain_base.__init__( self, parent, msg, part, re )
        self.paras = None

    def set_styles( self ):
        self.StyleSetForeground( 1, "#009C46" )
        self.StyleSetForeground( 2, "#DA6A00" )
        self.StyleSetForeground( 3, "#6404B5" )
        self.StyleSetSize( 4, 8 )
        self.StyleSetBackground( 4, "#FFFFCF" )
        self.StyleSetForeground( 4, "#0000FF" )
        self.StyleSetHotSpot( 4, True )
        self.hotspot_style = 4
        
    def insert_text( self, width ):
        self.paras = infotrope.flowed.parse( self.unitext, part=self.part )
        self.SetText('')
        tgtx = width - 20
        if tgtx < 50:
            tgtx = 50
        x = 0
        y = 0
        lines = 0
        for p in self.paras:
            txt = encode_ui( p.txt )
            st = p.quote_depth
            if st < 0:
                raise "Arse"
            if st > 3:
                st = 3
            pfx = ''
            if p.quote_depth > 0:
                pfx = '>' * p.quote_depth + ' '
            ll,xx,yy = self.insert_wrapped_text( txt, tgtx, tgtx, st, pfx )
            lines += ll
            if xx > x:
                x = xx
            y += yy
            if p.crlf:
                self.AddText( '\n' )
                y += self.TextHeight(lines)
                lines += 1
        return lines,x,y

class multipart(base,wx.Panel):
    def __init__( self, parent, msg, part, re ):
        base.__init__( self, parent, msg, part, re )
        self.sizer = None
        self.parts = {}
        if self.part.type=='MESSAGE' and self.part.part_id!='':
            wx.Panel.__init__( self, parent, -1, style=wx.SUNKEN_BORDER )
        else:
            wx.Panel.__init__( self, parent, -1 )
        self.sizer = wx.BoxSizer( wx.VERTICAL )
        self.add_children( self.part )
        self.SetSizer( self.sizer )
        self.sizer.Fit( self )
        self.SetAutoLayout(1)

    def add_children( self, part ):
        for subpart in part.children:
            if subpart.disposition=='INLINE':
                if subpart.type=='MESSAGE' and subpart.subtype=='RFC822':
                    s = wx.BoxSizer( wx.VERTICAL )
                    foo = process( self, self.msg, subpart, self.resize_call, self.sizer )
                    s.Add( foo, foo.expand, wx.ADJUST_MINSIZE|wx.EXPAND|wx.ALL, border=5 )
                    self.children.append( foo )
                    self.sizer.Add( s, 1, wx.EXPAND|wx.ADJUST_MINSIZE )
                    self.expand = 1
                else:
                    foo = process( self, self.msg, subpart, self.resize_call, self.sizer )
                    if foo is None:
                        foo = unknown( self, self.msg, subpart, self.resize_call, self.sizer )
                    self.parts[subpart.part_id] = foo
                    self.children.append( foo )
                    if foo.expand:
                        self.sizer.Add( foo, foo.expand, wx.EXPAND|wx.GROW|wx.ADJUST_MINSIZE )
                        self.expand = 1
                    else:
                        self.sizer.Add( foo, foo.expand, wx.EXPAND|wx.GROW|wx.ADJUST_MINSIZE )
            else:
                # Attachment of some form.
                foo = unknown( self, self.msg, subpart, self.resize_call, self.sizer )
                self.children.append( foo )
                self.sizer.Add( foo, 0, wx.ADJUST_MINSIZE|wx.EXPAND )
#display_factories['MESSAGE']['RFC822'] = multipart
#display_factories['MULTIPART']['x-default'] = multipart

class header(base,wx.Panel):
    def __init__( self, parent, msg, part, re ):
        base.__init__( self, parent, msg, part, re )
        wx.Panel.__init__( self, parent, -1 )
        self.master_sizer = wx.BoxSizer( wx.VERTICAL )
        self.sizer = wx.FlexGridSizer( cols=2, vgap=5, hgap=5 )
        self.sizer.AddGrowableCol( 1 )
        env = None
        if self.part.part_id=='HEADER':
            env = self.msg.envelope()
        else:
            env = self.part.envelope
        for x in env.From:
            self.sizer.Add( wx.StaticText( self, -1, 'From' ), 0 )
            self.sizer.Add( self.text( x ), 1, wx.GROW|wx.EXPAND )
        for x in env.To:
            self.sizer.Add( wx.StaticText( self, -1, 'To' ) )
            self.sizer.Add( self.text( x ), 1, wx.GROW|wx.EXPAND )
        for x in env.CC:
            self.sizer.Add( wx.StaticText( self, -1, 'CC' ) )
            self.sizer.Add( self.text( x ), 1, wx.GROW|wx.EXPAND )
        if self.msg.get_sent_date_real( env ) is not None:
            self.sizer.Add( wx.StaticText( self, -1, "Date" ) )
            self.sizer.Add( wx.StaticText( self, -1, time.asctime( self.msg.get_sent_date_real( env ) ) ) )
        self.master_sizer.Add( self.sizer, 0, wx.GROW|wx.EXPAND )
        if env.Subject is not None:
            self.master_sizer.Add( wx.StaticText( self, -1, encode_ui( env.Subject ), style=wx.ALIGN_CENTRE ), 0, wx.GROW|wx.EXPAND )
        if self.part.part_id=='HEADER':
            flags = self.msg.flags()
        else:
            ppart = self.msg.parts().find_id( self.part.part_id[:-7] )
            if 'X-KEYWORDS' in ppart.disposition_params:
                flags = ppart.disposition_params['X-KEYWORDS'].lower().split(' ')
            else:
                flags = []
        flags = [ x.capitalize() for x in flags if x[0] not in ['\\','$'] ]
        self.flagctl = {}
        if flags:
            flszr = wx.BoxSizer( wx.HORIZONTAL )
            flszr.Add( wx.StaticText( self, -1, encode_ui( "Keywords:" ) ), 1, wx.GROW|wx.EXPAND )
            for fl in flags:
                flszr.Add( wx.StaticText( self, -1, encode_ui( fl ) ), 1, wx.GROW|wx.EXPAND|wx.ALL, border=5 )
            self.master_sizer.Add( flszr, 0 )
        self.SetSizer( self.master_sizer )
        self.master_sizer.Fit( self )
        self.SetAutoLayout( 1 )

    def text( self, x ):
        txt = x.hname
        if x.address!=x.hname:
            txt += " <%s>" % x.address
        t = wx.StaticText( self, -1, encode_ui( txt ) );
        return t

display_factories['MESSAGE']['RFC822-HEADER'] = header

class text_html(base,wx.html.HtmlWindow):
    def __init__( self, parent, msg, part, re ):
        base.__init__( self, parent, msg, part, re )
        wx.html.HtmlWindow.__init__( self, parent, -1 )
        self.unitext = ''
        self._proc = msg.send_body( part, self.newtext )
        #print "Here"
        self.expand = 1
        # Don't call post_init here, HtmlWindow needs resize!
        wx.EVT_SIZE( self, self.resize_local )

    def newtext( self, text, partial, full ):
        #print "There"
        if full:
            wx.GetApp().status( "Loaded %d%% of part %s" % ( (partial*100)/full, self.part.part_id ) )
        self.unitext = text
        self.GetMinSizeFromWidth(100)
        self.prev_size = None
        self.last_size = -1
        self.GetContainer().Refresh()
        self.GetContainerSizer().Layout()
        self.GetContainerSizer().Layout()
        self.reset_sizing()
        self.GetContainer().Refresh()
        self.GetContainerSizer().Layout()
        self.GetContainerSizer().Layout()
        
    def OnLinkClicked( self, linkinfo ):
        txt = linkinfo.GetHtmlCell().ConvertToText( None )
        txt = txt.strip()
        # Does this look like a URI?
        tu = None
        if txt.find( '.' )!=-1:
            if txt.find( '/' )!=-1: # Contains both a dot and a slash, probably a URI-a-like.
                while txt[0].isalpha(): # Strip off pre-existing scheme-like.
                    txt = txt[1:]
                while txt[1] in ':/;\\':
                    txt = txt[1:]
                txt = 'http://' + txt # Whack a scheme back on.
                try:
                    tu = infotrope.url.URL( txt )
                except:
                    pass
        ru = infotrope.url.URL( linkinfo.GetHref() )
        if tu is not None:
            if ru.scheme != tu.scheme:
                if self.Phish( tu, ru ):
                    return
            if tu.server != ru.server:
                if self.Phish( tu, ru ):
                    return
        wx.GetApp().process_url( infotrope.url.URL( linkinfo.GetHref() ) )

    def Phish( self, tu, ru ):
        import polymer.dialogs
        d = polymer.dialogs.MessageDialog( self, "This link appears to go to a different site than it says.\nThis is likely to be a deliberate attempt to mislead you.\nDo you want to open link to:\n  %s" % ( ru.asString() ), "Infotrope Polymer", wx.YES_NO|wx.ICON_ERROR )
        return wx.ID_YES!=d.ShowModal()
        
    def OnOpeningURL( self, type, url ):
        if url.find('cid:')==0:
            nu = self.msg.uri().asString() + '#' + url
            return nu
        elif url.find( self.msg.uri().asString() + '#' )==0:
            return wx.html.HTML_OPEN
        if type==wx.html.HTML_URL_PAGE:
            return wx.html.HTML_OPEN
        return wx.html.HTML_BLOCK

    def resize_local( self, event ):
        event.Skip()
        self.resize( event )

    def GetMinSizeFromWidth_impl( self, w ):
        if wx.USE_UNICODE:
            self.SetPage( self.unitext )
        else:
            self.SetPage( infotrope.encoding.encode_min( self.unitext )[0] )
        self.SetSize( (w - wx.SystemSettings.GetMetric( wx.SYS_VSCROLL_X ),40) )
        self.Layout()
        self.Refresh()
        self.Update()
        #print `self.GetVirtualSize()`,`self.GetClientSize()`
        #return (-1, self.GetVirtualSize()[1] )# - wx.SystemSettings.GetMetric( wx.SYS_VSCROLL_X ) )
        return (self.GetVirtualSize()[0] - wx.SystemSettings.GetMetric( wx.SYS_VSCROLL_X ), self.GetVirtualSize()[1] )# - wx.SystemSettings.GetMetric( wx.SYS_VSCROLL_X ) )
display_factories['TEXT']['HTML'] = text_html

class child_controller:
    "Mix in for base."
    def __init__( self ):
        self.mypos = None
        self.ch_map = {}
    
    def view_child_part( self, part=None ):
        if self.mypos is None:
            pos = 0
            while True:
                si = self.GetContainingSizer().GetItem( pos )
                if si is None:
                    break
                if si.GetWindow() is self:
                    self.mypos = pos
                    break
                pos += 1
        if self.mypos is None:
            raise "Can't find myself, whoops."
        children = [ x for x in self.GetContainingSizer().GetChildren() if self.part.find_id(x.GetWindow().part.part_id) is not None and x.GetWindow() is not self ]
        for kiddie in children:
            cpi = kiddie.GetWindow().part.part_id
            kid = None
            for x in self.part.children:
                if x.find_id( cpi ) is not None:
                    kid = x
                    break
            if kid is None:
                kid = kiddie.GetWindow().part
            pi = kid.part_id
            if pi not in self.ch_map:
                self.ch_map[pi] = []
            self.ch_map[pi].append( kiddie )
        if part is not None:
            if part.part_id not in self.ch_map:
                fpos = self.mypos + 1
                w = process( self.parent, self.msg, part, self.resize_call )
                self.GetContainingSizer().Insert( fpos, w, 1, wx.ADJUST_MINSIZE|wx.EXPAND )
                self.ch_map[part.part_id] = [self.GetContainingSizer().GetItem( w )]
        partid = None
        if part is not None:
            partid=part.part_id
        for pid,val in self.ch_map.items():
            for x in val:
                self.GetContainingSizer().Show(x.GetWindow(),(partid is not None and pid==partid))
        self.resize_call()
                

class multipart_alternative(base,wx.Panel,child_controller):
    def __init__( self, parent, msg, part, re ):
        base.__init__( self, parent, msg, part, re )
        wx.Panel.__init__( self, parent, -1 )
        child_controller.__init__( self )
        self.ctrl = wx.BoxSizer( wx.HORIZONTAL )
        self.ctrl.Add( wx.StaticText( self, -1, "This part is available in:" ), 0 )
        b = self.part.children[:]
        b.reverse()
        b = [ x for x in b if x.type in display_factories and ( x.subtype in display_factories[x.type] or 'x-default' in display_factories[x.type] ) ]
        self.real_choices = b
        choices = [ x.part_id[len(self.part.part_id)+1:] + ' ' + x.type.lower() + '/' + x.subtype.lower() for x in self.real_choices ]
        self.switch = wx.Choice( self, -1, choices=choices )
        self.current_choice = None
        offset = -1
        coffset = -1
        if len(b):
            for ch in b:
                offset += 1
                if ch.disposition=='INLINE' and ( msg.mailbox().server().bandwidth is None or ((8 * ch.size) / msg.mailbox().server().bandwidth) < 0.5 ):
                    self.current_choice = ch
                    coffset = offset
                    break
            if coffset == -1:
                offset = -1
                for ch in b:
                    offset += 1
                    sz = None
                    if ch.disposition=='INLINE':
                        if sz is None or sz > ch.size:
                            self.current_choice = ch
                            coffset = offset
        self.switch.SetSelection( coffset )
        self.ctrl.Add( self.switch, 1, wx.GROW )
        self.SetSizer( self.ctrl )
        self.ctrl.Fit( self )
        self.SetAutoLayout(1)
        wx.EVT_CHOICE( self.switch, -1, self.change_choice )

    def change_choice( self, event=None ):
        chv = self.switch.GetSelection()
        part = self.real_choices[chv]
        if part is self.current_choice:
            return
        self.view_child_part( part )
        self.current_choice = part

display_factories['MULTIPART']['ALTERNATIVE'] = multipart_alternative

class unknown(base,wx.Panel,child_controller):
    def __init__( self, parent, message, part, re, show_inline=None ):
        base.__init__( self, parent, message, part, re )
        wx.Panel.__init__( self, parent, -1, style=wx.SUNKEN_BORDER )
        child_controller.__init__( self )
        self.descr_sizer = wx.BoxSizer( wx.VERTICAL )
        self.master_sizer = wx.BoxSizer( wx.HORIZONTAL )
        icon = wx.GetApp().get_mime_icon(part.type, part.subtype)
        if icon:
            self.drag_handle = wx.StaticBitmap(self, -1, wx.BitmapFromIcon(icon))
            wx.EVT_LEFT_DOWN(self.drag_handle, self.drag_init)
            self.master_sizer.Add(self.drag_handle)
        if part.description is not None:
            self.descr_sizer.Add( wx.StaticText( self, -1, encode_ui( part.description ) ), 0 )
        if part.filename() is not None:
            self.descr_sizer.Add( wx.StaticText( self, -1, encode_ui( part.filename() ) ), 0 )
        type_descr = wx.GetApp().get_mime_description( part.type, part.subtype )
        self.descr_sizer.Add( wx.StaticText( self, -1, type_descr ), 0 )
        self.cache_detail = None
        szp = self.do_cache_detail(message,part)
        if szp is not None:
            self.cache_detail = wx.StaticText( self, -1, szp )
            message.watch(self, part)
            self.descr_sizer.Add( self.cache_detail, 0 )
        self.master_sizer.Add( self.descr_sizer, 1 )
        self.save_button = wx.Button( self, -1, "Save" )
        self.master_sizer.Add( self.save_button, 0, wx.ALIGN_CENTER|wx.ADJUST_MINSIZE|wx.ALL, border=5 )
        wx.EVT_BUTTON( self.save_button, -1, self.save_file )
        if self.get_extension() is not None:
            self.ext_button = wx.Button( self, -1, "Open" )
            self.master_sizer.Add( self.ext_button, 0, wx.ALIGN_CENTER|wx.ADJUST_MINSIZE|wx.ALL, border=5 )
            wx.EVT_BUTTON( self.ext_button, -1, self.view_file )
        if part.type == 'MESSAGE' and part.subtype == 'RFC822':
            self.extract_button = wx.Button( self, -1, "Extract" )
            self.master_sizer.Add( self.extract_button, 0, wx.ALIGN_CENTER|wx.ALL, border=5 )
            wx.EVT_BUTTON( self.extract_button, -1, self.extract )
        elif part.type in display_factories:
            if part.subtype in display_factories[part.type] or 'x-default' in display_factories[part.type]:
                self.inline_button = wx.ToggleButton( self, -1, "Inline" )
                self.master_sizer.Add( self.inline_button, 0, wx.ALIGN_CENTER|wx.ADJUST_MINSIZE|wx.ALL, border=5 )
                si = show_inline
                if show_inline is None:
                    si = part.disposition == 'INLINE'
                self.inline_button.SetValue( si )
                wx.EVT_TOGGLEBUTTON( self.inline_button, -1, self.view_inline )
        self.SetSizer( self.master_sizer )
        self.master_sizer.Fit( self )
        self.SetAutoLayout( 1 )
        self.controlled = None

    def do_cache_detail(self,message,part):
        if part.size is not None:
            szp = '%d bytes' % ( part.size )
            szs = part.size
            if szs > 4096:
                szs /= 1024.0
                szp = '%.2fk' % ( szs )
                if szs > 1024:
                    szs /= 1024.0
                    szp = '%.2fM' % ( szs )
            if part.children:
                szp += ' (total)'
            elif message.have_cached(part):
                szp += " (cached)"
            else:
                szp += " (not cached)"
            return szp
        return None

    def message_watch_notify(self, message, part):
        if self.cache_detail is not None:
            self.cache_detail.SetLabel(self.do_cache_detail(message,part))
        self.master_sizer.Layout()

    def drag_init(self, event):
        import polymer.dragdrop
        data = polymer.dragdrop.URLDataObject(self.msg.uri().asString()+'/;SECTION='+self.part.part_id)
        source = wx.DropSource(self.drag_handle)
        source.SetData(data)
        source.DoDragDrop(True)

    def extract( self, event ):
        import infotrope.message
        mi = self.msg.mailbox().mbox_info()
        m = infotrope.message.MessagePart( self.msg, self.part )
        m.msg_flags = [ '\\Seen', '$MDNSent' ]
        if 'X-KEYWORDS' in self.part.disposition_params:
            m.msg_flags += [ x for x in self.part.disposition_params['X-KEYWORDS'].lower().split(' ') if x[0] not in '\\$' ]
        mi.append( m )
        
    def save_file( self, event ):
        import polymer.dialogs
        ext = self.get_extension()
        if ext is None:
            ext = 'dat'
        filename = 'polymer_file'
        sfn = self.part.filename()
        if sfn is not None:
            filename = sfn
        if filename.find('.')==-1:
            filename = filename + '.' + ext
        fdlg = wx.FileDialog( self, "Save Part", style=wx.SAVE|wx.OVERWRITE_PROMPT )
        fdlg.SetFilename( filename )
        if polymer.dialogs.save_dir:
            fdlg.SetDirectory( polymer.dialogs.save_dir )
        if fdlg.ShowModal()==wx.ID_OK:
            filename = fdlg.GetPath()
            polymer.dialogs.save_dir = fdlg.GetDirectory()
            if self.part.type == 'TEXT':
                f = file( filename, 'w' )
                ss = StringIO( self.msg.body( self.part ) )
                for l in ss:
                    l = l.rstrip('\r\n')
                    f.write(l + '\n')
                f.close()
            else:
                f = file( filename, 'wb' )
                f.write( self.msg.body_decode( self.part ) )
                f.close()

    def get_extension( self ):
        mime_type = self.part.type.lower() + '/' + self.part.subtype.lower()
        ft = wx.TheMimeTypesManager.GetFileTypeFromMimeType( mime_type )
        ext = None
        if ft is not None:
            if len(ft.GetExtensions()):
                ext = ft.GetExtensions()[0]
        sfn = self.part.filename()
        if sfn is not None:
            if ft is not None and sfn.find('.')!=-1:
                for x in ft.GetExtensions():
                    if sfn[-(len(x)+1):]==('.'+x):
                        ext = x
        return ext
        
    def view_file( self, event ):
        ext = self.get_extension()
        filename = os.tempnam( None, "Polymer" ) + '.' + ext
        fp = file( filename, 'w' )
        fp.write( self.msg.body_decode( self.part ) )
        fp.close()
        try:
            os.stat( '/usr/bin/gnome-open' )
            wx.Execute( '/usr/bin/gnome-open "%s"' % ( filename ) )
        except OSError:
            wx.Execute( ft.GetOpenCommand( filename ) )
    
    def view_inline( self, event ):
        if self.inline_button.GetValue():
            self.view_child_part( self.part )
        else:
            self.view_child_part()
display_factories['x-default'] = unknown

class vcard(base,wx.Panel):
    def __init__( self, parent, msg, part, re ):
        import infotrope.mimedir
        base.__init__( self, parent, msg, part, re )
        wx.Panel.__init__( self, parent, -1 )
        self.sizer = wx.BoxSizer( wx.HORIZONTAL )
        p = infotrope.mimedir.MimeDirectory()
        f = StringIO( msg.body( part ) )
        p.parse( f )
        self.vcf = p.asComponents()[0]
        labels = wx.BoxSizer( wx.VERTICAL )
        labels.Add( wx.StaticText( self, -1, encode_ui(self.vcf.contents[self.vcf.contentsByName['FN'][0]].value) ), 0, wx.ADJUST_MINSIZE|wx.EXPAND )
        if 'LABEL' in self.vcf.contentsByName:
            l = self.vcf.contents[self.vcf.contentsByName['LABEL'][0]]
            t = l.value
            if u'ENCODING' in l.params:
                if u'QUOTED-PRINTABLE' in l.params[u'ENCODING']:
                    t = l.value.encode('utf-8').decode('quoted-printable')
                f = StringIO( t )
            for line in f:
                line = line.strip(' \r\n')
                labels.Add( wx.StaticText( self, -1, encode_ui( line ) ), 1, wx.EXPAND|wx.ADJUST_MINSIZE )
        self.sizer.Add( labels )
        buttons = wx.BoxSizer( wx.VERTICAL )
        buttons.Add( wx.Button( self, -1, "Import" ) )
        self.sizer.Add( buttons, 0, wx.EXPAND|wx.ADJUST_MINSIZE|wx.ALL, border=5 )
        self.SetSizer( self.sizer )
        self.sizer.Fit( self )
        self.SetAutoLayout(1)
        self.expand = 0
        wx.EVT_BUTTON( self, -1, self.importer )

    def importer( self, event ):
        import infotrope.acap
        email_addresses = []
        pref_email_address = None
        if u'EMAIL' in self.vcf.contentsByName:
            for email in [ self.vcf.contents[x] for x in self.vcf.contentsByName['EMAIL'] ]:
                if u'TYPE' in email.params:
                    if u'INTERNET' in email.params[u'TYPE']:
                        email_addresses.append( email.value )
                        if u'PREF' in email.params[u'TYPE']:
                            pref_email_address = email.value
        if len(email_addresses):
            if pref_email_address is None:
                pref_email_address = email_addresses[0]
            acap = wx.GetApp().acap_home()
            srt = 'SEARCH "/addressbook/~/" DEPTH 0 RETURN ("*") ' + ('OR ' * (len(email_addresses)-1)) + ' '.join(['OR PREFIX "addressbook.Email" "i;octet" {%d+}\r\n%s\x00 EQUAL "addressbook.Email" "i;octet" "%s"' % ( len(x)+1, x, x ) for x in email_addresses])
            srch = infotrope.acap.search( srt, connection=acap, ret=["*"] )
            srch.send()
            cand = {}
            def stock( cand, a, x ):
                cand[a] = x.value.encode( 'utf-8' )
            def stock_multi( cand, a, x ):
                if a not in cand:
                    cand[a] = []
                cand[a].append( x.value.encode( 'utf-8' ) )
            def type_map( cand, a, x, inet=False ):
                if u'TYPE' in x.params:
                    if inet and u'INTERNET' not in x.params[u'TYPE']:
                        return
                    if u'PREF' in x.params[u'TYPE']:
                        cand[a] = x.value.encode( 'utf-8' ) + '\0'.join( [''] + [ z.encode('utf-8').lower() for z in x.params[u'TYPE'] if z!=u'PREF' and z!=u'INTERNET' ] )
                        return
                    if a+'Other' not in cand:
                        cand[a+'Other'] = []
                    cand[a+'Other'].append( x.value.encode( 'utf-8' ) + '\0'.join( [''] + [ z.encode('utf-8').lower() for z in x.params[u'TYPE'] if z!=u'PREF' and z!=u'INTERNET' ] ) )
            def type_map_inet( cand, a, x ):
                type_map( cand, a, x, True )
            mapping = {
                'FN': ( 'addressbook.CommonName', stock ),
                'BDAY': ( 'addressbook.Bday', stock ),
                'TEL': ('addressbook.Telephone', type_map ),
                'EMAIL': ('addressbook.Email', type_map_inet ),
                'MAILER': ('addressbook.Mailer', stock ),
                'TITLE': ('addressbook.Title', stock ),
                'ROLE': ('addressbook.Role', stock ),
                'ORG': ('addressbook.Organization', stock ),
                'CATEGORIES': ('addressbook.Categories', stock_multi ),
                'NOTE': ('addressbook.Note', stock ),
                'URL': ('addressbook.HomePage', stock )
                }
            for attr in self.vcf.contents:
                if attr.name in mapping:
                    mapping[attr.name][1]( cand, mapping[attr.name][0], attr )
            t,r,s = srch.wait()
            en = None
            if r.lower()=='ok':
                en = srch[0]
                ename = srch.entries()[0]
            if en is None:
                entrypath = '/addressbook/~/Polymer_' + pref_email_address
            else:
                entrypath = ename
            for xattr in en:
                if xattr in cand:
                    if isinstance(en[xattr]['value'],list):
                        if en[xattr]['value'] == cand[xattr]:
                            del cand[xattr]
            acap.store( entrypath, cand )
            
display_factories['TEXT']['X-VCARD'] = vcard

def process_dir( parent, msg, part, re ):
    if 'PROFILE' in part.params:
        if part.params['PROFILE'] == 'VCARD':
            return vcard( parent, msg, part, re )
    return text_plain_fx( parent, msg, part, re )
display_factories['TEXT']['DIRECTORY'] = process_dir

class image( base, wx.StaticBitmap ):
    def __init__( self, parent, msg, part, re, idata=None ):
        base.__init__( self, parent, msg, part, re )
        self.idata = idata
        wx.StaticBitmap.__init__( self, parent, -1, idata.ConvertToBitmap() )
        self.post_init()

    def GetMinSizeFromWidth_impl( self, w ):
        mw = self.idata.GetWidth()
        mh = self.idata.GetHeight()
        if w > mw:
            return mw, mh
        nh = ((mh*w)/mw)
        self.SetBitmap( self.idata.Scale( w, nh ).ConvertToBitmap() )
        return ( w, nh )

def image_generic( parent, msg, part, re ):
    f = StringIO( msg.body_decode( part ) )
    i = wx.ImageFromStreamMime( wx.InputStream( f ), part.type + '/' + part.subtype )
    if i.Ok():
        return image( parent, msg, part, re, i )
    return None
#display_factories['IMAGE']['x-default'] = image_generic

# The Apple Mac. Too cool to follow standards.
# In particular, JPEG images are sent as "image/jpg". Bug report is in.
def macs_are_fuckers( parent, msg, part, re ):
    "Say it like it is."
    if part.type == 'IMAGE':
        if part.subtype == 'JPG':
            part.subtype = 'JPEG'
    return process( parent, msg, part, re )
display_factories['IMAGE']['JPG'] = macs_are_fuckers


# cid: URI stuff.
class fsh( wx.FileSystemHandler ):
    def __init__( self ):
        wx.FileSystemHandler.__init__( self )
        
    def CanOpen( self, u ):
        return (self.GetProtocol(u) == 'cid')

    def OpenFile( self, fs, u ):
        try:
            left = self.GetLeftLocation(u).encode('utf-8')
            msg_u = infotrope.url.URL( left )
            cid = '<' + self.GetRightLocation( u ).encode('utf-8') + '>'
            c = wx.GetApp().connection( msg_u )
            mbox = c.mailbox( msg_u.mailbox )
            msg = mbox[msg_u.uid]
            parts = msg.parts()
            p = parts.find_cid( cid )
            if p is None:
                return None
            data = msg.body_decode(p)
            sio = StringIO(data)
            wxi = wx.InputStream(sio)
            wxf = wx.FSFile(wxi, u, (p.type+'/'+p.subtype).lower(), self.GetAnchor(u), wx.DateTime())
            return wxf
        except:
            import sys
            print "EXCEPTION IN OpenFile:",sys.exc_info()[1],`sys.exc_type`
            return None
        
_fsh = fsh()
wx.FileSystem.AddHandler( _fsh )

        
