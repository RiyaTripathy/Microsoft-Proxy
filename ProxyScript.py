import os
import urllib.request
import sys
import requests
import json
import configparser
from datetime import datetime
import uuid

#Fetching Microsoft IPv4 endpoints

orig_stdout = sys.stdout
sys.stdout = open('endpointlist.txt', 'w')

# helper to call the webservice and parse the response
def  webApiGet(methodName, instanceName, clientRequestId):
    ws = "https://endpoints.office.com"
    requestPath = ws + '/' + methodName + '/' + instanceName + '?clientRequestId=' + clientRequestId
    request = urllib.request.Request(requestPath)
    with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())


# path where client ID and latest version number will be stored
datapath ='endpoints_clientid_latestversion.txt'

# getting today's date
DateToday = datetime.now().date()

# fetch client ID and version if data exists; otherwise create new file
if os.path.exists(datapath):
    with open(datapath, 'r') as fin:
        clientRequestId = fin.readline().strip()
        latestVersion = fin.readline().strip()

    # call version method to check the latest version, and pull new data if version number is different
    try:
        version = webApiGet('version', 'Worldwide', clientRequestId)
    except urllib.request.URLError as e:
        with open('message.txt', 'w') as f:
            f.write("Microsoft endpoint URL is not valid")
            exit()
    except urllib.request.HTTPError as e:
        with open('message.txt', 'w') as f:
            f.write("Unable to establish connection with the microsoft endpoint")
            exit()


    #get the difference between today's date and last version and check if its equal to 30
    s = latestVersion
    date1 = datetime(year=int(s[0:4]), month=int(s[4:6]), day=int(s[6:8]))
    lastversion = date1.date()

    diff = DateToday-lastversion
    days = diff.days
	
    # Read the config file to retrieve url, token , zonename and days_gap
    config = configparser.ConfigParser()
    config.read(sys.argv[1])
    url = config.get('Okta Variables', 'url')
    token = config.get('Okta Variables', 'token')
    zonename = config.get('Okta Variables', 'zonename')
    days_gap = int(config.get('Day Count', 'days_gap'))

    if days == days_gap:

        # write the new version number to the data file
        with open(datapath, 'w') as fout:
            fout.write(clientRequestId + '\n' + version['latest'])

        #call endpoint method to write the IPv4 addresses in endpointlist.txt
        try:
            endpointSets = webApiGet('endpoints', 'Worldwide', clientRequestId)
        except urllib.request.URLError as e:
            with open('message.txt', 'w') as f:
                f.write("Microsoft endpoint URL is not valid")
                exit()
        except urllib.request.HTTPError as e:
            with open('message.txt', 'w') as f:
                f.write("Unable to establish connection with the microsoft endpoint")
                exit()
        # filter results for Allow and Optimize endpoints, and transform these into tuples with port and category
        flatUrls = []
        for endpointSet in endpointSets:
            if endpointSet['id'] == 1:
                id = endpointSet['id']
                urls = endpointSet['urls'] if 'urls' in endpointSet else []
                tcpPorts = endpointSet['tcpPorts'] if 'tcpPorts' in endpointSet else ''
                udpPorts = endpointSet['udpPorts'] if 'udpPorts' in endpointSet else ''
                flatUrls.extend([(id, url, tcpPorts, udpPorts) for url in urls])
        flatIps = []
        for endpointSet in endpointSets:
            if endpointSet['id'] == 1:
                ips = endpointSet['ips'] if 'ips' in endpointSet else []
                id = endpointSet['id']
                # IPv4 strings have dots while IPv6 strings have colons, here we only require IPv4
                ip4s = [ip for ip in ips if '.' in ip]
                # If you want IPv6 also then uncomment the following line
                # ip6s = [ip for ip in ips if ':' in ip]
                tcpPorts = endpointSet['tcpPorts'] if 'tcpPorts' in endpointSet else ''
                udpPorts = endpointSet['udpPorts'] if 'udpPorts' in endpointSet else ''
                flatIps.extend([(id, ip, tcpPorts, udpPorts) for ip in ip4s])
                # Uncomment the below line if you want IPv6 addresses too
                # flatIps.extend([(id, ip, tcpPorts, udpPorts) for ip in ip6s])
        # print the proxy addresses to the endpointlist.txt
        print('\n'.join(sorted(set([ip for (id, ip, tcpPorts, udpPorts) in flatIps]))))

        # Resuming printing to console
        sys.stdout.close()
        sys.stdout = orig_stdout

        #Read the endpoint.txt to retrieve latest proxy IP address
        listofproxies = []
        with open('endpointlist.txt', 'r') as fp:
            for line in fp:
                listofproxies.append(line.strip())

        i = 0
        proxies = []
        for item in listofproxies:
            proxies.append("{'type': 'CIDR', 'value': '" + str(item) + "'}")

        msproxy = str(proxies).replace("'", '"')
        msproxy = msproxy.replace('"{', "{")
        msproxy = msproxy.replace('}"', "}")

    # Fetch the JSON Response pattern using GET Zone API

        #Form the Header

        headers = {
          'authorization': 'SSWS '+token,
          'content-type': 'application/json'
        }

        #Form the URL to fetch the id of the zone mentioned in the config file
        final_url = url + 'api/v1/zones?q=' + zonename

        # Call Get Zone API using HTTP GET to get the id of LegacyIPZone
        r1 = requests.get(final_url, headers=headers)
        data = json.loads(r1.text)
        get_status = r1.status_code

        with open('message.txt', 'w') as fout:
            if (get_status == 404):
                fout.write("Not found: LegacyIPZone not found")
                exit()
            if (get_status == 401):
                fout.write("Either URL is not correct or Invalid Token while retrieving LegacyIPZone Details")
                exit()


        #Retrieve the id of the zone and form the new url to fetch the response body for put API
        d = {}
        d = data[0]
        zoneid = d['id']
        newurl = url + 'api/v1/zones/' + zoneid


        r2 = requests.get(newurl, headers=headers)
        get_status = r2.status_code
        with open('message.txt', 'a+') as fout:
            if(get_status == 404):
                fout.write("Not found: LegacyIPZone not found")
                exit()
            if(get_status == 401):
                fout.write("Either URL is not correct or Invalid Token while retrieving LegacyIPZone Details")
                exit()

        # Manipulate the json response to update the proxy IPs
        data = json.loads(r2.text)

        data['proxies'] = msproxy
        data = str(data)
        data = data.replace("'[", "[")
        data = data.replace("]'", "]")
        data = data.replace("'", '"')
        data = data.replace('True', 'true')
        data = data.replace('False', 'false')
        data = data.replace('u"', '"')

        #Call the Update Zone API using HTTP PUT
        r3 = requests.put(newurl, headers=headers, data=data)
        put_status = r3.status_code
        #Save the response and status code to the message.txt file
        with open('message.txt', 'w') as fout:
            if (put_status == 404):
                fout.write("Not found: LegacyIPZone not found while putting the new proxy IPs in LegacyIPZone")
                exit()
            if (put_status == 401):
                fout.write("Either url is not correct or invalid token provided while putting the new proxy IPs in LegacyIPZone")
                exit()
            if (put_status == 400):
                fout.write("Request body not formed well while putting the new proxy IPs in LegacyIPZone")
                exit()
            if (put_status == 200):
                fout.write("Microsoft Endpoints are updated to Okta successfully!")
                exit()

else:
    with open('message.txt', 'w') as fout:
        fout.write('endpoints_clientid_latestversion.txt file does not exists! Creating a new file... '+'\n'+'Please change the days_gap value in config.txt file to the difference between current date and latest version date(2nd entry in the endpoints_clientid_latestversion.txt file)and run the script again manually.Once done, change days_gap value back to 30 and save it.'+'\n')
        clientRequestId = str(uuid.uuid4())
        try:
            version = webApiGet('version', 'Worldwide', clientRequestId)
        except urllib.request.URLError as e:
            with open('message.txt', 'w') as f:
                f.write("Microsoft endpoint URL is not valid")
                exit()
        except urllib.request.HTTPError as e:
            with open('message.txt', 'w') as f:
                f.write("Unable to establish connection with the microsoft endpoint")
                exit()
        # write the new version number to the data file
        with open(datapath, 'w') as fout:
            fout.write(clientRequestId + '\n' + version['latest'])

