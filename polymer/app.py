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

"""
Application object and helpers.
"""

import sys
import wx
import infotrope.acap
import infotrope.imap
import infotrope.url
import infotrope.environment
import os
import os.path
import infotrope.serverman
import polymer.encode
import polymer.mainframe
import polymer.options

import infotrope.datasets.email
import infotrope.datasets.personality
import weakref

import webbrowser

try:
    import gnomevfs
except:
    pass

app_name = 'Infotrope Polymer'
app_version = '0.0.3'

__revision__ = "$revision:$"

# Platform specific stuff.

polymerlaunch = None

if wx.Platform == '__WXMAC__':
    import MacOS
    if not MacOS.WMAvailable():
        print "Start this with 'pythonw', preferably from the console."
        raise "Need GUI"
    import findertools
    polymerlaunch = findertools.launch

save_excepthook = sys.excepthook
def fatal_excepthook( extype, value, trace ):
    """
    Fatal exception handler, used when --fatal is requsted.
    """
    global save_excepthook
    sys.excepthook = save_excepthook
    sys.excepthook( extype, value, trace )
    sys.exit( 100 )

def gui_excepthook( extype, value, trace ):
    """
    Standard GUI exception handler, prints annotated traceback.
    """
    try:
        global save_excepthook
        sys.excepthook = save_excepthook
        sys.excepthook( extype, value, trace )
        tmp = wx.Dialog( None, -1, "Python Exception",
                         style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER )
        szr = wx.BoxSizer( wx.VERTICAL )
        szr.Add( wx.StaticText( tmp, -1,
                                """Infotrope Polymer has suffered an exception.
                                I apologise, but something obviously isn't working.
                                Please let me know if it's important to you - it is
                                to me.
                                
                                Thanks,
                                Dave.
                                
                                Dave Cridland <dave@cridland.net>""" ), 0, wx.ALL, border=5 )
        szr.Add( wx.StaticText( tmp, -1, "Type: %s" % `extype` ),
                 0, wx.ALL, border=5 )
        szr.Add( wx.StaticText( tmp, -1, "Value: %s" % str(value) ),
                 0, wx.ALL, border=5 )
        tracetxt = u''
        while trace is not None:
            tracetxt += u"Line %s, lasti %s\n" % ( `trace.tb_lineno`, `trace.tb_lasti` )
            tracetxt += u"  In %s [%s:%d]:\n" % ( trace.tb_frame.f_code.co_name, trace.tb_frame.f_code.co_filename, trace.tb_frame.f_code.co_firstlineno )
            tracetxt += u"   With locals:\n"
            for var,val in trace.tb_frame.f_locals.items():
                tracetxt += u"     %s = %s\n" % ( var, `val` )
            trace = trace.tb_next
        tracetxt += u'Exception type: %s, value: %s\n' % ( `extype`, str(value) )
        szr.Add( wx.TextCtrl( tmp, -1, polymer.encode.encode_ui(tracetxt), style=wx.TE_READONLY|wx.TE_MULTILINE ), 1, wx.EXPAND|wx.ALL, border=5 )
        szr.Add( wx.Button( tmp, wx.ID_OK, "Oh" ), 0, wx.GROW|wx.ALIGN_CENTRE|wx.ALL, border=5 )
        tmp.SetSizer( szr )
        szr.Fit( tmp )
        tmp.SetAutoLayout(1)
        tmp.ShowModal()
        tmp.Destroy()
    finally:
        del trace
        sys.excepthook = gui_excepthook

