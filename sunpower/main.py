import json
import time
from urllib import request

from config import Config

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning) 

"""
SunPower does not provide a consumer accessible API.
This has not stopped me.
They do provide a website you can use to monitor your panels, so
a bit of hackery is required.

In HASS, I've set up the following custom sensor:

sensor:
  - platform: command_line
    scan_interval: 300
    name: Solar Production
    command: python sunpower.py
    unit_of_measurement: "kW"


TODO:
    * Make this a proper HASS module. (Maybe, because I also don't want to
        tip sunpower about their awesome site security model. ._.

"""


def config():
    """Return config values like username and password"""
    try:
        cfg = Config(open("sunpower.cfg", "r"))
        assert cfg.username, "Username not defined in config"
        assert cfg.password, "Password not defined in config"
        assert cfg.address, "Address not defined in config"
        if "offset" not in cfg:
            cfg.offset = 300
        return cfg
    except Exception as ex:
        print("Could not read configuration file: {}".format(ex))
        raise


def refresh_token(username, password):
    login_url = ("https://elhapi.edp.sunpower.com/v1/elh/authenticate")
    payload = json.dumps({"username": username, "password": password})
    req = request.Request(
        url=login_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload.encode(),
    )
    with request.urlopen(req) as resp:
        content = json.loads(resp.read().decode('utf-8'))
        #assert content["StatusCode"] == "200", "Fetch failed! {}".format(
        #    content)
        print(content)
        print(time.time())
        expiry = content["expiresEpm"] - 300 # 5 minute fuzz
        token = content["tokenID"]
        return {"expiry": expiry, "tokenID": token}


def check_token(username, password):
    cred_file = "/tmp/sunpower.cred"
    try:
        # case 1) old token available and not expired
        with open(cred_file) as cred:
            creds = json.loads(cred.read())
            if time.time() < creds["expiry"]:
                return creds["tokenID"]
        # case 2) old token available but expired 
        with open(cred_file, "w") as cred:
            creds = refresh_token(username, password)
            cred.write(json.dumps(creds))
            return creds["tokenID"]
    # case 3) no old token available
    except Exception as ex:
        with open(cred_file, "w") as cred:
            creds = refresh_token(username, password)
            cred.write(json.dumps(creds))
            return creds["tokenID"]


# def smooth(value):
#     """Attempt to "smooth" the data to prevent spikes on cloudy days. """
#     try:
#         with open("/tmp/solar.data", "r+") as history:
#             data = json.loads(history.read())
#             data.append(value)
#             history.seek(0)
#             data = data[-5:]
#             history.write(json.dumps(data))
#             history.truncate()
#     except Exception as ex:
#         with open("/tmp/solar_error.log", "a") as log:
#             log.write("{}: {}\n".format(time.strftime("%D-%T"), ex))
#         data = [0, 0, 0, 0, value]
#         with open("/tmp/solar.data", "w") as history:
#             history.write(json.dumps(data))
#     return sum(data) / float(len(data))


def get_ts(offset_secs=0):
    zulu = "%Y-%m-%dT%H:%M:00"
    now = time.localtime(int(time.time() + offset_secs))
    return time.strftime(zulu, now)


def fetch(address, tokenid, offset=30):
    """Fetch the data from SunPower. The panels update once every 5 minutes
    or so. """
    url = ("https://elhapi.edp.sunpower.com/v1/elh/address/%s/currentpower" % address)
    args = dict(
            #interval="HOUR",
            starttime=get_ts(-(offset*60)),
            endtime=get_ts(+120)
            )
    headers = {
            'Accept': "application/json, text/plain",
            'Accept-Language': "en-US",
            'Referer': 'https://monitor.us.sunpower.com/',
            'Authorization': 'SP-CUSTOM %s' % tokenid
            }

    # can't use requests because ":"
    arg_list = []
    for arg in args.items():
        arg_list.append("{}={}".format(arg[0], arg[1]))
    url = "{}?{}".format(url, "&".join(arg_list))

    # print('Token = %s' % tokenid)
    # print('Fetching %s' % url)
    # print(headers)
    req = request.Request(
            url=url,
            headers=headers,
            method="GET")
    with request.urlopen(req) as resp:
        content = resp.read().decode('utf-8')
        return json.loads(content)


def latest_data(config):
    tokenid = check_token(config.username, config.password)
    data = fetch(address=config.address, tokenid=tokenid, offset=config.offset)
    #print(data)
    #if int(data.get('StatusCode', 500)) != 200:
   #     raise Exception("Bad reply: {}".format(
   #         data.get('ResponseMessage', "Unknown")))
    #current = data.get('Payload', {
    #    }).get('CurrentProduction', {}).get('value', 0)

    current = data.get('data').get('production')
    #current = data.get('powerData',[])[-1].split(',')[2]
    # print(current)
    return float(current)#smooth(float(current))


def main():
    try:
        print(latest_data(config()))
    except Exception as ex:
        print("Error:{}".format(ex))

if __name__ == '__main__':
    main()
