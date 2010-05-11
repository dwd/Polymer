#
# Copyright 2004,2005 Dave Cridland <dave@cridland.net>
#
# This file forms part of the Infotrope Python Library.
#
# The Infotrope Python Library is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# The Infotrope Python Library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with the Infotrope Python Library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

import infotrope.url
import infotrope.serverman
import infotrope.message

class Recipient:
    '''
    A Recipient, typically a email address or URI.
    The URI may be of scheme imap or mailto, currently.
    mailto URIs should not be used directly, just pass in
    a string containing the email address.
    '''
    def __init__( self, arg ):
        if isinstance( arg, str ):
            if arg.startswith( 'news:' ):
                arg = infotrope.url.URL( arg )
            else:
                arg = infotrope.url.URL( 'mailto:' + arg )
        if not isinstance( arg, infotrope.url.URL_base ):
            raise "Nope, you can only send to a URL or a string."
        if arg.scheme not in ['imap','imaps','mailto','news']:
            raise arg.scheme + " URIs not supported."
        self.uri = arg
        self.srv = None
        self.when_ready = None

    def is_email( self ):
        return self.uri.scheme == 'mailto'

    def is_mailbox( self ):
        return self.uri.scheme in ['imap','imaps']

    def is_news( self ):
        return self.uri.scheme == 'news'

    def prep( self, when_ready ):
        self.when_ready = when_ready
        self.prep_step()

    def prep_step( self ):
        if self.is_mailbox():
            if self.srv is None:
                sm = infotrope.serverman.get_serverman()
                srv = sm.get(self.uri)
                srv.notify_ready( self.server_ready )
                return
        self.when_ready( self )
        self.when_ready = None

    def server_ready( self, srv ):
        self.srv = srv
        self.prep_step()

    def server( self ):
        if self.srv is None:
            if self.is_mailbox():
                sm = infotrope.serverman.get_serverman()
                self.srv = sm[self.uri]
        return self.srv

    def mailbox( self ):
        s = self.server()
        if s is not None:
            mi = s.mbox_info( self.uri.mailbox )
            return mi

    def email( self ):
        if self.is_mailbox():
            mi = self.mailbox()
            if mi is not None:
                return mi.postaddress()
        elif self.is_email():
            return self.uri.path

    def __str__( self ):
        return str(self.uri)

