import os
import syslog
import subprocess
import time

# ------- Logging & user feedback (from the K5 Fonts Hack)

LIBRARIAN_SYNC = "LibrarianSync"

# We'll need this to kill stderr
DEVNULL = open(os.devnull, 'wb')
# NOTE: Use subprocess.DEVNULL w/ Python >= 3.3

# Do the device check dance...
with open('/proc/usid', 'r') as f:
    kusid = f.read()

kmodel = kusid[2:4]
kmodel_v2 = kusid[3:6]
touch_devcodes = ['0F', '11', '10', '12']
pw_devcodes = ['24', '1B', '1D', '1F', '1C', '20']
pw2_devcodes = ['D4', '5A', 'D5', 'D6', 'D7', 'D8', 'F2', '17', '60', 'F4',
                'F9', '62', '61', '5F']
kv_devcodes = ['13', '54', '2A', '4F', '52', '53']
kt2_devcodes = ['C6', 'DD']
pw3_devcodes = ['0G1', '0G2', '0G4', '0G5', '0G6', '0G7',
                '0KB', '0KC', '0KD', '0KE', '0KF', '0KG']
koa_devcodes = ['0GC', '0GD', '0GP', '0GQ', '0GR', '0GS']
kt3_devcodes = ['0DT', '0K9', '0KA']

if kmodel in kv_devcodes:
    SCREEN_X_RES = 1088
    SCREEN_Y_RES = 1448
    EIPS_X_RES = 16
    EIPS_Y_RES = 24
elif kmodel in pw_devcodes or kmodel in pw2_devcodes:
    # PaperWhite 1/2
    SCREEN_X_RES = 768
    SCREEN_Y_RES = 1024
    EIPS_X_RES = 16
    EIPS_Y_RES = 24
elif kmodel in kt2_devcodes:
    # KT2
    SCREEN_X_RES = 608
    SCREEN_Y_RES = 800
    EIPS_X_RES = 16
    EIPS_Y_RES = 24
elif kmodel in touch_devcodes:
    # Touch
    SCREEN_X_RES = 600
    SCREEN_Y_RES = 800
    EIPS_X_RES = 12
    EIPS_Y_RES = 20
elif kmodel_v2 in pw3_devcodes or kmodel_v2 in koa_devcodes:
    # PW3 & Oasis (NOTE: Hopefully matches the KV...)
    SCREEN_X_RES = 1088
    SCREEN_Y_RES = 1448
    EIPS_X_RES = 16
    EIPS_Y_RES = 24
elif kmodel_v2 in kt3_devcodes:
    # KT3 (NOTE: Hopefully matches the KT2...)
    SCREEN_X_RES = 608
    SCREEN_Y_RES = 800
    EIPS_X_RES = 16
    EIPS_Y_RES = 24
else:
    # Fallback.
    SCREEN_X_RES = 600
    SCREEN_Y_RES = 800
    EIPS_X_RES = 12
    EIPS_Y_RES = 20
EIPS_MAXCHARS = SCREEN_X_RES / EIPS_X_RES
EIPS_MAXLINES = SCREEN_Y_RES / EIPS_Y_RES

LAST_SHOWN = 0
MINIMAL_DELAY = 0.15


def log(program, function, msg, level="I", display=True):
    global LAST_SHOWN
    # open syslog
    syslog.openlog('system: %s %s:%s:' % (level, program, function))
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
        displayed += msg.encode('ascii', 'replace')
        # pad with blanks
        displayed += (EIPS_MAXCHARS - len(displayed))*' '
        # to prevent unsightly screen flickering if ever two logs
        # are to be displayed in close temporal proximity
        delta = time.time() - LAST_SHOWN
        if delta < MINIMAL_DELAY:
            time.sleep(MINIMAL_DELAY-delta)
        # print using eips
        subprocess.call(['eips', '0', str(EIPS_MAXLINES - 3), program_display],
                        stderr=DEVNULL)
        subprocess.call(['eips', '0', str(EIPS_MAXLINES - 2), displayed],
                        stderr=DEVNULL)
        LAST_SHOWN = time.time()
