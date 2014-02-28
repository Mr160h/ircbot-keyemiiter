from socket import *
import sys, time, random, string, threading
from time import sleep
import win32con, win32api, win32gui, atexit

check_found = lambda s, k: (True if s.find(k) > -1 else False)

key_name_to_vk = {}
key_code_to_name = {}

_better_names = {
    "escape": "esc",
    "return": "enter",
    "back": "pgup",
    "next": "pgdn",
}

def _fillvkmap():
    # Pull the VK_names from win32con
    names = [entry for entry in win32con.__dict__ if entry.startswith("VK_")]
    for name in names:
        code = getattr(win32con, name)
        n = name[3:].lower()
        key_name_to_vk[n] = code
        if n in _better_names:
            n = _better_names[n]
            key_name_to_vk[n] = code
        key_code_to_name[code] = n


_fillvkmap()

def get_vk(chardesc):
    if len(chardesc)==1:
        # it is a character.
        info = win32api.VkKeyScan(chardesc)
        if info==-1:
            return None, None
        vk = win32api.LOBYTE(info)
        state = win32api.HIBYTE(info)
        modifiers = 0
        if state & 0x1:
            modifiers |= win32con.SHIFT_PRESSED
        if state & 0x2:
            modifiers |= win32con.LEFT_CTRL_PRESSED | win32con.RIGHT_CTRL_PRESSED
        if state & 0x4:
            modifiers |= win32con.LEFT_ALT_PRESSED | win32con.RIGHT_ALT_PRESSED
        return vk, modifiers
    # must be a 'key name'
    return key_name_to_vk.get(chardesc.lower()), 0

modifiers = {
    "alt" : win32con.LEFT_ALT_PRESSED | win32con.RIGHT_ALT_PRESSED, 
    "lalt" : win32con.LEFT_ALT_PRESSED, 
    "ralt" : win32con.RIGHT_ALT_PRESSED,
    "ctrl" : win32con.LEFT_CTRL_PRESSED | win32con.RIGHT_CTRL_PRESSED,
    "ctl" : win32con.LEFT_CTRL_PRESSED | win32con.RIGHT_CTRL_PRESSED,
    "control" : win32con.LEFT_CTRL_PRESSED | win32con.RIGHT_CTRL_PRESSED,
    "lctrl" : win32con.LEFT_CTRL_PRESSED,
    "lctl" : win32con.LEFT_CTRL_PRESSED,
    "rctrl" : win32con.RIGHT_CTRL_PRESSED,
    "rctl" : win32con.RIGHT_CTRL_PRESSED,
    "shift" : win32con.SHIFT_PRESSED,
    "key" : 0, # ignore key tag.
}

def parse_key_name(name):
    name = name + "-" # Add a sentinal
    start = pos = 0
    max = len(name)
    toks = []
    while pos<max:
        if name[pos] in "+-":
            tok = name[start:pos]
            # use the ascii lower() version of tok, so ascii chars require
            # an explicit shift modifier - ie 'Ctrl+G' should be treated as
            # 'ctrl+g' - 'ctrl+shift+g' would be needed if desired.
            # This is mainly to avoid changing all the old keystroke defs
            toks.append(tok.lower())
            pos += 1 # skip the sep
            start = pos
        pos += 1
    flags = 0
    # do the modifiers
    for tok in toks[:-1]:
        mod = modifiers.get(tok.lower())
        if mod is not None:
            flags |= mod
    # the key name
    vk, this_flags = get_vk(toks[-1])
    return vk, flags | this_flags

_checks = [
    [ # Shift
    ("Shift", win32con.SHIFT_PRESSED),
    ],
    [ # Ctrl key
    ("Ctrl", win32con.LEFT_CTRL_PRESSED | win32con.RIGHT_CTRL_PRESSED),
    ("LCtrl", win32con.LEFT_CTRL_PRESSED),
    ("RCtrl", win32con.RIGHT_CTRL_PRESSED),
    ],
    [ # Alt key
    ("Alt", win32con.LEFT_ALT_PRESSED | win32con.RIGHT_ALT_PRESSED),
    ("LAlt", win32con.LEFT_ALT_PRESSED),
    ("RAlt", win32con.RIGHT_ALT_PRESSED),
    ],
]

