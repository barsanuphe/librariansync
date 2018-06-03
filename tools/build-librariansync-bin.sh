#! /bin/bash -e

# checking argument
if [ $# -eq 0 ]; then
    echo "Version number must be provided."
    exit 1
fi

HACKNAME="librariansync"
PKGNAME="${HACKNAME}"
PKGVER=$1
DEVICE="kindle5"

# Setup KindleTool packaging metadata flags to avoid cluttering the invocations
PKGREV="$(git describe --tags --always HEAD)"
KT_PM_FLAGS=( "-xPackageName=${PKGNAME}" "-xPackageVersion=${PKGVER}-r${PKGREV}" "-xPackageAuthor=barsanuphe" "-xPackageMaintainer=barsanuphe" "-X" )

# check for kindletool
if (( $(/usr/bin/kindletool version | wc -l) != 1 )) ; then
    echo "KindleTool (https://github.com/NiLuJe/KindleTool) needed to build this package."
    exit 1
fi

# create tar.gz
cp -R ../librariansync .
cp ../README.md .
tar -zcvf librariansync.tar.gz \
    librariansync/generate_collections.py \
    librariansync/menu.json \
    README.md \
    librariansync/config.xml \
    librariansync/kindle_contents.py \
    librariansync/kindle_logging.py \
    librariansync/cc_update.py

# patch config.xml
# not exactly the most elegant way to do this.
sed -i "s/<version>1.0<\/version>/<version>${PKGVER}<\/version>/g" librariansync/config.xml

# build the update
/usr/bin/kindletool create ota2 "${KT_PM_FLAGS[@]}" -d ${DEVICE} librariansync.tar.gz install.sh Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin

# create release archive
tar -zcvf librariansync-${PKGVER}.tar.gz Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin README.md

# cleanup
rm README.md
rm -R librariansync
rm librariansync.tar.gz
rm Update_${PKGNAME}_${PKGVER}_${DEVICE}.bin
