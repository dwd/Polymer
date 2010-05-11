import time
import wx

class operation:
    def __init__( self, title, status = None, pmax = None ):
        self._title = title
        self._start = time.time()
        self._end = None
        self._pcur = 0
        self._pmax = pmax
        self._status = status or "Running..."
        
        self._twidg = None
        self._pwidg = None
        self._pgbar = None
        self._st_txt = None

        wx.GetApp().progwin().add_op( self )

    def update( self, status, pcur = None ):
        if pcur:
            self._pcur = pcur
        self._status = status

    def setmax( self, pmax ):
        self._pmax = pmax

    def title( self, parent ):
        if self._twidg is None:
            self._twidg = wx.StaticText( parent, -1, self._title )
        return self._twidg

    def progress( self, parent ):
        if self._pgbar is None:
            r = self._pmax or 10
            self._pgbar = wx.Gauge( parent, -1, r, style=wx.GA_HORIZONTAL )
        if self._pmax:
            self._pgbar.SetRange( self._pmax )
            self._pgbar.SetValue( self._pcur )
        self._pgbar.SetMinSize( (40, 10) )
        #print "Gauge:",`self._pgbar.GetMinSize()`
        if self._st_txt is None:
            self._st_txt = wx.StaticText( parent, -1, self._status )
        else:
            self._st_txt.SetLabel( self._status )
        #self._st_txt.Layout()
        #print "self._status",`self._status`,`self._st_txt.GetMinSize()`
        if self._pwidg is None:
            self._pwidg = wx.BoxSizer( wx.VERTICAL )
            self._pwidg.Add( self._pgbar, 0, wx.EXPAND )
            self._pwidg.Add( self._st_txt, 0, wx.ALL|wx.ALIGN_CENTRE_HORIZONTAL, border=2 )
            #self._pwidg.SetMinSize( (0,50) )
            #self._pwidg.SetItemMinSize( self._st_txt, 20, 10 )
        #self._pwidg.Layout()
        #print "Sizer:",`self._pwidg.GetMinSize()`
        return self._pwidg

    def stop( self ):
        self._status = 'Complete'
        self._pcur = self._pmax or 10
        self._end = time.time()

    def current( self ):
        if self._end is None:
            return True
        return ( time.time() - self._end ) < 3.0

    def long_runner( self ):
        if self._end is None:
            return ( time.time() - self._start ) > 0.75
        return False

class operation_handle:
    def __init__( self, title, status=None, pmax=None ):
        self.__op = operation( title, status, pmax )

    def update( self, status, pcur=None ):
        self.__op.update( status, pcur )
    
    def setmax( self, pmax ):
        self.__op.setmax( pmax )

    def stop( self ):
        self.__op.stop()
        self.__op = None

    def __del__( self ):
        if self.__op is not None:
            self.__op.stop()

class progwin( wx.MiniFrame ):
    def __init__( self ):
        wx.MiniFrame.__init__( self, None, -1, "In Progress...", name='polymer', style=wx.STAY_ON_TOP )
        self.panel = wx.Panel( self, -1 )
        self.sizer = wx.FlexGridSizer( cols=2, vgap=0 )
        self.sizer.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_ALL )
        self.panel.SetSizer( self.sizer )
        self.sizer.Fit( self.panel )
        self.panel.SetAutoLayout( True )
        #self.Enable( False )

        self._ops = []
        self._displayed_ops = []

        self._timer = wx.GetApp().timer( self.prod )
        self._timer_started = False

    def add_op( self, op ):
        self._ops.append( op )
        if not self._timer_started:
            self._timer.Start( 250 )
            self._timer_started = True
        
    def prod( self ):
        for x in self._displayed_ops:
            #print "--REMOVE"
            title = x.title( self.panel )
            progress = x.progress( self.panel )
            self.sizer.Show( title, False, True )
            self.sizer.Show( progress, False, True )
            self.sizer.Detach( title )
            self.sizer.Detach( progress )
        self.sizer.Layout()
        self._displayed_ops = []
        k = self._ops
        self._ops = [ x for x in k if x.current() ]
        showme = False
        for x in self._ops:
            if x.long_runner():
                showme = True
                break
        if showme:
            for x in self._ops:
                #print "++ADD"
                self._displayed_ops.append( x )
                title = x.title( self.panel )
                self.sizer.Add( title, 1, wx.ALL|wx.ALIGN_CENTRE_VERTICAL|wx.ALIGN_CENTER_HORIZONTAL, border=2 )
                self.sizer.Show( title, True, True )
                progress = x.progress( self.panel )
                self.sizer.Add( progress, 0, wx.ALL|wx.EXPAND, border=1 )
                self.sizer.Show( progress, True, True )
            self.sizer.Layout()
            #print `self.sizer.GetMinSize()`,`progress.GetMinSize()`
            s = self.sizer.GetMinSize()
            self.SetClientSize( s )
        self.Show( showme )
        if not self._ops:
            self._timer.Stop()
            self._timer_started = False
