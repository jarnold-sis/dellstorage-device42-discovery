#!/usr/bin/python

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import json
import base64
import configparser

#process Storage Center info from DSM and convert to Device42 Format
def processStorageCenter(storagecenter):
    sysdata = {}
    sysdata.update({'name': storagecenter['name']})
    sysdata.update({'manufacturer': 'Dell Inc.'})
    sysdata.update({'os': 'Storage Center'})
    sysdata.update({'osver': storagecenter['version']})
    sysdata.update({'type': 'cluster'})
    return sysdata   

#process Storage Center Controller info from DSM and convert to Device42 Format
def processController(controller):
    sysdata = {}
    sysdata.update({'name': controller['scName'] + ' - Controller - ' + str(controller['hardwareSerialNumber'])})
    sysdata.update({'serial_no': controller['serviceTag']})
    sysdata.update({'manufacturer': 'Dell Inc.'})
    sysdata.update({'os': 'Storage Center'})
    sysdata.update({'osver': controller['version']})
    sysdata.update({'hardware': controller['model'].upper()})
    sysdata.update({'object_category': 'Storage Infrastructure'})

    if 'SC8000' in controller['model'].upper():
        sysdata.update({'cpucount': 2})
        sysdata.update({'cpucore': 6})
        sysdata.update({'cpupower': 2500})
        sysdata.update({'type': 'physical'})
        
    elif 'SC9000' in controller['model'].upper():
        sysdata.update({'cpucount': 2})
        sysdata.update({'cpucore': 8})
        sysdata.update({'cpupower': 3200})
        sysdata.update({'type': 'physical'})

    #Other models exist but these are the only ones I have available to play with   
    else:
        sysdata.update({'type': 'physical'})

    sysdata.update({'memory': round(((float(controller['availableMemory'].split(' ')[0])/1024)/1024),3)})
    
    #if int(controller['availableMemory'].split(' ')[0]) > 16000000000:
    #    sysdata.update({'memory': 65536})
    #else:
    #    sysdata.update({'memory': 16384})

    return sysdata

#process Storage Center Disk Tray info from DSM and convert to Device42 Format
def processEnclosure(enclosure):
    sysdata = {}       
    sysdata.update({'name': enclosure['scName'] + ' - ' + enclosure['instanceName']})
        
    #This is the enclosure built into the base SC4020 chassis so needs special handling for the name
    if 'SC4020' in enclosure['model']:
        sysdata = {}
        sysdata.update({'name': enclosure['scName'] + ' - Chassis'})
        sysdata.update({'hardware': 'Dell Storage SC4020 Chassis'})
        sysdata.update({'is_it_blade_host': 'yes'})
    elif 'SC200' in enclosure['model']:
        sysdata.update({'hardware': 'Dell Storage SC200 Expansion Enclosure'})
    elif 'SC220' in enclosure['model']:
        sysdata.update({'hardware': 'Dell Storage SC220 Expansion Enclosure'})
    else:
        sysdata.update({'hardware': enclosure['model']})
            
    sysdata.update({'serial_no': enclosure['serviceTag']})
    sysdata.update({'manufacturer': 'Dell Inc.'})
    sysdata.update({'type': 'physical'})
    sysdata.update({'object_category': 'Storage Infrastructure'})
        
    return sysdata

#process Storage Center Disk info from DSM and convert to Device42 Format
def processDisk(disk,enclosureName,diskspeed):
    diskdata = {}
    diskdata.update({'type': 'Hard Disk'})
    diskdata.update({'name': disk['instanceName']})
    diskdata.update({'modelno': disk['product']})
    diskdata.update({'serial_no': disk['serialNumber']})
    if 'GB' in disk['manufacturerCapacity']:
        diskdata.update({'hddsize': disk['manufacturerCapacity'].split(' ')[0]})
    if 'TB' in disk['manufacturerCapacity']:
        diskdata.update({'hddsize': float(disk['manufacturerCapacity'].split(' ')[0]) * 1000})

    #character limit for hard disk rpm is 8
    if diskspeed == 'Read-Intensive SSD':
        diskspeed = 'RI SSD'
    elif diskspeed == 'Write-Intensive SSD':
        diskspeed = 'WI SSD'

    diskdata.update({'hddrpm': diskspeed})
    diskdata.update({'firmware': disk['revision']})
    diskdata.update({'assignment': 'device'})
    diskdata.update({'manufacturer': disk['vendor']})
    diskdata.update({'device': enclosureName})
    diskdata.update({'raid_group': disk['diskTier']})
    diskdata.update({'slot': disk['enclosurePosition']})

    return diskdata