def make_key_name(vk, flags):
    # Check alt keys.
    flags_done = 0
    parts = []
    for moddata in _checks:
        for name, checkflag in moddata:
            if flags & checkflag:
                parts.append(name)
                flags_done = flags_done & checkflag
                break
    if flags_done & flags:
        parts.append(hex( flags & ~flags_done ) )
    # Now the key name.
    if vk is None:
        parts.append("<Unknown scan code>")
    else:
        try:
            parts.append(key_code_to_name[vk])
        except KeyError:
            # Not in our virtual key map - ask Windows what character this
            # key corresponds to.
            scancode = win32api.MapVirtualKey(vk, MAPVK_VK_TO_CHAR)
            parts.append(unichr(scancode))
    sep = "+"
    if sep in parts: sep = "-"
    return sep.join([p.capitalize() for p in parts])

def now():
    return int(round(time.time() * 1000))

class Protocol:
    def __init__(self, server, port=6667):
        print "IRC: Connecting to '%s:%i'" % (server,port)
        self.connection = socket(AF_INET, SOCK_STREAM)
        self.connection.connect((server, port))

    def send(self, message):
        datasent = 0
        message += "\n"

        """
        Continue sending chunks of the message until
        the entire message has been sent to the server
        """
        while datasent < len(message):
            sent = self.connection.send(message)
            if sent == 0:
                raise RuntimeError, "Connection reset by peer."
            else:
                datasent += sent

    def recv(self):
        return self.connection.recv(1024)

    def join(self, channel):
        joinData = "JOIN %s" % channel
        print "IRC: JOIN: '%s'" % ( joinData )
        self.send(joinData)

    def notice(self, nickname, text):
        print "IRC: Notice..."
        self.send("NOTICE %s :%s" % (nickname, text))

    def privmsg(self, reciever, message):
        self.send("PRIVMSG %s :%s" % (reciever, message))

    def identify(self, username, password = None):
        print "IRC: Identify '%s' '%s' '%s'" % ( username, username, password )
        if password:
            passData = "PASS %s" % password
            print "IRC: " + passData
            self.send( passData )
        userData = "USER %s localhost localhost :%s" % (username, username)
        print "IRC: " + userData
        self.send( userData )
        nickData = "NICK %s" % username
        self.send( nickData )
        print "IRC: " + nickData

    def whois(self, nickname):
        print "IRC: Whois..."
        self.send("WHOIS %s" % nickname)

        # Pull down who is data from server
        data = str()
        while not check_found(data, "End of WHOIS"):
            data += self.recv()

        return data

    def disconnect(self, message="Disconnected"):
        print "IRC: disconnect"
        self.send("QUIT :%s" % message)
        #time.sleep(5.0)
        #self.connection.shutdown(SHUT_RDWR)
        #self.connection.close()

class Bot:
    def __init__(self, server, port, channel, nick, password = None ):
        # Initialize IRC protocol
        self.protocol = Protocol(server, port)
        self.protocol.identify(nick,password)

        # Initialize class variables
        self.server = server
        self.port = port
        self.channel = channel
        self.nick = nick
        self.password = password
        self.data = None
        self.joined = False

    def update(self):
        # Recieve incoming data from server
        self.data = self.protocol.recv()
        self.lines = filter(len, string.split(self.data, "\r\n") )
        #if len(self.lines) > 0:
        #    print self.lines

        # Check for and respond to PING requests
        if check_found(self.data, "PING"):
            ping = self.data.rstrip().split()
            pongData = "PONG %s" % ping[1]
            print "IRC: PONG: '%s'" % ( pongData )
            self.protocol.send( pongData )

            # Check to see if the client has joined their
            # specirfied channel yet, if not then join it
            if not self.joined:
                print "IRC: joining channel '%s'..." % ( self.ircBot.channel )
                self.protocol.join(self.channel)
                self.joined = True

    def get_args(self):
        return self.data.split()[4:]

    def get_username(self):
        return self.data.split("!")[0].strip(":")

    def get_hostname(self):
        return self.data.split("!")[1].split(" ")[0]

