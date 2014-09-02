#! /bin/sh -e

HACKNAME="librariansync"
PKGNAME="${HACKNAME}"
PKGVER="1.0"
DEVICE="pw2"

# check for kindletool
if (( $(kindletool version | wc -l) != 1 )) ; then
    echo "KindleTool (https://github.com/NiLuJe/KindleTool) needed to build this package."
    exit 1
fi

# create tar.gz
cp -R ../librariansync .
tar -zcvf librariansync.tar.gz librariansync/generate_collections.py librariansync/menu.json librariansync/README.md librariansync/config.xml

# build the update
kindletool create ota2 -d ${DEVICE} librariansync.tar.gz install.sh Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin

# cleanup
rm -R librariansync
rm librariansync.tar.gz