class AcapHome( polymer.dialogs.Base ):
    """
    Dialog to request home ACAP server
    """
    def __init__( self, parent, defaulturl=None ):
        """
        Normal dialog init.
        """
        self.home = None
        if defaulturl is not None:
            try:
                self.home = infotrope.url.URL( defaulturl )
            except:
                pass
        polymer.dialogs.Base.__init__( self, parent, "ACAP Server" )
        
    def add_prompts( self, p ):
        """
        Add prompts for ACAP hostname and authentication details.
        """
        self.AddPreamble( p, "Infotrope Polymer needs to know where your\nprimary ACAP server is." )
        self.AddPreamble( p, "Please enter the information below." )
        self.AddPreamble( p, "If you don't have an ACAP server, and\nyou don't wish to use the free public-acap server,\njust cancel this dialog." )
        u = None
        m = 'Any'
        s = None
        if self.home is not None:
            s = self.home.server
            if self.home.port is not None:
                s = '%s:%d' % ( self.home.server, self.home.port )
            if self.home.mechanism is not None:
                m = self.decode_sasl_method( self.home.mechanism )
            u = self.home.username
        if u is None:
            import getpass
            try:
                u = getpass.getuser()
            except:
                pass
        self.AddPrompt( p, "ACAP Server", '_acap_server', s )
        self.AddSecurityPrompt( p, "Authentication", "Username", '_acap', m, u )

    def Okay( self, event ):
        """
        On OK button, construct URL from details.
        """
        server = polymer.encode.decode_ui( self.prompts['_acap_server'].GetValue() )
        uri = infotrope.url.URL('acap://%s/' % server)
        mechinfo = self.encode_sasl_method( self.prompts['_acap_method'].GetStringSelection() )
        if mechinfo != 'ANONYMOUS':
            uri.username = polymer.encode.decode_ui( self.prompts['_acap_username'].GetValue() ).encode('utf8')
            uri.mechanism = mechinfo
        self.home = infotrope.url.URL( uri )
        self.SetReturnCode( wx.ID_OK )
        self.EndModal( wx.ID_OK )

EVT_PROD_ID = wx.NewId()
class ProdEvent(wx.PyEvent):
    def __init__( self ):
        wx.PyEvent.__init__( self )
        self.SetEventType( EVT_PROD_ID )

    def Clone( self ):
        return ProdEvent()
def EVT_PROD(win,func):
    win.Connect( -1, -1, EVT_PROD_ID, func )

