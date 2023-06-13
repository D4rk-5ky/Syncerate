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

To start with clone this repo to your desired location.

Then start with make a list of Source datasets.
	
	The dataset's you wish to backup from
	
And then then make a list of Destiantion datasets
	
	The location you wish to save your backup to.
	
----

### lets make the sources list first.


The easy way to get a list for the sources is to use the command

```
zfs list -o name

Storage/Archivy
Storage/DataSet With Spaces
Storage/Grafana
Storage/HedgeDoc
Storage/Heimdall
Storage/Home-Assistant
Storage/Joplin
Storage/Kavita
Storage/Media
Storage/Mosquitto
Storage/NextCloud
Storage/Podcasts
Storage/Portainer
Storage/SyncThing
Storage/Vikunja
Storage/WallaBag
Storage/WatchTower
Storage/booksonic
```

Use whatever text editor such as Nano or Vim to make a file with the desired source datasets.

----

### Then the destination list is a little more loose.
You can decide yourself where you wish to safe the Dataets on the receiving end.

To make make sure the datasets goes to the right places i have choosen to compare the last part of the Datasets name to ensure they are transferred to the right location.

lets create a list for the destination

```
Storage/Docker-SyncoidTest/Archivy
Storage/Docker-SyncoidTest/DataSet With Spaces
Storage/Docker-SyncoidTest/Grafana
Storage/Docker-SyncoidTest/HedgeDoc
Storage/Docker-SyncoidTest/Heimdall
Storage/Docker-SyncoidTest/Home-Assistant
Storage/Docker-SyncoidTest/Joplin
Storage/Docker-SyncoidTest/Kavita
Storage/Docker-SyncoidTest/Media
Storage/Docker-SyncoidTest/Mosquitto
Storage/Docker-SyncoidTest/NextCloud
Storage/Docker-SyncoidTest/Podcasts
Storage/Docker-SyncoidTest/Portainer
Storage/Docker-SyncoidTest/SyncThing
Storage/Docker-SyncoidTest/Vikunja
Storage/Docker-SyncoidTest/WallaBag
Storage/Docker-SyncoidTest/WatchTower
Storage/Docker-SyncoidTest/booksonic
```

Now remember that the ledaing dataset i have choosen to save under needs to be created manually.
The script can only create the dataset it receive not something that doesnt exist.

So i wiuld prepare that with
`zfs create Storage/Docker-SyncoidTest`

----

