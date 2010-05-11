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
import polymer.encode
import polymer.dialogs

"""
This is support code for GUI based use of serverman, Infotrope's URL manager.

Essentially, it provides very little, just a GUI based callback function.
"""

translate = {
    'password': ('Password',True),
    'username': ('Username',False)
    }

class Security( polymer.dialogs.Base ):
    def __init__( self, mech, vals ):
        self.mech = mech
        self.vals = vals
        polymer.dialogs.Base.__init__( self, None, "Authentication Needed" )

    def add_prompts( self, p ):
        self.AddPreamble( p, "Authentication information is needed\nfor service %s on server %s.\nusing method %s" % ( self.mech.sasl.service, self.mech.sasl.host, self.mech.mechname ) )
        for var,val in self.vals.items():
            q = True
            n = var.capitalize()
            if var in translate:
                n,q = translate[var]
            self.AddPromptReal( p, n, var, password=q )

    def Okay( self, event ):
        for var in self.vals.keys():
            if var in self.prompts:
                self.vals[var] = polymer.encode.decode_ui( self.prompts[var].GetValue() )
        self.SetReturnCode( wx.ID_OK )
        self.EndModal( wx.ID_OK )

def callback( mech, vals ):
    '''Fantastically simple WX based callback function for SASL.'''
    dlg = Security( mech, vals )
    foo = dlg.ShowModal()
    dlg.Destroy()
    if foo!=wx.ID_OK:
        import infotrope.sasl
        raise infotrope.sasl.cancelled( mech.sasl, mech )
    
class SecurityQuestion( polymer.dialogs.Base ):
    def __init__( self, mech, question ):
        self.mech = mech
        self.question = question
        polymer.dialogs.Base.__init__( self, None, "Security Question", flags=wx.YES_NO|wx.ICON_WARNING )

    def add_prompts( self, p ):
        self.AddPreamble( p, "Question about authentication to:\n%s\n%s" % ( self.mech.uri(), self.question ) )

def secquery( mech, question ):
    d = SecurityQuestion( mech, question )
    return d.ShowModal() == wx.ID_YES