def main():
    #parse the config file
    config = configparser.ConfigParser()
    # config.readfp(open('dellstorage-device42.cfg'))
    config.read_file(open('dellstorage-device42.cfg'))
    dellusername = config.get('dell','username')
    dellpassword = config.get('dell','password')
    dellUri = config.get('dell','baseUri')
    d42username = config.get('device42','username')
    d42password = config.get('device42','password')
    device42Uri = config.get('device42','baseUri')
    d42_data_string=d42username + ':' + d42password
    d42_data_bytes=d42_data_string.encode("utf-8")
    dsheaders = {'Authorization': 'Basic ' + base64.b64encode(d42_data_bytes).decode(), 'Content-Type': 'application/x-www-form-urlencoded'}

    #Start a session with Dell Storage Manager
    s=requests.Session()
    s.headers.update({'Accept': 'application/json', 'Content-Type': 'application/json', 'x-dell-api-version': '3.1'})
    s.verify=False #disable once we get a real cert
    dell_data_string=dellusername + ':' + dellpassword
    dell_data_bytes=dell_data_string.encode("utf-8")
    dellauth = {'Authorization': 'Basic ' + base64.b64encode(dell_data_bytes).decode(), 'Content-Type': 'application/json', 'x-dell-api-version': '3.0'}
    r=s.post(dellUri+'/ApiConnection/Login','{}',headers=dellauth)

    #Loop through all available Storage Centers and push as much info as possible to Device42
    storagecenters=s.get(dellUri+'/StorageCenter/StorageCenter')
    for storagecenter in storagecenters.json():
        devicesInCluster=[]   
        storagecentersysdata = processStorageCenter(storagecenter)
        
        #do enclosures before controllers in case one is a controller chassis (e.g SC4020)
        try:
            enclosures=s.get(dellUri+'/StorageCenter/StorageCenter/'+storagecenter['instanceId']+'/EnclosureList')
            disks=s.get(dellUri+'/StorageCenter/StorageCenter/'+storagecenter['instanceId']+'/DiskConfigurationList')
            disktiers=s.get(dellUri+'/StorageCenter/StorageCenter/'+storagecenter['instanceId']+'/DiskFolderTierList')
        except Exception as err:
            print(err)

        if enclosures.status_code == 200:
            for enclosure in enclosures.json(): 
                enclosuresysdata = processEnclosure(enclosure)
                devicesInCluster.append(enclosuresysdata['name'])
                r=requests.post(device42Uri+'/device/',data=enclosuresysdata,headers=dsheaders)

                for disk in disks.json():
                    #print(json.dumps(disk, sort_keys=True, indent=4))
                    if enclosure['instanceName'] == disk['enclosureName']:
                        for disktier in disktiers.json():
                            if disk['diskTier'] == disktier['diskTier']:
                                diskspeed = disktier['availableDiskClasses'][0]

                        diskdata = processDisk(disk,enclosuresysdata['name'],diskspeed)
                        r=requests.post(device42Uri+'/parts/',data=diskdata,headers=dsheaders)
        else:
            print('Error getting enclosures - Response Code ' + str(enclosures.status_code))
            print(enclosures.text)
         
        controllers=s.get(dellUri+'/StorageCenter/StorageCenter/'+storagecenter['instanceId']+'/ControllerList')
        for controller in controllers.json():
            controllersysdata = processController(controller)
            devicesInCluster.append(controllersysdata['name'])
            r=requests.post(device42Uri+'/device/',data=controllersysdata,headers=dsheaders)
            
            controlleripdata = {}
            controlleripdata.update({'ipaddress': controller['ipAddress']})
            controlleripdata.update({'device': controllersysdata['name']})
            r=requests.post(device42Uri+'/ips/',data=controlleripdata,headers=dsheaders)
        
        storagecentersysdata.update({'devices_in_cluster': ','.join(devicesInCluster)})
        r=requests.post(device42Uri+'/device/',data=storagecentersysdata,headers=dsheaders)
        
        storagecenteripdata = {}
        storagecenteripdata.update({'ipaddress': storagecenter['managementIp']})
        storagecenteripdata.update({'device': storagecentersysdata['name']})
        r=requests.post(device42Uri+'/ips/',data=storagecenteripdata,headers=dsheaders)
        
    #Log off Dell Storage Manager
    r=s.post(dellUri+'/ApiConnection/Logout','{}')

    return

if __name__ == '__main__': 
    main()
