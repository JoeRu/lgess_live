#!/bin/sh
# Removes lgess_live from an LG ESS.  Usage: ./uninstall.sh <ess-ip>
HOST=${1:?usage: $0 <ess-ip>}
ssh root@$HOST '/etc/init.d/lgess_live stop; rm -f /etc/rc5.d/S95lgess_live /etc/init.d/lgess_live; rm -rf /usr/local/lgess_live'
