#! /bin/sh -e

HACKNAME="librariansync"
PKGNAME="${HACKNAME}"
PKGVER=$1
DEVICE="kindle5"

# check for kindletool
if (( $(kindletool version | wc -l) != 1 )) ; then
    echo "KindleTool (https://github.com/NiLuJe/KindleTool) needed to build this package."
    exit 1
fi

# create tar.gz
cp -R ../librariansync .
tar -zcvf librariansync.tar.gz \
    librariansync/generate_collections.py \
    librariansync/menu.json \
    librariansync/README.md \
    librariansync/config.xml \
    librariansync/kindle_contents.py \
    librariansync/kindle_logging.py \
    librariansync/cc_update.py

# patch config.xml
# not exactly the most elegant way to do this.
sed -i "s/<version>1.0<\/version>/<version>${PKGVER}<\/version>/g" librariansync/config.xml

# build the update
kindletool create ota2 -d ${DEVICE} librariansync.tar.gz install.sh Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin

# create release archive
cp librariansync/README.md .
tar -zcvf librariansync-${PKGVER}.tar.gz Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin README.md

# cleanup
rm README.md
rm -R librariansync
rm librariansync.tar.gz
rm Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin