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
import wx.calendar
import polymer.treenav
import infotrope.acap
import polymer.encode
import infotrope.mimedir

import dateutil.parser
import dateutil.relativedelta
import dateutil.rrule
import datetime

"""
ACAP Calendaring [SCRAP] WX support stuff.
"""

class Listing(wx.ListCtrl):
    """Control to list the results of a search."""
    def __init__( self, parent, search ):
        wx.ListCtrl.__init__( self, parent, -1, style=wx.LC_REPORT|wx.LC_VIRTUAL )
        self.InsertColumn( 0, "Date" )
        self.InsertColumn( 1, "Duration" )
        self.InsertColumn( 2, "Description" )
        self._search = search
        self._count = 0

    def set_search( self, search ):
        self._search = search
        self._count = 0
        self.set_count()

    def set_count( self ):
        c = len( self._search )
        #print `c`,`self._count`
        if self._count!=c:
            self._count = c
            self.SetItemCount( c )

    def OnGetItemImage( self, which ):
        return -1

    def OnGetItemAttr( self, which ):
        return None
    
    def OnGetItemText( self, which, what ):
        if self._search is None:
            return u''
        entry = self._search[which]
        txt = u''
        if what==0:
            if 'scrap.dtstart' in entry:
                d = dateutil.parser.parse( entry['scrap.dtstart']['value'] )
                txt = d.strftime( "%a, %d %b %Y" );
        elif what==1:
            if 'scrap.dtend' in entry:
                txt = dateutil.parser.parse( entry['scrap.dtend']['value'] ).strftime( "%a, %d %b %Y" )
        elif what==2:
            if 'scrap.summary' in entry:
                txt = entry['scrap.summary']['value'].decode( 'utf-8' )
        return polymer.encode.encode_ui(txt)

    def addto( self, entryname ):
        'Call this from your notify object on the search.'
        self.set_count()

    def change( self, entryname ):
        'Call this from the notify object on the search'
        self.set_count()

    def removefrom( self, entryname ):
        'Call this from the notify object on the search'
        self.set_count()

class PanelScrapEntry(wx.Panel):
    def __init__( self, parent ):
        wx.Panel.__init__( self, parent, -1 )

_strftime_iso = '%Y%m%dT%H%M%SZ'

class extend_calendar:
    def __init__( self, uri, dtstart, dtend ):
        self.uri = uri
        self.dtstart = dtstart
        self.dtend = dtend
        self.context = 'polymer.scrap-rrule-expand.' + self.uri.path
        self.pending = []
        self.complete = False
        #print "Extending calendar at",self.uri.asString()
        self.search = infotrope.acap.search( 'SEARCH "%s" MAKECONTEXT NOTIFY "%s" RETURN ("scrap.dtstart" "scrap.dtend" "scrap.rrule" "scrap.uid" "scrap.summary") AND EQUAL "scrap.type" "i;ascii-casemap" "event" NOT EQUAL "scrap.rrule" "i;octet" NIL' % ( self.uri.path, self.context ), context=self.context, connection=wx.GetApp().connection( self.uri ), notify=self )
        self.search.send()

    def notify_addto( self, entryname ):
        if not self.complete:
            #print "Pending",`entryname`,"extension..."
            self.pending.append( entryname )
        else:
            self.notify_addto_real( entryname )
            wx.GetApp().connection(self.uri).store_flush()
        
    def notify_addto_real( self, entryname ):
        #print "Extending calendar entry",entryname
        e = self.search[entryname]
        #print "Entry::",`e`
        dtstart = dateutil.parser.parse( e['scrap.dtstart']['value'] )
        duration = dateutil.parser.parse( e['scrap.dtend']['value'] ) - dtstart
        rrule = dateutil.rrule.rrulestr( e['scrap.rrule']['value'], dtstart=dtstart )
        for ndtstart in rrule.between( self.dtstart, self.dtend, inc=True ):
            rsrch = infotrope.acap.search( 'SEARCH "%s" RETURN ("scrap.dtstart") AND EQUAL "scrap.uid" "i;octet" "%s" EQUAL "scrap.dtstart" "i;ascii-casemap" "%s"' % ( self.uri.path, e['scrap.uid']['value'], ndtstart.strftime(_strftime_iso) ), connection=wx.GetApp().connection( self.uri ) )
            rsrch.send()
            #print "Adding recurrence at",`ndtstart`
            nep = self.uri.path + entryname + ndtstart.strftime(_strftime_iso)
            ne = {'scrap.type':'event','scrap.uid':e['scrap.uid']['value'],'scrap.summary':e['scrap.summary']['value'],'scrap.dtstart':ndtstart.strftime(_strftime_iso),'scrap.dtend':(ndtstart+duration).strftime(_strftime_iso)}
            rsrch.wait()
            if len(rsrch)==0:
                #print "No recurrence present, adding."
                wx.GetApp().connection(self.uri).store(nep,ne,True)
            #print "Done"

    def notify_removefrom( self, entryname ):
        #print "De-extending calendar entry",entryname
        e = self.search[entryname]
        rsrch = infotrope.acap.search( 'SEARCH "%s" RETURN ("entry") AND AND EQUAL "scrap.rrule" "i;octet" NIL EQUAL "scrap.uid" "i;octet" "%s" COMPARESTRICT "scrap.dtstart" "i;ascii-casemap" "%s"' % ( self.uri.path, datetime.datetime.now().strftime(_strftime_iso) ), connection=wx.GetApp().connection( self.uri ) )
        rsrch.send()
        rsrch.wait()
        for x in rsrch:
            wx.GetApp().connection( self.uri ).store( self.uri.path + x, {"entry":None} )

    def notify_change( self, entryname ):
        #print "Yuckky, change."
        self.notify_removefrom( entryname )
        self.notify_addto( entryname )

    def notify_complete( self, status ):
        #print "Calendar extension complete, status is",`status`
        self.complete = True
        for x in self.pending:
            self.notify_addto_real( x )
        wx.GetApp().connection( self.uri ).store_flush()
        self.pending = []

