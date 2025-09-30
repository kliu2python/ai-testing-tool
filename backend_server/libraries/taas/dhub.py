import json
import uuid
from time import sleep

from libraries.taas.base import Base


class Dhub(Base):
    def __init__(self, version: str = None, browser: str = None,
                 portal_ip: list = None, base_url='http://10.160.24.88:32677',
                 resolutions: str = None, ram: str = '2Gi'):
        super().__init__(base_url)
        self.version = version
        self.browser = browser
        self.portal_ip = portal_ip
        self.resolutions = resolutions
        self.ram = ram
        self.pod_name = None
        self.node_name = None
        self.vnc_port = None
        self.adb_port = None

    def create_emulator(self, creator: str = "automation"):
        retry = 5

        endpoint = '/dhub/emulator/create'
        json_body = {'os': 'android', 'version': self.version,
                     'creator': creator
                     }
        while True:
            resp = self.post(endpoint, json_body)
            if resp.status_code < 300:
                resp_body = json.loads(resp.content)
                self.pod_name = resp_body.get('pod_name')
                print(f"emulator {self.pod_name} created")
                return True
            if retry < 0:
                print("failed to create emulator after 5 retry")
                return False
            retry -= 1
            print("retry to create emulator pod")

    def delete_emulator(self, pod_name: str = None):
        if not pod_name:
            pod_name = self.pod_name
        endpoint = '/dhub/emulator/delete'
        json_body = {'pod_name': pod_name, 'creator': 'automation'}
        resp = self.post(endpoint, json_body)
        if resp.status_code < 300:
            self.pod_name = None
            return True
        return False

    def check_emulator(self, pod_name: str = None):
        if not pod_name:
            pod_name = self.pod_name
        endpoint = f'/dhub/emulator/check/{pod_name}'
        resp = self.get(endpoint)
        print(f'the emulator status {resp}')
        if resp.status_code < 300:
            resp_body = json.loads(resp.content)
            count = 10
            while count > 0:
                results = resp_body.get('results')
                if results.get('status') in ['Running']:
                    self.adb_port = results.get('adb_port')
                    self.vnc_port = results.get('vnc_port')
                    return True
                resp_body = json.loads(self.get(endpoint).content)
                count -= 1
                sleep(3)
        return False

    def check_device_status(self, pod_name: str = None):
        if not pod_name:
            pod_name = self.pod_name
        endpoint = f'/dhub/emulator/device/check/{pod_name}'
        while True:
            resp = self.get(endpoint)
            resp_body = json.loads(resp.content)
            results = resp_body.get('results')
            if not isinstance(results, str):
                if results.get('status') in ['ready']:
                    print(f"{pod_name} device is ready to use")
                    sleep(3)
                    break
            sleep(1)

    def create_selenium_pod(self, node_name: str = None):
        endpoint = '/dhub/selenium/create'
        json_body = {'browser': self.browser,
                     'version': self.version,
                     'resolutions': self.resolutions,
                     'ram': self.ram
                     }
        if not node_name:
            self.node_name = (f'{self.browser}-{self.version}'
                              f'-{str(uuid.uuid1()).split("-")[0]}-'
                              f'{self.resolutions}')
        else:
            self.node_name = node_name
        json_body['node_name'] = self.node_name
        if self.portal_ip:
            json_body['portal_ip'] = self.portal_ip
        resp = self.post(endpoint, json_body)
        if resp.status_code < 300:
            resp_body = json.loads(resp.content)
            self.pod_name = resp_body.get('pod_name')
            return True
        return False

    def delete_selenium_pod(self, node_name: str = None):
        if not node_name:
            node_name = self.node_name
        endpoint = f'/dhub/selenium/delete/{node_name}'
        json_body = {'pod_name': node_name, 'creator': 'automation'}
        resp = self.post(endpoint, json_body)
        if resp.status_code < 300:
            self.pod_name = None
            return True
        return False

    def check_selenium_node(self, node_name: str = None):
        if not node_name:
            node_name = self.pod_name
        endpoint = f'/dhub/selenium/check/{node_name}'
        resp = self.get(endpoint)
        if resp.status_code < 300:
            resp_body = json.loads(resp.content)
            count = 10
            while count > 0:
                results = resp_body.get('results')
                if results in ['UP']:
                    return True
                resp_body = json.loads(self.get(endpoint).content)
                count -= 1
                sleep(1)
        return False

    def check_ftc_version_on_selenium(self, pod_name: str):
        endpoint = f'/dhub/selenium/check/{pod_name}'
        json_body = {"commands": "curl -v https://ftc.fortinet.com/version"}
        resp = self.post(endpoint, data=json_body)
        if resp.status_code < 300:
            if isinstance(json.loads(resp.content), dict):
                return json.loads(resp.content)["results"]
        else:
            print(f'The code is {resp.status_code} and the reason is '
                  f'{resp.content}')
            return "error when check version"


if __name__ == "__main__":
    dhub_client = Dhub("14")
    dhub_client.create_emulator()
    dhub_client.check_emulator()
    print(f'{dhub_client.adb_port} and for pod {dhub_client.pod_name}')
    res = dhub_client.delete_emulator()
    if res:
        print('deleted pod')
