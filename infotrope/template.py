import infotrope.message

"""Given an optional imap.message and an action, this creates a suitable
template message.

It'll also tell you what actions are possible."""

class Action:
    def __init__(self, name, descr, parent=None):
        self.name = name
        self.descr = descr
        self.subactions = []
        self.metatype = parent or self
        if self.metatype is not self:
            self.metatype.subactions.append(self)

    def __repr__(self):
        return "<Action '%s', metatype '%s'>" % (self.name, self.metatype.name)

New = Action("New Message","Create a new message")
Reply = Action("Reply","Reply to current message")
ReplySender = Action("Reply Sender", "Reply to sender", Reply)
ReplyAll = Action("Reply All", "Reply to all", Reply)
#ReplyList = Action("Reply List", "Reply to list", Reply)
#ReplyListSender = Action("Reply List/Sender", "Reply to list and sender", Reply)
Forward = Action("Forward","Forward current message")

def all():
    return [New,Reply,Forward]

def all_possible(msg=None):
    if not msg:
        return [New]
    return [Forward,Reply]

def quote(msg, part):
    if part.type == 'TEXT':
        if part.subtype == 'PLAIN':
            if 'FORMAT' in part.params and part.params['FORMAT'].upper() == 'FLOWED':
                paras = infotrope.flowed.parse(msg.body(part))
                for p in paras:
                    p.quote_depth += 1
                return paras
            else:
                import StringIO
                x = StringIO.StringIO(msg.body(part))
                paras = []
                for l in x:
                    p = infotrope.flowed.para(1, l.rstrip())
                    p.flowed = False
                    paras.append(p)
                return paras
    return []

class reply_done:
    def __init__(self, msg):
        self.msg = msg
    def __call__(self):
        self.msg.flag('\\Answered')

class forward_done:
    def __init__(self, msg):
        self.msg = msg
    def __call__(self):
        self.msg.flag('$Forwarded')

def create(action, msg=None):
    #print `action`,`action.metatype`,`all_possible(msg)`
    if action.metatype in all_possible(msg):
        base = infotrope.message.Message()
        text = infotrope.message.FlowedTextPart()
        base.subparts.append( text )
        if action is Forward:
            base.subparts.append( infotrope.message.MessagePart(msg) )
            base.send_completed = forward_done(msg)
            return base
        if action.metatype is Reply:
            part = msg.parts().find_id('1')
            pp,pref = part.find('TEXT',{'PLAIN':4})
            paras = quote(msg, pp)
            text.set_paras(paras)
            base.to = msg.envelope().From
            if action is ReplyAll:
                base.cc = msg.envelope().To + msg.envelope().CC
            base.add_gen_header('In-Reply-To', msg.envelope().MessageID)
            refs = msg.reply_header('References')
            if refs:
                base.add_gen_header('References', msg.envelope().MessageID + ', ' + refs)
            else:
                base.add_gen_header('References', msg.envelope().MessageID)
            if msg.envelope().Subject:
                ns = msg.envelope().Subject
                ns.strip()
                if ns.lower()[:3] != 're:':
                    ns = u'Re: ' + ns
                base.subject = ns
            base.send_completed = reply_done(msg)
            return base
    return None
