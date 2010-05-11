import ctypes

# Zlib pullin.
zlib = None
zlib_counter = 0
def init_zlib():
    global zlib
    global zlib_counter
    if zlib is None:
        try:
            zlib = ctypes.cdll.LoadLibrary( '/usr/lib/libz.so' )
        except:
            try:
                zlib = ctypes.windll.zlibwapi
            except:
                import os.path
                zlib = ctypes.windll.LoadLibrary( os.path.join( os.path.dirname( __file__ ), 'zlibwapi.dll' ) )
    zlib_counter += 1

def fini_zlib():
    global zlib
    global zlib_counter
    if zlib is None:
        zlib_counter = 0
    else:
        zlib_counter -= 1
        if zlib_counter <= 0:
            zlib = None

# Redefinitions, based on zlib 1.2.3
class z_stream(ctypes.Structure):
    _fields_ = [
        ("next_in", ctypes.c_char_p),
        ("avail_in", ctypes.c_uint),
        ("total_in", ctypes.c_ulong),
        
        ("next_out", ctypes.c_void_p),
        ("avail_out", ctypes.c_uint),
        ("total_out", ctypes.c_ulong),
        
        ("msg", ctypes.c_char_p),
        ("state", ctypes.c_void_p),
        
        ("alloc_func", ctypes.c_void_p),
        ("free_func", ctypes.c_void_p),
        ("opaque", ctypes.c_void_p),
        
        ("data_type", ctypes.c_int),
        ("adler", ctypes.c_ulong),
        ("reserved", ctypes.c_ulong)
    ]


# RFC195X Generic objects
class rfc195X:
    def __init__( self, dict_load=None ):
        init_zlib()
        self._zstream = z_stream()
        self.__buffer = ctypes.create_string_buffer( 16384 )
        self.__in_buffer = ''
        self.__out_buffer = ''
        self._zstream.next_out = ctypes.addressof(self.__buffer)
        self._zstream.avail_out = 16384
        self._dict = dict_load
        self._data = False
        n = self.do_init_fn()
        if n:
            print "Initialization failed with %s" % `n`
            raise "Initialization failed with %s" % `n`
        if self._zstream.avail_out == 0:
            self.accumulate( self.__buffer.raw )
        else:
            self.accumulate( self.__buffer.raw[:-self._zstream.avail_out] )

    def __del__( self ):
        fini_zlib()
        
    def set_dict_loader( self, w ):
        self._dict = w

    def add( self, s, flush=0 ):
        if not s and not flush:
            return ''
        if s:
            self._data = True
        if flush==2 and not self._data:
            return ''
        if flush:
            self._data = False
        self.__in_buffer += str(s)
        done = False
        while not done:
            self._zstream.next_out = ctypes.addressof(self.__buffer)
            self._zstream.avail_out = 16384
            self._zstream.next_in = ctypes.c_char_p( self.__in_buffer )
            self._zstream.avail_in = len(self.__in_buffer)
            r = self.do_work_fn( flush )
            if r < 0 and r != -5:
                raise "zlib error: %d" % r
            if self._zstream.avail_in:
                self.__in_buffer = self.__in_buffer[-self._zstream.avail_in:]
            else:
                self.__in_buffer = ''
            if self._zstream.avail_in == 0:
                if flush != 4 or r == 0:
                    done = True
            if self._zstream.avail_out == 0:
                self.accumulate( self.__buffer.raw )
                self._zstream.avail_out = 16384
                done = False
            else:
                self.accumulate( self.__buffer.raw[:-self._zstream.avail_out] )
                self._zstream.avail_out = 16384
                done = True
            if flush == 4 and r != 1:
                done  = False
            if r == 1:
                self.do_reset_fn()
            if r == 2:
                self._dict( self )
                done  = False
        d = self.__out_buffer
        self.__out_buffer = ''
        return d

    def finish( self ):
        return self.add( '', 4 )

    def flush( self ):
        tmp = self.add( '', 2 )
        return tmp
        
    def accumulate( self, d ):
        self.__out_buffer += d
        
