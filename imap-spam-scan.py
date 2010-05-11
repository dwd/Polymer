import infotrope.serverman
import sys
import time

sm = infotrope.serverman.serverman()# logger=infotrope.serverman.cli_logger )

imuri = sys.argv[1]
try:
    import os
    import infotrope.sasl
    if not os.path.exists(sys.argv[2]):
        os.mkdir(sys.argv[2],0700)
    infotrope.sasl.set_stash_file(os.path.join(sys.argv[2], 'stash'))
except:
    pass

print "Connecting to %s" % (imuri)
imap = sm[imuri]
print "Connected."

def process_mail(mbox, cat_name, filter_string, prog, flags):
    f = infotrope.imap.mailbox_filter( mbox, filter_string )
    s = 0
    uid = 0
    msgs = []
    print "Mailbox has",`len(f)`,"%s messages" % (cat_name)
    import os
    p = None
    count = 0
    while s < len(f):
        while s < len(f):
            nuid = f.seqno( s+1 )
            if nuid != uid:
                uid = nuid
                break
            s += 1
        if uid is None:
            continue
        try:
            msg = f[uid]
            txt = msg.body_raw('')
            if p is None:
                p = os.popen( prog, "w" )
            p.write( "From ???@???? Sat Jan  3 01:05:34 1996\r\n" )
            p.write( txt )
            msgs.append(msg)
            count += 1
            if count >= 250:
                p.close()
                freezer = mbox.freeze()
                for msg in msgs:
                    msg.flag(flags)
                msgs = []
                freezer = None
                p = None
                count = 0
                s = 0
        except:
            print "Exception for message", uid
            try:
                msg = f[uid]
                msgs.append(msg)
                count += 1
            except:
                pass
        print "Remaining %s:" % cat_name,`(len(f) - s)`,"buffered:",count
    if p is not None:
        p.close()
        freezer = mbox.freeze()
        for msg in msgs:
            msg.flag(flags)
        freezer = None

def scan_tree( mi=None ):
    import infotrope.imap
    if mi is None:
        mi = imap.mbox_info()
    elif mi.selectable():
	print "Processing mailbox",`mi`
        mbox = mi.open()
        if mbox is not None:
            process_mail(mbox, "spam", "KEYWORD $Junk UNDELETED NOT KEYWORD Amavis", "sa-learn --mbox --progress --spam --no-sync -", ["Amavis", "\\Deleted", "$AutoJunk"])
            process_mail(mbox, "ham", "UNDELETED UNKEYWORD Amavis OR ANSWERED KEYWORD $Submitted", "sa-learn --mbox --progress --ham --no-sync -", ["Amavis", "$AutoNotJunk"])
    for c in mi.children().values():
        scan_tree( c )

def sa_sync():
    import os
    os.system('sa-learn --sync')

scan_tree()
sa_sync()
