#!/bin/sh
#
#       Shell script that takes a beacon email message and does stuff with it
#
#       e.g. Post to Facebook, Send a XMPP(Jabber) message, update and OpenHAB item
#

LOG=/var/log/beacon_messages
HABURL=
XMPP_DEST=
tmp="/tmp/beacon.in.$$"

cp /dev/null $tmp

cat >> $tmp

#   Extract required fields

subject=`egrep "^Subject:" $tmp | head -1 | sed -e "s/Subject: //"`
type=`fgrep "<beacon+" $tmp | tail -1 | sed -e "s/.*beacon+//" -e "s/@.*//" | tr '[a-z]' '[A-Z]'`

#   If it is not a beacon message ignore it

if test "$subject" != "Beacon"
then
    rm -f $tmp
	exit 0
fi

echo "$datetime beacon: Received $type message" >> $LOG

#   Strip crud

msg=`cat $tmp | sed -e "1,/^$/d" -e "s/Call OC.*//" -e "s/'//g" | tr "\n" " "`

#   Determine type

echo $msg | egrep -q "^VR at"
if test $? -eq 0
then
    type="VR"
fi
echo $msg | egrep -q "^FR at"
if test $? -eq 0
then
    type="FR"
fi


datetime=`date +"%d.%m.%Y %H:%M:%S"`
echo "$datetime beacon: $msg" >> $LOG

case "$type" in
    132500)
        /share/scripts/fbpost.php $type "$msg"
        ;;
    VR|FR)
        /share/scripts/xsend.py $XMPP_DEST "$type: $msg"
        curl --header "Content-Type: text/plain" --request PUT --data "$type" $HABURL
        /share/scripts/fbpost.php $type "$msg"
        ;;
    TEST)
        /share/scripts/xsend.py $XMPP_DEST "$type: $msg"
        /share/scripts/fbpost.php $type "$msg"
        ;;
    SUPPORT)
        /share/scripts/xsend.py $XMPP_DEST "$type: $msg"
        curl --header "Content-Type: text/plain" --request PUT --data "$type" $HABURL
        /share/scripts/fbpost.php $type "$msg"
        ;;
    *)
        /share/scripts/fbpost.php Beacon "$msg" > /tmp/beaconmsg.out 2>&1
        ;;
esac

rm -f $tmp
