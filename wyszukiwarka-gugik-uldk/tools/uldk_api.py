from urllib.error import HTTPError
from urllib.request import urlopen

from .exceptions import *


class URL:

    def __init__(self, base_url, **params):

        self.base_url = base_url
        self.params = {}
        for k, v in params.items():
            self.add_param(k, v)

    def add_param(self, key, value):

        if isinstance(value, (tuple, list)):
            value = [str(v) for v in value]
        else:
            value = str(value)
        self.params[key] = value

    def __str__(self):
        url = self.base_url

        if self.params:
            url += "?"
        
        for key,value in self.params.items():
            if isinstance(value, (tuple, list)):
                value = ",".join(value)
            url += "{}={}&".format(key, value)

        return url

class ULDKSearch:

    url = r"http://uldk.gugik.gov.pl/service.php"

    def __init__(self, target, results, method = ""):
        self.url = URL(ULDKSearch.url, obiekt=target, wynik=results)
        if method:
            self.url.add_param("request", method)

    def search(self):
        url = str(self.url)
        try:
            with urlopen(url) as u:
                content = u.read()
            content = content.decode()
            content_lines = content.split("\n")
            status = content_lines[0]
            if status != "0":
                raise RequestException(status)
        except HTTPError as e:
            raise e
        return content_lines[1:-1]

class ULDKSearchTeryt(ULDKSearch):
    def __init__(self, target, results, teryt):
        super().__init__(target, results)
        self.url.add_param("teryt", teryt)

class ULDKSearchParcel(ULDKSearch):
    def __init__(self, target, results, teryt):
        super().__init__(target, results, "GetParcelById")
        self.url.add_param("id", teryt)

class ULDKSearchPoint(ULDKSearch):
    def __init__(self, target, results, x, y, srid=2180):
        super().__init__(target, results, "GetParcelByXY")
        self.url.add_param("xy", (x,y,srid))
