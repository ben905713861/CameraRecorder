import os

import requests
from requests.auth import HTTPDigestAuth
from onvif import ONVIFCamera
import xml.etree.ElementTree as ET

def get_onvif_streams(host, port, username, password):
    cam = ONVIFCamera(host, port, username, password)
    media_service = cam.create_media_service()
    profiles = media_service.GetProfiles()
    rtsp_urls = []
    for profile in profiles:
        stream_setup = {
            'Stream': 'RTP-Unicast',
            'Transport': {'Protocol': 'RTSP'}
        }
        uri = media_service.GetStreamUri({
            'StreamSetup': stream_setup,
            'ProfileToken': profile.token
        })
        rtsp_urls.append(uri.Uri)
    return rtsp_urls

def get_isapi_streams(host, port, username, password):
    response = requests.get(
        f"http://{host}:{port}/ISAPI/Streaming/channels",
        auth=HTTPDigestAuth(username, password),
        timeout=5
    )
    xml = response.text
    root = ET.fromstring(xml)
    ns = {'hik': 'http://www.hikvision.com/ver20/XMLSchema'}
    id_elements = root.findall('hik:StreamingChannel/hik:id', ns)
    rtsp_urls = [
        f"rtsp://{username}:{password}@{host}:554/Streaming/Channels/{elem.text}"
        for elem in id_elements
    ]
    return rtsp_urls

def get_streams(host, port, username, password, **_):
    try:
        return get_onvif_streams(host, port, username, password)
    except:
        try:
            return get_isapi_streams(host, port, username, password)
        except:
            raise ConnectionError("unable to retrieve RTSP stream URLs using both ONVIF and ISAPI methods")
