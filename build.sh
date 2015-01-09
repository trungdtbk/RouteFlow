#!/bin/sh

INSTALL_VMS=0
FETCH_ONLY=0
UPDATE=0
QUIET=1

OVS_VERSION="deb"
MONGO_VERSION="deb"
ZMQ_VERSION="3.2.4"
USE_MONGO=1

RFDIR=`pwd`
CONTROLLERS=""
DO="echo"
SUPER="$DO sudo"
APT_OPTS="-y"
PIP_OPTS=""

ROUTEFLOW_GIT="https://github.com/routeflow/RouteFlow.git"
DEPENDENCIES="build-essential git-core libboost-dev libboost-dev \
    libboost-program-options-dev libboost-thread-dev \
    libboost-filesystem-dev libboost-system-dev libnl-3-dev libnl-route-3-dev \
    python-dev python-pip python-bson"

usage() {
    echo "usage:$0 [-hcqvdsgiu] [-m MONGO_VERSION] [-o OVS_VERSION]" \
         "[controllers]"
    echo "Build RouteFlow and all of its dependencies."
    echo;
    echo "General options:"
    echo "  -h    Print this usage message"
    echo "  -c    Carry out the build (default: only echo commands)"
    echo "  -f    Only fetch the dependencies"
    echo "  -i    Install RouteFlow VMs"
    echo "  -p    Path to RouteFlow source directory"
    echo "  -v    Verbose output"
    echo;
    echo "Build options:"
    echo "  -d    Install binary versions of dependencies (default)"
    echo "  -s    Build release versions of dependencies"
    echo "  -g    Build git versions of dependencies"
    echo "  -u    Update (rebuild) dependencies even if they have been built"
    echo "  -z    Use ZeroMQ for IPC"
    echo;
    echo "Dependency version options:"
    echo "  Versions can be specified as \"deb\", \"X.Y.Z\" or \"git\""
    echo "  -m    Specify the MongoDB version to fetch" \
         "(default: $MONGO_VERSION)"
    echo "  -o    Specify the Open vSwitch version to fetch" \
         "(default: $OVS_VERSION)"
    echo;
    echo "Valid controllers: nox, ryu. Multiple may be" \
         "specified at once."
    echo "Controllers must be specified at the end of the command."
    echo;
    echo "Report bugs to: https://github.com/routeflow/RouteFlow/issues"
}

verlte() {
    local result=`echo "$1 < $2" | bc`
    [ "$result" = "1" ]
}

verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

get_versions() {
    text=`lsb_release -a 2>/dev/null`
    if [ $? -ne 0 ]; then
        return;
    fi

    # We need particular versions of our dependencies. If Ubuntu does not have
    # them in the repositories, then we need to fetch/build them.
    if (echo "$text" | grep -q "Ubuntu"); then
        version=`lsb_release -a 2>/dev/null | grep "Release" | cut -f2`

        # Versions prior to Ubuntu 12.04 don't supply MongoDB-2.0 and OVS.
        if (verlt $version "12.04"); then
            MONGO_VERSION="2.0.9"
            OVS_VERSION="1.10.0"
        fi

        if (echo "$*" | grep -q "ryu"); then
            OVS_VERSION="1.10.0";
        fi

        if (verlt $version "12.04"); then
            return
        elif (echo "$*" | grep -q "nox"); then
            echo "Cannot install NOX-Classic on Ubuntu 12.04+." && exit 1
        fi
    fi
}

parse_opts() {
    while getopts hcfqip:vdsgum:o:z option; do
        case "${option}" in
            c) DO="";
               SUPER="sudo";;
            f) FETCH_ONLY=1;
               APT_OPTS="${APT_OPTS} -d";;
            i) INSTALL_VMS=1;;
            p) RFDIR=${OPTARG};;
            v) QUIET=0;;
            d) MONGO_VERSION="deb";
               # ZMQ_VERSION="deb";  # Requires Ubuntu 13.10+
               OVS_VERSION="deb";;
            g) MONGO_VERSION="git";
               ZMQ_VERSION="git";
               OVS_VERSION="git";;
            u) UPDATE=1;;
            m) MONGO_VERSION=${OPTARG};;
            o) OVS_VERSION=${OPTARG};;
            z) USE_MONGO=0;;
            *) usage;
               exit 1;;
        esac
    done

    if [ $QUIET -eq 1 ]; then
        APT_OPTS="${APT_OPTS} -qq"
        PIP_OPTS="-q"
    fi
}

##
# Builds RouteFlow and all specified controllers.
#
# $@ - Commandline args to parse for controller names
##
build_routeflow() {
    print_status "Building RouteFlow"
    cd $RFDIR

    for arg in $@; do
        case $arg in
            nox) . $RFDIR/dist/build_nox.sh; get_nox;;
            ryu) . $RFDIR/dist/build_ryu.sh; get_ryu;;
        esac
    done

    if [ $FETCH_ONLY -ne 1 ]; then
        $DO ./boot.sh
        if [ $USE_MONGO -eq 1 ]; then
            $DO ./configure --with-ipc=mongo --enable-silent-rules --silent
        else
            $DO ./configure --with-ipc=zeromq --with-bson=api-mongo \
                            --enable-silent-rules --silent
        fi
        $DO make || fail "Couldn't build RouteFlow"

        if [ $INSTALL_VMS -eq 1 ]; then
            $DO cd rftest
            $SUPER mkdir -p /cgroup

            grep -q cgroup /etc/fstab
            if [ $? -eq 1 ]; then
                if [ -z "$DO" ]; then
                    echo "none /cgroup cgroup defaults 0 0" | $SUPER tee -a /etc/fstab > /dev/null
                else
                    $SUPER echo "none /cgroup cgroup defaults 0 0 >> /etc/fstab"
                fi
                if [ $? -ne 0 ]; then
                    print_status "Can't add cgroup to /etc/fstab" $YELLOW
                fi
            fi
            $SUPER mount none -t cgroup /cgroup
            $SUPER ./create || fail "Couldn't install VMs"
            $DO cd -
        fi
    fi

    print_status "Finishing up"
}

main() {
    get_versions $@
    parse_opts $@

    if [ `basename $RFDIR` != "RouteFlow" ]; then
        RFDIR="${RFDIR}/RouteFlow"
        if [ ! -d "$RFDIR" ]; then
            echo "Cannot find RouteFlow directory; Fetching it."
            git clone "$ROUTEFLOW_GIT" || exit 1;
        fi
    fi

    # Import scripts from dist/
    . $RFDIR/dist/common.sh
    for app in ovs mongo bson zmq; do
        . "$RFDIR/dist/build_$app.sh"
    done

    if [ "$DO" = "echo" ]; then
        print_status "Warning user" $YELLOW
        echo "This script may perform invasive changes to your system. By" \
             "default, we only"
        echo "print the changes that will be made. To confirm the build" \
             "process, add the"
        echo "\"-c\" option to the commandline arguments."
    fi

    print_status "Fetching dependencies"
    pkg_install "$DEPENDENCIES"
    get_ovs "$OVS_VERSION"

    if [ $USE_MONGO -eq 1 ]; then
        $SUPER pip install "pymongo"
        get_mongo "$MONGO_VERSION"
    else
        get_bson
        get_zmq "$ZMQ_VERSION"
    fi

    build_routeflow $@
}

main $@
