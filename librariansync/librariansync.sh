#!/bin/sh
#
# Wrapper script for the LibrarianSync KUAL extension
#
##

## First, a bit of stuff needed for loggign & visual feedback (adapted from libkh5)
KH_HACKNAME="librariansync"

# Pull some helper functions for logging
_FUNCTIONS=/etc/upstart/functions
[ -f ${_FUNCTIONS} ] && . ${_FUNCTIONS}

# Do the model dance...
kmodel="$(cut -c3-4 /proc/usid)"
case "${kmodel}" in
	"24" | "1B" | "1D" | "1F" | "1C" | "20" )
		# PaperWhite...
		IS_TOUCH="false"
	;;
	"D4" | "5A" | "D5" | "D6" | "D7" | "D8" | "F2" | "17" | "60" | "F4" | "F9" | "62" | "61" | "5F" )
		# PaperWhite 2...
		IS_TOUCH="false"
	;;
	* )
		# Touch
		IS_TOUCH="true"
	;;
esac
# Now use the right constants for our model...
if [ "${IS_TOUCH}" == "true" ] ; then
	SCREEN_X_RES=600	# _v_width @ upstart/functions
	SCREEN_Y_RES=800	# _v_height @ upstart/functions
	EIPS_X_RES=12		# from f_puts @ upstart/functions
	EIPS_Y_RES=20		# from f_puts @ upstart/functions
else
	SCREEN_X_RES=768	# NOTE: Yep, 768, not a typo...
	SCREEN_Y_RES=1024
	EIPS_X_RES=16		# Manually mesured, should be accurate.
	EIPS_Y_RES=24		# Manually mesured, should be accurate.
fi
EIPS_MAXCHARS="$((${SCREEN_X_RES} / ${EIPS_X_RES}))"
EIPS_MAXLINES="$((${SCREEN_Y_RES} / ${EIPS_Y_RES}))"

## Custom logging
# Arg 1 is logging message
# Arg 2 is logging level
# Arg 3 is eips logging status (quiet|verbose|auto)
# Arg 4 is eips message
##
kh_msg()
{
	# We need at least two args
	if [ $# -lt 2 ] ; then
		f_log W ${KH_HACKNAME} libkh5 "" "not enough arguments passed to kh_msg ($# while we need at least 2)"
		return
	fi

	kh_msg_string="${1}"
	kh_loglvl="${2}"

	# Check if we want to trigger an additionnal eips print
	case "${3}" in
		"q" | "Q" )
			kh_show_eips="false"
		;;
		"v" | "V" )
			kh_show_eips="true"
		;;
		* )
			# NOTE: No verbose mode handling for us
			kh_show_eips="false"
		;;
	esac

	# If we have a fourth argument, use it as a specific string to pass to eips, else use the same as f_log
	if [ -n "${4}" ] ; then
		kh_eips_string="${4}"
	else
		kh_eips_string="${kh_msg_string}"
	fi

	# Print to log
	f_log ${kh_loglvl} ${KH_HACKNAME} kh_msg "" "${kh_msg_string}"

	# Do we want to trigger an eips print?
	if [ "${kh_show_eips}" == "true" ] ; then
		# NOTE: Hardcode the tag
		kh_eips_tag="L"

		# If loglevel is anything else than I, add it to our tag
		if [ "${kh_loglvl}" != "I" ] ; then
			kh_eips_tag="${kh_eips_tag} ${kh_loglvl}"
		fi

		# Add a leading whitespace to avoid starting right at the left edge of the screen...
		kh_eips_tag=" ${kh_eips_tag}"

		# Tag our message
		kh_eips_string="${kh_eips_tag} ${kh_eips_string}"

		# Since eips doesn't trigger a full refresh, we'll have to padd our string with blank spaces to make sure two consecutive messages don't run into each other.
		while [ ${#kh_eips_string} -lt ${EIPS_MAXCHARS} ] ; do
			kh_eips_string="${kh_eips_string} "
		done

		# And finally, show our formatted message on the bottom of the screen (NOTE: Redirect to /dev/null to kill unavailable character & pixel not in range warning messages)
		eips 0 $((${EIPS_MAXLINES} - 2)) "${kh_eips_string}" >/dev/null
	fi
}

## And now we can start to do stuff!
generate_collections()
{
	# Go away if we don't have Python...
	if [ ! -f "/mnt/us/python/bin/python2.7" ] ; then
		kh_msg "can't do that: python is not installed" W v "python is not installed"
		return 1
	fi

	# Need to shift a bit to have consistent positional params
	shift

	if [ $# -lt 1 ] ; then
		kh_msg "not enough arguments passed to generate_collections ($# while we need at least 1)" W v "missing command"
		return 1
	fi

	command="${1}"

	# Let's go!
	kh_msg "Starting a ${command} action . . ." I v

	# Call our Python script
	/mnt/us/python/bin/python2.7 "${PWD}/generate_collections.py" "${command}"
	# And show some feedback
	if [ $? -eq 0 ] ; then
		kh_msg "Success :)" I v
	else
		kh_msg "Failure :(" W v
	fi
}

## Main
case "${1}" in
	"rebuild" )
		generate_collections "${1}"
	;;
	"add" )
		generate_collections "${1}"
	;;
	"rebuild_from_folders" )
		generate_collections "${1}"
	;;
	"update_from_calibre_plugin_json" )
		generate_collections "${1}"
	;;
	"rebuild_from_calibre_plugin_json" )
		generate_collections "${1}"
	;;
	"export" )
		generate_collections "${1}"
	;;
	* )
		kh_msg "invalid action (${1})" W v "invalid action"
	;;
esac
