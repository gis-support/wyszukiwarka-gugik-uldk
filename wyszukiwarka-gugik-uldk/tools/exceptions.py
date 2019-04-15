class ApplicationException(Exception):
    pass

    
class InvalidGeomException(ApplicationException):
    pass


class RequestException(ApplicationException):
    pass


class PlotRequestException(RequestException):
    pass


class PrecinctRequestException(RequestException):
    pass