class PanelScrap(wx.Panel, polymer.treenav.NavPanel):
    def __init__( self, notebook, controller ):
        self._pagename = "Calendar %s" % controller._name        
        polymer.treenav.NavPanel.__init__( self, notebook, self._pagename, wx.Panel.__init__, controller )
        self.uri = controller.uri
        #print "Opening scrap calendar",self.uri.asString()
        self._top_sizer = wx.BoxSizer( wx.HORIZONTAL )
        self._calctrl = wx.calendar.CalendarCtrl( self, -1, style=wx.calendar.CAL_SHOW_HOLIDAYS )
        self._listing = Listing( self, None )
        self._top_sizer.Add( self._calctrl, 0, wx.EXPAND|wx.GROW )
        self._top_sizer.Add( self._listing, 1, wx.EXPAND|wx.GROW )
        self._selected = None
        self._display = PanelScrapEntry( self )
        self._main_sizer = wx.BoxSizer( wx.VERTICAL )
        self._main_sizer.Add( self._top_sizer, 0, wx.GROW )
        self._display_panel = wx.Panel( self, -1 )
        self._main_sizer.Add( self._display_panel, 1, wx.GROW )
        self.SetSizer( self._main_sizer )
        self.SetAutoLayout( True )
        self._main_sizer.Fit( self )
        wx.EVT_LIST_ITEM_SELECTED( self._listing, -1, self.select )
        wx.calendar.EVT_CALENDAR_SEL_CHANGED( self._calctrl, -1, self.dolisting )

    def dolisting( self, evt ):
        self._context = 'polymer.scrap-listing.' + self.uri.path
        self.dtstart = self._calctrl.PyGetDate()
        self.dtend = self.dtstart + dateutil.relativedelta.relativedelta( days=1 )
        print `self.dtstart`,`self.dtend`
        self.extender = extend_calendar( self.uri, self.dtstart, self.dtend )
        self._search = infotrope.acap.search( 'SEARCH "%s" MAKECONTEXT ENUMERATE NOTIFY "%s" RETURN ("*") SORT ("scrap.dtstart" "+i;octet" "scrap.dtend" "-i;octet") AND AND AND EQUAL "scrap.type" "i;ascii-casemap" "event" NOT EQUAL "entry" "i;octet" "" NOT EQUAL "scrap.dtstart" "i;octet" NIL AND COMPARE "scrap.dtstart" "+i;ascii-casemap" "%s" COMPARESTRICT "scrap.dtstart" "-i;ascii-casemap" "%s"' % ( self.uri.path, self._context, self.dtstart.strftime( _strftime_iso ), self.dtend.strftime( _strftime_iso ) ), context = self._context, notify = self, connection=wx.GetApp().connection( self.uri ) )
        self._search.send()
        self._listing.set_search( self._search )

    def foreground( self ):
        for i in range( self.GetParent().GetPageCount() ):
            if self is self.GetParent().GetPage( i ):
                self.GetParent().SetSelection( i )
                break

    def delete( self ):
        if self is self.GetParent().GetPage( self.GetParent().GetSelection() ):
            self.GetParent().AdvanceSelection()
        for i in range( self.GetParent().GetPageCount() ):
            if self is self.GetParent().GetPage( i ):
                self.GetParent().RemovePage( i )
                break

    def notify_addto( self, entryname ):
        #print 'SCRAP Adding',`entryname`
        self._listing.addto( entryname )

    def notify_removefrom( self, entryname ):
        self._listing.removefrom( entryname )
        if self._selected is not None:
            if self._selected==entryname:
                print "Something for removed current entry."

    def notify_change( self, entryname ):
        self._listing.change( entryname )
        if self._selected is not None:
            if self._selected==entryname:
                print "Something for changed current entry."

    def select( self, event ):
        #print "SELECT ADDR"
        id = event.GetIndex()
        self._display.select( self._search[ id ] )

    def notify_complete( self, status ):
        #print 'Calendar search: ',`status`
        pass

