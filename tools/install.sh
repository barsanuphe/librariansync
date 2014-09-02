#!/bin/sh

# creating extensions dir if it does not exist
if [ ! -d /mnt/us/extensions ]; then
    mkdir /mnt/us/extensions
fi

# uncompressing librariansync files to /mnt/us/extenstions
[ -f librariansync.tar.gz ] && {
    tar -xvf librariansync.tar.gz -C /mnt/us/extensions
    rm -f librariansync.tar.gz
}

return 0