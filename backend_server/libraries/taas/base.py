import requests


class Base:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()

    def get(self, endpoint, params=None):
        url = self.base_url + endpoint
        response = self.session.get(url, params=params)
        return response

    def post(self, endpoint, data=None):
        url = self.base_url + endpoint
        response = self.session.post(url, json=data)
        return response

    def delete(self, endpoint, data=None):
        url = self.base_url + endpoint
        response = self.session.delete(url, json=data)
        return response

    def close_session(self):
        self.session.close()