class KeyEmitter:
    def __init__( self, keyMap, windowClass = None, windowTitle = None ):
        self.keyMap = keyMap
        self.windowClass = windowClass
        self.windowTitle = windowTitle;
        self.hwnd = None
        self.lastKeyKeyUpThread = None
        self.lastKeyKeyUpStopEvent = None
        self.lastKeyKeyUpFailedEvent = None

    def keyDown( self, key ):
        if not key:
            return

        modifiers = 0
        if key[ 3 ]:
            modifiers |= 1 << 29
            win32api.SendMessage(self.hwnd, win32con.WM_SYSKEYDOWN, win32con.VK_MENU, modifiers)
        win32api.SendMessage(self.hwnd, win32con.WM_KEYDOWN, key[ 0 ], modifiers ) 

    def keyUp( self, key ):
        if not key:
            return

        modifiers = 1 << 31
        win32api.SendMessage(self.hwnd, win32con.WM_KEYUP, key[0], modifiers)
        if key[ 3 ]:
            modifiers |= 1 << 31
            win32api.SendMessage(self.hwnd, win32con.WM_KEYUP, win32con.VK_MENU, modifiers )
            win32api.SendMessage(self.hwnd, win32con.WM_SYSKEYUP, win32con.VK_MENU, modifiers )

    def delayedKeyUp( self, key ):
        print "delayedKeyUp '%i' for %.1f seconds" % ( key[ 0 ], key[ 2 ] )
        self.lastKeyKeyUpStopEvent = threading.Event()
        self.lastKeyKeyUpFailedEvent = threading.Event()
        self.lastKeyKeyUpThread = threading.Thread(target=self.delayedKeyUpThread,
                                                    args=(self.lastKeyKeyUpStopEvent, 
                                                            self.lastKeyKeyUpFailedEvent, key, key[ 2 ] * 1000 + now() ) )
        self.lastKeyKeyUpThread.start()

    def delayedKeyUpThread( self, stopEvent, failedEvent, key, keyUpTime ):
        try:
            while not stopEvent.is_set():
                if now() >= keyUpTime:
                    self.keyUp( key )
                    return
            self.keyUp( key )
        except:
            print "=== Unhandled exception in delayedKeyUpThread - raising ==="
            failedEvent.set()
            raise


    def onInput( self, cmd ):
        if not cmd in self.keyMap:
            #print "Ignoring invalid key '%s'" % ( cmd )
            #print self.keyMap
            return

        self.hwnd = win32gui.FindWindow( windowClass, windowTitle )

        if not self.hwnd:
            print "KeyEmitter: Window for window class '" + windowClass + "' not found"
            return

        print "Cmd: '%s'" % ( cmd )
        key = self.keyMap[ cmd ]

        # release last key
        if self.lastKeyKeyUpThread:
            self.lastKeyKeyUpStopEvent.set()
            self.lastKeyKeyUpThread.join()
            self.lastKeyKeyUpThread = None

        # press next key
        self.keyDown( key )
        if key[ 2 ] != 0:
            self.delayedKeyUp( key )
        else:
            self.keyUp( key )

class ISuckAtGames:
    def __init__( self, ircBot, keyEmitter ):
        self.ircBot = ircBot
        self.keyEmitter = keyEmitter

    def parseLine( self, line ): 
        complete=line[1:].split(':',1) #Parse the message into useful data 
        info=None
        msg=None
        if len(complete) > 0:
            print "complete: '%s'" % complete
            info=complete[0].rstrip().split(' ')
            if len(complete) > 1:
                print "info: '%s'" % info
                msg=complete[1].strip().lower()
        sender=info[0].split('!') 
        print "sender: '%s'" % sender
        return ( complete, info, msg, sender )

    def handleReplies( self, code, sender ):
        if not code or not sender:
            return

        if code == "376": # end of motd
            if not self.ircBot.joined:
                print "IRC: FOUND END OF MOTD"
                print "IRC: joining channel '%s'..." % ( self.ircBot.channel )
                self.ircBot.protocol.join(self.ircBot.channel)
                self.ircBot.joined = True

    def run(self):
        try:
            while True:
                # thread failed
                if self.keyEmitter.lastKeyKeyUpFailedEvent:
                    if self.keyEmitter.lastKeyKeyUpFailedEvent.is_set():
                        sys.exit()

                self.ircBot.update()
                for line in self.ircBot.lines:
                    line = line.rstrip()
                    if bt.joined:
                        #print "IRC: '%s'" % ( line )
                        if check_found(line, "PRIVMSG"):
                            parsed = self.parseLine( line )
                            self.keyEmitter.onInput( parsed[2] )
                    else:
                        print "IRC: '%s'" % ( line )
                        parsed = self.parseLine( line )
                        if len(parsed) >= 4 and len(parsed[1]) >= 2 and len(parsed[3]) >= 1:
                            self.handleReplies( parsed[1][1], parsed[3][ 0 ] )        
        except (KeyboardInterrupt):
            print "Ctrl-C detect - exiting..."
            self.ircBot.protocol.disconnect()
            if self.keyEmitter.lastKeyKeyUpStopEvent:
                self.keyEmitter.lastKeyKeyUpStopEvent.set()
            sys.exit()
        except:
            print "=== Unhandled exception in main thread - raising ==="
            if self.keyEmitter.lastKeyKeyUpStopEvent:
                self.keyEmitter.lastKeyKeyUpStopEvent.set()
            self.ircBot.protocol.disconnect()
            raise

