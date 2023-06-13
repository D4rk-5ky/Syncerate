# SynCoid-Iterate

This is a Python3 script to use 

[Jim Salter's](https://github.com/jimsalterjrs) : [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid) 

To Send/Recieve Dataset's in list's

To make backing up ZFS DataSet's easy

----

### It has included options like 
1. Go over a list of ZFS Dataset's and Send/Receive them to a Remote/Local ZFS POOL
2. Logs
3. Send Mail on error or succesfull run
4. Shutdown the system when done
5. Use MQTT to send a message in case that is needed.
	(I use it to send an MQTT message to HomeAssistant and then it wil safely shutdown a PI4 and take the power from the Switch)
	
----

# How to use this script.

To start with one would have to make a list of Source datasets.
	The dataset's you wish to backup from
	
And then then make a list of Destiantion datasets
	The location you wish to save your backup to.
	
----

### lets make the sources list first.


