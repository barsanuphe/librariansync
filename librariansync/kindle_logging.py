import os, syslog, subprocess


#-------- Logging & user feedback (from the K5 Fonts Hack)
# NOTE: Hardcode HACKNAME for now
HACKNAME="librariansync"

# We'll need this to kill stderr
DEVNULL = open(os.devnull, 'wb')
# NOTE: Use subprocess.DEVNULL w/ Python 3.3

# Do the device check dance...
with open('/proc/usid', 'r') as f:
    kusid=f.read()

kmodel=kusid[2:4]
pw_devcodes=['24', '1B', '1D', '1F', '1C', '20']
pw2_devcodes=['D4', '5A', 'D5', 'D6', 'D7', 'D8', 'F2', '17', '60', 'F4', 'F9', '62', '61', '5F']

if kmodel in pw_devcodes or kmodel in pw2_devcodes:
    # PaperWhite 1/2
    SCREEN_X_RES=768
    SCREEN_Y_RES=1024
    EIPS_X_RES=16
    EIPS_Y_RES=24
else:
    # Touch
    SCREEN_X_RES=600
    SCREEN_Y_RES=800
    EIPS_X_RES=12
    EIPS_Y_RES=20
EIPS_MAXCHARS=SCREEN_X_RES / EIPS_X_RES
EIPS_MAXLINES=SCREEN_Y_RES / EIPS_Y_RES

def kh_msg(msg, level='I', show='a', eips_msg=None):
    # Check if we want to trigger an additionnal eips print
    if show == 'q':
        show_eips=False
    elif show == 'v':
        show_eips=True
    else:
        # NOTE: No verbose mode handling
        show_eips=False

    # Unless we specified a different message, print the full message over eips
    if not eips_msg:
        eips_msg=msg

    # Setup syslog
    syslog.openlog('system: {} {}:kh_msg::'.format(level, HACKNAME))
    if level == "E":
        priority = syslog.LOG_ERR
    elif level == "W":
        priority = syslog.LOG_WARNING
    else:
        priority = syslog.LOG_INFO
    priority |= syslog.LOG_LOCAL4
    # Print to log
    syslog.syslog(priority, msg)

    # Do we want to trigger an eips print?
    if show_eips:
        # NOTE: Hardcode the tag
        eips_tag="L"

        # If loglevel is anything else than I, add it to our tag
        if level != "I":
            eips_tag+=" {}".format(level)

        # Add a leading whitespace to avoid starting right at the left edge of the screen...
        eips_tag=" {}".format(eips_tag)

        # Tag our message
        eips_msg="{} {}".format(eips_tag, eips_msg)

        # Pad with blanks
        eips_msg='{0: <{maxchars}}'.format(eips_msg, maxchars=EIPS_MAXCHARS)

        # And print it (bottom of the screen)
        eips_y_pos=EIPS_MAXLINES - 2
        subprocess.call(['eips', '0', str(eips_y_pos), eips_msg], stderr=DEVNULL)