if __name__ == '__main__':
    windowClass = "SDL_app"
    windowTitle = None
    retroDoomKeyMap = {
        # hash key, (key,is_char_key,time down,alt modifier)
        # movement
        "w":(win32con.VK_UP,False,0.5,False),
        "w1":(win32con.VK_UP,False,1.0,False),
        "w2":(win32con.VK_UP,False,2.0,False),
        "up":(win32con.VK_UP,False,0.5,False),
        "forward":(win32con.VK_UP,False,0.5,False),
        "s":(win32con.VK_DOWN,False,0.2,False),
        "s1":(win32con.VK_DOWN,False,1.0,False),
        "s2":(win32con.VK_DOWN,False,2.0,False),
        "down":(win32con.VK_DOWN,False,0.2,False),
        "back":(win32con.VK_DOWN,False,0.2,False),
        "a":(win32con.VK_LEFT,False,0.2,True),
        "d":(win32con.VK_RIGHT,False,0.2,True),
        "q":(win32con.VK_LEFT,False,0.325,False),
        "q90":(win32con.VK_LEFT,False,0.75,False),
        "q180":(win32con.VK_LEFT,False,1.5,False),
        "left":(win32con.VK_LEFT,False,0.2,False),
        "left90":(win32con.VK_LEFT,False,0.75,False),
        "left180":(win32con.VK_LEFT,False,1.5,False),
        "e":(win32con.VK_RIGHT,False,0.325,False),
        "e90":(win32con.VK_RIGHT,False,0.75,False),
        "e180":(win32con.VK_RIGHT,False,1.5,False),
        "right":(win32con.VK_RIGHT,False,0.2,False),
        "right90":(win32con.VK_RIGHT,False,0.75,False),
        "right180":(win32con.VK_RIGHT,False,1.5,False),
        # weapons
        "f":(win32con.VK_LCONTROL,False,0,False),
        "fire":(win32con.VK_LCONTROL,False,0,False),
        "shoot":(win32con.VK_LCONTROL,False,0,False),
        "mouse1":(win32con.VK_LCONTROL,False,0,False),
        "punch":(win32con.VK_LCONTROL,False,0,False),
        "1":(get_vk("1")[0],True,0,False),
        "2":(get_vk("2")[0],True,0,False),
        "3":(get_vk("3")[0],True,0,False),
        "4":(get_vk("4")[0],True,0,False),
        "5":(get_vk("5")[0],True,0,False),
        "6":(get_vk("6")[0],True,0,False),
        "7":(get_vk("7")[0],True,0,False),
        # interaction
        "enter":(win32con.VK_RETURN,False,0,False),
        "space":(win32con.VK_SPACE,False,0,False),
        # general
        "idkfaidkfa":(get_vk("i")[0],True,0,False),
        #"save":(get_vk("F6")[0],True,0,False),
        #"loadload":(get_vk("F9")[0],True,0,False),
        "tab":(get_vk("tab")[0],True,0,False),
        "map":(get_vk("tab")[0],True,0,False),
        #"overlay":(get_vk("o")[0],True,0,False),
        "iddqdiddqd":(get_vk("g")[0],True,0,False),
    }

    print "Creating IRC bot"
    bt = Bot( "irc.freenode.net", 6667, "#channel", "name","password")
    print "Creating Key Emitter"
    ke = KeyEmitter( retroDoomKeyMap, windowClass, windowTitle )
    print "Creating Main App"
    app = ISuckAtGames(bt,ke)
    print "Entering Main Loop"
    app.run()