class MyApp(wx.App,infotrope.environment.environment):
    """
    Main application object.
    """
    def __init__( self, redirect=True ):
        import time
        self._email = None
        self._personalities = None
        self._timer = None
        self._progwin = None
        self.frame = None
        self.args = None
        self.non_starter = False
        self.cache = None
        self.cachepfx = None
        self.timers = []
        self._bookmarks = None
        self._filters = None
        self.home = None
        self.options = None
        self.icon = None
        self.sm = None
        self.settings = {}
        self.settings['uid-column-displayed'] = False
        self.start_time = time.time()
        self.frozen = None
        'Environment stuff'
        infotrope.environment.environment.__init__( self )
        self.defcall = False #True # Breaks with True during setup.
        self.__defcalls = []
        wx.App.__init__( self, redirect=redirect )

    def secquery( self, mech, question ):
        import polymer.serverman
        return polymer.serverman.secquery( mech, question )

    def callback( self, mech, vals ):
        import polymer.serverman
        return polymer.serverman.callback( mech, vals )
    
    def defer_call( self, obj, *args, **kw ):
        self.__defcalls.append( infotrope.environment.caller( obj, *args, **kw ) )
        #print " ** Now",len(self.__defcalls),"calls."
        self.AddPendingEvent( ProdEvent() )
        #print " ** Posted event"

    def make_operation( self, title, status=None, pmax=None ):
        import polymer.progress
        return polymer.progress.operation_handle( title, status, pmax )
        
    def get_mime_description( self, mtype, subtype ):
        """
        Given a IMAP-style TYPE and SUBTYPE, return a description from somewhere.
        We try GNOME first, and fallback to WX.
        If WX fails too, give up and return the traditional type/subtype.
        """
        mtype = mtype.lower()
        subtype = subtype.lower()
        try:
            descr = gnomevfs.mime_get_description( mtype + '/' + subtype )
            if descr is not None:
                return descr
        except:
            pass
        ft = wx.TheMimeTypesManager.GetFileTypeFromMimeType( mtype + '/' + subtype )
        if ft is not None:
            if len(ft.GetDescription()) != 0:
                return ft.GetDescription()
        return mtype+'/'+subtype

    def get_mime_icon(self, mtype, subtype):
        mtype = mtype.lower()
        if subtype is None:
            subtype = 'x-default'
        else:
            subtype = subtype.lower()
        for t,s in [(mtype,subtype),('application','octet-stream'),('text','plain')]:
            ft = wx.TheMimeTypesManager.GetFileTypeFromMimeType(t + '/' + s)
            if ft is not None:
                icon = ft.GetIcon()
                if icon is not None and icon is not wx.NullIcon and icon.Ok():
                    return icon
            icon = wx.ArtProvider.GetIcon("gnome-%s-%s" % (t, s), wx.ART_MESSAGE_BOX)
            if icon is not None and icon is not wx.NullIcon and icon.Ok():
                return icon
            icon = wx.ArtProvider.GetIcon("gnome-mime-%s-%s" % (t, s), wx.ART_MESSAGE_BOX)
            if icon is not None and icon is not wx.NullIcon and icon.Ok():
                return icon
            icon = wx.ArtProvider.GetIcon("gnome-mime-%s" % (t), wx.ART_MESSAGE_BOX)
            if icon is not None and icon is not wx.NullIcon and icon.Ok():
                return icon
        icon = wx.ArtProvider.GetIcon(wx.ART_NORMAL_FILE, wx.ART_MESSAGE_BOX)
        if icon is None or icon is wx.NullIcon or not icon.Ok():
            return None
        return icon

    def connection( self, what ):
        """
        Wrapper to the serverman connection management object.
        """
        return self.sm[what]

    def remove_timers( self, unused=None ):
        """
        Delete all timers which don't exist anymore.
        """
        tmp = []
        for timeref in self.timers:
            realtime = timeref()
            if realtime is not None:
                tmp.append( weakref.ref( realtime, self.remove_timers ) )
        self.timers = tmp

    def prod( self, evt=None ):
        """
        Prodding - just passes prodding onto the serverman.
        """
        if self.sm is not None:
            self.sm.prod()
        objs = self.__defcalls
        if objs:
            #print " == Calling",len(objs),"deferred calls"
            self.__defcalls = []
            for o in objs:
                o()

    def status( self, message ):
        """
        Set status on main application frame.
        """
        if self.frame is not None:
            self.frame.add_status_text( message )

    def acap_home_uri( self ):
        """
        Returns the connection object for the primary (home) ACAP server.
        """
        if self.home:
            return
        if not self.home:
            if self.options.acap:
                if self.options.acap[0:7]!='acap://':
                    self.options.acap = 'acap://'+self.options.acap+'/'
                self.home = infotrope.url.URL( self.options.acap )
            elif self.cache:
                try:
                    self.home = infotrope.url.URL( file( self.cache ).readline().strip(' \r\n') )
                except:
                    pass
        if not self.home:
            durl = None
            import socket
            s = None
            try:
                s = socket.gethostbyname( 'acap' )
            except:
                pass
            if s is not None:
                try:
                    s = socket.gethostbyaddr( s )[0]
                except:
                    pass
                durl = 'acap://;AUTH=*@' + s + '/'
            for f in [wx.StandardPaths.Get().GetConfigDir(),wx.StandardPaths.Get().GetUserConfigDir()]:
                try:
                    durl = infotrope.url.URL( file( os.path.join( f, 'acapsrv.cfg' ) ).readline().strip( ' \r\n' ) )
                except:
                    pass
            if durl is None:
                durl = 'acap://;AUTH=*@public-acap.dave.cridland.net/'
            d = AcapHome( None, durl )
            if wx.ID_OK == d.ShowModal():
                self.home = d.home
                if self.acap_home() is None:
                    self.non_starter = True
            else:
                self.home = infotrope.url.URL('acap://nobody@__DUMMY__/')
                w = polymer.dialogs.MessageDialog( None, "I'll use a dummy ACAP server.\nThis functionality has not been tested well.", "Infotrope Polymer", wx.ICON_WARNING|wx.OK )
                w.ShowModal()
            d.Destroy()
        if self.home and self.cache:
            f = file( self.cache, "w" )
            f.write( self.home.asString() )
            f.write( '\n' )
            f.close()

    def acap_home( self ):
        if not self.home:
            self.acap_home_uri()
        if not self.home:
            return None    
        return self.sm[self.home]

    def get_option( self, what ):
        return self.settings[what]

    def set_option( self, what, how ):
        self.settings[what] = how

    def alert( self, uri, what ):
        foo = polymer.dialogs.ErrorDialog( None, "Alert from %s:\n%s" % ( uri.asString(), what ), "Infotrope Polymer" )
        foo.ShowModal()

    def running_as_exec( self ):
        if self.frozen is None:
            self.frozen = hasattr(sys, "frozen")
        return self.frozen
    
    def find_image( self, base ):
        polydir = os.path.dirname( __file__ )
        if self.running_as_exec():
            polydir = os.path.dirname( sys.executable )
            polydir = os.path.join( polydir, '..\\data' )
        for x in base.split('/'):
            polydir = os.path.join( polydir, x )
        return polydir

    def OnInit(self):
        """
        WX init function.
        """
        import infotrope.serverman
        self.options,self.args = polymer.options.handle_options()
        self.exit_clean_flag = False

        self.SetAppName( self.options.appname )
        
        if self.options.debug:
            self.logging = True
            self.SetAssertMode( wx.PYAPP_ASSERT_EXCEPTION )
        else:        
            self.SetAssertMode( wx.PYAPP_ASSERT_DIALOG )

        if self.options.trace:
            if self.options.trace.lower() in ["yes","1"]:
                self.protologging = True
            else:
                self.protologging = False
        else:
            self.protologging = self.logging
        
        if self.running_as_exec():
            if os.path.basename(sys.executable) == 'polymer.exe':
                if self.options.console:
                    dlg = polymer.dialogs.ErrorDialog( None, "Console mode not available from polymer.exe\nRun polymerd.exe instead.", "Infotrope Polymer" )
                    dlg.ShowModal()
                self.options.console = False
            else:
                self.options.console = True

        if not self.options.console:
            self.RedirectStdio()
            self.SetOutputWindowAttributes( title='Polymer Console' )
        
        wx.InitAllImageHandlers()
        if '__WXMSW__' in wx.PlatformInfo:
            self.icon = wx.Icon( self.find_image('invsys.ico'), wx.BITMAP_TYPE_ICO )
        else:
            self.icon = wx.Icon( self.find_image('invsys64.bmp'), wx.BITMAP_TYPE_BMP )

        if self.options.delay:
            self.sock_delay = self.options.delay
        if self.options.bandwidth:
            self.sock_bandwidth = self.options.bandwidth
        EVT_PROD( self, self.prod )
        self.sock_readable, self.sock_writable = self.readable, self.writable
        self.sm = infotrope.serverman.serverman( self )
        if self.sm is None:
            self.non_starter = True
            return False
        if not self.options.kiosk:
            import infotrope.sasl
            import infotrope.imap
            import infotrope.acap
            if self.options.cache:
                cachepfx = self.options.cache
            else:
                cachepfx = wx.StandardPaths.Get().GetUserDataDir()
            if not os.path.exists( cachepfx ):
                os.mkdir( cachepfx, 0700 )
            if not os.path.exists( os.path.join( cachepfx, 'cache' ) ):
                os.mkdir( os.path.join( cachepfx, 'cache' ) )
            infotrope.sasl.set_stash_file( os.path.join( cachepfx, 'stash' ) )
            infotrope.imap.set_cache_root( os.path.join( cachepfx, 'cache', 'imap' ) )
            infotrope.acap.set_cache_root( os.path.join( cachepfx, 'cache', 'acap' ) )
            self.cache = os.path.join( cachepfx, 'cache', 'master2' )
            self.cachepfx = cachepfx
        if self.options.ban_imap:
            import infotrope.imap
            s = self.options.ban_imap
            s = s.split(',')
            s = [ x.upper() for x in s ]
            infotrope.imap.suppress_extension = s
        if self.options.ban_esmtp:
            import infotrope.esmtp
            s = self.options.ban_esmtp
            s = s.split(',')
            s = [ x.upper() for x in s ]
            infotrope.esmtp.suppress_extension = s
        try:
            self.logger( "ACAP startup..." )
            self.acap_home_uri()
            if self.home is None:
                self.logger( "ACAP startup failed?" )
                self.non_starter = True
        except:
            self.logger( "ACAP startup exploded." )
            self.non_starter = True
            raise
        if self.non_starter:
            self.logger( "I'm a non-starter!" )
            return False
        self._timer = wx.PyTimer( self.prod )
        if self.options.mailto is not None:
            u = infotrope.url.URL( self.options.mailto )
            if u.scheme == 'mailto':
                self.process_url( self.options.mailto )
                self._timer.Start( 500 )
                return True
            else:
                d = polymer.dialogs.ErrorDialog( None, "URL is not mailto scheme.", "Infotrope Polymer" )
                d.ShowModal()
            self.non_starter = True
        if not self.non_starter:
            #self.help_provider = wx.help.SimpleHelpProvider()
            #wx.help.HelpProvider_Set( self.help_provider )
            if self.options.debug:
                self.logger( "Frame setup." )
            frame = polymer.mainframe.PolymerMainFrame( (640,480), self.options.debug )
            frame.SetIcon( self.icon )
            frame.Show(True)
            self.SetTopWindow(frame)
            self._timer.Start( 500 )
            if self.options.debug:
                self.logger( "Init complete." )
            self.frame = frame
            if self.options.exceptions:
                self.logger( "Setting GUI exception handler" )
                sys.excepthook = gui_excepthook
            if self.options.fatal:
                self.logger( "Switching to fatal exceptions" )
                sys.excepthook = fatal_excepthook
            if self.options.url is not None:
                self.process_url( self.options.url )
            return True
        return False

    def readable( self ):
        self.AddPendingEvent( ProdEvent() )
    def writable( self ):
        self.AddPendingEvent( ProdEvent() )

    def progwin( self ):
        if self._progwin is None:
            import polymer.progress
            self._progwin = polymer.progress.progwin()
        return self._progwin

    def pre_shutdown( self ):
        """
        Shutdown all timers, used just before shutdown.
        """
        self.logger( "Pre shutdown" )
        self._progwin = None
        if self.sm is not None:
            self.sm.status = None
        if self._timer is not None:
            self._timer.Stop()
            self._timer = None
        for x in self.timers:
            t = x()
            if t is not None:
                t.Stop()
        self.timers = []
        if self._email:
            self._email.shutdown()
        self._email = None
        if self._personalities:
            self._personalities.shutdown()
        self._personalities = None
        if self._bookmarks:
            self._bookmarks.shutdown()
        self._bookmarks = None
        if self._filters:
            self._filters.shutdown()
        self._filters = None
        self.sm = None
        self.logger( "Shutdown SM" )
        infotrope.serverman.shutdown()
        self.logger( "SM shutdown complete" )
    
    def OnExit( self ):
        """
        Called on shutdown.
        """
        if self.frame is not None:
            del self.frame
            self.frame = None
        if self.exit_clean_flag:
            if not self.options.kiosk:
                if self.cachepfx is not None:
                    def superm( path ):
                        import stat
                        st = os.stat(path)
                        if stat.S_ISDIR( st.st_mode ):
                            for x in os.listdir(path):
                                superm( os.path.join( path, x ) )
                            os.rmdir( path )
                        else:
                            os.remove( path )
                    superm( self.cachepfx )
        self.pre_shutdown()
        
    def email( self ):
        """
        Return email dataset entries.
        """
        self.acap_home_uri()
        if self._email is None:
            uri = infotrope.url.URL( self.home )
            uri.path = '/email/~/'
            uri = infotrope.url.URL( uri.asString() )
            self._email = infotrope.datasets.base.get_dataset( uri )
        return self._email

    def personalities( self ):
        """
        Return personality (identity) entries.
        """
        self.acap_home_uri()
        if self._personalities is None:
            uri = infotrope.url.URL( self.home )
            uri.path = '/personality/~/'
            uri = infotrope.url.URL( uri.asString() )
            self._personalities = infotrope.datasets.base.get_dataset( uri )
        return self._personalities

    def bookmarks( self ):
        """
        Return top-level bookmarks.
        """
        self.acap_home_uri()
        if self._bookmarks is None:
            u = infotrope.url.URL( self.home )
            u.path = '/bookmarks/~/'
            u = infotrope.url.URL( u.asString() )
            self._bookmarks = infotrope.datasets.base.get_dataset( u )
        return self._bookmarks
    
    def filters( self ):
        """
        Return top-level bookmarks.
        """
        import polymer.filters
        self.acap_home_uri()
        if self._filters is None:
            u = infotrope.url.URL( self.home )
            u.path = '/vendor.infotrope.filter/~/'
            u = infotrope.url.URL( u.asString() )
            self._filters = infotrope.datasets.base.get_dataset( u )
        return self._filters

    def process_url( self, url ):
        """
        Given a URI, do something sensible with it.
        """
        u = infotrope.url.URL( url )
        if u.scheme=='mailto':
            m = polymer.composer.MailtoMessage( self.frame, u )
            m.Show( True )
        elif u.scheme in ['http','https']:
            webbrowser.open( u.asString() )
        elif u.scheme in ['imap','imaps']:
            self.frame.process_imap_url( u )
        elif u.scheme=='acap':
            if u.dataset_class is not None:
                if u.dataset_class == 'email':
                    print "Add to email accounts."
                elif u.dataset_class == 'personality':
                    print "Add to personalities."
                elif u.dataset_class == 'bookmarks':
                    if u.path[-1:]=='/':
                        conn = self.sm.get( self.home )
                        if conn.ready:
                            import time
                            import socket
                            conn.store( '/bookmarks/~/' + str(time.time()) + '@' + socket.gethostname(), {'bookmarks.Name': 'Imported bookmarks', 'bookmarks.Type': 'folder', 'subdataset':[u.asString()] } )
                    else:
                        print "Add to bookmarks, possibly as Alias"
                elif u.dataset_class == 'addressbook':
                    print "If it's a dataset, add subdataset, otherwise add Reference."
                else:
                    print "No idea what to do with this class."
            else:
                print "Not clear what to do with a classless URI."
        else:
            print 'No idea what I might do with this.'
    
    def logger( self, *txt ):
        """
        Emit debugging log entry.
        """
        if self.options.debug:
            print "DEBUG LOG:",txt

    def proto_logger( self, uri, t, txt ):
        if self.protologging:
            print "TRACE: %s %.3f %s" % ( str(uri.root_user()), t - self.start_time, `txt` )

    def timer( self, callback ):
        """
        Create a timer, and record its existence for later destruction.
        """
        timer = wx.PyTimer( callback )
        self.timers.append( weakref.ref( timer, self.remove_timers ) )
        return timer
