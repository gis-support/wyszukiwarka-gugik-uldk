from urllib.request import urlopen
from urllib.error import HTTPError
try:
    from .exceptions import *
except ImportError:
    from exceptions import *



class ULDK_API:

    url = r"http://uldk.gugik.gov.pl/service.php"

    #przedmiot zapytania
    obiekt = [
        "wojewodztwo",
        "powiat",
        "gmina",
        "obreb",
        "dzialka", #unikać masowych zapytań
    ]
    
    #zwracany atrybut przedmiotu zapytania
    wynik = [
        "teryt",
        "wojewodztwo",
        "powiat",
        "gmina",
        "obreb",
        "numer",
        "geom_zakres", #bbox
        "geom_wkt",
        "geom_postgis", #WKB
        "kw",
        "zrodlo",
        #ponizej parametry obsługiwane tylko przy zapytaniu z parametrem debug 
        "url",
        "response",
    ]

    # obiekt = {e:e for e in obiekt}
    # wynik = {e:e for e in wynik}

    @staticmethod
    def format_url(obiekt, wynik, filter_ = "", url = url, by_xy = False, debug = False):
        """
        funkcja do wysyłania requestów:
        url - adres usługi,
        obiekt - pojedyczny przedmiot
        wynik - jeden lub wiele zwracanych atrybutów przedmiotu zapytania
        filter - fraza filtrująca: teryt lub współrzędne punktu w EPSG:2180 przy parametrze by_xy = True
        by_xy - szukanie po punkcie, domyślnie False
        """
        
        url += "?"
        url += "debug&" if debug else "" #03.01.2019 chyba nieobsługiwany
        
        url += "obiekt=" + obiekt.strip()
        url += "&"

        if type(wynik) is str:
            wynik = [wynik]

        url += "wynik="
        for w in wynik:
            url += w.strip() + ","
        url += "&"

        if filter_:
            url += "punkt_xy=" if by_xy else "teryt="
            url += filter_.strip()
            url += "&"
        return url
    
    @staticmethod
    def send_request(url):
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