class TreeNodeScrap(polymer.treenav.TreeNode):
    def __init__( self, tree, pid, uri=None, entry=None ):
        name = 'Calendar'
        if entry is not None:
            if 'scrap.name' in entry:
                name = entry['scrap.name']['value']
            else:
                name = entry['entry']['value']
        polymer.treenav.TreeNode.__init__( self, tree, pid, name )
        self._pending = []
        self._nodes = {}
        self.uri = uri
        self._panel = None
        if self.uri is None:
            self.uri = infotrope.url.URL( wx.GetApp().home )
            self.uri.path = '/scrap/~/'
        #print "Addressbook context is ",`self._context`
        self._tried = 0
        self.do_search()

    def do_search( self ):
        self._context = 'polymer.%s::%d' % ( self.uri.path, self._tried )
        self.search = infotrope.acap.search( 'SEARCH "%s" MAKECONTEXT NOTIFY "%s" RETURN ("entry" "subdataset" "scrap.name") AND EQUAL "scrap.type" "i;ascii-casemap" "calendar" NOT EQUAL "subdataset" "i;octet" NIL' % ( self.uri.path, self._context ), context=self._context, notify=self, connection=wx.GetApp().connection( self.uri ) )
        self.search.send()
    
    def process_pending( self ):
        #print "Processing, id is",`self._id`
        if self._id is not None:
            pending = self._pending
            self._pending = []
            for entry in pending:
                #print "Adding entry ", entry
                e = infotrope.datasets.base.entry( self.search[entry], self.uri )
                node = TreeNodeScrap( self.tree(), self._id, e.subdataset(), self.search[entry] )
                self._nodes[entry] = node
            self.tree().Refresh()
    
    def set_id( self, id ):
        self._id = id

    def notify_addto( self, entryname ):
        #print 'SCRAP ADDTO'
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
        #print 'SCRAP COMPLETE',`status`
        if status!='ok':
            if self._tried==0:
                # Oh dear, probably doesn't exist.
                self._tried = 1
                if self.uri.path=='/scrap/~/':
                    #print "Creating base calendar..."
                    wx.GetApp().connection( self.uri ).send( 'STORE ("/scrap/~/" "vendor.infotrope.polymer.search" "1")' )
                    self.do_search()
        
    def try_expand( self, event ):
        return True

    def select( self, event ):
        if self._panel is None:
            self._panel = PanelScrap( self.tree().notebook(), self )
        self.tree().update()
        self._panel.foreground()

    def import_query( self, event ):
        df = wx.FileDialog( self.tree(), "Import iCalendar file", wildcard="*.ics" );
        if df.ShowModal():
            f = df.GetPath();
            self.import_ics_file( f )

    def import_new( self, event ):
        df = wx.FileDialog( self.tree(), "Import iCalendar file", wildcard="*.ics" );
        if df.ShowModal():
            f = df.GetPath();
            self.import_ics_file_new( f )

    def import_ics_file( self, file ):
        p = infotrope.mimedir.MimeDirectory()
        p.parse( open( file, "r" ) )
        ics = p.asComponents()[0]
        self.import_ics( ics )

    def import_ics_file_new( self, file ):
        p = infotrope.mimedir.MimeDirectory()
        p.parse( open( file, "r" ) )
        ics = p.asComponents()[0]
        calname = file[:-4]
        relcalid = calname
        if 'X-WR-CALNAME' in ics.contentsByName:
            calname = ics.contents[ics.contentsByName['X-WR-CALNAME'][0]].value
        if 'X-WR-RELCALID' in ics.contentsByName:
            relcalid = ics.contents[ics.contentsByName['X-WR-RELCALID'][0]].value
        wx.GetApp().connection( self.uri ).store( self.uri.path + relcalid, {'scrap.type':'calendar','scrap.name':calname,'subdataset':['.']}, True )
        self.import_ics( ics, self.uri.path + relcalid + '/' )

    def import_ics( self, ics, path=None, default_tzinfo=None ):
        if path is None:
            path = self.uri.path
        conn = wx.GetApp().connection( self.uri )
        for idx in ics.componentsByName['VEVENT']:
            event = ics.contents[idx]
            epath = path + event.contents[event.contentsByName['UID'][0]].value.encode('base64').strip()
            e = {}
            e['scrap.type'] = 'event'
            if 'UID' in event.contentsByName:
                e['scrap.uid'] = event.contents[event.contentsByName['UID'][0]].value
            e['scrap.dtstart'] = event.contents[event.contentsByName['DTSTART'][0]].value
            if 'DTEND' in event.contentsByName:
                e['scrap.dtend'] = event.contents[event.contentsByName['DTEND'][0]].value
            else:
                end = dateutil.parser.parse(e['scrap.dtstart'])
                duration = event.contents[event.contentsByName['DURATION'][0]].value
                if duration[0] == '+':
                    duration = duration[2:]
                else:
                    duration = duration[1:]
                time = False
                count = 0
                for c in duration:
                    if c in "0123456789":
                        count *= 10;
                        count += int(c)
                    else:
                        if time:
                            if c.upper()=='H':
                                end += dateutil.relativedelta.relativedelta( hours=count )
                            elif c.upper()=='M':
                                end += dateutil.relativedelta.relativedelta( minutes=count )
                            elif c.upper()=='S':
                                end += dateutil.relativedelta.relativedelta( seconds=count )
                        else:
                            if c.upper()=='T':
                                time = True
                            elif c.upper()=='D':
                                end += dateutil.relativedelta.relativedelta( days=count )
                            elif c.upper()=='W':
                                end += dateutil.relativedelta.relativedelta( weeks=count )
                if len(e['scrap.dtstart'])==8:
                    e['scrap.dtend'] = end.strftime('%Y%m%d')
                else:
                    e['scrap.dtend'] = end.strftime( _strftime_iso )
            if 'SUMMARY' in event.contentsByName:
                e['scrap.summary'] = event.contents[event.contentsByName['SUMMARY'][0]].value
            if 'RRULE' in event.contentsByName:
                e['scrap.rrule'] = event.contents[event.contentsByName['RRULE'][0]].value
            if 'DESCRIPTION' in event.contentsByName:
                e['scrap.description'] = event.contents[event.contentsByName['DESCRIPTION'][0]].value
            #print "Storing",`e`,"to",`epath`
            conn.store( epath, e, True )
        conn.store_flush()

    def menu_new( self, event ):
        d = polymer.dialogs.TextEntryDialog( self.tree(), "New Calendar", "Enter a name for the Calendar" );
        if d.ShowModal():
            wx.GetApp().connection( self.uri ).store( self.uri.path + d.GetValue().encode( 'base64' ).strip(), {"scrap.name":polymer.encode.decode_ui( d.GetValue() ).encode( 'utf-8' ), "scrap.type":"calendar" } )

    def context_menu( self, event, frame ):
        if self._menu is None:
            self._menu = wx.Menu()
            ID_NEW = wx.NewId()
            self._menu.Append( ID_NEW, "&New", "Create new Calendar below this one" )
            wx.EVT_MENU( self._menu, ID_NEW, self.menu_new )
            ID_IMPORT = wx.NewId()
            self._menu.Append( ID_IMPORT, "&Import", "Import iCalendar file" )
            wx.EVT_MENU( self._menu, ID_IMPORT, self.import_query )
            ID_IMPORT_NEW = wx.NewId()
            self._menu.Append( ID_IMPORT_NEW, "I&mport New", "Import iCalendar file as new" )
            wx.EVT_MENU( self._menu, ID_IMPORT_NEW, self.import_new )
        self.tree().PopupMenu( self._menu, event.GetPoint() )
