#!/bin/sh
# Installs or updates lgess_live on an LG ESS.  Usage: ./install.sh <ess-ip>
set -e
HOST=${1:?usage: $0 <ess-ip>}
DIR=$(dirname "$0")
ssh root@$HOST 'mkdir -p /usr/local/lgess_live'
ssh root@$HOST 'cat > /usr/local/lgess_live/lgess_live.py' < "$DIR/custom_components/lgess_live/ess/lgess_live.py"
ssh root@$HOST 'cat > /etc/init.d/lgess_live && chmod 755 /etc/init.d/lgess_live' < "$DIR/custom_components/lgess_live/ess/lgess_live.init"
ssh root@$HOST 'ln -sf ../init.d/lgess_live /etc/rc5.d/S95lgess_live && /etc/init.d/lgess_live restart'
sleep 2
curl -s -m 5 "http://$HOST:8085/api/live" && echo