class Transmit:
    def __init__( self, msg, env, smtp=None, sender=None, drafts=None, localimap=None ):
        self.msg = msg
        self.recips = []
        self.drafts = None
        self.smtp = smtp
        self.nntp = None
        self.sender = sender
        self.email_only = []
        self.folders_pa = []
        self.folders_nopa = []
        self.imapser_pa = {}
        self.imapser_nopa = {}
        self.news = []
        self.recip_map = {}
        self.callback = None
        self.esmtp_needed = False
        self.nntp_needed = False
        self.success = True
        self.env = env
        self._operation = None
        self.imaplocal = localimap or []

    def set_smtp( self, s ):
        self.smtp = s

    def add_recipient( self, r ):
        if not isinstance( r, Recipient ):
            r = Recipient( r )
        if r.is_news():
            if self.nntp is None:
                import os
                nh = os.getenv('NNTPSERVER')
                if nh is None:
                    raise "NNTP not supported, need env set."
                sm = infotrope.serverman.get_serverman()
                self.nntp = sm.get('nntp://'+nh)
        if len([x for x in self.recips if x.uri == r.uri ])==0:
            self.recips.append( r )

    def log( self, *what ):
        import infotrope.serverman
        sm = infotrope.serverman.get_serverman()
        sm.log( "Transmit", *what )

    def transmit( self, callback ):
        self.callback = callback
        self._operation = self.env.make_operation( "Transmit", "Collecting Data", 3 )
        self.collect_recipients()

    def collect_recipients( self ):
        for x in self.recips:
            self.recip_map[str(x)] = False
        for x in self.recips:
            x.prep( self.recip_ready )

    def recip_ready( self, r ):
        if str(r) in self.recip_map:
            del self.recip_map[str(r)]
        if not self.recip_map:
            self.examine_recipients()

    def examine_recipients( self ):
        import time
        self.log( "Examining recipients." )
        if self._operation:
            self._operation.update( "Storing copies", 1 )
        for x in self.recips:
            self.log( "Considering recipient", `x.uri` )
            if x.is_email():
                self.log( "... Is email only." )
                self.email_only.append( x )
            elif x.is_news():
                self.news.append(x)
            else:
                imapser = x.uri.root_user().asString()
                self.log( "... Is IMAP." )
                if x.email() is None:
                    self.log( "... Has no POSTADDRESS." )
                    self.folders_nopa.append( x )
                    self.imapser_nopa.setdefault( imapser, [] ).append( x )
                else:
                    self.log( "... Has POSTADDRESS:", `x.email()` )
                    self.folders_pa.append( x )
                    self.imapser_pa.setdefault( imapser, [] ).append( x )
        src_uris = self.msg.uri[:]
        self.log( "Have source URIs", `src_uris` )
        if self.imapser_nopa:
            self.src_uris = src_uris
            self.append_ops = {}
            self.nopas_prog = {}
            self.do_nopas()
        else:
            self.final_send()

    def do_nopas(self):
        for serv in self.imapser_nopa.keys():
            if serv in self.nopas_prog:
                continue
            recips = self.imapser_nopa[serv]
            x = recips[0]
            recips = recips[1:]
            if recips:
                self.imapser_nopa[serv] = recips
            else:
                del self.imapser_nopa[serv]
            self.nopas_prog[serv] = x.mailbox().append(self.msg, self.append_done)
            self.append_ops[self.nopas_prog[serv]] = serv
            
    def append_done(self, optag, success, msg):
        del self.nopas_prog[self.append_ops[optag]]
        del self.append_ops[optag]
        if not success and self.callback:
            self.callback(success,msg)
        elif not self.append_ops and not self.imapser_nopa:
            self.final_send()
        elif self.imapser_nopa:
            self.do_nopas()
        
    def final_send(self):
        if len(self.folders_pa) + len(self.email_only):
            self.log("Getting submission server")
            self.esmtp_needed = True
            self.smtp.notify_ready( self.esmtp_ready )
        if self.news:
            self.nntp_needed = True
            self.nntp.notify_ready( self.nntp_ready )
        self.log("Checking status")
        if not self.nntp_needed and not self.esmtp_needed:
            if self.callback:
                self.callback( self.success )
            if self._operation:
                self._operation.stop()
                self._operation = None
        elif self._operation:
            self._operation.update( "Sending message", 2 )

    def esmtp_ready( self, smtp ):
        if not smtp.ready:
            self.esmtp_complete( False, "Server unavailable" )
            return
        for x in self.imaplocal:
            smtp.add_friend(x)
        imap_first = None # By default, use POSTADDRESS.
        imap_first_len = 0
        trprops_smtp = self.smtp.get_trprops()
        trprops_smtp.lengthonly = True # Find the length, not the data.
        def tmp_uri( u ): # Spoof URLAUTH.
            return u.asString() + ';expires=1974-04-22T11:15:00Z;urlauth=anonymous:internal:01234567890123456789012345678901'
        trprops_smtp.uriratifier = tmp_uri
        #print "\n\nESMTP TL COUNT\n\n"
        smtp_len = self.msg.transmission_list( trprops_smtp )
        #print "\n\nESMTP TL COUNT DONE\n\n"
        allfolders = self.folders_pa[:]
        if self.drafts is not None:
            allfolders.append( Recipient( self.drafts ) )
        if len(allfolders) and self.smtp.have_capability('BURL'):
            for x in allfolders:
                if x.server().have_capability( 'UIDPLUS' ) and x.server().have_capability( 'URLAUTH' ): # Has the capabilities we need.
                    trprops_imap = x.get_trprops()
                    trprops_imap.lengthonly = True
                    l = self.msg.transmission_list( trprops_imap )
                    if l < smtp_len:
                        if imap_first is None or l < imap_first_len:
                            imap_first = x
        if imap_first:
            imap_first.append( self.msg )
        email_addresses = [x.email() for x in self.folders_pa + self.email_only if x is not imap_first ]
        if len(email_addresses):
            self.esmtp_trans = self.smtp.transaction( self.sender, email_addresses, self.msg, self.esmtp_complete )

    def esmtp_complete( self, st, txt ):
        self.success = self.success and st
        self.esmtp_needed = False
        if not self.nntp_needed:
            self.callback( self.success, txt )
            if self._operation:
                self._operation.stop()
                self._operation = None

    def nntp_ready( self, nntp ):
        if not nntp.ready:
            self.nntp_complete( None, 0x500, None, "NNTP server unavailable" )
            return
        self.nntp.cmd_post( self.msg.transmission_list( self.nntp.get_trprops() )[0][1], self.nntp_complete )

    def nntp_complete( self, cmd, r, e, txt ):
        self.success = self.success and (t&0xF00) == 0x200
        self.nntp_needed = False
        if not self.esmtp_needed:
            self.callback( self.success, txt )
            if self._operation:
                self._operation.stop()
                self._operation = None