class rfc1950_uncompress(rfc195X):
    def __init__( self ):
        rfc195X.__init__( self )
        self._preload_data = None
        self._reset = True

    def do_init_fn( self ):
        return zlib.inflateInit_( ctypes.byref( self._zstream ), 9, "1.2.3", ctypes.sizeof( self._zstream ) )

    def do_work_fn( self, flush ):
        self._reset = False
        return zlib.inflate( ctypes.byref( self._zstream ), flush )

    def do_reset_fn( self ):
        r = zlib.inflateReset( ctypes.byref( self._zstream ) )
        self._reset = True
        if self._preload_data is not None:
            self.preload( self._preload_data )
        elif self._dict:
            self._dict( self )

    def preload( self, stuff ):
        if self._reset:
            stuff = stuff[:32768-262]
            r = zlib.inflateSetDictionary( ctypes.byref( self._zstream ), stuff, len(stuff) )
        else:
            self._preload_data = stuff
    
    def __del__( self ):
        zlib.inflateEnd( ctypes.byref( self._zstream ) )
        rfc195X.__del__( self )
        
class rfc1950_compress(rfc195X):
    def __init__( self, lvl=None, wbits=None, memlevel=None ):
	self.__lvl=lvl or 9
	self.__wbits=wbits or 15
	self.__memlevel=memlevel or 8
        rfc195X.__init__( self )

    def do_init_fn( self ):
        return zlib.deflateInit2_( ctypes.byref( self._zstream ), self.__lvl, 8, self.__wbits, self.__memlevel, 0, "1.2.3", ctypes.sizeof( self._zstream ) )

    def do_work_fn( self, flush ):
        return zlib.deflate( ctypes.byref( self._zstream ), flush )

    def do_reset_fn( self ):
        pass
    
    def preload( self, stuff ):
        stuff = stuff[:32768-262]
        tmp = self.finish()
        r = zlib.deflateReset( ctypes.byref( self._zstream ) )
        r = zlib.deflateSetDictionary( ctypes.byref( self._zstream ), stuff, len(stuff) )
        return tmp
    
    def __del__( self ):
        zlib.deflateEnd( ctypes.byref( self._zstream ) )
        rfc195X.__del__( self )
        

# RFC1951
class rfc1951_compress(rfc1950_compress):
    def __init__( self, lvl=None, wbits=None, memlevel=None ):
        wbits = wbits or 15
        wbits = -wbits
        rfc1950_compress.__init__( self, lvl, wbits, memlevel )

class rfc1951_uncompress(rfc1950_uncompress):
    def __init__( self ):
        rfc1950_uncompress.__init__( self )

    def do_init_fn( self ):
        return zlib.inflateInit2_( ctypes.byref( self._zstream ), -15, "1.2.3", ctypes.sizeof( self._zstream ) )

# RFC1952
class rfc1952_compress(rfc1950_compress):
    def __init__( self, dowhat ):
        rfc1950_compress.__init__( self )

    def do_init_fn( self ):
        return zlib.deflateInit2_( ctypes.byref( self._zstream ), 9, 8, 16+15, 9, 0, "1.2.3", ctypes.sizeof( self._zstream ) )
        
class rfc1952_uncompress(rfc1950_uncompress):
    def __init__( self, dowhat ):
        rfc1950_uncompress.__init__( self )

    def do_init_fn( self ):
        return zlib.inflateInit2_( ctypes.byref( self._zstream ), 16+15, "1.2.3", ctypes.sizeof( self._zstream ) )

# Get objects.

def compress( what, scheme ):
    import infotrope.url
    if isinstance(scheme,infotrope.url.URL_base):
        scheme = scheme.scheme
    else:
        try:
            u = infotrope.url.URL( scheme )
            scheme = u.scheme
        except:
            pass
    what = what.lower()
    if scheme in ['http','https']:
        if what.lower() == 'deflate':
            return rfc1950_compress()
        elif what.lower() == 'gzip':
            return rfc1952_compress()
        else:
            raise KeyError, what
    else:
        if what.lower() == 'deflate':
            return rfc1951_compress()
        elif what.lower() == 'zlib':
            return rfc1950_compress()
        elif what.lower() == 'gzip':
            return rfc1952_compress()
        else:
            raise KeyError, what

def decompress( what, scheme ):
    import infotrope.url
    if isinstance(scheme,infotrope.url.URL_base):
        scheme = scheme.scheme
    else:
        try:
            u = infotrope.url.URL( scheme )
            scheme = u.scheme
        except:
            pass
    what = what.lower()
    if scheme in ['http','https']:
        if what.lower() == 'deflate':
            return rfc1950_uncompress()
        elif what.lower() == 'gzip':
            return rfc1952_uncompress()
        else:
            raise KeyError, what
    else:
        if what.lower() == 'deflate':
            return rfc1951_uncompress()
        elif what.lower() == 'zlib':
            return rfc1950_uncompress()
        elif what.lower() == 'gzip':
            return rfc1952_uncompress()
        else:
            raise KeyError, what
