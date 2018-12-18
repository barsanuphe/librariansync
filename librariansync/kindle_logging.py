import syslog
from _fbink import ffi, lib as fbink

# ------- Logging & user feedback (from the K5 Fonts Hack)

LIBRARIAN_SYNC = "LibrarianSync"

# Setup FBInk to our liking...
FBINK_CFG = ffi.new("FBInkConfig *")
FBINK_CFG.is_quiet = True
FBINK_CFG.is_padded = True
FBINK_CFG.is_centered = True
# FIXME: Switch from padded + centered to rpadded when that hits a snapshot...
#FBINK_CFG.is_rpadded = True
FBINK_CFG.row = -6

# And initialize it
fbink.fbink_init(fbink.FBFD_AUTO, FBINK_CFG)


def log(program, function, msg, level="I", display=True):
    global LAST_SHOWN
    # open syslog
    syslog.openlog("system: %s %s:%s:" % (level, program, function))
    # set priority
    priority = syslog.LOG_INFO
    if level == "E":
        priority = syslog.LOG_ERR
    elif level == "W":
        priority = syslog.LOG_WARNING
    priority |= syslog.LOG_LOCAL4
    # write to syslog
    syslog.syslog(priority, msg)
    #
    # NOTE: showlog / showlog -f to check the logs
    #

    if display:
        program_display = " %s: " % program
        displayed = " "
        # If loglevel is anything else than I, add it to our tag
        if level != "I":
            displayed += "[%s] " % level
        displayed += msg.encode('utf-8', 'replace')
        # print using fbink
        fbink.fbink_print(fbink.FBFD_AUTO, "%s\n%s" % (program_display, displayed), FBINK_CFG)
